from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import EmailStr, Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore", case_sensitive=False)

    app_name: str = "Mosaic Budget"
    app_timezone: str = "America/New_York"
    app_secret_key: str = Field(min_length=32)
    app_encryption_key: str
    database_url: str
    trusted_hosts: str = "*"
    cookie_secure: bool = False
    session_days: int = 30

    bootstrap_admin_email: EmailStr
    bootstrap_admin_password: str = Field(min_length=14)
    bootstrap_admin_name: str = "Administrator"

    simplefin_sync_interval_minutes: int = Field(default=180, ge=60, le=1440)
    simplefin_routine_days: int = Field(default=7, ge=5, le=30)
    simplefin_deep_days: int = Field(default=90, ge=30, le=90)
    simplefin_max_requests_24h: int = Field(default=20, ge=1, le=24)
    simplefin_timeout_seconds: int = Field(default=45, ge=10, le=180)

    smtp_host: str = ""
    smtp_port: int = 587
    smtp_username: str = ""
    smtp_password: str = ""
    smtp_from: str = ""
    smtp_to: str = ""
    smtp_starttls: bool = True
    smtp_ssl: bool = False

    ntfy_url: str = "https://ntfy.sh"
    ntfy_topic: str = ""
    ntfy_token: str = ""

    external_heartbeat_url: str = ""
    backup_stale_hours: int = Field(default=36, ge=12, le=720)
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"

    @field_validator("bootstrap_admin_password")
    @classmethod
    def reject_placeholder_passwords(cls, value: str) -> str:
        lowered = value.lower()
        if "change_me" in lowered or value in {"password", "changeme", "admin123456789"}:
            raise ValueError("BOOTSTRAP_ADMIN_PASSWORD must be replaced with a strong password")
        return value

    @property
    def trusted_host_list(self) -> list[str]:
        return [item.strip() for item in self.trusted_hosts.split(",") if item.strip()]

    @property
    def smtp_enabled(self) -> bool:
        return bool(self.smtp_host and self.smtp_from and self.smtp_to)

    @property
    def ntfy_enabled(self) -> bool:
        return bool(self.ntfy_url and self.ntfy_topic)


@lru_cache
def get_settings() -> Settings:
    return Settings()
