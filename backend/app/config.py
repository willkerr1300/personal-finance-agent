from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    database_url: str
    internal_api_key: str
    encryption_key: str

    # Amadeus API — get sandbox keys at https://developers.amadeus.com
    # Leave empty to run in mock mode (realistic sample data, no real API calls)
    amadeus_client_id: str = ""
    amadeus_client_secret: str = ""
    # "test" uses test.api.amadeus.com; "production" uses api.amadeus.com
    amadeus_env: str = "test"

    # Anthropic API — get key at https://console.anthropic.com
    # Leave empty to use the built-in rule-based trip spec parser fallback
    anthropic_api_key: str = ""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


settings = Settings()
