from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    API_V1_STR: str = "/api/v1"
    PROJECT_NAME: str = "FastAPI Project"
    DATABASE_URL: str

    model_config = SettingsConfigDict(env_file=".env")

settings = Settings() 