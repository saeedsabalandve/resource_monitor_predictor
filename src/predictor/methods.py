# src/predictor/methods.py
# Implementation of multiple prediction methods
# Each method provides specialized forecasting capabilities
# Includes ARIMA, Prophet, LSTM, Exponential Smoothing, and Linear Regression

import numpy as np
import pandas as pd
from typing import List, Optional
from datetime import datetime, timedelta
from loguru import logger

from .base import BasePredictor, PredictionResult, TrainingData


class ARIMAPredictor(BasePredictor):
    """
    ARIMA (Auto-Regressive Integrated Moving Average) predictor
    Best for stationary time series data
    Automatically selects optimal parameters using auto_arima
    """
    
    def __init__(self):
        super().__init__("arima")
        self.model = None
        self.order = None
        self.std_dev = 0
    
    async def train(self, data: TrainingData) -> bool:
        """Train ARIMA model with automatic parameter selection"""
        try:
            from pmdarima import auto_arima
            
            if not self.validate_data(data):
                logger.error("Invalid training data for ARIMA")
                return False
            
            # Convert to pandas Series
            series = pd.Series(
                data.values,
                index=pd.DatetimeIndex(data.timestamps)
            )
            
            # Ensure regular frequency
            series = series.asfreq('T').interpolate()
            
            # Auto-select best ARIMA parameters
            self.model = auto_arima(
                series,
                start_p=1, start_q=1,
                max_p=5, max_q=5,
                seasonal=False,
                trace=False,
                error_action='ignore',
                suppress_warnings=True,
                stepwise=True,
                n_jobs=1
            )
            
            self.order = self.model.order
            self.std_dev = np.std(self.model.resid())
            self.is_trained = True
            
            self.model_metadata = {
                'order': self.order,
                'aic': self.model.aic(),
                'bic': self.model.bic()
            }
            
            logger.info(f"ARIMA model trained with order {self.order}")
            return True
            
        except Exception as e:
            logger.error(f"ARIMA training failed: {e}")
            return False
    
    async def predict(self, horizon_minutes: int) -> List[PredictionResult]:
        """Generate ARIMA predictions"""
        try:
            if not self.is_trained:
                raise ValueError("Model not trained")
            
            # Generate predictions
            forecast, conf_int = self.model.predict(
                n_periods=horizon_minutes,
                return_conf_int=True
            )
            
            results = []
            current_time = datetime.now()
            
            for i, (pred, (lower, upper)) in enumerate(zip(forecast, conf_int)):
                result = PredictionResult(
                    method=self.method_name,
                    resource_type="generic",
                    metric_name="predicted_value",
                    timestamp=(current_time + timedelta(minutes=i+1)).isoformat(),
                    predicted_value=float(pred),
                    confidence_lower=float(lower),
                    confidence_upper=float(upper),
                    prediction_horizon_minutes=horizon_minutes,
                    model_accuracy=self.model_metadata.get('aic', 0),
                    metadata={'order': self.order}
                )
                results.append(result)
            
            logger.info(f"ARIMA generated {len(results)} predictions")
            return results
            
        except Exception as e:
            logger.error(f"ARIMA prediction failed: {e}")
            return []
    
    async def evaluate_accuracy(self, test_data: TrainingData) -> float:
        """Evaluate ARIMA model accuracy using RMSE"""
        try:
            if not self.is_trained:
                return 0.0
            
            predictions = self.model.predict(n_periods=len(test_data.values))
            mse = np.mean((np.array(test_data.values) - predictions) ** 2)
            rmse = np.sqrt(mse)
            
            return float(rmse)
            
        except Exception as e:
            logger.error(f"ARIMA evaluation failed: {e}")
            return 0.0


class ProphetPredictor(BasePredictor):
    """
    Facebook Prophet predictor
    Excellent for time series with strong seasonal patterns
    Handles holidays and changepoints automatically
    """
    
    def __init__(self):
        super().__init__("prophet")
        self.model = None
    
    async def train(self, data: TrainingData) -> bool:
        """Train Prophet model"""
        try:
            from prophet import Prophet
            
            if not self.validate_data(data):
                logger.error("Invalid training data for Prophet")
                return False
            
            # Prepare DataFrame for Prophet
            df = pd.DataFrame({
                'ds': data.timestamps,
                'y': data.values
            })
            
            # Initialize and configure Prophet
            self.model = Prophet(
                interval_width=0.95,
                yearly_seasonality=True,
                weekly_seasonality=True,
                daily_seasonality=True,
                changepoint_prior_scale=0.05
            )
            
            # Add hourly seasonality for resource metrics
            self.model.add_seasonality(
                name='hourly',
                period=1/24,
                fourier_order=5
            )
            
            self.model.fit(df)
            self.is_trained = True
            
            # Create future dataframe for validation
            future = self.model.make_future_dataframe(periods=0)
            forecast = self.model.predict(future)
            
            self.model_metadata = {
                'changepoints': len(self.model.changepoints),
                'seasonality_modes': self.model.seasonalities
            }
            
            logger.info("Prophet model trained successfully")
            return True
            
        except Exception as e:
            logger.error(f"Prophet training failed: {e}")
            return False
    
    async def predict(self, horizon_minutes: int) -> List[PredictionResult]:
        """Generate Prophet predictions"""
        try:
            if not self.is_trained:
                raise ValueError("Model not trained")
            
            # Create future dataframe
            future = self.model.make_future_dataframe(
                periods=horizon_minutes,
                freq='T'
            )
            
            # Generate forecast
            forecast = self.model.predict(future)
            
            results = []
            
            # Get only future predictions
            future_forecast = forecast.tail(horizon_minutes)
            
            for _, row in future_forecast.iterrows():
                result = PredictionResult(
                    method=self.method_name,
                    resource_type="generic",
                    metric_name="predicted_value",
                    timestamp=row['ds'].isoformat(),
                    predicted_value=float(row['yhat']),
                    confidence_lower=float(row['yhat_lower']),
                    confidence_upper=float(row['yhat_upper']),
                    prediction_horizon_minutes=horizon_minutes,
                    model_accuracy=0.95,  # Prophet's built-in confidence
                    metadata={'trend': float(row.get('trend', 0))}
                )
                results.append(result)
            
            logger.info(f"Prophet generated {len(results)} predictions")
            return results
            
        except Exception as e:
            logger.error(f"Prophet prediction failed: {e}")
            return []
    
    async def evaluate_accuracy(self, test_data: TrainingData) -> float:
        """Evaluate Prophet model accuracy using MAE"""
        try:
            if not self.is_trained:
                return 0.0
            
            df = pd.DataFrame({
                'ds': test_data.timestamps,
                'y': test_data.values
            })
            
            forecast = self.model.predict(df[['ds']])
            mae = np.mean(np.abs(test_data.values - forecast['yhat'].values))
            
            return float(mae)
            
        except Exception as e:
            logger.error(f"Prophet evaluation failed: {e}")
            return 0.0


class LSTMPredictor(BasePredictor):
    """
    LSTM (Long Short-Term Memory) neural network predictor
    Best for complex, non-linear time series patterns
    Requires significant training data for optimal performance
    """
    
    def __init__(self):
        super().__init__("lstm")
        self.model = None
        self.scaler = None
        self.sequence_length = 60  # 1 hour of minute data
    
    async def train(self, data: TrainingData) -> bool:
        """Train LSTM model"""
        try:
            import tensorflow as tf
            from sklearn.preprocessing import MinMaxScaler
            
            if not self.validate_data(data):
                logger.error("Invalid training data for LSTM")
                return False
            
            # Scale data
            self.scaler = MinMaxScaler(feature_range=(0, 1))
            scaled_data = self.scaler.fit_transform(
                np.array(data.values).reshape(-1, 1)
            )
            
            # Create sequences
            X, y = self._create_sequences(scaled_data, self.sequence_length)
            
            if len(X) == 0:
                logger.error("Insufficient data for LSTM sequences")
                return False
            
            # Build LSTM model
            self.model = tf.keras.Sequential([
                tf.keras.layers.LSTM(50, return_sequences=True, input_shape=(self.sequence_length, 1)),
                tf.keras.layers.Dropout(0.2),
                tf.keras.layers.LSTM(50, return_sequences=True),
                tf.keras.layers.Dropout(0.2),
                tf.keras.layers.LSTM(50),
                tf.keras.layers.Dropout(0.2),
                tf.keras.layers.Dense(1)
            ])
            
            # Compile model
            self.model.compile(
                optimizer=tf.keras.optimizers.Adam(learning_rate=0.001),
                loss='mean_squared_error',
                metrics=['mae']
            )
            
            # Train model
            history = self.model.fit(
                X, y,
                epochs=50,
                batch_size=32,
                validation_split=0.2,
                verbose=0,
                callbacks=[
                    tf.keras.callbacks.EarlyStopping(
                        patience=5,
                        restore_best_weights=True
                    )
                ]
            )
            
            self.is_trained = True
            self.model_metadata = {
                'final_loss': float(history.history['loss'][-1]),
                'final_val_loss': float(history.history['val_loss'][-1])
            }
            
            logger.info("LSTM model trained successfully")
            return True
            
        except Exception as e:
            logger.error(f"LSTM training failed: {e}")
            return False
    
    def _create_sequences(self, data: np.ndarray, seq_length: int):
        """Create sequences for LSTM training"""
        X, y = [], []
        for i in range(seq_length, len(data)):
            X.append(data[i-seq_length:i, 0])
            y.append(data[i, 0])
        return np.array(X).reshape(-1, seq_length, 1), np.array(y)
    
    async def predict(self, horizon_minutes: int) -> List[PredictionResult]:
        """Generate LSTM predictions"""
        try:
            if not self.is_trained:
                raise ValueError("Model not trained")
            
            # Get last sequence for prediction
            last_sequence = self._get_last_sequence(horizon_minutes)
            
            predictions = []
            current_sequence = last_sequence.copy()
            
            for i in range(horizon_minutes):
                # Predict next value
                next_pred = self.model.predict(
                    current_sequence.reshape(1, self.sequence_length, 1),
                    verbose=0
                )
                
                # Inverse transform
                pred_value = self.scaler.inverse_transform(next_pred)[0][0]
                predictions.append(pred_value)
                
                # Update sequence for next prediction
                current_sequence = np.roll(current_sequence, -1)
                current_sequence[-1] = next_pred
            
            # Create prediction results
            results = []
            current_time = datetime.now()
            
            for i, pred in enumerate(predictions):
                result = PredictionResult(
                    method=self.method_name,
                    resource_type="generic",
                    metric_name="predicted_value",
                    timestamp=(current_time + timedelta(minutes=i+1)).isoformat(),
                    predicted_value=float(pred),
                    confidence_lower=float(pred * 0.9),
                    confidence_upper=float(pred * 1.1),
                    prediction_horizon_minutes=horizon_minutes,
                    model_accuracy=self.model_metadata.get('final_loss', 0),
                    metadata={}
                )
                results.append(result)
            
            logger.info(f"LSTM generated {len(results)} predictions")
            return results
            
        except Exception as e:
            logger.error(f"LSTM prediction failed: {e}")
            return []
    
    def _get_last_sequence(self, horizon_minutes: int) -> np.ndarray:
        """Get the last sequence for prediction seeding"""
        # This would be implemented to get actual last sequence from data
        return np.zeros(self.sequence_length)
    
    async def evaluate_accuracy(self, test_data: TrainingData) -> float:
        """Evaluate LSTM model accuracy"""
        try:
            if not self.is_trained:
                return 0.0
            
            scaled_test = self.scaler.transform(
                np.array(test_data.values).reshape(-1, 1)
            )
            X_test, y_test = self._create_sequences(
                scaled_test, 
                self.sequence_length
            )
            
            loss = self.model.evaluate(X_test, y_test, verbose=0)
            return float(loss[0])
            
        except Exception as e:
            logger.error(f"LSTM evaluation failed: {e}")
            return 0.0


class ExponentialSmoothingPredictor(BasePredictor):
    """
    Exponential Smoothing predictor (Holt-Winters)
    Good for data with trend and seasonality
    Computationally efficient for real-time predictions
    """
    
    def __init__(self):
        super().__init__("exponential_smoothing")
        self.model = None
        self.alpha = None
        self.beta = None
    
    async def train(self, data: TrainingData) -> bool:
        """Train Exponential Smoothing model"""
        try:
            from statsmodels.tsa.holtwinters import ExponentialSmoothing
            
            if not self.validate_data(data):
                logger.error("Invalid training data for Exponential Smoothing")
                return False
            
            # Convert to pandas Series
            series = pd.Series(
                data.values,
                index=pd.DatetimeIndex(data.timestamps)
            )
            
            # Fit Holt-Winters model
            self.model = ExponentialSmoothing(
                series,
                seasonal_periods=60,  # Hourly seasonality
                trend='add',
                seasonal='add',
                damped_trend=True
            ).fit()
            
            self.alpha = self.model.params.get('smoothing_level', 0.5)
            self.beta = self.model.params.get('smoothing_trend', 0.5)
            self.is_trained = True
            
            self.model_metadata = {
                'alpha': self.alpha,
                'beta': self.beta,
                'aic': self.model.aic
            }
            
            logger.info(f"Exponential Smoothing model trained with α={self.alpha:.3f}")
            return True
            
        except Exception as e:
            logger.error(f"Exponential Smoothing training failed: {e}")
            return False
    
    async def predict(self, horizon_minutes: int) -> List[PredictionResult]:
        """Generate Exponential Smoothing predictions"""
        try:
            if not self.is_trained:
                raise ValueError("Model not trained")
            
            # Generate forecast
            forecast = self.model.forecast(horizon_minutes)
            
            results = []
            current_time = datetime.now()
            
            for i, pred in enumerate(forecast):
                result = PredictionResult(
                    method=self.method_name,
                    resource_type="generic",
                    metric_name="predicted_value",
                    timestamp=(current_time + timedelta(minutes=i+1)).isoformat(),
                    predicted_value=float(pred),
                    confidence_lower=float(pred * 0.95),
                    confidence_upper=float(pred * 1.05),
                    prediction_horizon_minutes=horizon_minutes,
                    model_accuracy=self.model_metadata.get('aic', 0),
                    metadata={'alpha': self.alpha}
                )
                results.append(result)
            
            logger.info(f"Exponential Smoothing generated {len(results)} predictions")
            return results
            
        except Exception as e:
            logger.error(f"Exponential Smoothing prediction failed: {e}")
            return []
    
    async def evaluate_accuracy(self, test_data: TrainingData) -> float:
        """Evaluate Exponential Smoothing model accuracy"""
        try:
            if not self.is_trained:
                return 0.0
            
            predictions = self.model.forecast(len(test_data.values))
            rmse = np.sqrt(np.mean((test_data.values - predictions) ** 2))
            
            return float(rmse)
            
        except Exception as e:
            logger.error(f"Exponential Smoothing evaluation failed: {e}")
            return 0.0


class LinearRegressionPredictor(BasePredictor):
    """
    Simple Linear Regression predictor
    Quick baseline predictions for linear trends
    Least computationally intensive method
    """
    
    def __init__(self):
        super().__init__("linear_regression")
        self.coefficients = None
        self.intercept = None
        self.r_squared = 0
    
    async def train(self, data: TrainingData) -> bool:
        """Train Linear Regression model"""
        try:
            from sklearn.linear_model import LinearRegression
            from sklearn.metrics import r2_score
            
            if not self.validate_data(data):
                logger.error("Invalid training data for Linear Regression")
                return False
            
            # Convert timestamps to numeric features
            X = np.array([
                (t - data.timestamps[0]).total_seconds() / 3600 
                for t in data.timestamps
            ]).reshape(-1, 1)
            
            y = np.array(data.values)
            
            # Fit linear regression
            model = LinearRegression()
            model.fit(X, y)
            
            self.coefficients = model.coef_[0]
            self.intercept = model.intercept_
            
            # Calculate R²
            predictions = model.predict(X)
            self.r_squared = r2_score(y, predictions)
            
            self.is_trained = True
            self.model_metadata = {
                'coefficient': float(self.coefficients),
                'intercept': float(self.intercept),
                'r_squared': float(self.r_squared)
            }
            
            logger.info(f"Linear Regression trained with R²={self.r_squared:.3f}")
            return True
            
        except Exception as e:
            logger.error(f"Linear Regression training failed: {e}")
            return False
    
    async def predict(self, horizon_minutes: int) -> List[PredictionResult]:
        """Generate Linear Regression predictions"""
        try:
            if not self.is_trained:
                raise ValueError("Model not trained")
            
            results = []
            current_time = datetime.now()
            base_hours = 0
            
            for i in range(horizon_minutes):
                hours_ahead = base_hours + (i + 1) / 60
                prediction = self.intercept + self.coefficients * hours_ahead
                
                # Simple confidence interval based on R²
                confidence_width = prediction * (1 - self.r_squared) * 0.5
                
                result = PredictionResult(
                    method=self.method_name,
                    resource_type="generic",
                    metric_name="predicted_value",
                    timestamp=(current_time + timedelta(minutes=i+1)).isoformat(),
                    predicted_value=float(prediction),
                    confidence_lower=float(prediction - confidence_width),
                    confidence_upper=float(prediction + confidence_width),
                    prediction_horizon_minutes=horizon_minutes,
                    model_accuracy=self.r_squared,
                    metadata={'r_squared': self.r_squared}
                )
                results.append(result)
            
            logger.info(f"Linear Regression generated {len(results)} predictions")
            return results
            
        except Exception as e:
            logger.error(f"Linear Regression prediction failed: {e}")
            return []
    
    async def evaluate_accuracy(self, test_data: TrainingData) -> float:
        """Return R² score as accuracy metric"""
        return self.r_squared
