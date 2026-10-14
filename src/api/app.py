"""FastAPI REST Service for Module 3: CorrelationDigitalTwin & Early Warning Advisory.

Serves live predictive failure diagnostics, health indices, and advisory card payloads
to OSIsoft PI Vision custom symbols and enterprise dashboards.
"""

from __future__ import annotations

import datetime as dt
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

import numpy as np
import pandas as pd
from fastapi import FastAPI, HTTPException, Query, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel, Field

from src.config_manager import ConfigManager
from src.module3_prediction.correlation_digital_twin import CorrelationDigitalTwin
from src.utils.logger import get_logger

logger = get_logger("PredictiveAPI")

# Global singleton digital twin model
twin_model: Optional[CorrelationDigitalTwin] = None
config_manager: Optional[ConfigManager] = None
telemetry_cache: Optional[pd.DataFrame] = None
cache_last_mtime: float = 0.0


def _get_latest_telemetry() -> pd.DataFrame:
    """Retrieve telemetry dataframe, automatically reloading from Parquet if modified on disk."""
    global telemetry_cache, cache_last_mtime, config_manager
    if config_manager is None:
        config_manager = ConfigManager()
    data_path = config_manager.get_telemetry_path()
    if data_path.exists():
        try:
            current_mtime = data_path.stat().st_mtime
            if current_mtime > cache_last_mtime or telemetry_cache is None:
                if str(data_path).lower().endswith(".parquet"):
                    telemetry_cache = pd.read_parquet(data_path)
                else:
                    import pickle
                    with open(data_path, "rb") as f:
                        telemetry_cache = pickle.load(f)
                cache_last_mtime = current_mtime
                logger.info(f"Refreshed telemetry cache from disk ({telemetry_cache.shape[0]:,} rows).")
        except Exception as e:
            logger.warning(f"Failed to check/reload telemetry cache: {e}")
    return telemetry_cache


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifecycle manager: initialize digital twin model and cached baseline on startup."""
    global twin_model, config_manager, telemetry_cache
    logger.info("Initializing PTTEP GT-2420A Predictive Anomaly API...")

    config_manager = ConfigManager()
    sensors = config_manager.load_sensors()
    model_path = Path("models/gt2420a_digital_twin.pkl")

    # Load pre-trained model if available
    if model_path.exists():
        logger.info(f"Loading pre-calibrated model from {model_path}...")
        twin_model = CorrelationDigitalTwin.load_model(model_path)
        if sensors and not twin_model.tag_name_map:
            twin_model._build_sensor_lookup_maps(sensors)
    else:
        logger.info("Pre-calibrated model not found. Calibrating digital twin from baseline telemetry...")
        data_path = config_manager.get_telemetry_path()
        if data_path.exists():
            if str(data_path).lower().endswith(".parquet"):
                df = pd.read_parquet(data_path)
            else:
                import pickle
                with open(data_path, "rb") as f:
                    df = pickle.load(f)
            
            corr_csv_path = config_manager.resolve_path("data/correlation_matrix.csv")
            corr_df = pd.read_csv(corr_csv_path, index_col=0) if corr_csv_path.exists() else None

            twin_model = CorrelationDigitalTwin(
                top_n_peers=5,
                min_correlation=0.65,
                sensor_catalog=sensors,
            )
            twin_model.fit(df, correlation_matrix=corr_df)
            twin_model.save_model(model_path)
            logger.info(f"Calibrated and saved model to {model_path}")
        else:
            logger.warning(f"Telemetry cache {data_path} not found. Digital twin is uncalibrated.")

    # Cache recent telemetry for zero-latency /advisory/latest responses
    data_path = config_manager.get_telemetry_path()
    if data_path.exists():
        if str(data_path).lower().endswith(".parquet"):
            telemetry_cache = pd.read_parquet(data_path)
        else:
            import pickle
            with open(data_path, "rb") as f:
                telemetry_cache = pickle.load(f)
        logger.info(f"Loaded telemetry cache: {telemetry_cache.shape[0]:,} rows × {telemetry_cache.shape[1]} sensors.")

    yield

    logger.info("Shutting down Predictive Anomaly API.")


app = FastAPI(
    title="PTTEP GT-2420A Predictive Digital Twin API",
    description=(
        "Production REST service serving Module 3 Many-to-Many virtual sensing anomaly detection, "
        "Sensor Contribution Index (SCI) attribution, and Diagnostic Early Warning Advisories "
        "to OSIsoft PI Vision custom symbols."
    ),
    version="1.0.0",
    lifespan=lifespan,
)

# Enable Cross-Origin Resource Sharing (CORS) for PI Vision Server
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allows PI Vision server on any domain/port
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ============================================================================
# Pydantic Request / Response Models
# ============================================================================

class TelemetrySnapshot(BaseModel):
    """Single concurrent telemetry snapshot across sensors."""
    timestamp: Optional[str] = Field(None, description="ISO timestamp of telemetry reading")
    sensors: Dict[str, float] = Field(
        ...,
        description="Key-value mapping of sensor AF paths or tag names to live numeric readings",
    )


class TimeSeriesWindow(BaseModel):
    """Historical time-series window for robust multi-point scoring."""
    lookback_points: int = Field(24, ge=1, le=240, description="Number of points in window")
    timestamps: List[str] = Field(..., description="List of ISO timestamp strings")
    data: Dict[str, List[float]] = Field(
        ...,
        description="Mapping of sensor AF path/name to array of sequential readings",
    )


class FaultSimulationRequest(BaseModel):
    """Request to inject synthetic degradation for PI Vision testing."""
    fault_type: str = Field(
        "combustion",
        description="Failure mode to simulate: 'combustion' (nozzle coking) or 'bearing' (babbitt heating)",
    )
    severity_pct: float = Field(
        100.0,
        ge=10.0,
        le=300.0,
        description="Fault magnitude scaling percentage",
    )


# ============================================================================
# API Endpoints
# ============================================================================

@app.get("/health", tags=["System"])
@app.get("/api/v1/health", tags=["System"])
def get_health() -> Dict[str, Any]:
    """Check API operational status, loaded model parameters, and threshold."""
    if twin_model is None or not twin_model.is_trained:
        return {
            "status": "INITIALIZING",
            "asset_id": "GT-2420A",
            "model": "CorrelationDigitalTwin",
            "is_trained": False,
        }

    return {
        "status": "HEALTHY",
        "asset_id": "GT-2420A",
        "model": "CorrelationDigitalTwin",
        "is_trained": True,
        "modeled_sensors_count": len(twin_model.models),
        "system_anomaly_threshold": round(twin_model.system_anomaly_threshold, 2),
        "min_correlation_cutoff": twin_model.min_correlation,
        "top_peers_per_cluster": twin_model.top_n_peers,
        "server_time_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
    }


@app.get("/api/v1/sensors", tags=["Metadata"])
def get_sensor_catalog() -> Dict[str, Any]:
    """Return all modeled sensors, their subsystems, categories, and assigned peer clusters."""
    if twin_model is None or not twin_model.is_trained:
        raise HTTPException(status_code=503, detail="Model is not yet initialized.")

    catalog = []
    for sensor, peers in twin_model.peer_map.items():
        clean_name = twin_model.tag_name_map.get(sensor, sensor.split("\\")[-1])
        subsystem = twin_model.subsystem_map.get(sensor, "General")
        category = twin_model.category_map.get(sensor, "General")
        catalog.append({
            "sensor_path": sensor,
            "tag_name": clean_name,
            "subsystem": subsystem,
            "category": category,
            "peer_count": len(peers),
            "peer_sensors": [twin_model.tag_name_map.get(p, p.split("\\")[-1]) for p in peers],
        })

    return {
        "asset_id": "GT-2420A",
        "total_sensors": len(catalog),
        "sensors": catalog,
    }


@app.get("/api/v1/advisory/latest", tags=["Early Warning"])
def get_latest_advisory(
    lookback: int = Query(24, ge=1, le=120, description="Telemetry points in evaluation window"),
    simulate_fault: Optional[str] = Query(
        None,
        pattern="^(none|combustion|bearing)$",
        description="Inject synthetic fault to preview PI Vision advisory alert card",
    ),
) -> Dict[str, Any]:
    """Provide the latest Early Warning Advisory card payload for PI Vision custom symbols.
    
    Reads the latest active operational telemetry from the server cache, evaluates
    multivariate correlation integrity, and formats the response for PI Vision.
    """
    if twin_model is None or not twin_model.is_trained:
        raise HTTPException(status_code=503, detail="Digital twin model is not loaded.")
    
    # Fast path: If pre-computed advisory exists from 5-min scheduled runner and no simulation requested
    advisory_file = Path("data/latest_advisory.json")
    if simulate_fault is None and advisory_file.exists():
        try:
            import json
            with open(advisory_file, "r", encoding="utf-8") as f:
                saved_alert = json.load(f)
            if "alert_id" in saved_alert:
                return saved_alert
        except Exception as e:
            logger.warning(f"Failed to read pre-computed advisory: {e}")

    df_cache = _get_latest_telemetry()
    if df_cache is None or df_cache.empty:
        raise HTTPException(status_code=503, detail="Telemetry cache is empty.")

    # Find the latest active base-load operating window
    numeric_df = df_cache.select_dtypes(include=[np.number])
    running_mask = (numeric_df > 10.0).sum(axis=1) > (len(numeric_df.columns) * 0.3)
    
    if running_mask.any():
        last_running_ts = df_cache[running_mask].index[-1]
        eval_window = df_cache.loc[:last_running_ts].tail(lookback).copy()
    else:
        eval_window = df_cache.tail(lookback).copy()

    # Apply synthetic fault if requested
    if simulate_fault == "combustion":
        tc_cols = [c for c in eval_window.columns if "exhaust temperature 8" in c.lower()]
        if tc_cols:
            target_col = tc_cols[0]
            vals = eval_window[target_col].to_numpy().copy()
            vals[-min(10, len(vals)):] -= np.linspace(15, 65, min(10, len(vals)))
            eval_window[target_col] = vals
    elif simulate_fault == "bearing":
        b_cols = [c for c in eval_window.columns if "journal bearing" in c.lower() and "temperature" in c.lower()]
        if b_cols:
            target_col = b_cols[0]
            vals = eval_window[target_col].to_numpy().copy()
            vals[-min(10, len(vals)):] += np.linspace(8, 25, min(10, len(vals)))
            eval_window[target_col] = vals

    # Score telemetry window and generate advisory
    alert = twin_model.diagnose_anomaly(eval_window, timestamp=eval_window.index[-1])
    return alert


@app.post("/api/v1/sync", tags=["Ingestion & Prediction"])
def sync_telemetry_and_predict(
    save_parquet: bool = Query(True, description="Persist incoming points to Apache Parquet"),
    sync_hours: int = Query(2, ge=1, le=48, description="Time window in hours to pull from PI Web API"),
) -> Dict[str, Any]:
    """Ingest latest telemetry from PI Web API, append to Parquet, and perform prediction simultaneously.
    
    1. Ingestion: Queries PI Web API for the latest sensor readings across all 158 channels.
    2. Storage: Appends and deduplicates new records into data/historical_data.parquet.
    3. Prediction: Evaluates the updated sliding window through CorrelationDigitalTwin and returns the advisory.
    """
    global telemetry_cache, twin_model, config_manager
    if twin_model is None or not twin_model.is_trained:
        raise HTTPException(status_code=503, detail="Digital twin model is not initialized.")

    from src.module1_pi_ingestion.pi_client import PIWebApiClient
    cfg = config_manager.load_config()
    sensors = config_manager.load_sensors()
    pi_client = PIWebApiClient(cfg, sensors)

    end_time = dt.datetime.now().replace(microsecond=0)
    start_time = end_time - dt.timedelta(hours=sync_hours)
    storage_path = config_manager.get_telemetry_path() if save_parquet else None

    logger.info(f"Syncing telemetry from PI Web API ({start_time} to {end_time})...")
    new_df = pi_client.pull_data(
        mode="test",
        custom_start=start_time,
        custom_end=end_time,
        custom_interval="5m",
        save_storage=save_parquet,
        storage_path=storage_path,
        resume=True,
    )

    if new_df.empty:
        raise HTTPException(status_code=502, detail="No telemetry returned from PI Web API.")

    # Update in-memory cache
    if telemetry_cache is not None and not telemetry_cache.empty:
        combined = pd.concat([telemetry_cache, new_df])
        telemetry_cache = combined[~combined.index.duplicated(keep="last")].sort_index()
    else:
        telemetry_cache = new_df

    # Run immediate prediction on latest window
    eval_window = telemetry_cache.tail(24)
    alert = twin_model.diagnose_anomaly(eval_window, timestamp=eval_window.index[-1])

    return {
        "status": "SYNCED_AND_EVALUATED",
        "ingested_points": len(new_df),
        "total_records": len(telemetry_cache),
        "parquet_persisted": save_parquet,
        "latest_timestamp": str(eval_window.index[-1]),
        "advisory": alert,
    }


@app.post("/api/v1/diagnose", tags=["Early Warning"])
def diagnose_telemetry(payload: Union[TelemetrySnapshot, TimeSeriesWindow]) -> Dict[str, Any]:
    """Score incoming live telemetry supplied directly by PI Vision or external callers.
    
    Accepts either a single concurrent snapshot (1 value per sensor) or a sequential
    time-series window (12 to 24 points per sensor) for transient spike filtering.
    """
    if twin_model is None or not twin_model.is_trained:
        raise HTTPException(status_code=503, detail="Digital twin model is not initialized.")

    if isinstance(payload, TelemetrySnapshot):
        # 1-point concurrent snapshot
        ts = pd.to_datetime(payload.timestamp) if payload.timestamp else pd.Timestamp.now(tz="UTC")
        row_dict = payload.sensors
        df = pd.DataFrame([row_dict], index=[ts])
    else:
        # Time-series window
        timestamps = [pd.to_datetime(t) for t in payload.timestamps]
        df = pd.DataFrame(payload.data, index=timestamps)

    # Match sensors by exact path or by tag name fallback
    matched_cols = {}
    for col in df.columns:
        if col in twin_model.models:
            matched_cols[col] = col
        else:
            # Match by tag name suffix
            for m_path in twin_model.models:
                m_tag = twin_model.tag_name_map.get(m_path, m_path.split("\\")[-1])
                if col.lower() == m_tag.lower():
                    matched_cols[col] = m_path
                    break

    df_renamed = df.rename(columns=matched_cols)
    if df_renamed.empty:
        raise HTTPException(status_code=400, detail="Provided sensor payload could not be mapped to modeled channels.")

    alert = twin_model.diagnose_anomaly(df_renamed, timestamp=df_renamed.index[-1])
    return alert


@app.post("/api/v1/simulate", tags=["Testing"])
def simulate_fault(request: FaultSimulationRequest) -> Dict[str, Any]:
    """Test endpoint for PI Vision developers to verify advisory card rendering in alarm states."""
    return get_latest_advisory(lookback=24, simulate_fault=request.fault_type)


@app.get("/api/v1/card-html", response_class=HTMLResponse, tags=["Visualization"])
def render_advisory_html_card(
    simulate: Optional[str] = Query(None, pattern="^(none|combustion|bearing)$")
) -> str:
    """Pre-rendered standalone HTML advisory card for direct embedding in PI Vision or iframes."""
    alert = get_latest_advisory(lookback=24, simulate_fault=simulate)
    
    severity = alert.get("severity", "NORMAL")
    badge_color = "#10b981" if severity == "NORMAL" else ("#f59e0b" if severity == "HIGH" else "#ef4444")
    health = alert.get("health_score", 100.0)
    incident = alert.get("predicted_incident", "Nominal Steady-State Operation")
    lead_time = alert.get("estimated_lead_time_hours", 0.0)
    diagnosis = alert.get("root_cause_diagnosis", "All parameters operating within expected physical clusters.")
    culprit = alert.get("culprit_sensor", {})
    witnesses = alert.get("supporting_witness_sensors", [])[:4]
    actions = alert.get("prescribed_operator_actions", ["Continue normal operational rounds."])

    witness_rows = ""
    for w in witnesses:
        status_color = "#ef4444" if w.get("status") == "DEVIATING" else "#10b981"
        witness_rows += f"""
        <tr>
            <td style="padding: 6px; border-bottom: 1px solid #334155;">{w.get('tag_name')}</td>
            <td style="padding: 6px; border-bottom: 1px solid #334155; text-align: right;">{w.get('actual')}</td>
            <td style="padding: 6px; border-bottom: 1px solid #334155; text-align: right;">{w.get('expected')}</td>
            <td style="padding: 6px; border-bottom: 1px solid #334155; text-align: right; color: {status_color}; font-weight: bold;">{w.get('residual'):+0.2f}</td>
            <td style="padding: 6px; border-bottom: 1px solid #334155; text-align: center;"><span style="color: {status_color}; font-weight: bold;">{w.get('status')}</span></td>
        </tr>
        """

    action_items = "".join(f"<li style='margin-bottom: 6px;'>{a}</li>" for a in actions)

    html = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="utf-8">
        <style>
            body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; background: #0f172a; color: #f8fafc; margin: 0; padding: 16px; }}
            .card {{ background: #1e293b; border-radius: 10px; border: 1px solid #334155; padding: 20px; box-shadow: 0 10px 25px -5px rgba(0,0,0,0.5); max-width: 720px; }}
            .header {{ display: flex; justify-content: space-between; align-items: center; border-bottom: 1px solid #334155; padding-bottom: 12px; margin-bottom: 16px; }}
            .badge {{ background: {badge_color}; color: #ffffff; padding: 4px 12px; border-radius: 9999px; font-size: 12px; font-weight: bold; letter-spacing: 0.5px; }}
            .score-box {{ display: flex; gap: 16px; margin-bottom: 16px; }}
            .metric {{ background: #0f172a; border: 1px solid #334155; border-radius: 8px; padding: 12px; flex: 1; text-align: center; }}
            .metric-val {{ font-size: 24px; font-weight: bold; color: {badge_color}; }}
            .section-title {{ font-size: 14px; text-transform: uppercase; letter-spacing: 1px; color: #94a3b8; margin-top: 16px; margin-bottom: 8px; font-weight: 600; }}
            .culprit-box {{ background: #0f172a; border-left: 4px solid {badge_color}; padding: 12px; border-radius: 4px; margin-bottom: 12px; font-size: 13px; }}
            table {{ width: 100%; border-collapse: collapse; font-size: 12px; }}
            th {{ background: #0f172a; padding: 6px; text-align: left; color: #94a3b8; border-bottom: 1px solid #475569; }}
            ul {{ margin: 0; padding-left: 20px; font-size: 13px; color: #cbd5e1; }}
        </style>
    </head>
    <body>
        <div class="card">
            <div class="header">
                <div>
                    <span style="font-size: 18px; font-weight: bold; color: #38bdf8;">PTTEP GT-2420A DIGITAL TWIN</span>
                    <div style="font-size: 11px; color: #94a3b8;">Alert ID: {alert.get('alert_id')} | {alert.get('timestamp')}</div>
                </div>
                <div class="badge">{severity}</div>
            </div>

            <div class="score-box">
                <div class="metric">
                    <div style="font-size: 11px; color: #94a3b8;">TURBINE HEALTH SCORE</div>
                    <div class="metric-val">{health:.1f} / 100</div>
                </div>
                <div class="metric">
                    <div style="font-size: 11px; color: #94a3b8;">ANOMALY SCORE (SPE)</div>
                    <div class="metric-val">{alert.get('composite_anomaly_score', 0):.1f}</div>
                    <div style="font-size: 10px; color: #64748b;">Threshold: {alert.get('system_threshold', 0):.1f}</div>
                </div>
                <div class="metric">
                    <div style="font-size: 11px; color: #94a3b8;">PREDICTED LEAD TIME</div>
                    <div class="metric-val" style="color: #38bdf8;">~{lead_time:.0f} Hours</div>
                </div>
            </div>

            <div class="section-title">1. What Is About to Happen</div>
            <div style="font-size: 14px; font-weight: bold; color: #f1f5f9; margin-bottom: 4px;">{incident}</div>
            <div style="font-size: 13px; color: #cbd5e1; line-height: 1.4;">{diagnosis}</div>

            <div class="section-title">2. Sensor Evidence & Fault Contribution</div>
            <div class="culprit-box">
                <b>Primary Culprit Sensor:</b> {culprit.get('tag_name')} ({culprit.get('subsystem')})<br>
                <b>Live Telemetry:</b> {culprit.get('actual_value')} | <b>Expected Twin Value:</b> {culprit.get('expected_digital_twin_value')} | <b>Residual:</b> {culprit.get('residual_deviation'):+0.2f} ({culprit.get('z_score'):+0.1f} &sigma;)<br>
                <b>Fault Contribution (SCI):</b> <span style="color: {badge_color}; font-weight: bold;">{culprit.get('contribution_index_pct')}% of total turbine anomaly error</span>
            </div>

            <div style="font-size: 12px; font-weight: 600; color: #94a3b8; margin-bottom: 6px;">Correlating Physical Peer Witnesses:</div>
            <table>
                <thead>
                    <tr>
                        <th>Witness Sensor</th>
                        <th style="text-align: right;">Live</th>
                        <th style="text-align: right;">Expected</th>
                        <th style="text-align: right;">Residual</th>
                        <th style="text-align: center;">Status</th>
                    </tr>
                </thead>
                <tbody>
                    {witness_rows}
                </tbody>
            </table>

            <div class="section-title">3. Prescribed Operator Actions</div>
            <ul>
                {action_items}
            </ul>
        </div>
    </body>
    </html>
    """
    return html
