from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings



class Settings(BaseSettings):
    app_name: str = "SignalOps"
    app_version: str = "0.1.0"
    api_host: str = "127.0.0.1"
    api_port: int = 8000
    cors_allow_origins: str = "*"
    persistence_db_path: str = "app/data/signalops.db"
    persistence_database_url: str = Field(
        default="",
        validation_alias=AliasChoices("DATABASE_URL", "PERSISTENCE_DATABASE_URL"),
    )
    







settings = Settings()
    