from functools import lru_cache

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.engine import make_url


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "mysql+asyncmy://expense:expense_demo@127.0.0.1:3308/expense_sharing"

    @field_validator("database_url")  # Check if URL is mysql+asyncmy or not and has a database name
    @classmethod
    def mysql_only(cls, value: str) -> str:
        url = make_url(value)
        if url.drivername != "mysql+asyncmy" or not url.database:
            raise ValueError("DATABASE_URL must use mysql+asyncmy and name a database")
        return value


# performance improve by loading setting only once and caching it for future use
@lru_cache
def get_settings() -> Settings:
    return Settings()
