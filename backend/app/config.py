import os
from pathlib import Path

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")
    database_url: str
    migration_database_url: str | None = None
    redis_url: str = "redis://localhost:6379/0"
    session_secret: str
    environment: str = "development"
    cookie_secure: bool = False
    session_ttl_hours: int = 12
    invite_ttl_hours: int = 168
    password_reset_ttl_minutes: int = 30
    cors_origins: list[str] = ["http://localhost:3000"]
    frontend_base_url: str = "http://localhost:3000"
    evidence_storage_dir: str = './private-evidence'
    evidence_retention_seconds: int = Field(default=2592000, ge=1, le=31536000)
    evidence_scanner_path: str | None = None
    smtp_host: str | None = None
    smtp_port: int = 587
    smtp_username: str | None = None
    smtp_password: str | None = None
    smtp_from_email: str | None = None

    @model_validator(mode="after")
    def secure_production_settings(self):
        if self.evidence_scanner_path and not os.path.isabs(self.evidence_scanner_path):
            raise ValueError('EVIDENCE_SCANNER_PATH must be an absolute executable path')
        if self.environment not in {"development", "test"}:
            if self.evidence_retention_seconds < 86400:
                raise ValueError('Evidence retention must be at least one day outside development and tests')
            if not self.cookie_secure:
                raise ValueError("COOKIE_SECURE must be enabled outside development and tests")
            if len(self.session_secret.encode()) < 32:
                raise ValueError("SESSION_SECRET must be a unique secret of at least 32 bytes outside development and tests")
            if not self.frontend_base_url.startswith("https://") or any(not origin.startswith("https://") for origin in self.cors_origins):
                raise ValueError("Frontend and CORS origins must use HTTPS outside development and tests")
        if self.environment == "production" and (not self.smtp_host or not self.smtp_from_email):
            raise ValueError("SMTP_HOST and SMTP_FROM_EMAIL must be configured for production password reset delivery")
        return self


settings = Settings(_secrets_dir="/run/secrets" if Path("/run/secrets").is_dir() else None)
