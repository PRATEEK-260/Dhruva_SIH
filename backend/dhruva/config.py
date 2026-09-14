"""Settings. Everything comes from the environment; no credential has a default."""

import os
import re

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_name: str = "dhruva"
    env: str = "dev"

    database_url: str = "postgresql://dhruva:dhruva@postgres:5432/dhruva"
    redis_url: str = "redis://redis:6379/0"

    # Set once the pinned bundle exists; INCOIS omits an intermediate cert.
    # See CLAUDE.md. Never disable verification instead.
    earthdata_token: str | None = None
    incois_ca_bundle: str | None = None
    incois_erddap_base: str = "https://erddap.incois.gov.in/erddap"
    open_meteo_marine_base: str = "https://marine-api.open-meteo.com/v1"


settings = Settings()


def database_dsn() -> str | None:
    """The database connection string, whatever it is called.

    DHRUVA_DSN grew up as a second name for DATABASE_URL and the two drifted:
    the api container had DATABASE_URL but not DHRUVA_DSN, so every /geo
    endpoint answered 503 "not configured" while /health/ready reported the same
    database perfectly healthy. One resolver, so they cannot disagree again.

    The SQLAlchemy driver suffix is stripped because asyncpg.connect() does not
    accept postgresql+asyncpg:// — and .env.example ships exactly that form.
    """
    dsn = os.environ.get("DHRUVA_DSN") or os.environ.get("DATABASE_URL") or settings.database_url
    if not dsn:
        return None
    return re.sub(r"^postgresql\+\w+://", "postgresql://", dsn)
