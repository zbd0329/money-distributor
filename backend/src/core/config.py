from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    API_V1_STR: str = "/api/v1"
    PROJECT_NAME: str = "Money-distribution-service"
    DATABASE_URL: str
    REDIS_HOST: str
    REDIS_PORT: int
    RABBITMQ_HOST: str
    RABBITMQ_PORT: int
    RABBITMQ_USER: str
    RABBITMQ_PASSWORD: str
    TEST_DATABASE_URL: str
    TEST_REDIS_HOST: str
    TEST_REDIS_PORT: int
    TEST_RABBITMQ_HOST: str
    TEST_RABBITMQ_PORT: int
    TEST_RABBITMQ_USER: str
    TEST_RABBITMQ_PASSWORD: str

    class Config:
        env_file = ".env"
        case_sensitive = True

settings = Settings() 