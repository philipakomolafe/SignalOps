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
    admin_emails: str = Field(
        default="",
        validation_alias=AliasChoices("ADMIN_EMAILS", "ADMIN_EMAIL"),
    )
    app_public_base_url: str = "http://127.0.0.1:8000"
    monitor_internal_token: str = Field(
        default="",
        validation_alias=AliasChoices("MONITOR_INTERNAL_TOKEN"),
    )
    shopify_api_key: str = Field(default="", validation_alias=AliasChoices("SHOPIFY_API_KEY"))
    shopify_api_secret: str = Field(default="", validation_alias=AliasChoices("SHOPIFY_API_SECRET"))
    shopify_scopes: str = Field(
        default="read_all_orders,read_orders,read_products",
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
    shopify_token_refresh_leeway_seconds: int = Field(
        default=300,
        validation_alias=AliasChoices("SHOPIFY_TOKEN_REFRESH_LEEWAY_SECONDS"),
    )
    flutterwave_public_key: str = Field(
        default="",
        validation_alias=AliasChoices("FLW_PUBLIC_KEY", "FLUTTERWAVE_PUBLIC_KEY"),
    )
    flutterwave_secret_key: str = Field(
        default="",
        validation_alias=AliasChoices("FLW_SECRET_KEY", "FLUTTERWAVE_SECRET_KEY"),
    )
    flutterwave_webhook_secret_hash: str = Field(
        default="",
        validation_alias=AliasChoices("FLW_WEBHOOK_SECRET_HASH", "FLUTTERWAVE_WEBHOOK_SECRET_HASH"),
    )
    flutterwave_api_base_url: str = Field(
        default="https://api.flutterwave.com",
        validation_alias=AliasChoices("FLW_API_BASE_URL", "FLUTTERWAVE_API_BASE_URL"),
    )
    flutterwave_starter_link: str = Field(
        default="",
        validation_alias=AliasChoices("FLW_STARTER_LINK", "FLUTTERWAVE_STARTER_LINK"),
    )
    flutterwave_pro_link: str = Field(
        default="",
        validation_alias=AliasChoices("FLW_PRO_LINK", "FLUTTERWAVE_PRO_LINK"),
    )
    flutterwave_starter_plan_id: str = Field(
        default="",
        validation_alias=AliasChoices("FLW_STARTER_PLAN_ID", "FLUTTERWAVE_STARTER_PLAN_ID"),
    )
    flutterwave_pro_plan_id: str = Field(
        default="",
        validation_alias=AliasChoices("FLW_PRO_PLAN_ID", "FLUTTERWAVE_PRO_PLAN_ID"),
    )
    billing_currency: str = Field(
        default="USD",
        validation_alias=AliasChoices("BILLING_CURRENCY"),
    )
    billing_starter_amount: float = Field(
        default=29.0,
        validation_alias=AliasChoices("BILLING_STARTER_AMOUNT"),
    )
    billing_pro_amount: float = Field(
        default=99.0,
        validation_alias=AliasChoices("BILLING_PRO_AMOUNT"),
    )
    resend_api_key: str = Field(
        default="",
        validation_alias=AliasChoices("RESEND_API_KEY"),
    )
    resend_from_email: str = Field(
        default="",
        validation_alias=AliasChoices("RESEND_FROM_EMAIL"),
    )
    password_reset_token_ttl_minutes: int = Field(
        default=20,
        validation_alias=AliasChoices("PASSWORD_RESET_TOKEN_TTL_MINUTES"),
    )
    retention_monitor_runs_days: int = Field(
        default=30,
        validation_alias=AliasChoices("RETENTION_MONITOR_RUNS_DAYS"),
    )
    retention_revoked_sessions_days: int = Field(
        default=30,
        validation_alias=AliasChoices("RETENTION_REVOKED_SESSIONS_DAYS"),
    )
    retention_inactive_shopify_days: int = Field(
        default=90,
        validation_alias=AliasChoices("RETENTION_INACTIVE_SHOPIFY_DAYS"),
    )
    retention_analysis_runs_days: int = Field(
        default=180,
        validation_alias=AliasChoices("RETENTION_ANALYSIS_RUNS_DAYS"),
    )
    




settings = Settings()
    