"""Module 3: Correlation-Driven Multi-Sensor Digital Twin & Predictive Anomaly Engine.

Constructs virtual-sensing digital twins for all sensors using their top-correlated
peer clusters (Module 2 topology). Detects physical correlation breakdown, isolates
the primary culprit sensor via the Sensor Contribution Index (SCI), and generates
actionable early warning advisories with root-cause diagnostic fault trees.
"""

from __future__ import annotations

import datetime as dt
import pickle
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

import numpy as np
import pandas as pd
from sklearn.linear_model import Ridge

from src.module3_prediction.base_predictor import BasePredictor
from src.utils.logger import get_logger

logger = get_logger("CorrelationDigitalTwin")


class CorrelationDigitalTwin(BasePredictor):
    """Predictive Multi-Sensor Digital Twin using Many-to-Many Correlation Graphs.
    
    For every sensor on the equipment, this model constructs an expected-value
    regression estimator using its strongest correlated peer sensors. When mechanical
    or thermodynamic degradation occurs, the correlation between physically coupled
    sensors breaks down, producing a sharp residual spike that is detected tens of
    hours before absolute operating limits (HH/LL) are breached.
    """

    def __init__(
        self,
        top_n_peers: int = 5,
        min_correlation: float = 0.65,
        alpha: float = 1.0,
        z_threshold: float = 3.0,
        system_anomaly_percentile: float = 99.0,
        sensor_catalog: Optional[List[Dict[str, Any]]] = None,
        config: Optional[Dict[str, Any]] = None,
    ) -> None:
        super().__init__(model_name="CorrelationDigitalTwin", config=config)
        self.top_n_peers = top_n_peers
        self.min_correlation = min_correlation
        self.alpha = alpha
        self.z_threshold = z_threshold
        self.system_anomaly_percentile = system_anomaly_percentile
        self.sensor_catalog = sensor_catalog or []

        # Internal calibrated states
        self.models: Dict[str, Ridge] = {}
        self.peer_map: Dict[str, List[str]] = {}
        self.residual_means: Dict[str, float] = {}
        self.residual_stds: Dict[str, float] = {}
        self.system_anomaly_threshold: float = 15.0
        self.subsystem_map: Dict[str, str] = {}
        self.category_map: Dict[str, str] = {}
        self.tag_name_map: Dict[str, str] = {}

        if self.sensor_catalog:
            self._build_sensor_lookup_maps(self.sensor_catalog)

    def _build_sensor_lookup_maps(self, catalog: List[Dict[str, Any]]) -> None:
        """Build path-to-metadata resolution lookups."""
        for item in catalog:
            path = item.get("full_af_path") or item.get("parent", "")
            if path:
                self.subsystem_map[path] = item.get("subsystem", "General")
                self.category_map[path] = item.get("category", "General")
                self.tag_name_map[path] = item.get("tag_name", path.split("\\")[-1])

    def fit(
        self,
        training_data: pd.DataFrame,
        correlation_matrix: Optional[pd.DataFrame] = None,
        **kwargs: Any,
    ) -> CorrelationDigitalTwin:
        """Calibrate digital twin models across all sensors using correlated peers.

        Parameters
        ----------
        training_data : pd.DataFrame
            Historical sensor telemetry DataFrame indexed by timestamp.
        correlation_matrix : pd.DataFrame, optional
            Precomputed square correlation matrix from Module 2. If None,
            Pearson correlation is computed directly from training_data.

        Returns
        -------
        CorrelationDigitalTwin
            Fitted instance.
        """
        clean_df = training_data.select_dtypes(include=[np.number]).dropna(how="all")
        if clean_df.empty:
            logger.warning("Empty dataset provided for digital twin training.")
            return self

        # Compute or validate correlation matrix
        if correlation_matrix is None or correlation_matrix.empty:
            logger.info("Computing Pearson correlation matrix for digital twin peer selection...")
            corr = clean_df.corr(method="pearson", min_periods=24)
        else:
            corr = correlation_matrix

        logger.info(f"Calibrating Digital Twin estimators across {clean_df.shape[1]} sensors...")
        self.models.clear()
        self.peer_map.clear()
        self.residual_means.clear()
        self.residual_stds.clear()

        sample_residuals: Dict[str, np.ndarray] = {}

        for sensor in clean_df.columns:
            if sensor not in corr.columns:
                continue

            # Select top peers (excluding self)
            peer_series = corr[sensor].drop(index=sensor, errors="ignore").dropna()
            if peer_series.empty:
                continue

            # Filter by absolute correlation threshold
            valid_peers = peer_series[peer_series.abs() >= self.min_correlation]
            if len(valid_peers) < 2:
                # If few exceed threshold, fall back to top available peers
                valid_peers = peer_series.abs().nlargest(min(3, len(peer_series)))
            else:
                valid_peers = valid_peers.abs().nlargest(self.top_n_peers)

            peer_cols = [p for p in valid_peers.index if p in clean_df.columns]
            if not peer_cols:
                continue

            # Prepare regression dataset
            subset = clean_df[[sensor] + peer_cols].dropna()
            if len(subset) < 20:
                continue

            X = subset[peer_cols]
            y = subset[sensor]

            # Fit Ridge model
            model = Ridge(alpha=self.alpha, fit_intercept=True)
            model.fit(X, y)
            y_pred = model.predict(X)
            raw_res = y.values - y_pred

            res_mean = float(np.mean(raw_res))
            res_std = float(np.std(raw_res))
            if res_std < 1e-6:
                res_std = 1.0  # Avoid zero-division

            self.models[sensor] = model
            self.peer_map[sensor] = peer_cols
            self.residual_means[sensor] = res_mean
            self.residual_stds[sensor] = res_std
            sample_residuals[sensor] = (raw_res - res_mean) / res_std

        # Compute baseline composite Squared Prediction Error (SPE)
        if sample_residuals:
            # Align length
            min_len = min(len(v) for v in sample_residuals.values())
            res_matrix = np.column_stack([v[:min_len] for v in sample_residuals.values()])
            spe_baseline = np.sum(res_matrix**2, axis=1)
            self.system_anomaly_threshold = float(
                np.percentile(spe_baseline, self.system_anomaly_percentile)
            )
        else:
            self.system_anomaly_threshold = 15.0

        self.is_trained = True
        logger.info(
            f"Successfully calibrated {len(self.models)} sensor digital twins. "
            f"System anomaly threshold (SPE): {self.system_anomaly_threshold:.2f}"
        )
        return self

    def predict_expected_values(self, data: pd.DataFrame) -> pd.DataFrame:
        r"""Generate virtual-sensing expected values \hat{X} for all modeled sensors."""
        if not self.is_trained:
            raise RuntimeError("CorrelationDigitalTwin must be fitted before predict_expected_values().")

        expected_dict: Dict[str, np.ndarray] = {}
        for sensor, model in self.models.items():
            peers = self.peer_map[sensor]
            if all(p in data.columns for p in peers):
                X = data[peers].ffill().fillna(0.0)
                expected_dict[sensor] = model.predict(X)
            else:
                expected_dict[sensor] = np.full(len(data), np.nan)

        return pd.DataFrame(expected_dict, index=data.index)

    def score_telemetry(self, data: pd.DataFrame) -> pd.DataFrame:
        """Compute full multi-sensor residuals, z-scores, and Sensor Contribution Index (SCI).

        Returns
        -------
        pd.DataFrame
            Summary dataframe containing:
            - composite_anomaly_score (SPE)
            - is_anomaly (boolean)
            - top_culprit_sensor (sensor with highest SCI)
            - top_culprit_sci_pct (percentage contribution)
            - top_culprit_residual (raw deviation from expected)
            - top_culprit_z_score (standard deviations of deviation)
        """
        if not self.is_trained:
            raise RuntimeError("CorrelationDigitalTwin must be fitted before score_telemetry().")

        z_scores_dict: Dict[str, np.ndarray] = {}
        raw_res_dict: Dict[str, np.ndarray] = {}

        for sensor, model in self.models.items():
            peers = self.peer_map[sensor]
            if sensor in data.columns and all(p in data.columns for p in peers):
                X = data[peers].ffill().fillna(0.0)
                y_pred = model.predict(X)
                y_actual = data[sensor].values
                raw_res = y_actual - y_pred
                mu = self.residual_means[sensor]
                sigma = self.residual_stds[sensor]
                z = (raw_res - mu) / sigma
                z_scores_dict[sensor] = z
                raw_res_dict[sensor] = raw_res

        if not z_scores_dict:
            return pd.DataFrame(index=data.index)

        z_df = pd.DataFrame(z_scores_dict, index=data.index)
        raw_res_df = pd.DataFrame(raw_res_dict, index=data.index)

        # Composite Anomaly Score: Squared Prediction Error (SPE)
        z_squared = z_df**2
        spe_series = z_squared.sum(axis=1)

        # Sensor Contribution Index (%)
        sci_df = z_squared.div(spe_series.replace(0, 1e-6), axis=0) * 100.0

        # Primary Culprit identification
        culprit_sensor = z_squared.idxmax(axis=1)

        # Extract culprit specific metrics per row
        culprit_sci = []
        culprit_raw = []
        culprit_z = []

        for idx, s_name in culprit_sensor.items():
            culprit_sci.append(sci_df.loc[idx, s_name] if pd.notna(s_name) else 0.0)
            culprit_raw.append(raw_res_df.loc[idx, s_name] if pd.notna(s_name) else 0.0)
            culprit_z.append(z_df.loc[idx, s_name] if pd.notna(s_name) else 0.0)

        is_anomaly = spe_series > self.system_anomaly_threshold

        scored_df = pd.DataFrame(
            {
                "composite_anomaly_score": spe_series,
                "is_anomaly": is_anomaly,
                "anomaly_flag": np.where(is_anomaly, -1, 1),
                "top_culprit_sensor": culprit_sensor,
                "top_culprit_sci_pct": culprit_sci,
                "top_culprit_residual": culprit_raw,
                "top_culprit_z_score": culprit_z,
            },
            index=data.index,
        )

        return scored_df

    def predict(self, feature_data: pd.DataFrame, **kwargs: Any) -> pd.DataFrame:
        """BasePredictor interface implementation: returns anomaly scoring dataframe."""
        return self.score_telemetry(feature_data)

    def evaluate(self, ground_truth: pd.DataFrame, predictions: pd.DataFrame) -> Dict[str, float]:
        """Compute summary anomaly statistics."""
        total = len(predictions)
        anomalies = int((predictions["anomaly_flag"] == -1).sum()) if "anomaly_flag" in predictions else 0
        ratio = round((anomalies / total) * 100.0, 2) if total > 0 else 0.0
        return {
            "total_points": total,
            "anomaly_count": anomalies,
            "anomaly_percentage": ratio,
            "system_anomaly_threshold": round(self.system_anomaly_threshold, 2),
            "modeled_sensors_count": len(self.models),
        }

    def diagnose_anomaly(
        self,
        data: pd.DataFrame,
        timestamp: Optional[Union[pd.Timestamp, str]] = None,
    ) -> Dict[str, Any]:
        """Generate a complete diagnostic Early Warning alert object for a specific timestamp.

        Parameters
        ----------
        data : pd.DataFrame
            Telemetry dataset containing the target timestamp.
        timestamp : Timestamp or str, optional
            Timestamp to diagnose. If None, diagnoses the last row of data.

        Returns
        -------
        dict
            Structured diagnostic early warning package.
        """
        if not self.is_trained:
            raise RuntimeError("Model must be trained before diagnosing anomalies.")

        scored = self.score_telemetry(data)
        if scored.empty:
            return {"status": "No data scored"}

        if timestamp is None:
            target_ts = data.index[-1]
        else:
            target_ts = pd.to_datetime(timestamp)
            if target_ts not in data.index:
                # Find closest timestamp
                target_ts = data.index[np.argmin(np.abs(data.index - target_ts))]

        row_scored = scored.loc[target_ts]
        culprit = row_scored["top_culprit_sensor"]
        culprit_tag = self.tag_name_map.get(culprit, culprit.split("\\")[-1])
        subsystem = self.subsystem_map.get(culprit, "Turbine Package")

        actual_val = float(data.loc[target_ts, culprit]) if culprit in data.columns else 0.0
        expected_df = self.predict_expected_values(data.loc[[target_ts]])
        expected_val = float(expected_df.loc[target_ts, culprit]) if culprit in expected_df.columns else actual_val
        residual = actual_val - expected_val
        z_score = float(row_scored["top_culprit_z_score"])
        sci_pct = float(row_scored["top_culprit_sci_pct"])
        anomaly_score = float(row_scored["composite_anomaly_score"])
        is_anom = bool(row_scored["is_anomaly"])

        # Collect Supporting Witness Sensors (Peers)
        peer_list = self.peer_map.get(culprit, [])
        witness_sensors = []
        for peer in peer_list:
            if peer in data.columns:
                val = data.loc[target_ts, peer]
                if pd.isna(val):
                    continue
                p_act = float(val)
                p_exp_val = expected_df.loc[target_ts, peer] if peer in expected_df.columns else p_act
                p_exp = float(p_exp_val) if not pd.isna(p_exp_val) else p_act
                p_res = p_act - p_exp
                p_sigma = self.residual_stds.get(peer, 1.0)
                p_z = p_res / p_sigma if p_sigma > 1e-6 else 0.0
                witness_sensors.append({
                    "sensor_path": peer,
                    "tag_name": self.tag_name_map.get(peer, peer.split("\\")[-1]),
                    "subsystem": self.subsystem_map.get(peer, "Unknown"),
                    "actual": round(p_act, 2),
                    "expected": round(p_exp, 2),
                    "residual": round(p_res, 2),
                    "z_score": round(p_z, 2),
                    "status": "NORMAL" if abs(p_z) < self.z_threshold else "DEVIATING",
                })

        # Diagnostic Fault Tree Logic
        diagnosis, recommended_actions, predicted_event, lead_time_hours = self._infer_root_cause(
            culprit=culprit,
            culprit_tag=culprit_tag,
            subsystem=subsystem,
            residual=residual,
            z_score=z_score,
            witness_sensors=witness_sensors,
        )

        alert_package = {
            "alert_id": f"ALT-{pd.to_datetime(target_ts).strftime('%Y%m%d-%H%M')}",
            "timestamp": str(target_ts),
            "asset_id": "GT-2420A",
            "is_anomaly": is_anom,
            "severity": "CRITICAL" if abs(z_score) >= 4.0 else ("HIGH" if is_anom else "NORMAL"),
            "health_score": round(max(0.0, 100.0 - (anomaly_score / self.system_anomaly_threshold) * 50.0), 1),
            "composite_anomaly_score": round(anomaly_score, 2),
            "system_threshold": round(self.system_anomaly_threshold, 2),
            "predicted_incident": predicted_event,
            "estimated_lead_time_hours": lead_time_hours,
            "culprit_sensor": {
                "sensor_path": culprit,
                "tag_name": culprit_tag,
                "subsystem": subsystem,
                "actual_value": round(actual_val, 2),
                "expected_digital_twin_value": round(expected_val, 2),
                "residual_deviation": round(residual, 2),
                "z_score": round(z_score, 2),
                "contribution_index_pct": round(sci_pct, 1),
            },
            "supporting_witness_sensors": witness_sensors,
            "root_cause_diagnosis": diagnosis,
            "prescribed_operator_actions": recommended_actions,
        }

        return alert_package

    def _infer_root_cause(
        self,
        culprit: str,
        culprit_tag: str,
        subsystem: str,
        residual: float,
        z_score: float,
        witness_sensors: List[Dict[str, Any]],
    ) -> Tuple[str, List[str], str, float]:
        """Match culprit and peer deviations against GT-2420A Diagnostic Fault Tree."""
        c_lower = (culprit + " " + culprit_tag).lower()

        # 1. Exhaust Temperature Spread / Combustion Flameout
        if "exhaust temperature" in c_lower or "tc" in c_lower:
            predicted_event = "Impending High Exhaust Temperature Spread Trip (TTXS_ALM)"
            lead_time = 24.0
            if residual < 0:
                diagnosis = (
                    f"Combustion chamber flame degradation or localized burner nozzle coking detected on '{culprit_tag}'. "
                    f"Thermocouple reads {abs(residual):.1f} deg C below expected cluster temperature."
                )
                actions = [
                    f"Check flame scanner UV intensity on the corresponding combustion can.",
                    f"Inspect thermocouple wiring terminal block for high resistance or cold junction drift.",
                    f"Plan fuel nozzle wash or inspection during next maintenance window.",
                ]
            else:
                diagnosis = (
                    f"Localized hot streak or combustion can over-firing detected on '{culprit_tag}'. "
                    f"Reads {residual:.1f} deg C above expected cluster baseline."
                )
                actions = [
                    f"Monitor exhaust temperature spread bar chart on DCS.",
                    f"Cross-check gas fuel distribution manifold pressures.",
                ]

        # 2. Journal & Thrust Bearings (Thermal / Lubrication)
        elif "bearing" in c_lower or "journal" in c_lower or "thrust" in c_lower:
            predicted_event = "Impending Bearing Babbitt Metal High-Temperature Trip (BT_HH)"
            lead_time = 48.0
            diagnosis = (
                f"Localized bearing babbitt metal overheating detected on '{culprit_tag}' (+{abs(residual):.1f} deg C residual). "
                f"Potential oil film breakdown or mechanical friction."
            )
            actions = [
                f"Inspect lube oil supply header pressure and filter differential pressure (DP).",
                f"Cross-check lube oil drain temperature for confirming evidence of fluid heating.",
                f"Monitor shaft radial vibration proximity probes for correlating rub or unbalance.",
            ]

        # 3. Vibration & Shaft Dynamics
        elif "vibration" in c_lower or "displacement" in c_lower or "probe" in c_lower:
            predicted_event = "Impending High Shaft Vibration Trip (VIB_HH) or Rotor Axial Excursion"
            lead_time = 12.0
            diagnosis = (
                f"Abnormal mechanical shaft vibration / displacement detected on '{culprit_tag}' ({z_score:+.1f} sigma excursion). "
                f"Indicates unbalance, coupling misalignment, or proximity probe looseness."
            )
            actions = [
                f"Verify proximitor probe DC gap voltage to rule out transducer loose mounting.",
                f"Check spectrum cascade plots for 1X (unbalance) vs 2X (misalignment) harmonic peaks.",
                f"Inspect compressor surge margin and inlet guide vane stability.",
            ]

        # 4. Anti-Surge & Compressor Process
        elif "surge" in c_lower or "valve" in c_lower:
            predicted_event = "Compressor Aerodynamic Surge Alert / Anti-Surge Actuator Fault"
            lead_time = 8.0
            diagnosis = (
                f"Anti-surge protection valve positioning divergence detected on '{culprit_tag}'. "
                f"Valve position failed to track expected governor nozzle loading curve."
            )
            actions = [
                f"Check instrument air pressure supply to anti-surge valve positioner.",
                f"Stroke actuator pilot valve to confirm smooth mechanical motion without stiction.",
                f"Verify compressor suction and discharge differential pressure transmitter calibration.",
            ]

        # 5. Fuel Gas & Hydraulic Governor Loop
        elif "fuel" in c_lower or "control oil" in c_lower or "pcd" in c_lower:
            predicted_event = "Fuel Gas Supply Regulation Instability / Hydraulic Servo Pressure Fault"
            lead_time = 18.0
            diagnosis = (
                f"Thermodynamic control loop mismatch detected on '{culprit_tag}'. "
                f"Fuel gas manifold regulation deviates from compressor discharge pressure (PCD)."
            )
            actions = [
                f"Inspect hydraulic power unit control oil pump pressure and servo valves.",
                f"Check fuel gas regulating valve position feedback and strainer differential.",
            ]

        # 6. Generic Physical Coupling Fallback
        else:
            predicted_event = f"Physical Parameter Anomaly on {subsystem}"
            lead_time = 36.0
            diagnosis = (
                f"Multivariate correlation breakdown detected on '{culprit_tag}' ({z_score:+.1f} sigma deviation). "
                f"Sensor has diverged from its historical physical cluster."
            )
            actions = [
                f"Verify physical instrument wiring, transmitter range, and calibration.",
                f"Review operational log sheets for recent process transitions or setpoint changes.",
            ]

        return diagnosis, actions, predicted_event, lead_time

    def generate_early_warnings(
        self,
        data: pd.DataFrame,
        lookback_steps: int = 24,
        min_consecutive_anomalies: int = 2,
    ) -> List[Dict[str, Any]]:
        """Scan recent telemetry window and extract validated Early Warning alerts."""
        if not self.is_trained:
            raise RuntimeError("Model must be trained before generating early warnings.")

        scored = self.score_telemetry(data.tail(lookback_steps))
        if scored.empty:
            return []

        anom_mask = scored["is_anomaly"].values
        alerts: List[Dict[str, Any]] = []

        # Find anomaly clusters
        streak = 0
        for i, is_anom in enumerate(anom_mask):
            if is_anom:
                streak += 1
                if streak >= min_consecutive_anomalies:
                    ts = scored.index[i]
                    alert = self.diagnose_anomaly(data, timestamp=ts)
                    alerts.append(alert)
                    # Reset streak to avoid duplicate alerts within the same run
                    streak = 0
            else:
                streak = 0

        return alerts

    def save_model(self, file_path: Union[str, Path]) -> None:
        """Persist calibrated digital twin model state to disk."""
        path = Path(file_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "top_n_peers": self.top_n_peers,
            "min_correlation": self.min_correlation,
            "alpha": self.alpha,
            "z_threshold": self.z_threshold,
            "system_anomaly_threshold": self.system_anomaly_threshold,
            "models": self.models,
            "peer_map": self.peer_map,
            "residual_means": self.residual_means,
            "residual_stds": self.residual_stds,
            "subsystem_map": self.subsystem_map,
            "category_map": self.category_map,
            "tag_name_map": self.tag_name_map,
            "is_trained": self.is_trained,
        }
        with open(path, "wb") as f:
            pickle.dump(payload, f)
        logger.info(f"Saved CorrelationDigitalTwin model to {path}")

    @classmethod
    def load_model(cls, file_path: Union[str, Path]) -> CorrelationDigitalTwin:
        """Load calibrated model state from disk."""
        path = Path(file_path)
        with open(path, "rb") as f:
            payload = pickle.load(f)

        instance = cls(
            top_n_peers=payload.get("top_n_peers", 5),
            min_correlation=payload.get("min_correlation", 0.65),
            alpha=payload.get("alpha", 1.0),
            z_threshold=payload.get("z_threshold", 3.0),
        )
        instance.system_anomaly_threshold = payload.get("system_anomaly_threshold", 15.0)
        instance.models = payload.get("models", {})
        instance.peer_map = payload.get("peer_map", {})
        instance.residual_means = payload.get("residual_means", {})
        instance.residual_stds = payload.get("residual_stds", {})
        instance.subsystem_map = payload.get("subsystem_map", {})
        instance.category_map = payload.get("category_map", {})
        instance.tag_name_map = payload.get("tag_name_map", {})
        instance.is_trained = payload.get("is_trained", False)
        logger.info(f"Loaded CorrelationDigitalTwin ({len(instance.models)} estimators) from {path}")
        return instance
