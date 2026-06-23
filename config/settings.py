# config/settings.py
# Centralized configuration management using Pydantic
# Loads from environment variables with validation
# Provides typed configuration for entire microservice

from pydantic_settings import BaseSettings
from typing import List, Optional
from enum import Enum


class PredictionMethod(str, Enum):
    """Supported prediction methods enumeration"""
    ARIMA = "arima"
    PROPHET = "prophet"
    LSTM = "lstm"
    EXPONENTIAL_SMOOTHING = "exponential_smoothing"
    LINEAR_REGRESSION = "linear_regression"


class AlertChannel(str, Enum):
    """Supported alert notification channels"""
    EMAIL = "email"
    SLACK = "slack"
    WEBHOOK = "webhook"


class Settings(BaseSettings):
    """
    Main application settings
    Loads configuration from environment variables
    """
    
    # Server Configuration
    SERVER_HOST: str = "0.0.0.0"
    SERVER_PORT: int = 8000
    DEBUG_MODE: bool = False
    LOG_LEVEL: str = "INFO"
    
    # Database URLs
    INFLUXDB_URL: str = "http://localhost:8086"
    INFLUXDB_TOKEN: str = ""
    INFLUXDB_ORG: str = "default"
    INFLUXDB_BUCKET: str = "resource_metrics"
    
    DATABASE_URL: str = "postgresql://monitor:password@localhost:5432/resource_monitor"
    REDIS_URL: str = "redis://localhost:6379/0"
    
    # Security
    SECRET_KEY: str = "change_this_in_production"
    JWT_ALGORITHM: str = "HS256"
    JWT_EXPIRATION: int = 3600
    API_KEY: str = ""
    
    # Collection Intervals (seconds)
    CPU_COLLECTION_INTERVAL: int = 10
    MEMORY_COLLECTION_INTERVAL: int = 10
    DISK_COLLECTION_INTERVAL: int = 60
    NETWORK_COLLECTION_INTERVAL: int = 30
    PROCESS_COLLECTION_INTERVAL: int = 120
    
    # Prediction Settings
    PREDICTION_HORIZON_HOURS: int = 24
    PREDICTION_INTERVAL_MINUTES: int = 15
    RETRAIN_INTERVAL_HOURS: int = 24
    MIN_DATA_POINTS_FOR_PREDICTION: int = 100
    ACTIVE_PREDICTION_METHODS: List[PredictionMethod] = [
        PredictionMethod.ARIMA,
        PredictionMethod.PROPHET,
        PredictionMethod.EXPONENTIAL_SMOOTHING
    ]
    
    # Alert Thresholds
    CPU_THRESHOLD_PERCENT: float = 90.0
    MEMORY_THRESHOLD_PERCENT: float = 85.0
    DISK_THRESHOLD_PERCENT: float = 90.0
    ALERT_COOLDOWN_MINUTES: int = 30
    ALERT_CHANNELS: List[AlertChannel] = [AlertChannel.EMAIL]
    
    # Performance
    MAX_WORKERS: int = 4
    CACHE_TTL_SECONDS: int = 300
    BATCH_SIZE: int = 1000
    RATE_LIMIT_REQUESTS: int = 100
    RATE_LIMIT_PERIOD: int = 60
    
    class Config:
        env_file = ".env"
        case_sensitive = True
