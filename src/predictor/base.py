# src/predictor/base.py
# Base predictor abstract class
# Defines interface for all prediction methods
# Ensures consistent prediction output format

from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional
from dataclasses import dataclass
from datetime import datetime, timedelta
import numpy as np


@dataclass
class PredictionResult:
    """Standardized prediction result structure"""
    method: str
    resource_type: str
    metric_name: str
    timestamp: str
    predicted_value: float
    confidence_lower: Optional[float]
    confidence_upper: Optional[float]
    prediction_horizon_minutes: int
    model_accuracy: float
    metadata: Dict[str, Any]


@dataclass
class TrainingData:
    """Structured training data for prediction models"""
    timestamps: List[datetime]
    values: List[float]
    metadata: Dict[str, Any]


class BasePredictor(ABC):
    """
    Abstract base class for all prediction methods
    Enforces implementation of required prediction interface
    """
    
    def __init__(self, method_name: str):
        self.method_name = method_name
        self.is_trained = False
        self.model_metadata = {}
    
    @abstractmethod
    async def train(self, data: TrainingData) -> bool:
        """
        Train the prediction model with historical data
        Returns True if training successful
        """
        pass
    
    @abstractmethod
    async def predict(self, horizon_minutes: int) -> List[PredictionResult]:
        """
        Generate predictions for specified horizon
        Returns list of prediction results at configured intervals
        """
        pass
    
    @abstractmethod
    async def evaluate_accuracy(self, test_data: TrainingData) -> float:
        """
        Evaluate model accuracy using test data
        Returns accuracy metric (R², RMSE, etc.)
        """
        pass
    
    def validate_data(self, data: TrainingData) -> bool:
        """
        Validate training data quality and completeness
        Checks for minimum data points and NaN values
        """
        if len(data.timestamps) < 10:
            return False
        
        if len(data.timestamps) != len(data.values):
            return False
        
        if any(np.isnan(data.values)):
            return False
        
        if any(np.isinf(data.values)):
            return False
        
        return True
    
    def calculate_confidence_intervals(
        self, 
        predictions: List[float], 
        std_dev: float
    ) -> List[tuple]:
        """
        Calculate 95% confidence intervals for predictions
        """
        confidence_intervals = []
        z_score = 1.96  # 95% confidence
        
        for pred in predictions:
            lower = pred - (z_score * std_dev)
            upper = pred + (z_score * std_dev)
            confidence_intervals.append((max(0, lower), upper))
        
        return confidence_intervals
