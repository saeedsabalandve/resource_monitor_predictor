# config/database.py
# Database configuration and connection management
# Handles connections to InfluxDB, PostgreSQL, and Redis
# Provides connection pooling and session management

from influxdb_client import InfluxDBClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
import redis.asyncio as redis
from typing import Optional
from .settings import Settings


class DatabaseConfig:
    """
    Manages database connections and configurations
    Implements connection pooling for performance
    """
    
    def __init__(self, settings: Settings):
        self.settings = settings
        self._influx_client: Optional[InfluxDBClient] = None
        self._postgres_engine = None
        self._postgres_session = None
        self._redis_client: Optional[redis.Redis] = None
    
    def get_influxdb_client(self) -> InfluxDBClient:
        """
        Returns InfluxDB client instance
        Creates new connection if doesn't exist
        Uses connection pooling internally
        """
        if not self._influx_client:
            self._influx_client = InfluxDBClient(
                url=self.settings.INFLUXDB_URL,
                token=self.settings.INFLUXDB_TOKEN,
                org=self.settings.INFLUXDB_ORG
            )
        return self._influx_client
    
    def get_postgres_session(self):
        """
        Returns SQLAlchemy session for PostgreSQL
        Creates engine with connection pooling
        """
        if not self._postgres_engine:
            self._postgres_engine = create_engine(
                self.settings.DATABASE_URL,
                pool_size=20,
                max_overflow=10,
                pool_pre_ping=True
            )
            self._postgres_session = sessionmaker(
                bind=self._postgres_engine
            )
        return self._postgres_session()
    
    async def get_redis_client(self) -> redis.Redis:
        """
        Returns async Redis client
        Used for caching and task queue
        """
        if not self._redis_client:
            self._redis_client = redis.from_url(
                self.settings.REDIS_URL,
                encoding="utf-8",
                decode_responses=True
            )
        return self._redis_client
    
    def close_connections(self):
        """
        Gracefully close all database connections
        """
        if self._influx_client:
            self._influx_client.close()
        
        if self._postgres_engine:
            self._postgres_engine.dispose()
        
        if self._redis_client:
            self._redis_client.close()
