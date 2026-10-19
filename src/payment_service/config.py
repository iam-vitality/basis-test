from functools import lru_cache

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore", hide_input_in_errors=True)

    database_url: str
    rabbitmq_url: str
    api_key: str = Field(min_length=1)
    webhook_secret: str = Field(min_length=1)
    webhook_dev_mode: bool = False
    webhook_allowed_hosts: str = "demo-receiver"

    @field_validator("database_url")
    @classmethod
    def database_scheme(cls, value: str) -> str:
        if not value.startswith("postgresql+asyncpg://"):
            raise ValueError("нужен адрес PostgreSQL asyncpg")
        return value

    @field_validator("rabbitmq_url")
    @classmethod
    def rabbit_scheme(cls, value: str) -> str:
        if not value.startswith(("amqp://", "amqps://")):
            raise ValueError("нужен адрес AMQP")
        return value

    @property
    def allowed_hosts(self) -> frozenset[str]:
        return frozenset(
            part.strip().lower() for part in self.webhook_allowed_hosts.split(",") if part.strip()
        )


@lru_cache
def get_settings() -> Settings:
    return Settings()
