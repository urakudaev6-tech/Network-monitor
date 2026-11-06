"""Read-only Gmail command agent for a local Network Monitor API.
Run explicitly: python email_agent.py. Python standard library only.
"""
import csv
import email
from email.header import decode_header, make_header
from email.message import EmailMessage
from email.utils import parseaddr
import imaplib
import io
import json
import os
from pathlib import Path
import re
import smtplib
import sqlite3
import sys
import time
from urllib.parse import urlencode
from urllib.request import urlopen, Request

ROOT = Path(__file__).resolve().parent
CONFIG = ROOT / '.env.email'
STATE = ROOT / 'email_agent_state.sqlite3'

def load_config():
    if not CONFIG.is_file():
        raise RuntimeError('Missing .env.email. Copy .env.email.example and configure it locally.')
    d = {}
    for raw in CONFIG.read_text(encoding='utf-8-sig').splitlines():
        raw = raw.strip()
        if not raw or raw.startswith('#') or '=' not in raw:
            continue
        k, v = raw.split('=', 1)
        d[k.strip()] = v.strip().strip('"').strip("'")
    addr = d.get('GMAIL_ADDRESS', '').lower()
    password = d.get('GMAIL_APP_PASSWORD', '').replace(' ', '')
    secret = d.get('NM_EMAIL_SECRET', '')
    if not re.fullmatch(r'[^@\s]+@gmail\.com', addr):
        raise RuntimeError('GMAIL_ADDRESS must be a Gmail address')
    if not password or len(secret) < 16:
        raise RuntimeError('Set GMAIL_APP_PASSWORD and NM_EMAIL_SECRET (at least 16 characters)')
    if d.get('NM_API_URL', 'http://127.0.0.1:8000').rstrip('/') != 'http://127.0.0.1:8000':
        raise RuntimeError('For safety NM_API_URL must be http://127.0.0.1:8000')
    return addr, password, secret

def api(path, params=None):
    url = 'http://127.0.0.1:8000' + path
    if params:
        url += '?' + urlencode(params)
    headers = {}
    security_file = ROOT / '.security10.json'
    if security_file.exists():
        cfg = json.loads(security_file.read_text(encoding='utf-8'))
        if cfg.get('enabled'):
            headers['Authorization'] = 'Bearer ' + cfg['agent_token']
    with urlopen(Request(url, headers=headers), timeout=12) as r:
        return json.load(r)

def textval(x):
    return str(x if x is not None else '-')

def scan_items(obj):
    if isinstance(obj, list):
        return obj
    if isinstance(obj, dict):
        for key in ('scans', 'items', 'history', 'results'):
            if isinstance(obj.get(key), list):
                return obj[key]
    return []

def field(item, *names, default=None):
    for n in names:
        if n in item:
            return item[n]
    return default

def scan_id(s):
    return field(s, 'id', 'scan_id')

def get_scans():
    return scan_items(api('/scanner/history', {'limit': 30}))

def get_scan_devices(s):
    sid = scan_id(s)
    if sid is None:
        raise ValueError('Scan ID not found')
    data = api('/scanner/history/' + str(sid))
    devices = field(data, 'devices', 'results', default=[])
    return devices if isinstance(devices, list) else []

def key_ip(d):
    return str(d.get('ip', '')).strip()

def responding(d):
    return d.get('detected', d.get('responded', d.get('is_alive', False))) is True

def changes():
    scans = get_scans()
    if len(scans) < 2:
        return 'Need at least two saved scans.', []
    a, b = scans[0], scans[1]
    if field(a, 'subnet') != field(b, 'subnet'):
        return 'Latest two scans have different subnets. Comparison not available.', []
    new = {key_ip(d): d for d in get_scan_devices(a) if key_ip(d) and responding(d)}
    old = {key_ip(d): d for d in get_scan_devices(b) if key_ip(d) and responding(d)}
    gained = sorted(new.keys() - old.keys())
    lost = sorted(old.keys() - new.keys())
    header = (f"Subnet: {field(a, 'subnet', default='-')}\n"
              f"Scan #{scan_id(b)} -> #{scan_id(a)}\n"
              f"Responding: {len(old)} -> {len(new)} (delta {len(new)-len(old):+d})\n"
              f"Newly responding: {len(gained)}\nStopped responding: {len(lost)}\n"
              'No ping response does not prove that a device is offline.')
    return header, [('NEW', ip) for ip in gained] + [('NO_RESPONSE', ip) for ip in lost]

def execute(subject):
    parts = subject.strip().upper().split()
    if not parts or parts[0] != 'NM':
        return None
    if len(parts) < 2:
        return 'Use NM STATUS, NM HISTORY, NM CHANGES, NM OFFLINE, NM DEVICE <IP>, NM REPORT', None
    cmd = parts[1]
    if cmd == 'STATUS' and len(parts) == 2:
        scans = get_scans()
        if not scans:
            return 'No saved scans.', None
        s = scans[0]
        return (f"Last scan #{scan_id(s)}\nSubnet: {field(s, 'subnet', default='-')}\n"
                f"Time: {field(s, 'scanned_at', default='-')}\n"
                f"Responding: {field(s, 'detected', default='-')} / {field(s, 'total', default='-')}\n"
                'Counts reflect scan observations, not guaranteed device availability.'), None
    if cmd == 'HISTORY' and len(parts) == 2:
        scans = get_scans()
        lines = [f"#{scan_id(s)} | {field(s,'scanned_at',default='-')} | {field(s,'subnet',default='-')} | {field(s,'detected',default='-')}/{field(s,'total',default='-')}" for s in scans[:20]]
        return '\n'.join(lines) or 'No saved scans.', None
    if cmd in ('CHANGES', 'OFFLINE') and len(parts) == 2:
        header, entries = changes()
        if cmd == 'OFFLINE':
            entries = [e for e in entries if e[0] == 'NO_RESPONSE']
        lines = [f'{kind}: {ip}' for kind, ip in entries]
        return header + '\n\n' + ('\n'.join(lines[:150]) or 'No matching changes.') + ('\n...truncated' if len(lines) > 150 else ''), None
    if cmd == 'DEVICE' and len(parts) == 3:
        import ipaddress
        try:
            ip = str(ipaddress.ip_address(parts[2]))
        except ValueError:
            return 'Invalid IP address.', None
        if ':' in ip:
            return 'IPv4 only.', None
        data = api('/scanner/devices', {'search': ip})
        if isinstance(data, dict):
            data = field(data, 'devices', 'items', default=[])
        items = [d for d in data if str(d.get('ip')) == ip]
        if not items:
            return f'No registry record for {ip}.', None
        d = items[0]
        fields = ['ip', 'mac', 'hostname', 'label', 'category', 'notes', 'first_seen', 'last_seen', 'subnet']
        return '\n'.join(f'{k}: {textval(d.get(k))}' for k in fields if k in d), None
    if cmd == 'REPORT' and len(parts) == 2:
        scans = get_scans()
        output = io.StringIO()
        w = csv.writer(output)
        w.writerow(['scan_id', 'scanned_at', 'subnet', 'detected', 'total'])
        for s in scans:
            w.writerow([scan_id(s), field(s,'scanned_at'), field(s,'subnet'), field(s,'detected'), field(s,'total')])
        return 'Attached: saved scan history (up to 30 records).', ('network_history.csv', output.getvalue().encode('utf-8-sig'))
    return 'Unknown command. Use NM STATUS, NM HISTORY, NM CHANGES, NM OFFLINE, NM DEVICE <IP>, NM REPORT.', None

def send(addr, password, subject, body, attachment=None):
    msg = EmailMessage()
    msg['From'] = addr
    msg['To'] = addr
    msg['Subject'] = 'NM RESULT: ' + subject[3:][:110]
    msg['X-Network-Monitor-Result'] = '1'
    msg.set_content(body)
    if attachment:
        filename, data = attachment
        msg.add_attachment(data, maintype='text', subtype='csv', filename=filename)
    with smtplib.SMTP_SSL('smtp.gmail.com', 465, timeout=20) as smtp:
        smtp.login(addr, password)
        smtp.send_message(msg)

def db_open():
    con = sqlite3.connect(STATE)
    con.execute('CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT NOT NULL)')
    con.execute('CREATE TABLE IF NOT EXISTS processed (uid INTEGER PRIMARY KEY, status TEXT NOT NULL, timestamp TEXT DEFAULT CURRENT_TIMESTAMP)')
    con.commit()
    return con

def meta(con, key):
    row = con.execute('SELECT value FROM meta WHERE key=?', (key,)).fetchone()
    return row[0] if row else None

def set_meta(con, key, val):
    con.execute('INSERT OR REPLACE INTO meta(key,value) VALUES(?,?)', (key, str(val)))
    con.commit()

def poll(addr, password, secret, con):
    with imaplib.IMAP4_SSL('imap.gmail.com', 993, timeout=25) as imap:
        imap.login(addr, password)
        typ, _ = imap.select('INBOX', readonly=True)
        if typ != 'OK':
            raise RuntimeError('Cannot select Gmail INBOX')
        typ, data = imap.uid('search', None, 'ALL')
        if typ != 'OK':
            raise RuntimeError('IMAP search failed')
        uids = [int(x) for x in data[0].split()]
        if meta(con, 'initialized') is None:
            set_meta(con, 'last_uid', max(uids, default=0))
            set_meta(con, 'initialized', 'yes')
            print('[email] Initialized. Old inbox messages will not be executed.', flush=True)
            return
        last = int(meta(con, 'last_uid') or '0')
        for uid in (x for x in uids if x > last):
            typ, items = imap.uid('fetch', str(uid), '(RFC822)')
            if typ != 'OK':
                raise RuntimeError('IMAP fetch failed')
            payload = next((x[1] for x in items if isinstance(x, tuple) and len(x)>1), None)
            if not payload:
                continue
            msg = email.message_from_bytes(payload)
            subject = str(make_header(decode_header(msg.get('Subject', '')))).strip()
            sender = parseaddr(msg.get('From', ''))[1].lower()
            if sender == addr and re.match(r'^NM(?:\s|$)', subject, re.I) and not msg.get('X-Network-Monitor-Result'):
                body = msg.get_body(preferencelist=('plain',)) if isinstance(msg, EmailMessage) else None
                if body is not None:
                    content = body.get_content()
                else:
                    part = next((p for p in msg.walk() if p.get_content_type() == 'text/plain'), None)
                    content = part.get_payload(decode=True).decode(part.get_content_charset() or 'utf-8', errors='replace') if part else ''
                if any(re.fullmatch(r'\s*KEY\s*:\s*' + re.escape(secret) + r'\s*', line, flags=re.I) for line in content.splitlines()):
                    try:
                        result = execute(subject)
                        if result is not None:
                            response, attachment = result
                            send(addr, password, subject, response, attachment)
                            print(f'[email] Processed UID {uid}: {subject}', flush=True)
                    except Exception as exc:
                        print(f'[email] UID {uid} failed ({type(exc).__name__}); will retry', flush=True)
                        raise
                else:
                    print(f'[email] Skipped UID {uid}: invalid or missing KEY', flush=True)
            set_meta(con, 'last_uid', uid)

def main():
    addr, password, secret = load_config()
    con = db_open()
    print('[email] Agent started. Gmail polling every 30s. Ctrl+C to stop.', flush=True)
    while True:
        try:
            poll(addr, password, secret, con)
        except (imaplib.IMAP4.error, OSError, RuntimeError, ValueError) as exc:
            print(f'[email] Poll error: {type(exc).__name__}: {str(exc)[:180]}', flush=True)
        time.sleep(30)

if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        print('\n[email] Stopped')
    except Exception as exc:
        print(f'[email] Startup failed: {exc}', file=sys.stderr)
        sys.exit(1)
