# src/main.py
# Main application entry point
# Initializes FastAPI application with all routes and middleware
# Configures CORS, authentication, and startup/shutdown events

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from contextlib import asynccontextmanager
import uvicorn

from config.settings import Settings
from config.logging import LoggingConfig
from config.database import DatabaseConfig
from src.api.routes import metrics, predictions, alerts, system
from src.collector.scheduler import CollectionScheduler
from src.predictor.manager import PredictionManager
from src.middleware.auth import AuthMiddleware
from src.middleware.rate_limit import RateLimitMiddleware


# Initialize settings and logging
settings = Settings()
LoggingConfig.setup_logging(settings.LOG_LEVEL)
db_config = DatabaseConfig(settings)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Application lifespan manager
    Handles startup and shutdown events
    Initializes collectors and prediction services
    """
    # Startup
    print("=" * 60)
    print("🚀 Starting Resource Monitor & Predictor Microservice")
    print("=" * 60)
    
    # Initialize database connections
    app.state.influx_client = db_config.get_influxdb_client()
    app.state.redis_client = await db_config.get_redis_client()
    app.state.db_session = db_config.get_postgres_session()
    
    # Start collection scheduler
    app.state.collection_scheduler = CollectionScheduler(
        settings=settings,
        influx_client=app.state.influx_client
    )
    await app.state.collection_scheduler.start()
    
    # Initialize prediction manager
    app.state.prediction_manager = PredictionManager(
        settings=settings,
        influx_client=app.state.influx_client,
        redis_client=app.state.redis_client
    )
    await app.state.prediction_manager.initialize()
    
    print("✅ All services initialized successfully")
    
    yield
    
    # Shutdown
    print("🛑 Shutting down services...")
    await app.state.collection_scheduler.stop()
    db_config.close_connections()
    print("✅ Shutdown complete")


# Create FastAPI application
app = FastAPI(
    title="Resource Monitor & Predictor API",
    description="Microservice for periodic resource monitoring and predictive analytics",
    version="1.0.0",
    lifespan=lifespan,
    docs_url="/api/docs",
    redoc_url="/api/redoc"
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure appropriately for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Add security middleware
app.add_middleware(
    TrustedHostMiddleware,
    allowed_hosts=["*"]  # Configure appropriately for production
)

# Add custom middleware
app.add_middleware(AuthMiddleware)
app.add_middleware(RateLimitMiddleware)

# Include API routers
app.include_router(metrics.router, prefix="/api/v1/metrics", tags=["Metrics"])
app.include_router(predictions.router, prefix="/api/v1/predict", tags=["Predictions"])
app.include_router(alerts.router, prefix="/api/v1/alerts", tags=["Alerts"])
app.include_router(system.router, prefix="/api/v1", tags=["System"])


@app.get("/")
async def root():
    """Root endpoint with API information"""
    return {
        "service": "Resource Monitor & Predictor",
        "version": "1.0.0",
        "status": "operational",
        "documentation": "/api/docs"
    }


if __name__ == "__main__":
    uvicorn.run(
        "src.main:app",
        host=settings.SERVER_HOST,
        port=settings.SERVER_PORT,
        reload=settings.DEBUG_MODE,
        workers=settings.MAX_WORKERS
  )
