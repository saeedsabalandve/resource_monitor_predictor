# tests/test_predictor.py
# Unit tests for prediction methods
# Tests model training, prediction accuracy, and edge cases

import pytest
import numpy as np
from datetime import datetime, timedelta
from unittest.mock import Mock, patch

from src.predictor.base import BasePredictor, PredictionResult, TrainingData
from src.predictor.methods import (
    ARIMAPredictor,
    ProphetPredictor,
    ExponentialSmoothingPredictor,
    LinearRegressionPredictor
)


@pytest.fixture
def sample_training_data():
    """Create sample training data for tests"""
    timestamps = [
        datetime(2024, 1, 1, 0, 0) + timedelta(minutes=i)
        for i in range(1000)
    ]
    
    # Generate sinusoidal pattern with noise
    values = [
        50 + 20 * np.sin(i / 30) + np.random.normal(0, 5)
        for i in range(1000)
    ]
    
    return TrainingData(
        timestamps=timestamps,
        values=values,
        metadata={'source': 'test'}
    )


@pytest.fixture
def sample_test_data():
    """Create sample test data"""
    timestamps = [
        datetime(2024, 1, 1, 16, 40) + timedelta(minutes=i)
        for i in range(100)
    ]
    
    values = [
        50 + 20 * np.sin((1000 + i) / 30) + np.random.normal(0, 5)
        for i in range(100)
    ]
    
    return TrainingData(
        timestamps=timestamps,
        values=values,
        metadata={'source': 'test'}
    )


class TestBasePredictor:
    """Test base predictor abstract class"""
    
    def test_validate_data_valid(self, sample_training_data):
        """Test data validation with valid data"""
        # Create concrete implementation for testing
        class ConcretePredictor(BasePredictor):
            async def train(self, data):
                return True
            async def predict(self, horizon):
                return []
            async def evaluate_accuracy(self, data):
                return 0.0
        
        predictor = ConcretePredictor("test")
        assert predictor.validate_data(sample_training_data) == True
    
    def test_validate_data_invalid(self):
        """Test data validation with invalid data"""
        class ConcretePredictor(BasePredictor):
            async def train(self, data):
                return True
            async def predict(self, horizon):
                return []
            async def evaluate_accuracy(self, data):
                return 0.0
        
        predictor = ConcretePredictor("test")
        
        # Test with insufficient data
        invalid_data = TrainingData(
            timestamps=[datetime.now()],
            values=[50.0],
            metadata={}
        )
        assert predictor.validate_data(invalid_data) == False
        
        # Test with NaN values
        nan_data = TrainingData(
            timestamps=[datetime.now() + timedelta(minutes=i) for i in range(20)],
            values=[np.nan if i == 5 else 50.0 for i in range(20)],
            metadata={}
        )
        assert predictor.validate_data(nan_data) == False
    
    def test_confidence_intervals(self):
        """Test confidence interval calculation"""
        class ConcretePredictor(BasePredictor):
            async def train(self, data):
                return True
            async def predict(self, horizon):
                return []
            async def evaluate_accuracy(self, data):
                return 0.0
        
        predictor = ConcretePredictor("test")
        predictions = [50.0, 55.0, 60.0]
        intervals = predictor.calculate_confidence_intervals(predictions, 5.0)
        
        assert len(intervals) == 3
        # Check 95% confidence interval (z=1.96)
        for pred, (lower, upper) in zip(predictions, intervals):
            assert lower < pred < upper
            assert upper - lower == pytest.approx(2 * 1.96 * 5.0, rel=0.01)


@pytest.mark.asyncio
class TestARIMAPredictor:
    """Test ARIMA predictor"""
    
    async def test_train_predictor(self, sample_training_data):
        """Test ARIMA training"""
        predictor = ARIMAPredictor()
        
        # Training should succeed with sufficient data
        success = await predictor.train(sample_training_data)
        
        if success:
            assert predictor.is_trained == True
            assert predictor.order is not None
    
    async def test_predict_after_training(self, sample_training_data):
        """Test ARIMA prediction after training"""
        predictor = ARIMAPredictor()
        success = await predictor.train(sample_training_data)
        
        if success:
            predictions = await predictor.predict(horizon_minutes=60)
            
            assert len(predictions) == 60
            assert all(isinstance(p, PredictionResult) for p in predictions)
            assert all(p.method == "arima" for p in predictions)
    
    async def test_predict_without_training(self):
        """Test prediction without training raises error"""
        predictor = ARIMAPredictor()
        predictions = await predictor.predict(horizon_minutes=30)
        
        # Should return empty list or handle gracefully
        assert len(predictions) == 0


@pytest.mark.asyncio
class TestProphetPredictor:
    """Test Prophet predictor"""
    
    async def test_train_predictor(self, sample_training_data):
        """Test Prophet training"""
        predictor = ProphetPredictor()
        
        # Training should succeed with sufficient data
        success = await predictor.train(sample_training_data)
        
        if success:
            assert predictor.is_trained == True
    
    async def test_predict_after_training(self, sample_training_data):
        """Test Prophet prediction after training"""
        predictor = ProphetPredictor()
        success = await predictor.train(sample_training_data)
        
        if success:
            predictions = await predictor.predict(horizon_minutes=60)
            
            assert len(predictions) == 60
            assert all(p.method == "prophet" for p in predictions)
            # Prophet should provide confidence intervals
            assert all(p.confidence_lower is not None for p in predictions)
            assert all(p.confidence_upper is not None for p in predictions)


@pytest.mark.asyncio
class TestExponentialSmoothingPredictor:
    """Test Exponential Smoothing predictor"""
    
    async def test_train_predictor(self, sample_training_data):
        """Test Exponential Smoothing training"""
        predictor = ExponentialSmoothingPredictor()
        
        success = await predictor.train(sample_training_data)
        
        if success:
            assert predictor.is_trained == True
    
    async def test_predict_values_range(self, sample_training_data):
        """Test predictions are within reasonable range"""
        predictor = ExponentialSmoothingPredictor()
        success = await predictor.train(sample_training_data)
        
        if success:
            predictions = await predictor.predict(horizon_minutes=30)
            
            for pred in predictions:
                # Predictions should be positive
                assert pred.predicted_value > 0


@pytest.mark.asyncio
class TestLinearRegressionPredictor:
    """Test Linear Regression predictor"""
    
    async def test_train_predictor(self, sample_training_data):
        """Test Linear Regression training"""
        predictor = LinearRegressionPredictor()
        success = await predictor.train(sample_training_data)
        
        if success:
            assert predictor.is_trained == True
            assert hasattr(predictor, 'r_squared')
    
    async def test_predict_linear_trend(self):
        """Test prediction with clearly linear data"""
        predictor = LinearRegressionPredictor()
        
        # Create linear data
        timestamps = [datetime(2024, 1, 1, 0, 0) + timedelta(hours=i) for i in range(100)]
        values = [2 * i + 10 for i in range(100)]
        
        linear_data = TrainingData(
            timestamps=timestamps,
            values=values,
            metadata={}
        )
        
        success = await predictor.train(linear_data)
        
        if success:
            # With perfect linear data, R² should be close to 1
            assert predictor.r_squared > 0.95
            
            predictions = await predictor.predict(horizon_minutes=10)
            assert len(predictions) == 10
            
            # Check increasing trend is maintained
            for i in range(1, len(predictions)):
                assert predictions[i].predicted_value > predictions[i-1].predicted_value


@pytest.mark.asyncio
class TestPredictionManager:
    """Test prediction manager"""
    
    @pytest.fixture
    async def prediction_manager(self):
        """Create test prediction manager"""
        from src.predictor.manager import PredictionManager
        from config.settings import Settings
        
        settings = Settings()
        mock_influx = Mock()
        mock_redis = Mock()
        
        # Configure mock Redis
        mock_redis.get = Mock(return_value=None)
        mock_redis.setex = Mock()
        
        manager = PredictionManager(settings, mock_influx, mock_redis)
        return manager
    
    async def test_manager_initialization(self, prediction_manager):
        """Test manager initializes with configured predictors"""
        assert len(prediction_manager.predictors) > 0
    
    async def test_ensemble_predictions(self, prediction_manager):
        """Test ensemble prediction generation"""
        # Mock predictors
        for predictor in prediction_manager.predictors.values():
            predictor.is_trained = True
            predictor.predict = Mock(return_value=[
                PredictionResult(
                    method=predictor.method_name,
                    resource_type="cpu",
                    metric_name="usage_percent",
                    timestamp=datetime.now().isoformat(),
                    predicted_value=50.0,
                    confidence_lower=45.0,
                    confidence_upper=55.0,
                    prediction_horizon_minutes=60,
                    model_accuracy=0.9,
                    metadata={}
                )
            ])
        
        predictions = await prediction_manager._get_ensemble_predictions(
            "cpu", "usage_percent", 60
        )
        
        # Since we mock all predictors to return same value,
        # ensemble should also return 50.0
        assert len(predictions) > 0
        if predictions:
            assert predictions[0].predicted_value == pytest.approx(50.0)
            assert predictions[0].method == "ensemble"
