"""Module 3: Prediction & Health Monitoring Base Architecture.
Defines abstract base classes and interfaces for future predictive maintenance,
degradation forecasting, and anomaly detection engines.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional
import pandas as pd


class BasePredictor(ABC):
    """Abstract Base Class for PTTEP GT-2420A Predictive Models."""

    def __init__(self, model_name: str, config: Optional[Dict[str, Any]] = None) -> None:
        self.model_name = model_name
        self.config = config or {}
        self.is_trained: bool = False

    @abstractmethod
    def fit(self, training_data: pd.DataFrame, **kwargs: Any) -> Any:
        """Train or calibrate the model on historical sensor telemetry."""
        pass

    @abstractmethod
    def predict(self, feature_data: pd.DataFrame, **kwargs: Any) -> pd.DataFrame:
        """Generate forward predictions for target sensors."""
        pass

    @abstractmethod
    def evaluate(self, ground_truth: pd.DataFrame, predictions: pd.DataFrame) -> Dict[str, float]:
        """Evaluate model performance using standard regression / detection metrics."""
        pass
