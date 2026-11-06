"""Authorized LAN scan and SMTP email report; no external dependencies beyond project."""
from __future__ import annotations

import csv
import io
import ipaddress
import smtplib
import ssl
from datetime import datetime
from email.message import EmailMessage
from threading import Lock

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from app.config import settings
from app.db.database import init_db
from app.monitoring.network_scanner import scan_subnet
from app.services.network_history import save_scan


class MailSettings(BaseSettings):
    model_config = SettingsConfigDict(env_file='.env', env_file_encoding='utf-8', extra='ignore')
    report_subnet: str = '192.168.100.0/24'
    report_timeout: float = Field(default=0.8, ge=0.2, le=5.0)
    smtp_host: str = 'smtp.gmail.com'
    smtp_port: int = Field(default=465, ge=1, le=65535)
    smtp_user: str = ''
    smtp_app_password: str = ''
    report_recipient: str = ''


mail_settings = MailSettings()
_lock = Lock()


def _csv_attachment(result: dict) -> tuple[bytes, int]:
    network = ipaddress.ip_network(result['subnet'], strict=False)
    detected = {d['ip'] for d in result['devices'] if d['detected']}
    candidates = [str(ip) for ip in network.hosts() if str(ip) not in detected]
    out = io.StringIO(newline='')
    writer = csv.writer(out, delimiter=';')
    writer.writerow(['IP', 'Статус'])
    for ip in candidates:
        writer.writerow([ip, 'Возможно свободен — требует проверки DHCP/ARP'])
    return ('\ufeff' + out.getvalue()).encode('utf-8'), len(candidates)


def send_report() -> dict:
    """Scan, persist and send. Never interpret ICMP silence as a free IP."""
    if not _lock.acquire(blocking=False):
        raise RuntimeError('Отчёт уже формируется')
    try:
        config = mail_settings
        if not (config.smtp_user and config.smtp_app_password and config.report_recipient):
            raise ValueError('Заполните SMTP_USER, SMTP_APP_PASSWORD и REPORT_RECIPIENT в .env')
        init_db()
        result = scan_subnet(config.report_subnet, settings.scan_allowed_cidrs, config.report_timeout)
        save_scan(result)
        csv_data, candidates = _csv_attachment(result)
        msg = EmailMessage()
        msg['From'] = config.smtp_user
        msg['To'] = config.report_recipient
        msg['Subject'] = f'Network Monitor — отчёт {datetime.now():%d.%m.%Y %H:%M}'
        msg.set_content(
            f"Подсеть: {result['subnet']}\n"
            f"Проверено хостов: {result['total']}\n"
            f"Обнаружено: {result['detected']}\n"
            f"Возможно свободны: {candidates}\n\n"
            'ВНИМАНИЕ: отсутствие ответа на ping НЕ означает, что IP свободен. '
            'Перед назначением проверьте DHCP-пул, резервации и ARP.\n'
            'Полный список кандидатов — во вложении CSV.\n'
        )
        msg.add_attachment(csv_data, maintype='text', subtype='csv', filename='ip_candidates.csv')
        with smtplib.SMTP_SSL(config.smtp_host, config.smtp_port,
                              context=ssl.create_default_context(), timeout=30) as smtp:
            smtp.login(config.smtp_user, config.smtp_app_password.replace(' ', ''))
            smtp.send_message(msg)
        return {'sent': True, 'detected': result['detected'], 'candidates': candidates,
                'subnet': result['subnet']}
    finally:
        _lock.release()
