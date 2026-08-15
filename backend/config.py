from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    openai_api_key: str = ""
    deepseek_api_key: str = ""
    deepgram_api_key: str = ""
    deepgram_language: str = "pl"
    # Where the live SQLite DB lives on the host (see README "Data & backups").
    # Set via DISPATCH_DATA_DIR in the root .env; the Tauri shell passes it
    # through when it spawns the backend.
    dispatch_data_dir: str = ""


settings = Settings()
