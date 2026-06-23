# src/predictor/manager.py
# Prediction manager orchestrating multiple prediction methods
# Handles model training, prediction generation, and ensemble methods
# Manages caching and periodic retraining

from typing import Dict, List, Optional, Any
from datetime import datetime, timedelta
from influxdb_client import InfluxDBClient
import redis.asyncio as redis
import json
from loguru import logger

from config.settings import Settings, PredictionMethod
from .base import BasePredictor, PredictionResult, TrainingData
from .methods import (
    ARIMAPredictor,
    ProphetPredictor,
    LSTMPredictor,
    ExponentialSmoothingPredictor,
    LinearRegressionPredictor
)


class PredictionManager:
    """
    Manages multiple prediction models and their lifecycle
    Provides unified interface for predictions with ensemble support
    Implements caching and automatic retraining
    """
    
    def __init__(
        self,
        settings: Settings,
        influx_client: InfluxDBClient,
        redis_client: redis.Redis
    ):
        self.settings = settings
        self.influx_client = influx_client
        self.redis_client = redis_client
        
        # Initialize predictors based on configuration
        self.predictors: Dict[str, BasePredictor] = {}
        self._initialize_predictors()
        
        # Cache settings
        self.cache_prefix = "prediction:"
        self.cache_ttl = settings.CACHE_TTL_SECONDS
    
    def _initialize_predictors(self):
        """Initialize configured prediction methods"""
        predictor_map = {
            PredictionMethod.ARIMA: ARIMAPredictor,
            PredictionMethod.PROPHET: ProphetPredictor,
            PredictionMethod.LSTM: LSTMPredictor,
            PredictionMethod.EXPONENTIAL_SMOOTHING: ExponentialSmoothingPredictor,
            PredictionMethod.LINEAR_REGRESSION: LinearRegressionPredictor
        }
        
        for method in self.settings.ACTIVE_PREDICTION_METHODS:
            predictor_class = predictor_map.get(method)
            if predictor_class:
                self.predictors[method.value] = predictor_class()
                logger.info(f"Initialized {method.value} predictor")
            else:
                logger.warning(f"Unknown prediction method: {method}")
    
    async def initialize(self):
        """
        Initialize prediction manager
        Train all models with historical data
        """
        logger.info("Initializing Prediction Manager...")
        
        for method_name, predictor in self.predictors.items():
            await self._train_predictor(predictor, method_name)
        
        logger.info(f"Prediction Manager initialized with {len(self.predictors)} methods")
    
    async def _train_predictor(self, predictor: BasePredictor, method_name: str):
        """
        Train a single predictor with historical data
        Fetches data from InfluxDB based on configured intervals
        """
        try:
            # Fetch historical data for training
            training_data = await self._fetch_training_data(
                hours_back=self.settings.RETRAIN_INTERVAL_HOURS
            )
            
            if training_data and len(training_data.timestamps) >= self.settings.MIN_DATA_POINTS_FOR_PREDICTION:
                success = await predictor.train(training_data)
                if success:
                    logger.info(f"Successfully trained {method_name} predictor")
                else:
                    logger.error(f"Failed to train {method_name} predictor")
            else:
                logger.warning(f"Insufficient data for training {method_name}")
                
        except Exception as e:
            logger.error(f"Error training {method_name} predictor: {e}")
    
    async def _fetch_training_data(self, hours_back: int) -> Optional[TrainingData]:
        """
        Fetch historical metrics from InfluxDB for training
        Returns structured training data
        """
        try:
            query_api = self.influx_client.query_api()
            
            # Query for CPU usage as example (extendable to other metrics)
            query = f'''
                from(bucket: "{self.settings.INFLUXDB_BUCKET}")
                    |> range(start: -{hours_back}h)
                    |> filter(fn: (r) => r._measurement == "resource_cpu")
                    |> filter(fn: (r) => r.metric_name == "usage_percent")
                    |> filter(fn: (r) => r._field == "value")
                    |> aggregateWindow(every: 1m, fn: mean, createEmpty: false)
                    |> yield(name: "mean")
            '''
            
            result = query_api.query(query, org=self.settings.INFLUXDB_ORG)
            
            timestamps = []
            values = []
            
            for table in result:
                for record in table.records:
                    timestamps.append(record.get_time())
                    values.append(record.get_value())
            
            if timestamps:
                return TrainingData(
                    timestamps=timestamps,
                    values=values,
                    metadata={'hours_back': hours_back, 'data_points': len(timestamps)}
                )
            
            return None
            
        except Exception as e:
            logger.error(f"Error fetching training data: {e}")
            return None
    
    async def get_predictions(
        self,
        resource_type: str,
        metric_name: str,
        horizon_hours: int = None,
        method: str = None
    ) -> List[PredictionResult]:
        """
        Get predictions for specified resource and metric
        Supports method-specific or ensemble predictions
        Uses caching for performance
        """
        if horizon_hours is None:
            horizon_hours = self.settings.PREDICTION_HORIZON_HOURS
        
        horizon_minutes = horizon_hours * 60
        
        # Check cache first
        cache_key = f"{self.cache_prefix}{resource_type}:{metric_name}:{horizon_hours}:{method or 'ensemble'}"
        cached = await self._get_cached_predictions(cache_key)
        if cached:
            return cached
        
        # Generate predictions
        if method and method in self.predictors:
            results = await self._get_method_predictions(
                method, resource_type, metric_name, horizon_minutes
            )
        else:
            # Ensemble prediction (average of all methods)
            results = await self._get_ensemble_predictions(
                resource_type, metric_name, horizon_minutes
            )
        
        # Cache results
        await self._cache_predictions(cache_key, results)
        
        return results
    
    async def _get_method_predictions(
        self,
        method: str,
        resource_type: str,
        metric_name: str,
        horizon_minutes: int
    ) -> List[PredictionResult]:
        """Get predictions from a specific method"""
        predictor = self.predictors.get(method)
        if not predictor or not predictor.is_trained:
            logger.warning(f"Predictor {method} not available or not trained")
            return []
        
        results = await predictor.predict(horizon_minutes)
        
        # Add resource context to predictions
        for result in results:
            result.resource_type = resource_type
            result.metric_name = metric_name
        
        return results
    
    async def _get_ensemble_predictions(
        self,
        resource_type: str,
        metric_name: str,
        horizon_minutes: int
    ) -> List[PredictionResult]:
        """Generate ensemble predictions by averaging all methods"""
        all_predictions = {}
        
        for method_name, predictor in self.predictors.items():
            if predictor.is_trained:
                predictions = await predictor.predict(horizon_minutes)
                for pred in predictions:
                    key = pred.timestamp
                    if key not in all_predictions:
                        all_predictions[key] = []
                    all_predictions[key].append(pred)
        
        # Average predictions for each timestamp
        ensemble_results = []
        for timestamp, preds in sorted(all_predictions.items()):
            if preds:
                avg_value = sum(p.predicted_value for p in preds) / len(preds)
                avg_confidence_lower = sum(
                    p.confidence_lower for p in preds if p.confidence_lower is not None
                ) / len(preds)
                avg_confidence_upper = sum(
                    p.confidence_upper for p in preds if p.confidence_upper is not None
                ) / len(preds)
                
                ensemble_result = PredictionResult(
                    method="ensemble",
                    resource_type=resource_type,
                    metric_name=metric_name,
                    timestamp=timestamp,
                    predicted_value=avg_value,
                    confidence_lower=avg_confidence_lower,
                    confidence_upper=avg_confidence_upper,
                    prediction_horizon_minutes=horizon_minutes,
                    model_accuracy=sum(p.model_accuracy for p in preds) / len(preds),
                    metadata={'methods_used': [p.method for p in preds]}
                )
                ensemble_results.append(ensemble_result)
        
        return ensemble_results
    
    async def _get_cached_predictions(self, cache_key: str) -> Optional[List[PredictionResult]]:
        """Retrieve cached predictions"""
        try:
            cached_data = await self.redis_client.get(cache_key)
            if cached_data:
                data = json.loads(cached_data)
                return [
                    PredictionResult(**item) for item in data
                ]
        except Exception as e:
            logger.debug(f"Cache miss or error: {e}")
        
        return None
    
    async def _cache_predictions(self, cache_key: str, predictions: List[PredictionResult]):
        """Cache prediction results"""
        try:
            data = json.dumps([p.__dict__ for p in predictions])
            await self.redis_client.setex(
                cache_key,
                self.cache_ttl,
                data
            )
        except Exception as e:
            logger.warning(f"Failed to cache predictions: {e}")
    
    async def get_model_accuracy(self, method: str = None) -> Dict[str, float]:
        """Get accuracy metrics for prediction models"""
        accuracy = {}
        
        predictors_to_check = (
            {method: self.predictors[method]} if method and method in self.predictors
            else self.predictors
        )
        
        for method_name, predictor in predictors_to_check.items():
            if predictor.is_trained:
                # Fetch recent test data
                test_data = await self._fetch_training_data(hours_back=1)
                if test_data:
                    acc = await predictor.evaluate_accuracy(test_data)
                    accuracy[method_name] = acc
        
        return accuracy
    
    async def retrain_all_models(self):
        """Force retraining of all prediction models"""
        logger.info("Retraining all prediction models...")
        for method_name, predictor in self.predictors.items():
            await self._train_predictor(predictor, method_name)
        logger.info("All models retrained")
