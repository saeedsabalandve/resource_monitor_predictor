# scripts/init_db.py
# Database initialization script
# Sets up InfluxDB buckets and PostgreSQL schema
# Creates initial configurations and indexes

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from influxdb_client import InfluxDBClient, BucketRetentionRules
from sqlalchemy import create_engine, text
from loguru import logger
from config.settings import Settings


def initialize_influxdb(settings: Settings):
    """
    Initialize InfluxDB with required buckets and retention policies
    """
    try:
        logger.info("Initializing InfluxDB...")
        
        client = InfluxDBClient(
            url=settings.INFLUXDB_URL,
            token=settings.INFLUXDB_TOKEN,
            org=settings.INFLUXDB_ORG
        )
        
        # Create buckets API
        buckets_api = client.buckets_api()
        
        # Check if bucket exists
        bucket_name = settings.INFLUXDB_BUCKET
        existing_bucket = buckets_api.find_bucket_by_name(bucket_name)
        
        if existing_bucket:
            logger.info(f"Bucket '{bucket_name}' already exists")
        else:
            # Create bucket with retention policy
            retention_rules = BucketRetentionRules(
                type="expire",
                every_seconds=30 * 24 * 3600  # 30 days retention
            )
            
            buckets_api.create_bucket(
                bucket_name=bucket_name,
                org=settings.INFLUXDB_ORG,
                retention_rules=retention_rules,
                description="Resource monitoring metrics bucket"
            )
            
            logger.info(f"Created bucket '{bucket_name}' with 30-day retention")
        
        client.close()
        logger.info("InfluxDB initialization complete")
        
    except Exception as e:
        logger.error(f"InfluxDB initialization failed: {e}")
        raise


def initialize_postgresql(settings: Settings):
    """
    Initialize PostgreSQL with required schema and tables
    """
    try:
        logger.info("Initializing PostgreSQL...")
        
        engine = create_engine(settings.DATABASE_URL)
        
        with engine.connect() as conn:
            # Create tables for configuration and metadata
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS alert_configurations (
                    id SERIAL PRIMARY KEY,
                    resource_type VARCHAR(50) NOT NULL,
                    metric_name VARCHAR(100) NOT NULL,
                    threshold_value FLOAT NOT NULL,
                    comparison_operator VARCHAR(20) DEFAULT 'greater_than',
                    severity VARCHAR(20) DEFAULT 'warning',
                    enabled BOOLEAN DEFAULT true,
                    cooldown_minutes INTEGER DEFAULT 30,
                    notification_channels JSONB DEFAULT '["email"]',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
                
                CREATE TABLE IF NOT EXISTS alert_history (
                    id SERIAL PRIMARY KEY,
                    config_id INTEGER REFERENCES alert_configurations(id),
                    resource_type VARCHAR(50) NOT NULL,
                    metric_name VARCHAR(100) NOT NULL,
                    current_value FLOAT NOT NULL,
                    threshold_value FLOAT NOT NULL,
                    severity VARCHAR(20),
                    triggered_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    acknowledged BOOLEAN DEFAULT false,
                    acknowledged_by VARCHAR(100),
                    acknowledged_at TIMESTAMP
                );
                
                CREATE TABLE IF NOT EXISTS prediction_models (
                    id SERIAL PRIMARY KEY,
                    method_name VARCHAR(50) NOT NULL,
                    resource_type VARCHAR(50) NOT NULL,
                    model_metadata JSONB,
                    accuracy FLOAT,
                    trained_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    is_active BOOLEAN DEFAULT true
                );
                
                CREATE TABLE IF NOT EXISTS collection_config (
                    id SERIAL PRIMARY KEY,
                    resource_type VARCHAR(50) NOT NULL,
                    interval_seconds INTEGER NOT NULL,
                    enabled BOOLEAN DEFAULT true,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
                
                -- Create indexes
                CREATE INDEX IF NOT EXISTS idx_alert_history_triggered 
                    ON alert_history(triggered_at);
                CREATE INDEX IF NOT EXISTS idx_alert_history_resource 
                    ON alert_history(resource_type, metric_name);
                CREATE INDEX IF NOT EXISTS idx_prediction_models_method 
                    ON prediction_models(method_name, resource_type);
                
                -- Insert default collection configurations
                INSERT INTO collection_config (resource_type, interval_seconds) VALUES
                    ('cpu', 10),
                    ('memory', 10),
                    ('disk', 60),
                    ('network', 30),
                    ('process', 120)
                ON CONFLICT DO NOTHING;
            """))
            
            conn.commit()
        
        logger.info("PostgreSQL initialization complete")
        
    except Exception as e:
        logger.error(f"PostgreSQL initialization failed: {e}")
        raise


def main():
    """
    Main initialization function
    Sets up all database components
    """
    print("=" * 60)
    print("🔧 Database Initialization")
    print("=" * 60)
    
    try:
        # Load settings
        settings = Settings()
        
        logger.info("Starting database initialization...")
        
        # Initialize InfluxDB
        initialize_influxdb(settings)
        
        # Initialize PostgreSQL
        initialize_postgresql(settings)
        
        print("\n✅ Database initialization complete!")
        print("\nNext steps:")
        print("1. Start the microservice: python src/main.py")
        print("2. Access API documentation: http://localhost:8000/api/docs")
        print("3. Monitor resource collection: http://localhost:8000/api/v1/metrics/current")
        
    except Exception as e:
        logger.error(f"Database initialization failed: {e}")
        print(f"\n❌ Initialization failed: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
