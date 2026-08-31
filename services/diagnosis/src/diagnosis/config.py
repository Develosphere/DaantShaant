from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="DIAGNOSIS_")

    host: str = "0.0.0.0"
    port: int = 8002


settings = Settings()
