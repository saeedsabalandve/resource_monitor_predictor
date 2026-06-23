# src/api/routes/system.py
# System API endpoints
# Health checks, service status, and administrative endpoints
# Provides monitoring of the microservice itself

from fastapi import APIRouter, HTTPException, Depends, Request
from typing import Dict, Any
from datetime import datetime
import psutil
import platform
from loguru import logger

from src.api.dependencies import verify_api_key

router = APIRouter()


@router.get("/health")
async def health_check(request: Request):
    """
    Health check endpoint
    Returns service health status with dependency checks
    """
    health_status = {
        "status": "healthy",
        "service": "Resource Monitor & Predictor",
        "version": "1.0.0",
        "timestamp": datetime.utcnow().isoformat()
    }
    
    checks = {}
    
    # Check InfluxDB connection
    try:
        influx_client = request.app.state.influx_client
        influx_client.ping()
        checks["influxdb"] = "connected"
    except Exception as e:
        checks["influxdb"] = f"error: {str(e)}"
        health_status["status"] = "degraded"
    
    # Check Redis connection
    try:
        redis_client = request.app.state.redis_client
        await redis_client.ping()
        checks["redis"] = "connected"
    except Exception as e:
        checks["redis"] = f"error: {str(e)}"
        health_status["status"] = "degraded"
    
    # Check collection scheduler
    try:
        scheduler = request.app.state.collection_scheduler
        checks["scheduler"] = "running" if scheduler.scheduler.running else "stopped"
    except Exception as e:
        checks["scheduler"] = f"error: {str(e)}"
    
    health_status["checks"] = checks
    
    return health_status


@router.get("/status")
async def get_service_status(
    request: Request,
    api_key: str = Depends(verify_api_key)
):
    """
    Get detailed service status
    Includes resource usage, uptime, and configuration
    """
    try:
        # Get process information
        process = psutil.Process()
        
        # System information
        system_info = {
            "platform": platform.platform(),
            "python_version": platform.python_version(),
            "processor": platform.processor(),
            "hostname": platform.node()
        }
        
        # Service process info
        service_info = {
            "pid": process.pid,
            "cpu_percent": process.cpu_percent(),
            "memory_usage_mb": process.memory_info().rss / (1024 * 1024),
            "memory_percent": process.memory_percent(),
            "threads": process.num_threads(),
            "open_files": len(process.open_files()),
            "connections": len(process.connections()),
            "create_time": datetime.fromtimestamp(process.create_time()).isoformat()
        }
        
        # Collection status
        scheduler = request.app.state.collection_scheduler
        collection_status = {
            "scheduler_running": scheduler.scheduler.running if scheduler else False,
            "jobs": []
        }
        
        if scheduler and scheduler.scheduler.running:
            for job in scheduler.scheduler.get_jobs():
                collection_status["jobs"].append({
                    "id": job.id,
                    "name": job.name,
                    "next_run": job.next_run_time.isoformat() if job.next_run_time else None
                })
        
        # Prediction engine status
        prediction_manager = request.app.state.prediction_manager
        prediction_status = {
            "methods_available": len(prediction_manager.predictors) if prediction_manager else 0,
            "methods_trained": sum(
                1 for p in prediction_manager.predictors.values() if p.is_trained
            ) if prediction_manager else 0,
            "methods": {}
        }
        
        if prediction_manager:
            for method_name, predictor in prediction_manager.predictors.items():
                prediction_status["methods"][method_name] = {
                    "trained": predictor.is_trained,
                    "metadata": predictor.model_metadata
                }
        
        return {
            "status": "operational",
            "timestamp": datetime.utcnow().isoformat(),
            "system": system_info,
            "service": service_info,
            "collection": collection_status,
            "prediction": prediction_status
        }
    
    except Exception as e:
        logger.error(f"Error getting service status: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/metrics/self")
async def get_self_metrics(
    request: Request,
    api_key: str = Depends(verify_api_key)
):
    """
    Get the microservice's own resource usage
    Self-monitoring endpoint
    """
    try:
        process = psutil.Process()
        
        # Collect self metrics
        memory_info = process.memory_info()
        cpu_times = process.cpu_times()
        
        self_metrics = {
            "cpu": {
                "percent": process.cpu_percent(),
                "user_time": cpu_times.user,
                "system_time": cpu_times.system,
                "threads": process.num_threads()
            },
            "memory": {
                "rss_mb": memory_info.rss / (1024 * 1024),
                "vms_mb": memory_info.vms / (1024 * 1024),
                "percent": process.memory_percent(),
                "shared_mb": getattr(memory_info, 'shared', 0) / (1024 * 1024)
            },
            "io": {
                "read_count": process.io_counters().read_count if hasattr(process, 'io_counters') else 0,
                "write_count": process.io_counters().write_count if hasattr(process, 'io_counters') else 0,
                "read_bytes_mb": process.io_counters().read_bytes / (1024 * 1024) if hasattr(process, 'io_counters') else 0,
                "write_bytes_mb": process.io_counters().write_bytes / (1024 * 1024) if hasattr(process, 'io_counters') else 0
            },
            "connections": {
                "total": len(process.connections()),
                "established": len([c for c in process.connections() if c.status == 'ESTABLISHED']),
                "listening": len([c for c in process.connections() if c.status == 'LISTEN'])
            },
            "uptime_seconds": (datetime.utcnow() - datetime.fromtimestamp(process.create_time())).total_seconds()
        }
        
        return {
            "status": "success",
            "timestamp": datetime.utcnow().isoformat(),
            "metrics": self_metrics
        }
    
    except Exception as e:
        logger.error(f"Error getting self metrics: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/cache/clear")
async def clear_cache(
    request: Request,
    api_key: str = Depends(verify_api_key)
):
    """
    Clear prediction cache
    Administrative endpoint for cache management
    """
    try:
        redis_client = request.app.state.redis_client
        
        # Clear prediction cache keys
        keys = await redis_client.keys("prediction:*")
        if keys:
            await redis_client.delete(*keys)
            cleared_count = len(keys)
        else:
            cleared_count = 0
        
        logger.info(f"Cleared {cleared_count} cache entries")
        
        return {
            "status": "success",
            "message": f"Cleared {cleared_count} cache entries",
            "timestamp": datetime.utcnow().isoformat()
        }
    
    except Exception as e:
        logger.error(f"Error clearing cache: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/config")
async def get_service_config(
    request: Request,
    api_key: str = Depends(verify_api_key)
):
    """
    Get current service configuration
    Returns non-sensitive configuration values
    """
    settings = request.app.state.settings
    
    return {
        "status": "success",
        "config": {
            "server": {
                "host": settings.SERVER_HOST,
                "port": settings.SERVER_PORT,
                "debug": settings.DEBUG_MODE
            },
            "collection_intervals": {
                "cpu": settings.CPU_COLLECTION_INTERVAL,
                "memory": settings.MEMORY_COLLECTION_INTERVAL,
                "disk": settings.DISK_COLLECTION_INTERVAL,
                "network": settings.NETWORK_COLLECTION_INTERVAL,
                "process": settings.PROCESS_COLLECTION_INTERVAL
            },
            "prediction": {
                "horizon_hours": settings.PREDICTION_HORIZON_HOURS,
                "interval_minutes": settings.PREDICTION_INTERVAL_MINUTES,
                "retrain_interval_hours": settings.RETRAIN_INTERVAL_HOURS,
                "active_methods": [m.value for m in settings.ACTIVE_PREDICTION_METHODS]
            },
            "alerts": {
                "cpu_threshold": settings.CPU_THRESHOLD_PERCENT,
                "memory_threshold": settings.MEMORY_THRESHOLD_PERCENT,
                "disk_threshold": settings.DISK_THRESHOLD_PERCENT,
                "cooldown_minutes": settings.ALERT_COOLDOWN_MINUTES
            }
        }
}
