# src/api/routes/predictions.py
# Predictions API endpoints
# Provides resource usage predictions using multiple methods
# Supports method selection, ensemble predictions, and accuracy metrics

from fastapi import APIRouter, HTTPException, Query, Depends, Request
from typing import Optional, List, Dict
from datetime import datetime
from loguru import logger

from src.api.dependencies import verify_api_key
from src.predictor.manager import PredictionManager

router = APIRouter()


@router.get("/{resource_type}")
async def get_predictions(
    request: Request,
    resource_type: str,
    metric_name: str = Query("usage_percent", description="Metric to predict"),
    horizon_hours: int = Query(24, ge=1, le=168, description="Prediction horizon in hours"),
    method: Optional[str] = Query(None, description="Prediction method (arima, prophet, lstm, etc.)"),
    api_key: str = Depends(verify_api_key)
):
    """
    Get resource usage predictions
    Supports multiple prediction methods and ensemble forecasting
    """
    try:
        prediction_manager: PredictionManager = request.app.state.prediction_manager
        
        # Validate method if specified
        if method and method not in prediction_manager.predictors:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid prediction method. Available: {list(prediction_manager.predictors.keys())}"
            )
        
        # Get predictions
        predictions = await prediction_manager.get_predictions(
            resource_type=resource_type,
            metric_name=metric_name,
            horizon_hours=horizon_hours,
            method=method
        )
        
        if not predictions:
            return {
                "status": "warning",
                "message": "No predictions available. Model may not be trained yet.",
                "predictions": []
            }
        
        # Format predictions for response
        formatted_predictions = []
        for pred in predictions:
            formatted_predictions.append({
                "timestamp": pred.timestamp,
                "predicted_value": pred.predicted_value,
                "confidence_lower": pred.confidence_lower,
                "confidence_upper": pred.confidence_upper,
                "method": pred.method,
                "model_accuracy": pred.model_accuracy
            })
        
        return {
            "status": "success",
            "resource_type": resource_type,
            "metric_name": metric_name,
            "horizon_hours": horizon_hours,
            "method": method or "ensemble",
            "predictions_count": len(formatted_predictions),
            "predictions": formatted_predictions
        }
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error generating predictions: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/generate")
async def generate_predictions(
    request: Request,
    resource_type: str = Query(..., description="Resource type"),
    metric_name: str = Query("usage_percent", description="Metric name"),
    horizon_hours: int = Query(24, ge=1, le=168),
    method: Optional[str] = Query(None, description="Prediction method or ensemble"),
    force_retrain: bool = Query(False, description="Force model retraining"),
    api_key: str = Depends(verify_api_key)
):
    """
    Generate new predictions with optional model retraining
    """
    try:
        prediction_manager: PredictionManager = request.app.state.prediction_manager
        
        # Optionally retrain models
        if force_retrain:
            await prediction_manager.retrain_all_models()
        
        # Generate predictions
        predictions = await prediction_manager.get_predictions(
            resource_type=resource_type,
            metric_name=metric_name,
            horizon_hours=horizon_hours,
            method=method
        )
        
        return {
            "status": "success",
            "message": f"Predictions generated successfully",
            "resource_type": resource_type,
            "metric_name": metric_name,
            "horizon_hours": horizon_hours,
            "method": method or "ensemble",
            "predictions_count": len(predictions),
            "retrained": force_retrain,
            "timestamp": datetime.utcnow().isoformat()
        }
    
    except Exception as e:
        logger.error(f"Error generating predictions: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/accuracy/{method}")
async def get_model_accuracy(
    request: Request,
    method: str,
    api_key: str = Depends(verify_api_key)
):
    """
    Get prediction model accuracy metrics
    Returns accuracy metrics for specified or all methods
    """
    try:
        prediction_manager: PredictionManager = request.app.state.prediction_manager
        
        if method != "all" and method not in prediction_manager.predictors:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid method. Available: {list(prediction_manager.predictors.keys())}"
            )
        
        accuracy = await prediction_manager.get_model_accuracy(
            method=None if method == "all" else method
        )
        
        return {
            "status": "success",
            "method": method,
            "accuracy_metrics": accuracy,
            "timestamp": datetime.utcnow().isoformat()
        }
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting model accuracy: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/methods/available")
async def get_available_methods(
    request: Request,
    api_key: str = Depends(verify_api_key)
):
    """
    List available prediction methods and their status
    """
    try:
        prediction_manager: PredictionManager = request.app.state.prediction_manager
        
        methods_info = {}
        for method_name, predictor in prediction_manager.predictors.items():
            methods_info[method_name] = {
                "name": method_name,
                "trained": predictor.is_trained,
                "metadata": predictor.model_metadata if predictor.is_trained else {},
                "type": predictor.__class__.__name__
            }
        
        return {
            "status": "success",
            "available_methods": methods_info,
            "ensemble_available": any(p.is_trained for p in prediction_manager.predictors.values())
        }
    
    except Exception as e:
        logger.error(f"Error getting available methods: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/comparison")
async def compare_predictions(
    request: Request,
    resource_type: str = Query("cpu", description="Resource type"),
    metric_name: str = Query("usage_percent", description="Metric name"),
    horizon_hours: int = Query(6, ge=1, le=24),
    api_key: str = Depends(verify_api_key)
):
    """
    Compare predictions from all available methods
    Returns predictions from each method for comparison
    """
    try:
        prediction_manager: PredictionManager = request.app.state.prediction_manager
        
        comparison = {}
        timestamps = set()
        
        # Get predictions from each method
        for method_name in prediction_manager.predictors.keys():
            predictions = await prediction_manager.get_predictions(
                resource_type=resource_type,
                metric_name=metric_name,
                horizon_hours=horizon_hours,
                method=method_name
            )
            
            if predictions:
                comparison[method_name] = {
                    "predictions": [
                        {
                            "timestamp": p.timestamp,
                            "value": p.predicted_value,
                            "lower": p.confidence_lower,
                            "upper": p.confidence_upper
                        }
                        for p in predictions
                    ],
                    "accuracy": predictions[0].model_accuracy if predictions else None
                }
                
                for p in predictions:
                    timestamps.add(p.timestamp)
        
        # Get ensemble predictions
        ensemble_predictions = await prediction_manager.get_predictions(
            resource_type=resource_type,
            metric_name=metric_name,
            horizon_hours=horizon_hours
        )
        
        if ensemble_predictions:
            comparison["ensemble"] = {
                "predictions": [
                    {
                        "timestamp": p.timestamp,
                        "value": p.predicted_value,
                        "lower": p.confidence_lower,
                        "upper": p.confidence_upper
                    }
                    for p in ensemble_predictions
                ],
                "accuracy": ensemble_predictions[0].model_accuracy if ensemble_predictions else None
            }
        
        return {
            "status": "success",
            "resource_type": resource_type,
            "metric_name": metric_name,
            "horizon_hours": horizon_hours,
            "methods_compared": list(comparison.keys()),
            "time_points": len(timestamps),
            "comparison": comparison
        }
    
    except Exception as e:
        logger.error(f"Error comparing predictions: {e}")
        raise HTTPException(status_code=500, detail=str(e))
