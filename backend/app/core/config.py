
from pathlib import Path

from pydantic_settings import BaseSettings

BACKEND_ROOT = Path(__file__).resolve().parents[2]

class Settings(BaseSettings):
    """Настройки приложения из переменных окружения."""
    environment: str = "development"
    database_url: str = "sqlite:///./novalab.db"
    secret_key: str = "your-super-secret-key-here"
    codect_api_url: str = "http://localhost:8001"
    codect_enabled: bool = False

    admin_login: str = "admin"
    admin_password: str = "admin123"

    s3_enabled: bool = True
    s3_endpoint_url: str = "https://s3.twcstorage.ru"
    s3_region: str = "ru-1"
    s3_access_key: str = ""
    s3_secret_key: str = ""
    s3_bucket: str = ""

    class Config:
        """Config."""
        env_file = ".env"
        env_file_encoding = "utf-8"
        extra = "ignore"

settings = Settings()
