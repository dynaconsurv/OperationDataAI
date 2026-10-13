"""Module 3: Prediction & Health Monitoring Engine.

Provides multi-sensor CorrelationDigitalTwin virtual sensing, residual-based
anomaly detection, root-cause sensor attribution, and failure forecasting.
"""

from src.module3_prediction.base_predictor import BasePredictor
from src.module3_prediction.anomaly_detector import SensorAnomalyDetector
from src.module3_prediction.correlation_digital_twin import CorrelationDigitalTwin
from src.module3_prediction.forecast_stub import SensorForecastStub

__all__ = [
    "BasePredictor",
    "SensorAnomalyDetector",
    "CorrelationDigitalTwin",
    "SensorForecastStub",
]
