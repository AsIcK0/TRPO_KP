"""Настройки приложения. Все секреты — только из окружения / .env, в коде их нет."""

from functools import lru_cache
from zoneinfo import ZoneInfo

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    database_url: str
    jwt_secret: str = Field(min_length=16)
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = Field(default=60, ge=1)

    s3_endpoint: str
    s3_access_key: str
    s3_secret_key: str
    s3_bucket: str
    s3_region: str = "us-east-1"

    max_upload_size_mb: int = Field(default=20, ge=1)
    reg_number_template: str = "ВХ-{YYYY}-{NNNNNN}"
    deadline_warning_days: int = Field(default=3, ge=0)

    # часовой пояс организации: по нему определяются дата регистрации, «сегодня» и просрочка
    app_timezone: str = "Europe/Moscow"
    log_level: str = "INFO"
    pdf_font_path: str | None = None  # путь к TTF с кириллицей (по умолчанию ищется DejaVu Sans)

    @field_validator("reg_number_template")
    @classmethod
    def _check_template(cls, value: str) -> str:
        from app.services.reg_number import validate_template

        return validate_template(value)

    @field_validator("app_timezone")
    @classmethod
    def _check_timezone(cls, value: str) -> str:
        try:
            ZoneInfo(value)
        except Exception as exc:  # ZoneInfoNotFoundError — подкласс KeyError, не ValueError
            raise ValueError(f"Неизвестный часовой пояс APP_TIMEZONE: {value}") from exc
        return value

    @property
    def timezone(self) -> ZoneInfo:
        return ZoneInfo(self.app_timezone)

    @property
    def max_upload_bytes(self) -> int:
        return self.max_upload_size_mb * 1024 * 1024


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]
