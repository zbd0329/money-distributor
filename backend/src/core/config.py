from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    API_V1_STR: str = "/api/v1"
    PROJECT_NAME: str = "Money-distribution-service"
    
    # MySQL 설정 추가
    mysql_host: str
    mysql_port: str
    mysql_user: str
    mysql_password: str
    mysql_database: str
    
    # DATABASE_URL 프로퍼티로 변경
    @property
    def DATABASE_URL(self) -> str:
        return f"mysql+asyncmy://{self.mysql_user}:{self.mysql_password}@{self.mysql_host}:{self.mysql_port}/{self.mysql_database}"

    model_config = SettingsConfigDict(env_file=".env")

settings = Settings() 