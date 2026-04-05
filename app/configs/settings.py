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
    app_public_base_url: str = "http://127.0.0.1:8000"
    monitor_internal_token: str = Field(
        default="",
        validation_alias=AliasChoices("MONITOR_INTERNAL_TOKEN"),
    )
    shopify_api_key: str = Field(default="", validation_alias=AliasChoices("SHOPIFY_API_KEY"))
    shopify_api_secret: str = Field(default="", validation_alias=AliasChoices("SHOPIFY_API_SECRET"))
    shopify_scopes: str = Field(
        default="read_orders",
        validation_alias=AliasChoices("SHOPIFY_SCOPES"),
    )
    shopify_api_version: str = Field(
        default="2026-04",
        validation_alias=AliasChoices("SHOPIFY_API_VERSION"),
    )
    shopify_state_secret: str = Field(
        default="",
        validation_alias=AliasChoices("SHOPIFY_STATE_SECRET"),
    )
    







settings = Settings()
    