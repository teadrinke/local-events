from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Auth: Bearer token in the Authorization header, not a query param.
    jambase_api_key: str
    jambase_base_url: str = "https://api.data.jambase.com/v3"
    request_timeout_s: float = 8.0
    cache_ttl_s: int = 300


settings = Settings()
