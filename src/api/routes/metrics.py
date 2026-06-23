# src/api/routes/metrics.py
# Metrics API endpoints
# Provides access to current and historical resource metrics
# Supports filtering, aggregation, and time range queries

from fastapi import APIRouter, HTTPException, Query, Depends, Request
from typing import Optional, List, Dict, Any
from datetime import datetime, timedelta
from loguru import logger

from src.api.dependencies import get_influx_client, verify_api_key
from src.collector.scheduler import CollectionScheduler

router = APIRouter()


@router.get("/current")
async def get_current_metrics(
    request: Request,
    resource_type: Optional[str] = Query(None, description="Filter by resource type"),
    api_key: str = Depends(verify_api_key)
):
    """
    Get current resource usage metrics
    Returns latest metrics for all or specified resource types
    """
    try:
        influx_client = request.app.state.influx_client
        query_api = influx_client.query_api()
        settings = request.app.state.settings if hasattr(request.app.state, 'settings') else None
        
        # Build query based on resource type filter
        measurement_filter = f'r._measurement == "resource_{resource_type}"' if resource_type else 'r._measurement =~ /^resource_/'
        
        query = f'''
            from(bucket: "{request.app.state.settings.INFLUXDB_BUCKET if settings else 'resource_metrics'}")
                |> range(start: -5m)
                |> filter(fn: (r) => {measurement_filter})
                |> filter(fn: (r) => r._field == "value")
                |> last()
                |> yield(name: "last")
        '''
        
        result = query_api.query(query)
        
        metrics = {}
        for table in result:
            for record in table.records:
                resource = record.get_measurement().replace("resource_", "")
                metric_name = record.values.get("metric_name", "unknown")
                value = record.get_value()
                timestamp = record.get_time().isoformat()
                
                if resource not in metrics:
                    metrics[resource] = []
                
                metrics[resource].append({
                    "metric_name": metric_name,
                    "value": value,
                    "unit": record.values.get("unit", ""),
                    "timestamp": timestamp
                })
        
        return {
            "status": "success",
            "timestamp": datetime.utcnow().isoformat(),
            "metrics": metrics
        }
    
    except Exception as e:
        logger.error(f"Error fetching current metrics: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/history")
async def get_historical_metrics(
    request: Request,
    resource_type: str = Query(..., description="Resource type (cpu, memory, disk, network)"),
    metric_name: str = Query(..., description="Specific metric name"),
    hours_back: int = Query(24, ge=1, le=720, description="Hours of history"),
    interval: str = Query("5m", description="Aggregation interval"),
    api_key: str = Depends(verify_api_key)
):
    """
    Get historical resource metrics
    Supports custom time ranges and aggregation intervals
    """
    try:
        influx_client = request.app.state.influx_client
        query_api = influx_client.query_api()
        settings = request.app.state.settings
        
        end_time = datetime.utcnow()
        start_time = end_time - timedelta(hours=hours_back)
        
        query = f'''
            from(bucket: "{settings.INFLUXDB_BUCKET}")
                |> range(start: {start_time.isoformat()}Z, stop: {end_time.isoformat()}Z)
                |> filter(fn: (r) => r._measurement == "resource_{resource_type}")
                |> filter(fn: (r) => r.metric_name == "{metric_name}")
                |> filter(fn: (r) => r._field == "value")
                |> aggregateWindow(every: {interval}, fn: mean, createEmpty: false)
                |> yield(name: "mean")
        '''
        
        result = query_api.query(query, org=settings.INFLUXDB_ORG)
        
        data_points = []
        for table in result:
            for record in table.records:
                data_points.append({
                    "timestamp": record.get_time().isoformat(),
                    "value": record.get_value(),
                    "unit": record.values.get("unit", "")
                })
        
        return {
            "status": "success",
            "resource_type": resource_type,
            "metric_name": metric_name,
            "hours_back": hours_back,
            "interval": interval,
            "data_points": len(data_points),
            "data": data_points
        }
    
    except Exception as e:
        logger.error(f"Error fetching historical metrics: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/summary")
async def get_metrics_summary(
    request: Request,
    hours_back: int = Query(24, ge=1, le=168, description="Hours for summary"),
    api_key: str = Depends(verify_api_key)
):
    """
    Get summarized resource metrics
    Returns min, max, average, and current values
    """
    try:
        influx_client = request.app.state.influx_client
        query_api = influx_client.query_api()
        settings = request.app.state.settings
        
        end_time = datetime.utcnow()
        start_time = end_time - timedelta(hours=hours_back)
        
        # Query for CPU usage as primary example
        query = f'''
            from(bucket: "{settings.INFLUXDB_BUCKET}")
                |> range(start: {start_time.isoformat()}Z, stop: {end_time.isoformat()}Z)
                |> filter(fn: (r) => r._measurement == "resource_cpu")
                |> filter(fn: (r) => r.metric_name == "usage_percent")
                |> filter(fn: (r) => r._field == "value")
                |> yield(name: "cpu_data")
        '''
        
        result = query_api.query(query, org=settings.INFLUXDB_ORG)
        
        values = []
        for table in result:
            for record in table.records:
                values.append(record.get_value())
        
        if not values:
            return {"status": "warning", "message": "No data available"}
        
        return {
            "status": "success",
            "summary": {
                "current": values[-1] if values else None,
                "average": sum(values) / len(values),
                "minimum": min(values),
                "maximum": max(values),
                "data_points": len(values),
                "period_hours": hours_back
            }
        }
    
    except Exception as e:
        logger.error(f"Error generating metrics summary: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/collect")
async def trigger_collection(
    request: Request,
    resource_type: Optional[str] = Query(None, description="Specific resource to collect"),
    api_key: str = Depends(verify_api_key)
):
    """
    Trigger manual resource metric collection
    Can collect specific or all resource types
    """
    try:
        scheduler: CollectionScheduler = request.app.state.collection_scheduler
        await scheduler.trigger_manual_collection(resource_type)
        
        return {
            "status": "success",
            "message": f"Collection triggered for {resource_type or 'all resources'}",
            "timestamp": datetime.utcnow().isoformat()
        }
    
    except Exception as e:
        logger.error(f"Error triggering collection: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/available-metrics")
async def get_available_metrics(
    request: Request,
    api_key: str = Depends(verify_api_key)
):
    """
    List all available metrics and their descriptions
    """
    metrics_catalog = {
        "cpu": {
            "metrics": [
                "usage_percent",
                "core_{i}_usage",
                "frequency_current",
                "time_user",
                "time_system",
                "time_idle",
                "load_1min",
                "load_5min",
                "load_15min"
            ],
            "interval_seconds": 10,
            "description": "CPU utilization and performance metrics"
        },
        "memory": {
            "metrics": [
                "total",
                "available",
                "used",
                "used_percent",
                "free",
                "swap_total",
                "swap_used",
                "swap_percent"
            ],
            "interval_seconds": 10,
            "description": "Memory and swap usage metrics"
        },
        "disk": {
            "metrics": [
                "{device}_total",
                "{device}_used",
                "{device}_used_percent",
                "read_bytes",
                "write_bytes",
                "read_count",
                "write_count"
            ],
            "interval_seconds": 60,
            "description": "Disk usage and I/O metrics"
        },
        "network": {
            "metrics": [
                "{interface}_bytes_sent",
                "{interface}_bytes_recv",
                "{interface}_packets_sent",
                "{interface}_packets_recv",
                "{interface}_errors_in",
                "{interface}_errors_out",
                "active_connections"
            ],
            "interval_seconds": 30,
            "description": "Network I/O and connection metrics"
        },
        "process": {
            "metrics": [
                "total_count",
                "top_cpu_{pid}"
            ],
            "interval_seconds": 120,
            "description": "Process-level resource consumption metrics"
        }
    }
    
    return {
        "status": "success",
        "available_metrics": metrics_catalog
      }
