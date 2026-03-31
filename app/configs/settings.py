from pydantic_settings import BaseSettings



class Settings(BaseSettings):
    app_name: str = "SignalOps"
    app_version: str = "0.1.0"
    api_host: str = "127.0.0.1"
    api_port: int = 8000
    cors_allow_origins: str = "*"
    persistence_db_path: str = "app/data/signalops.db"
    







settings = Settings()
    