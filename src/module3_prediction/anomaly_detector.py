"""Baseline Multi-Sensor Anomaly Detector using Isolation Forest and Statistical Deviations."""

from __future__ import annotations

from typing import Any, Dict, List, Optional
import numpy as np
import pandas as pd
from sklearn.ensemble import IsolationForest

from src.module3_prediction.base_predictor import BasePredictor
from src.utils.logger import get_logger

logger = get_logger("AnomalyDetector")


class SensorAnomalyDetector(BasePredictor):
    """Detects multi-sensor operational anomalies and abnormal excursions."""

    def __init__(self, contamination: float = 0.02, config: Optional[Dict[str, Any]] = None) -> None:
        super().__init__(model_name="IsolationForest_AnomalyDetector", config=config)
        self.contamination = contamination
        self.model = IsolationForest(
            contamination=self.contamination,
            random_state=42,
            n_estimators=100,
        )

    def fit(self, training_data: pd.DataFrame, **kwargs: Any) -> SensorAnomalyDetector:
        """Fit Isolation Forest on historical sensor data."""
        clean_df = training_data.select_dtypes(include=[np.number]).dropna()
        if clean_df.empty:
            logger.warning("Empty data provided for training anomaly detector.")
            return self

        logger.info(f"Training Anomaly Detector on {clean_df.shape[0]} samples across {clean_df.shape[1]} sensors...")
        self.model.fit(clean_df)
        self.is_trained = True
        return self

    def predict(self, feature_data: pd.DataFrame, **kwargs: Any) -> pd.DataFrame:
        """Score each timestamp: returns anomaly flag (-1 = anomaly, 1 = normal) and score."""
        clean_df = feature_data.select_dtypes(include=[np.number]).fillna(method="ffill").fillna(0.0)
        if not self.is_trained:
            logger.warning("Model not fitted. Fitting on incoming data.")
            self.fit(clean_df)

        scores = self.model.decision_function(clean_df)
        preds = self.model.predict(clean_df)

        result_df = pd.DataFrame(
            {
                "anomaly_flag": preds,
                "is_anomaly": preds == -1,
                "anomaly_score": scores,  # Lower score indicates more abnormal
            },
            index=clean_df.index,
        )
        return result_df

    def evaluate(self, ground_truth: pd.DataFrame, predictions: pd.DataFrame) -> Dict[str, float]:
        """Compute summary statistics of detected anomalies."""
        n_anomalies = int((predictions["anomaly_flag"] == -1).sum())
        total = len(predictions)
        ratio = round((n_anomalies / total) * 100.0, 2) if total > 0 else 0.0
        return {
            "total_points": total,
            "anomaly_count": n_anomalies,
            "anomaly_percentage": ratio,
        }
