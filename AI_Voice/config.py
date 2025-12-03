"""
Configuration management for AI Voice system.
Uses pydantic-settings for type-safe environment variable loading.
"""

from pydantic_settings import BaseSettings
from pydantic import Field
from typing import Optional
import os


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""
    
    # Server
    host: str = Field(default="0.0.0.0", env="HOST")
    port: int = Field(default=8000, env="PORT")
    debug: bool = Field(default=False, env="DEBUG")
    environment: str = Field(default="development", env="ENVIRONMENT")
    
    # Deepgram
    deepgram_api_key: str = Field(..., env="DEEPGRAM_API_KEY")
    
    # AWS Bedrock
    aws_region: str = Field(default="us-west-2", env="AWS_REGION")
    aws_access_key_id: Optional[str] = Field(default=None, env="AWS_ACCESS_KEY_ID")
    aws_secret_access_key: Optional[str] = Field(default=None, env="AWS_SECRET_ACCESS_KEY")
    aws_bedrock_model_id: str = Field(
        default="deepseek.deepseek-r1-distill-qwen-32b",
        env="AWS_BEDROCK_MODEL_ID"
    )
    
    # Database
    database_url: str = Field(
        default="postgresql+asyncpg://postgres:postgres@localhost:5432/ai_voice",
        env="DATABASE_URL"
    )
    
    # Redis
    redis_url: str = Field(default="redis://localhost:6379/0", env="REDIS_URL")
    redis_password: Optional[str] = Field(default=None, env="REDIS_PASSWORD")
    
    # Twilio (optional for now)
    twilio_account_sid: Optional[str] = Field(default=None, env="TWILIO_ACCOUNT_SID")
    twilio_auth_token: Optional[str] = Field(default=None, env="TWILIO_AUTH_TOKEN")
    twilio_phone_number: Optional[str] = Field(default=None, env="TWILIO_PHONE_NUMBER")
    
    # Salesforce (for production)
    sf_client_id: Optional[str] = Field(default=None, env="SF_CLIENT_ID")
    sf_client_secret: Optional[str] = Field(default=None, env="SF_CLIENT_SECRET")
    sf_refresh_token: Optional[str] = Field(default=None, env="SF_REFRESH_TOKEN")
    sf_instance_url: Optional[str] = Field(default=None, env="SF_INSTANCE_URL")
    
    # Security
    secret_key: str = Field(default="change-this-secret-key", env="SECRET_KEY")
    cors_origins: str = Field(
        default="http://localhost:3000,http://localhost:8000",
        env="CORS_ORIGINS"
    )
    
    # Logging
    log_level: str = Field(default="INFO", env="LOG_LEVEL")
    log_format: str = Field(default="json", env="LOG_FORMAT")
    
    # Call Settings
    max_call_duration_seconds: int = Field(default=7200, env="MAX_CALL_DURATION_SECONDS")
    call_recording_enabled: bool = Field(default=True, env="CALL_RECORDING_ENABLED")
    
    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = False
        extra = "ignore"  # Ignore extra fields in .env
    
    @property
    def cors_origins_list(self) -> list[str]:
        """Parse CORS origins into list."""
        return [origin.strip() for origin in self.cors_origins.split(",")]
    
    @property
    def is_production(self) -> bool:
        """Check if running in production."""
        return self.environment.lower() == "production"
    
    @property
    def is_development(self) -> bool:
        """Check if running in development."""
        return self.environment.lower() == "development"


# Global settings instance
settings = Settings()
