import os
from pathlib import Path
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")


class Config:
    """Base configuration with sane defaults."""
    SECRET_KEY = os.environ.get("SECRET_KEY", "dev-concurrency-secret-key-urban-parking-2026")
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    BASE_HOURLY_RATE = float(os.environ.get("BASE_HOURLY_RATE", 50.0))
    MIN_SURGE_MULTIPLIER = 1.0
    MAX_SURGE_MULTIPLIER = 2.0
    JSON_AS_ASCII = False


class DevelopmentConfig(Config):
    """Development configuration using SQLite."""
    DEBUG = True
    DB_PATH = os.environ.get("DATABASE_PATH", str(BASE_DIR / "parking.db"))
    SQLALCHEMY_DATABASE_URI = os.environ.get("DATABASE_URL") or f"sqlite:///{DB_PATH}"
    # SQLite-specific concurrency engine options
    SQLALCHEMY_ENGINE_OPTIONS = {
        "connect_args": {"timeout": 15.0},
        "pool_pre_ping": True,
    }


class ProductionConfig(Config):
    """Production configuration using PostgreSQL or fallback database."""
    DEBUG = False
    raw_db_url = os.environ.get("DATABASE_URL", "")
    # Render and Railway provide 'postgres://' which SQLAlchemy 1.4+ expects as 'postgresql://'
    if raw_db_url.startswith("postgres://"):
        raw_db_url = raw_db_url.replace("postgres://", "postgresql://", 1)

    SQLALCHEMY_DATABASE_URI = raw_db_url or f"sqlite:///{BASE_DIR / 'parking_prod.db'}"
    SQLALCHEMY_ENGINE_OPTIONS = {
        "pool_size": int(os.environ.get("DB_POOL_SIZE", 10)),
        "max_overflow": int(os.environ.get("DB_MAX_OVERFLOW", 20)),
        "pool_pre_ping": True,
        "pool_recycle": 300,
    }


class TestingConfig(Config):
    """Testing configuration with in-memory SQLite or temporary database."""
    TESTING = True
    DEBUG = True
    SQLALCHEMY_DATABASE_URI = os.environ.get("TEST_DATABASE_URL", "sqlite:///:memory:")
    SQLALCHEMY_ENGINE_OPTIONS = {
        "connect_args": {"timeout": 15.0},
    }
    WTF_CSRF_ENABLED = False


config_by_name = {
    "development": DevelopmentConfig,
    "production": ProductionConfig,
    "testing": TestingConfig,
    "default": DevelopmentConfig,
}
