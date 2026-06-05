from functools import lru_cache
from pydantic import field_validator, model_validator
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Application settings loaded from environment / .env file."""

    # Application
    app_name: str = "CRM Backend"
    debug: bool = False
    api_version: str = "1.0.0"

    # Database — individual components (used to build database_url)
    db_host: str = "localhost"
    db_port: str = "5432"
    db_user: str = "postgres"
    db_password: str = "postgres"
    db_name: str = "crm_db"

    # Full URL — if DATABASE_URL is set it takes precedence;
    # otherwise it is assembled from the DB_* components above.
    database_url: str = ""

    # Security
    secret_key: str = "your-secret-key-change-in-production-minimum-32-characters-long"
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 30
    refresh_token_expire_days: int = 7

    # reCAPTCHA
    recaptcha_secret_key: str = "your-recaptcha-secret-key"

    @model_validator(mode="after")
    def assemble_database_url(self) -> "Settings":
        """Build database_url from components if not explicitly provided.
        Always uses the asyncpg driver for the application engine.
        """
        if not self.database_url:
            self.database_url = (
                f"postgresql+asyncpg://{self.db_user}:{self.db_password}"
                f"@{self.db_host}:{self.db_port}/{self.db_name}"
            )
        else:
            # Normalise driver: replace sync prefixes with asyncpg
            url = self.database_url
            for prefix in ("postgres://", "postgresql://"):
                if url.startswith(prefix):
                    self.database_url = "postgresql+asyncpg://" + url[len(prefix):]
                    break
        return self

    @property
    def sync_database_url(self) -> str:
        """Synchronous database URL for Alembic migrations (uses psycopg2)."""
        return self.database_url.replace("postgresql+asyncpg://", "postgresql://", 1)

    model_config = {"env_file": ".env", "extra": "ignore"}


@lru_cache()
def get_settings() -> Settings:
    """Return cached Settings instance."""
    return Settings()
