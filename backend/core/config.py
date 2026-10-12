from dataclasses import dataclass
import os

@dataclass(frozen=True)
class Settings:
    app_name: str = "AI Autonomous Company"
    environment: str = "development"
    version: str = "0.1.0"
    database_url: str = "sqlite+pysqlite:///./dev_company.sqlite3"

def get_settings() -> Settings:
    return Settings(
        app_name=os.getenv("COMPANY_APP_NAME", "AI Autonomous Company"),
        environment=os.getenv("COMPANY_ENV", "development"),
        database_url=os.getenv("COMPANY_DATABASE_URL", "sqlite+pysqlite:///./dev_company.sqlite3"),
    )
