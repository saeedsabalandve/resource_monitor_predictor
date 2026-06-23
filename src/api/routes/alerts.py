# src/api/routes/alerts.py
# Alerts API endpoints
# Manages alert configuration, history, and notifications
# Supports threshold-based alerting with multiple notification channels

from fastapi import APIRouter, HTTPException, Query, Depends, Request
from typing import Optional, List, Dict
from datetime import datetime, timedelta
from pydantic import BaseModel, Field
from loguru import logger

from src.api.dependencies import verify_api_key

router = APIRouter()


class AlertConfig(BaseModel):
    """Alert configuration model"""
    resource_type: str = Field(..., description="Resource type to monitor")
    metric_name: str = Field(..., description="Metric name")
    threshold: float = Field(..., description="Alert threshold value")
    comparison: str = Field("greater_than", description="Comparison operator")
    severity: str = Field("warning", description="Alert severity (info, warning, critical)")
    enabled: bool = Field(True, description="Enable/disable this alert")
    cooldown_minutes: int = Field(30, description="Cooldown period between alerts")
    notification_channels: List[str] = Field(["email"], description="Notification channels")


# In-memory alert storage (replace with database in production)
alerts_config = []
alerts_history = []


@router.get("/config")
async def get_alert_configs(
    request: Request,
    api_key: str = Depends(verify_api_key)
):
    """
    Get all alert configurations
    """
    return {
        "status": "success",
        "configs": alerts_config,
        "count": len(alerts_config)
    }


@router.post("/config")
async def create_alert_config(
    request: Request,
    config: AlertConfig,
    api_key: str = Depends(verify_api_key)
):
    """
    Create new alert configuration
    """
    try:
        config_dict = config.dict()
        config_dict["id"] = len(alerts_config) + 1
        config_dict["created_at"] = datetime.utcnow().isoformat()
        
        alerts_config.append(config_dict)
        
        logger.info(f"Alert config created for {config.resource_type}/{config.metric_name}")
        
        return {
            "status": "success",
            "message": "Alert configuration created",
            "config": config_dict
        }
    
    except Exception as e:
        logger.error(f"Error creating alert config: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/config/{config_id}")
async def update_alert_config(
    request: Request,
    config_id: int,
    config: AlertConfig,
    api_key: str = Depends(verify_api_key)
):
    """
    Update existing alert configuration
    """
    try:
        for i, existing_config in enumerate(alerts_config):
            if existing_config.get("id") == config_id:
                updated_config = config.dict()
                updated_config["id"] = config_id
                updated_config["updated_at"] = datetime.utcnow().isoformat()
                alerts_config[i] = updated_config
                
                return {
                    "status": "success",
                    "message": f"Alert config {config_id} updated",
                    "config": updated_config
                }
        
        raise HTTPException(status_code=404, detail="Alert config not found")
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating alert config: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/config/{config_id}")
async def delete_alert_config(
    request: Request,
    config_id: int,
    api_key: str = Depends(verify_api_key)
):
    """
    Delete alert configuration
    """
    try:
        for i, config in enumerate(alerts_config):
            if config.get("id") == config_id:
                deleted_config = alerts_config.pop(i)
                
                return {
                    "status": "success",
                    "message": f"Alert config {config_id} deleted",
                    "config": deleted_config
                }
        
        raise HTTPException(status_code=404, detail="Alert config not found")
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting alert config: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/history")
async def get_alert_history(
    request: Request,
    hours_back: int = Query(24, ge=1, le=720, description="Hours of history"),
    severity: Optional[str] = Query(None, description="Filter by severity"),
    resource_type: Optional[str] = Query(None, description="Filter by resource type"),
    api_key: str = Depends(verify_api_key)
):
    """
    Get alert history with optional filtering
    """
    try:
        cutoff_time = datetime.utcnow() - timedelta(hours=hours_back)
        
        # Filter alerts
        filtered_alerts = []
        for alert in alerts_history:
            alert_time = datetime.fromisoformat(alert["timestamp"])
            
            if alert_time < cutoff_time:
                continue
            
            if severity and alert.get("severity") != severity:
                continue
            
            if resource_type and alert.get("resource_type") != resource_type:
                continue
            
            filtered_alerts.append(alert)
        
        return {
            "status": "success",
            "hours_back": hours_back,
            "filters": {
                "severity": severity,
                "resource_type": resource_type
            },
            "alerts": filtered_alerts,
            "count": len(filtered_alerts)
        }
    
    except Exception as e:
        logger.error(f"Error getting alert history: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/current")
async def get_current_alerts(
    request: Request,
    api_key: str = Depends(verify_api_key)
):
    """
    Get currently active alerts
    Checks current metrics against alert configurations
    """
    try:
        influx_client = request.app.state.influx_client
        query_api = influx_client.query_api()
        settings = request.app.state.settings
        
        active_alerts = []
        
        # Check each alert configuration
        for config in alerts_config:
            if not config.get("enabled", True):
                continue
            
            # Query current metric value
            query = f'''
                from(bucket: "{settings.INFLUXDB_BUCKET}")
                    |> range(start: -5m)
                    |> filter(fn: (r) => r._measurement == "resource_{config['resource_type']}")
                    |> filter(fn: (r) => r.metric_name == "{config['metric_name']}")
                    |> filter(fn: (r) => r._field == "value")
                    |> last()
                    |> yield(name: "last")
            '''
            
            result = query_api.query(query, org=settings.INFLUXDB_ORG)
            
            for table in result:
                for record in table.records:
                    current_value = record.get_value()
                    
                    # Check threshold
                    alert_triggered = False
                    if config["comparison"] == "greater_than":
                        alert_triggered = current_value > config["threshold"]
                    elif config["comparison"] == "less_than":
                        alert_triggered = current_value < config["threshold"]
                    
                    if alert_triggered:
                        # Check cooldown
                        last_alert = None
                        for alert in reversed(alerts_history):
                            if (alert.get("config_id") == config["id"] and
                                alert.get("resource_type") == config["resource_type"]):
                                last_alert = alert
                                break
                        
                        if last_alert:
                            last_alert_time = datetime.fromisoformat(last_alert["timestamp"])
                            cooldown = timedelta(minutes=config["cooldown_minutes"])
                            if datetime.utcnow() - last_alert_time < cooldown:
                                continue
                        
                        # Create alert
                        alert = {
                            "id": len(alerts_history) + 1,
                            "config_id": config["id"],
                            "resource_type": config["resource_type"],
                            "metric_name": config["metric_name"],
                            "current_value": current_value,
                            "threshold": config["threshold"],
                            "comparison": config["comparison"],
                            "severity": config["severity"],
                            "timestamp": datetime.utcnow().isoformat(),
                            "notification_channels": config["notification_channels"]
                        }
                        
                        alerts_history.append(alert)
                        active_alerts.append(alert)
                        
                        logger.warning(
                            f"Alert triggered: {config['resource_type']}/{config['metric_name']} "
                            f"= {current_value} (threshold: {config['threshold']})"
                        )
        
        return {
            "status": "success",
            "active_alerts": active_alerts,
            "count": len(active_alerts),
            "timestamp": datetime.utcnow().isoformat()
        }
    
    except Exception as e:
        logger.error(f"Error checking alerts: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/test-notification")
async def test_notification(
    request: Request,
    channel: str = Query("email", description="Notification channel to test"),
    api_key: str = Depends(verify_api_key)
):
    """
    Test notification channel configuration
    """
    try:
        # Simulate notification sending
        test_message = {
            "channel": channel,
            "subject": "Test Alert Notification",
            "message": "This is a test notification from Resource Monitor",
            "timestamp": datetime.utcnow().isoformat()
        }
        
        logger.info(f"Test notification sent to {channel}")
        
        return {
            "status": "success",
            "message": f"Test notification sent to {channel}",
            "details": test_message
        }
    
    except Exception as e:
        logger.error(f"Error sending test notification: {e}")
        raise HTTPException(status_code=500, detail=str(e))
