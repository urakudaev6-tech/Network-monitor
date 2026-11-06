"""Конфигурация приложения через pydantic-settings + .env."""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    database_url: str = "sqlite:///./network_monitor.db"
    max_workers: int = 5
    # NETWORK30_SCHEDULED_SCANNER
    # Disabled by default. Only a single explicitly authorized CIDR may be scheduled.
    auto_scan_enabled: bool = False
    auto_scan_subnet: str = ""
    auto_scan_interval: int = 3600  # seconds, minimum 300
    auto_scan_timeout: float = 0.8
    auto_scan_workers: int = 16
    auto_scan_retries: int = 1
    scheduler_interval: int = 60                     # секунд, 0 = выключен
    scan_allowed_cidrs: str = ""  # Explicitly authorize subnets; empty = disabled
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"

    @property
    def cors_origins_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


settings = Settings()