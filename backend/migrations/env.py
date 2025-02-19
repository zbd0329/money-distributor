from logging.config import fileConfig
from sqlalchemy import engine_from_config
from sqlalchemy import pool
from alembic import context

# this is the Alembic Config object
config = context.config

# DB 모델 import
from src.db.models import Base
from src.core.config import settings

# DB URL 설정
config.set_main_option("sqlalchemy.url", settings.DATABASE_URL)

# Interpret the config file for Python logging
fileConfig(config.config_file_name)

# DB 모델 메타데이터 추가
target_metadata = Base.metadata 