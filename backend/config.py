"""Pydantic settings management"""

from pydantic_settings import BaseSettings
import logging

class Settings(BaseSettings):
    """Application settings loaded from environment variables."""
    class Config:
        env_file = ".env"

    # Database
    POSTGRES_URL: str
    # Upstash Redis
    UPSTASH_REDIS_REST_URL: str
    UPSTASH_REDIS_REST_TOKEN: str
    
    # SECRETS
    PIN_PEPPER: str
    JWT_SECRET: str
    JWT_ALGORITHM: str
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24 * 30  # 30 days
    JIOSAAVN_PROXY_URL: str = ""
    
    def get_logger(self, name: str):
        
        logger = logging.getLogger(name)
        logger.setLevel(logging.INFO)
        handler = logging.StreamHandler()
        formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )
        handler.setFormatter(formatter)
        logger.addHandler(handler)
        return logger
    
settings = Settings()
