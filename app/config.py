from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    """Application settings"""
    
    # Application
    app_name: str = "CRM Backend"
    debug: bool = True
    api_version: str = "1.0.0"
    
    # Database
    database_url: str = "postgresql://postgres:postgres@localhost:5432/crm_db"
    
    # Security
    secret_key: str = "your-secret-key-change-in-production-minimum-32-characters-long"
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 30
    refresh_token_expire_days: int = 7
    
    class Config:
        env_file = ".env"


@lru_cache()
def get_settings() -> Settings:
    """Get cached settings instance"""
    return Settings()
