"""Streamlit Web Application for PTTEP GT-2420A Analytics.
Provides interactive Dashboard, Module 1 Execution & Limits Viewer,
Module 2 Correlation Heatmap, Module 3 Prediction Preview, and Settings Management.
"""

from __future__ import annotations

import datetime as dt
import json
from pathlib import Path
from typing import Any, Dict, List, Optional
import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from src.config_manager import ConfigManager
from src.module1_pi_ingestion.pipeline import Module1Pipeline
from src.module1_pi_ingestion.sql_storage import SQLStorageManager
from src.module2_correlation.correlation_engine import CorrelationEngine
from src.module2_correlation.clustering import SensorClusterer
from src.module3_prediction.anomaly_detector import SensorAnomalyDetector
from src.module3_prediction.forecast_stub import SensorForecastStub

st.set_page_config(
    page_title="PTTEP PI Analytics | GT-2420A",
    page_icon="⚡",
    layout="wide",
    initial_sidebar_state="expanded",
)


@st.cache_resource
def get_config_manager() -> ConfigManager:
    return ConfigManager()


cm = get_config_manager()
config = cm.load_config()
sensors = cm.load_sensors()
meta = cm.load_last_run_meta()
sql_storage = SQLStorageManager(config)

# Sidebar
st.sidebar.image("https://upload.wikimedia.org/wikipedia/commons/thumb/c/c8/PTTEP_Logo.svg/1200px-PTTEP_Logo.svg.png", width=180)
st.sidebar.title("GT-2420A Analytics")
st.sidebar.markdown("**Asset:** `MALAYSIA\\BORF\\GTG\\GT-2420A`")

page = st.sidebar.radio(
    "Navigation",
    ["📊 Dashboard", "⚡ Module 1: Ingestion & Limits", "🔬 Module 2: Correlation Engine", "🔮 Module 3: Prediction Engine", "⚙️ Settings"],
)

st.sidebar.markdown("---")
mock_active = config.get("pi_web_api", {}).get("mock_mode", True)
if mock_active:
    st.sidebar.info("🛡️ **Mode:** SIMULATION (Offline Safe)\n\nLive PI network calls disabled during development.")
else:
    st.sidebar.warning("🌐 **Mode:** LIVE PI SERVER\n\nTargeting `kul-pivision.pttep.com`")

st.sidebar.caption(f"DB Engine: `{sql_storage.active_backend.upper()}` | Tags: `{len(sensors)}`")


# ==========================================
# PAGE 1: DASHBOARD
# ==========================================
if page == "📊 Dashboard":
    st.title("📊 Operating Dashboard: GT-2420A Telemetry & Limits")
    st.markdown("Real-time summary of historical PI ingestion, execution metrics, and statistical operating parameters (**Normal, HH, H, L, LL**).")

    # Metric Cards Row
    col1, col2, col3, col4, col5 = st.columns(5)
    with col1:
        last_pull = meta.get("last_pull_timestamp")
        st.metric("Last Data Pull", str(last_pull) if last_pull else "Never")
    with col2:
        duration = meta.get("duration_seconds", 0.0)
        st.metric("Time Taken (Duration)", f"{duration:.2f} s")
    with col3:
        mode_str = meta.get("pull_mode", "N/A")
        st.metric("Pull Mode", mode_str)
    with col4:
        limits_count = meta.get("limits_calculated", 0)
        st.metric("Operating Limits Set", f"{limits_count:,}")
    with col5:
        inserted = meta.get("sql_inserted", 0)
        skipped = meta.get("sql_skipped", 0)
        st.metric("SQL Inserts / Skipped", f"{inserted} / {skipped}")

    st.markdown("---")

    # Load Telemetry (Parquet with fallback to Pickle)
    data_path = cm.get_telemetry_path()
    df_telemetry = None
    if data_path.exists():
        try:
            if str(data_path).lower().endswith(".parquet"):
                df_telemetry = pd.read_parquet(data_path, engine="pyarrow")
            else:
                import pickle
                with open(data_path, "rb") as f:
                    df_telemetry = pickle.load(f)
        except Exception:
            df_telemetry = None

    # Load Limits from SQL
    pivot_limits = sql_storage.fetch_current_limits_pivot()

    tab_limits, tab_chart = st.tabs(["📋 Operating Limits (HH / H / Normal / L / LL)", "📈 Sensor Trend & Limit Bounds"])

    with tab_limits:
        if pivot_limits.empty:
            st.info("No operating limits currently in SQL table. Head over to **Module 1: Ingestion & Limits** to trigger your first run!")
        else:
            # Filters
            f_col1, f_col2, f_col3 = st.columns([2, 2, 1])
            with f_col1:
                subsystems = ["All"] + sorted(list({s.get("subsystem", "Unknown") for s in sensors}))
                selected_subsys = st.selectbox("Filter by Subsystem", subsystems)
            with f_col2:
                search_query = st.text_input("Search Tag Name / Path", "")
            with f_col3:
                st.markdown("<div style='height:28px'></div>", unsafe_allow_html=True)
                csv = pivot_limits.to_csv(index=False)
                st.download_button("📥 Export CSV", csv, "gt2420a_operating_limits.csv", "text/csv")

            filtered_df = pivot_limits.copy()
            if selected_subsys != "All":
                filtered_df = filtered_df[filtered_df["af_path"].str.contains(selected_subsys, case=False, na=False)]
            if search_query:
                filtered_df = filtered_df[filtered_df["af_path"].str.contains(search_query, case=False, na=False)]

            # Clean Display Names
            display_df = filtered_df.copy()
            display_df["Short Name"] = display_df["af_path"].apply(lambda p: p.split("\\")[-1])
            display_df["Subsystem"] = display_df["af_path"].apply(lambda p: p.split("\\")[4] if len(p.split("\\")) >= 5 else "General")

            order_cols = ["Subsystem", "Short Name", "LL", "L", "Normal", "H", "HH", "af_path"]
            final_cols = [c for c in order_cols if c in display_df.columns]
            st.dataframe(
                display_df[final_cols].style.format({
                    "LL": "{:.3f}",
                    "L": "{:.3f}",
                    "Normal": "{:.3f}",
                    "H": "{:.3f}",
                    "HH": "{:.3f}",
                }),
                use_container_width=True,
                height=450,
            )
            st.caption(f"Showing {len(display_df)} of {len(pivot_limits)} configured operating thresholds stored in `{sql_storage.table_name}`.")

    with tab_chart:
        if df_telemetry is None or df_telemetry.empty:
            st.info("Telemetry data not yet cached. Run Module 1 to populate.")
        else:
            all_cols = list(df_telemetry.columns)
            selected_sensor = st.selectbox("Select Sensor to Inspect", all_cols, index=0)

            # Get limits for this sensor if available
            sensor_limits = {}
            if not pivot_limits.empty:
                match = pivot_limits[pivot_limits["af_path"] == selected_sensor]
                if not match.empty:
                    sensor_limits = match.iloc[0].to_dict()

            series = df_telemetry[selected_sensor].dropna()
            fig = go.Figure()

            # Raw trend
            fig.add_trace(go.Scatter(x=series.index, y=series.values, mode="lines", name="Telemetry Value", line=dict(color="#29b5e8", width=1.8)))

            # Limit horizontal lines
            if "HH" in sensor_limits and pd.notna(sensor_limits["HH"]):
                fig.add_hline(y=sensor_limits["HH"], line_dash="dash", line_color="red", annotation_text=f"HH ({sensor_limits['HH']:.2f})")
            if "H" in sensor_limits and pd.notna(sensor_limits["H"]):
                fig.add_hline(y=sensor_limits["H"], line_dash="dot", line_color="orange", annotation_text=f"H ({sensor_limits['H']:.2f})")
            if "Normal" in sensor_limits and pd.notna(sensor_limits["Normal"]):
                fig.add_hline(y=sensor_limits["Normal"], line_dash="solid", line_color="green", annotation_text=f"Normal ({sensor_limits['Normal']:.2f})")
            if "L" in sensor_limits and pd.notna(sensor_limits["L"]):
                fig.add_hline(y=sensor_limits["L"], line_dash="dot", line_color="orange", annotation_text=f"L ({sensor_limits['L']:.2f})")
            if "LL" in sensor_limits and pd.notna(sensor_limits["LL"]):
                fig.add_hline(y=sensor_limits["LL"], line_dash="dash", line_color="red", annotation_text=f"LL ({sensor_limits['LL']:.2f})")

            fig.update_layout(
                title=f"Historical Telemetry & Operating Limits: {selected_sensor.split('\\')[-1]}",
                xaxis_title="Timestamp",
                yaxis_title="Measurement",
                height=480,
                hovermode="x unified",
                template="plotly_dark",
            )
            st.plotly_chart(fig, use_container_width=True)


# ==========================================
# PAGE 2: MODULE 1 (INGESTION & LIMITS)
# ==========================================
elif page == "⚡ Module 1: Ingestion & Limits":
    st.title("⚡ Module 1: PI Telemetry Ingestion & Statistical Limits Engine")
    st.markdown("""
    This module extracts historical time-series data from PI Web API, serializes the dataset into local pickle storage,
    computes the 5 statistical operating thresholds (**Normal, HH, H, L, LL**), and synchronizes them into the SQL database
    using change-detection deduplication.
    """)

    col_ctrl, col_info = st.columns([1, 1])

    with col_ctrl:
        st.subheader("Run Telemetry Ingestion")
        st.markdown(f"**Target System:** `MALAYSIA\\BORF\\GTG\\GT-2420A` ({len(sensors)} sensor attributes)")

        # Sampling Interval Selector
        interval_opts = ["1m", "5m", "10m", "15m", "30m", "1h"]
        cfg_int = config.get("pi_web_api", {}).get("sample_interval", "1h")
        init_idx = interval_opts.index(cfg_int) if cfg_int in interval_opts else 5
        sel_interval = st.selectbox(
            "⏱️ Telemetry Sampling Interval:",
            interval_opts,
            index=init_idx,
            help="For minute-level sampling (1m, 5m, etc.), multi-hour ranges are automatically split hour-by-hour between start and stop."
        )

        is_minute_sel = sel_interval.endswith("m") and not sel_interval.endswith("mo")

        mode_choice = st.radio(
            "Select Execution Scope & Time Range:",
            [
                "🧪 1-Day Test Run (Last 24 Hours)",
                "⏱️ Specific Hourly Window (Choose Date & Hour range)",
                "📅 12-Month Full Ingestion (Complete historical training)",
                "🗓️ Custom Date & Time Range",
            ],
            index=0,
        )

        custom_start = None
        custom_end = None
        exec_mode = "test"

        if mode_choice == "⏱️ Specific Hourly Window (Choose Date & Hour range)":
            h_date = st.date_input("Target Date:", value=dt.date.today() - dt.timedelta(days=1))
            h_start, h_end = st.slider("Select Hour Range (Between Hours):", 0, 24, (8, 9), step=1)
            if h_start >= h_end:
                st.error("Stop hour must be greater than start hour.")
                h_end = min(24, h_start + 1)
            custom_start = dt.datetime.combine(h_date, dt.time(h_start if h_start < 24 else 23, 59 if h_start == 24 else 0))
            custom_end = dt.datetime.combine(h_date, dt.time(h_end if h_end < 24 else 23, 59 if h_end == 24 else 0)) if h_end < 24 else dt.datetime.combine(h_date + dt.timedelta(days=1), dt.time(0, 0))
            hours_count = max(1, h_end - h_start)
            st.info(f"📅 Range: `{custom_start.strftime('%Y-%m-%d %H:%M')}` to `{custom_end.strftime('%Y-%m-%d %H:%M')}` ({hours_count} hr{'s' if hours_count > 1 else ''}). Minute data will be fetched in {hours_count} hourly slice{'s' if hours_count > 1 else ''}.")

        elif mode_choice == "🗓️ Custom Date & Time Range":
            c_col1, c_col2 = st.columns(2)
            with c_col1:
                start_d = st.date_input("Start Date:", value=dt.date.today() - dt.timedelta(days=1))
                start_t = st.time_input("Start Time:", value=dt.time(0, 0))
                custom_start = dt.datetime.combine(start_d, start_t)
            with c_col2:
                end_d = st.date_input("Stop Date:", value=dt.date.today())
                end_t = st.time_input("Stop Time:", value=dt.time(0, 0))
                custom_end = dt.datetime.combine(end_d, end_t)
            if custom_start >= custom_end:
                st.error("Start time must be before Stop time.")

        elif mode_choice == "📅 12-Month Full Ingestion (Complete historical training)":
            exec_mode = "full"
            if is_minute_sel:
                st.warning("⚠️ 12-Month ingestion at minute resolution involves ~525,600 intervals per tag. Hourly queries will be automatically sliced, but this will take considerable time.")

        elif mode_choice == "🧪 1-Day Test Run (Last 24 Hours)":
            exec_mode = "test"
            if is_minute_sel:
                st.info(f"ℹ️ 1-Day ingestion at `{sel_interval}` resolution will be automatically split into 24 hourly slices between start and stop.")

        mock_override = st.checkbox("Force Simulation Mode (Synthetic GT-2420A Data)", value=config.get("pi_web_api", {}).get("mock_mode", True))

        if not mock_override:
            st.warning("⚠️ **Live PI Web API is selected.** Ensure your machine is connected to PTTEP's internal network / VPN.")

        run_btn = st.button("🚀 Trigger Ingestion & Limits Calculation", type="primary", use_container_width=True)

        if run_btn:
            st.markdown("### 🔄 Ingestion & Processing Progress")
            progress_bar = st.progress(0.0, text="Initializing pipeline...")
            metrics_box = st.empty()
            status_box = st.status("📡 Connecting to PI Web API...", expanded=True)

            def on_progress_ui(fraction: float, message: str, details: Optional[Dict[str, Any]] = None):
                clamped_frac = min(1.0, max(0.0, float(fraction)))
                pct = int(clamped_frac * 100)
                progress_bar.progress(clamped_frac, text=f"Overall Progress: {pct}% | {message}")

                details = details or {}
                elapsed = details.get("elapsed", 0.0)
                eta = details.get("eta")
                tags_done = details.get("tags_completed", 0)
                total_tags = details.get("total_tags", len(sensors))
                points = details.get("points_collected", 0)

                eta_str = f"{eta}s remaining" if eta is not None and eta > 0 else ("Finishing up..." if pct >= 85 else "Calculating ETA...")

                with metrics_box.container():
                    m1, m2, m3, m4 = st.columns(4)
                    m1.metric("Progress", f"{pct}%")
                    m2.metric("Sensors Ingested", f"{tags_done} / {total_tags}")
                    m3.metric("Data Points", f"{points:,}")
                    m4.metric("Estimated ETA", eta_str if pct < 100 else f"Done in {elapsed}s")

                status_box.write(f"• `{message}` (Elapsed: `{elapsed}s`)")

            pipeline = Module1Pipeline(config_manager=cm)
            res = pipeline.run(
                mode=exec_mode,
                force_mock=mock_override,
                custom_start=custom_start,
                custom_end=custom_end,
                custom_interval=sel_interval,
                progress_callback=on_progress_ui,
            )

            if res.get("status") == "Success":
                status_box.update(label="✅ Ingestion & Limit Synchronization Completed!", state="complete", expanded=False)
                st.success(f"🎉 Successfully ingested {res['tags_successful']} tags and calculated {res['limits_calculated']} operating limits in {res['duration_seconds']}s!")
                st.balloons()
            else:
                status_box.update(label=f"❌ Ingestion Failed: {res.get('last_error')}", state="error", expanded=True)
                st.error(f"❌ Ingestion failed: {res.get('last_error')}")

    with col_info:
        st.subheader("Last Pipeline Execution Telemetry")
        latest_meta = cm.load_last_run_meta()
        st.json(latest_meta)

    st.markdown("---")
    st.subheader("Database Audit Log (`operating_limits`)")
    df_sql = sql_storage.fetch_all_limits_dataframe()
    if df_sql.empty:
        st.info("No records in database yet.")
    else:
        st.dataframe(df_sql.head(50), use_container_width=True, height=350)
        st.caption(f"Total audit records in database: {len(df_sql)}")


# ==========================================
# PAGE 3: MODULE 2 (CORRELATION ENGINE)
# ==========================================
elif page == "🔬 Module 2: Correlation Engine":
    st.title("🔬 Module 2: Multi-Sensor Many-to-Many Correlation Engine")
    st.markdown("Identify thermodynamic, aerodynamic, and mechanical interdependencies across all GT-2420A sensors.")

    data_path = cm.get_telemetry_path()
    if not data_path.exists():
        st.warning("⚠️ Historical telemetry data not found. Please run **Module 1** first to ingest data.")
    else:
        if str(data_path).lower().endswith(".parquet"):
            df_telemetry = pd.read_parquet(data_path, engine="pyarrow")
        else:
            import pickle
            with open(data_path, "rb") as f:
                df_telemetry = pickle.load(f)

        c_col1, c_col2, c_col3 = st.columns([1, 1, 1])
        with c_col1:
            corr_method = st.selectbox("Correlation Metric", ["pearson", "spearman"])
        with c_col2:
            subsystem_filter = st.selectbox("Subsystem Focus", ["All Subsystems"] + sorted(list({s.get("subsystem", "Unknown") for s in sensors})))
        with c_col3:
            top_n = st.slider("Top Coupled Pairs Count", 10, 50, 20)

        engine = CorrelationEngine(method=corr_method)
        with st.spinner("Computing Many-to-Many correlation matrix..."):
            corr_matrix = engine.compute_correlation_matrix(df_telemetry)

        tab_pairs, tab_heatmap, tab_scatter, tab_clustering = st.tabs([
            "🏆 Top Correlated Pairs", "🗺️ Many-to-Many Heatmap", "🔍 Pairwise Scatter Analysis", "🧩 ML Sensor Clusters"
        ])

        with tab_pairs:
            pair_mode = st.radio("Filter Pairs:", ["all", "cross_subsystem", "positive", "negative"], horizontal=True)
            top_pairs_df = engine.extract_top_pairs(top_n=top_n, filter_mode=pair_mode, sensors_meta=sensors)

            if not top_pairs_df.empty:
                # Add formatted names
                disp_pairs = top_pairs_df.copy()
                disp_pairs["Sensor 1"] = disp_pairs["Sensor_1"].apply(lambda p: p.split("\\")[-1])
                disp_pairs["Sensor 2"] = disp_pairs["Sensor_2"].apply(lambda p: p.split("\\")[-1])
                disp_pairs["Relationship"] = disp_pairs["Subsystem_1"] + " ↔ " + disp_pairs["Subsystem_2"]

                cols = ["Sensor 1", "Sensor 2", "Relationship", "Correlation", "Abs_Correlation"]
                st.dataframe(
                    disp_pairs[cols].style.background_gradient(subset=["Correlation"], cmap="coolwarm", vmin=-1.0, vmax=1.0).format({
                        "Correlation": "{:+.4f}",
                        "Abs_Correlation": "{:.4f}",
                    }),
                    use_container_width=True,
                    height=450,
                )

        with tab_heatmap:
            # Subsystem slice or top sensors
            display_corr = corr_matrix
            if subsystem_filter != "All Subsystems":
                sub_cols = [c for c in corr_matrix.columns if subsystem_filter in c]
                if len(sub_cols) > 1:
                    display_corr = corr_matrix.loc[sub_cols, sub_cols]

            # Short column labels for clean heatmap
            short_labels = [c.split("\\")[-1][:25] for c in display_corr.columns]

            fig_heat = px.imshow(
                display_corr.values,
                x=short_labels,
                y=short_labels,
                color_continuous_scale="RdBu_r",
                zmin=-1.0,
                zmax=1.0,
                title=f"Correlation Matrix ({subsystem_filter}, {len(display_corr)} sensors)",
            )
            fig_heat.update_layout(height=700, template="plotly_dark")
            st.plotly_chart(fig_heat, use_container_width=True)

        with tab_scatter:
            all_sensor_paths = list(df_telemetry.columns)
            s_col1, s_col2 = st.columns(2)
            with s_col1:
                sensor_x = st.selectbox("Sensor X-Axis", all_sensor_paths, index=0)
            with s_col2:
                sensor_y = st.selectbox("Sensor Y-Axis", all_sensor_paths, index=min(1, len(all_sensor_paths) - 1))

            sx = df_telemetry[sensor_x].dropna()
            sy = df_telemetry[sensor_y].dropna()
            common_idx = sx.index.intersection(sy.index)

            scat_df = pd.DataFrame({
                sensor_x.split("\\")[-1]: sx.loc[common_idx],
                sensor_y.split("\\")[-1]: sy.loc[common_idx],
            })
            val_corr = float(scat_df.corr().iloc[0, 1])

            fig_scatter = px.scatter(
                scat_df,
                x=scat_df.columns[0],
                y=scat_df.columns[1],
                trendline="ols",
                title=f"Scatter Correlation: {val_corr:+.4f}",
                template="plotly_dark",
            )
            fig_scatter.update_layout(height=480)
            st.plotly_chart(fig_scatter, use_container_width=True)

        with tab_clustering:
            n_clusters = st.slider("Number of Hierarchical Clusters", 2, 10, 5)
            clusterer = SensorClusterer(n_clusters=n_clusters)
            cluster_labels = clusterer.fit(corr_matrix)
            cluster_df = clusterer.get_cluster_dataframe()

            cluster_df["Sensor"] = cluster_df["af_path"].apply(lambda p: p.split("\\")[-1])
            cluster_df["Subsystem"] = cluster_df["af_path"].apply(lambda p: p.split("\\")[4] if len(p.split("\\")) >= 5 else "General")

            st.dataframe(cluster_df[["Cluster ID", "Subsystem", "Sensor", "af_path"]].rename(columns={"cluster_id": "Cluster ID"}), use_container_width=True, height=450)


# ==========================================
# PAGE 4: MODULE 3 (PREDICTION ENGINE)
# ==========================================
elif page == "🔮 Module 3: Prediction Engine":
    st.title("🔮 Module 3: Prediction & Health Monitoring Engine")
    st.info("ℹ️ **Status: Scaffolding Ready (To be developed further with production models)**")

    st.markdown("""
    This module provides the foundation for forward time-series degradation forecasting and multivariate anomaly detection.
    Below is the interactive baseline Anomaly Detector and Time-Series Forecaster stub.
    """)

    data_path = cm.get_telemetry_path()
    if not data_path.exists():
        st.warning("Please run Module 1 first to generate telemetry.")
    else:
        if str(data_path).lower().endswith(".parquet"):
            df_telemetry = pd.read_parquet(data_path, engine="pyarrow")
        else:
            import pickle
            with open(data_path, "rb") as f:
                df_telemetry = pickle.load(f)

        tab_anom, tab_fc = st.tabs(["🚨 Multivariate Anomaly Detection", "📈 Parameter Forecast Stub"])

        with tab_anom:
            st.subheader("Isolation Forest Multivariate Anomaly Score")
            contam = st.slider("Expected Contamination / Anomaly Rate (%)", 0.5, 10.0, 2.0, 0.5) / 100.0
            detector = SensorAnomalyDetector(contamination=contam)
            preds = detector.predict(df_telemetry)
            eval_metrics = detector.evaluate(df_telemetry, preds)

            m1, m2, m3 = st.columns(3)
            with m1:
                st.metric("Total Samples Checked", f"{eval_metrics['total_points']:,}")
            with m2:
                st.metric("Anomalous Points Flagged", f"{eval_metrics['anomaly_count']:,}")
            with m3:
                st.metric("Anomaly Rate", f"{eval_metrics['anomaly_percentage']}%")

            fig_anom = go.Figure()
            fig_anom.add_trace(go.Scatter(x=preds.index, y=preds["anomaly_score"], mode="lines", name="Health Score", line=dict(color="#00cc96")))
            anom_points = preds[preds["is_anomaly"]]
            fig_anom.add_trace(go.Scatter(x=anom_points.index, y=anom_points["anomaly_score"], mode="markers", name="Anomalous Excursion", marker=dict(color="red", size=6)))
            fig_anom.update_layout(title="Turbine Operational Health Profile (Lower Score = Higher Deviation)", xaxis_title="Timestamp", yaxis_title="Anomaly Score", height=420, template="plotly_dark")
            st.plotly_chart(fig_anom, use_container_width=True)

        with tab_fc:
            st.subheader("24-Hour Forward Forecast Stub")
            target = st.selectbox("Select Parameter to Forecast", list(df_telemetry.columns), index=0)
            horizon = st.slider("Forecast Horizon (Hours)", 6, 72, 24)

            stub = SensorForecastStub(target_sensor=target, horizon_hours=horizon)
            stub.fit(df_telemetry)
            fc_df = stub.predict()

            recent_actual = df_telemetry[target].tail(48)
            fig_fc = go.Figure()
            fig_fc.add_trace(go.Scatter(x=recent_actual.index, y=recent_actual.values, mode="lines", name="Recent Actual", line=dict(color="#29b5e8")))
            fig_fc.add_trace(go.Scatter(x=fc_df.index, y=fc_df["forecast"], mode="lines", name="Forecast", line=dict(color="#ff9900", dash="dash")))
            fig_fc.add_trace(go.Scatter(x=fc_df.index, y=fc_df["upper_bound"], mode="lines", line=dict(width=0), showlegend=False))
            fig_fc.add_trace(go.Scatter(x=fc_df.index, y=fc_df["lower_bound"], mode="lines", line=dict(width=0), fillcolor="rgba(255, 153, 0, 0.2)", fill="tonexty", name="Confidence Band"))

            fig_fc.update_layout(title=f"Forward Forecast Projection: {target.split('\\')[-1]}", xaxis_title="Timestamp", yaxis_title="Value", height=420, template="plotly_dark")
            st.plotly_chart(fig_fc, use_container_width=True)


# ==========================================
# PAGE 5: SETTINGS
# ==========================================
elif page == "⚙️ Settings":
    st.title("⚙️ System Configuration Settings")
    st.markdown("All configurations are loaded from and persisted directly to `config/config.json`.")

    with st.form("settings_form"):
        st.subheader("🌐 PI Web API Settings")
        p_col1, p_col2 = st.columns(2)
        with p_col1:
            pi_url = st.text_input("PI Web API URL", value=config.get("pi_web_api", {}).get("url", ""))
            pi_af_db = st.text_input("AF Database Path", value=config.get("pi_web_api", {}).get("af_db", ""))
            pi_user = st.text_input("PI Web API Username", value=config.get("pi_web_api", {}).get("username", ""))
            pi_pass = st.text_input("PI Web API Password", value=config.get("pi_web_api", {}).get("password", ""), type="password")
        with p_col2:
            pi_auth = st.selectbox("Authentication Type", ["basic", "ntlm"], index=0 if config.get("pi_web_api", {}).get("auth_type") == "basic" else 1)
            pi_verify_ssl = st.checkbox("Verify SSL Certificate", value=config.get("pi_web_api", {}).get("verify_ssl", False))
            setting_interval_opts = ["1m", "5m", "10m", "15m", "30m", "1h", "2h", "1d"]
            curr_setting_int = config.get("pi_web_api", {}).get("sample_interval", "1h")
            setting_int_idx = setting_interval_opts.index(curr_setting_int) if curr_setting_int in setting_interval_opts else 5
            pi_interval = st.selectbox("Interpolation Interval", setting_interval_opts, index=setting_int_idx)
            pi_timeout = st.number_input("Request Timeout (seconds)", min_value=5, max_value=300, value=config.get("pi_web_api", {}).get("timeout_seconds", 30))

        st.markdown("---")
        st.subheader("🗄️ SQL Database Settings")
        d_col1, d_col2 = st.columns(2)
        with d_col1:
            db_engine = st.selectbox("Database Engine", ["mssql", "sqlite"], index=0 if config.get("database", {}).get("engine") == "mssql" else 1)
            db_host = st.text_input("Host Server", value=config.get("database", {}).get("host", "localhost"))
            db_port = st.number_input("Port", value=config.get("database", {}).get("port", 1433))
            db_name = st.text_input("Database Name", value=config.get("database", {}).get("database", "OperationLimits"))
        with d_col2:
            db_user = st.text_input("SQL User", value=config.get("database", {}).get("user", "pi-ai"))
            db_pass = st.text_input("SQL Password", value=config.get("database", {}).get("password", "Ptt3p@2026"), type="password")
            db_driver = st.text_input("ODBC Driver", value=config.get("database", {}).get("driver", "SQL Server"))
            db_table = st.text_input("Table Name", value=config.get("database", {}).get("table_name", "operating_limits"))
            db_fallback = st.checkbox("Enable SQLite Fallback (if MS SQL unreachable)", value=config.get("database", {}).get("use_sqlite_fallback", True))

        st.markdown("---")
        st.subheader("📏 Statistical Operating Limit Settings")
        l_col1, l_col2 = st.columns(2)
        with l_col1:
            lim_method = st.selectbox("Calculation Method", ["percentile", "sigma"], index=0 if config.get("operating_limits", {}).get("method") == "percentile" else 1)
            norm_stat = st.selectbox("Normal Value Statistic", ["median", "mean"], index=0 if config.get("operating_limits", {}).get("normal_stat") == "median" else 1)
        with l_col2:
            p_hh = st.number_input("Percentile HH", 90.0, 99.9, float(config.get("operating_limits", {}).get("percentiles", {}).get("hh", 99.0)))
            p_h = st.number_input("Percentile H", 80.0, 98.0, float(config.get("operating_limits", {}).get("percentiles", {}).get("h", 95.0)))
            p_l = st.number_input("Percentile L", 1.0, 20.0, float(config.get("operating_limits", {}).get("percentiles", {}).get("l", 5.0)))
            p_ll = st.number_input("Percentile LL", 0.1, 10.0, float(config.get("operating_limits", {}).get("percentiles", {}).get("ll", 1.0)))

        save_settings = st.form_submit_button("💾 Save All Configurations", type="primary")

        if save_settings:
            config["pi_web_api"].update({
                "url": pi_url,
                "af_db": pi_af_db,
                "username": pi_user,
                "password": pi_pass,
                "auth_type": pi_auth,
                "verify_ssl": pi_verify_ssl,
                "mock_mode": pi_mock,
                "sample_interval": pi_interval,
                "timeout_seconds": int(pi_timeout),
            })
            config["database"].update({
                "engine": db_engine,
                "host": db_host,
                "port": int(db_port),
                "database": db_name,
                "user": db_user,
                "password": db_pass,
                "driver": db_driver,
                "table_name": db_table,
                "use_sqlite_fallback": db_fallback,
            })
            config["operating_limits"].update({
                "method": lim_method,
                "normal_stat": norm_stat,
                "percentiles": {
                    "hh": float(p_hh),
                    "h": float(p_h),
                    "l": float(p_l),
                    "ll": float(p_ll),
                },
            })
            cm.save_config(config)
            st.success("Configuration successfully updated and persisted to `config/config.json`!")
            st.rerun()

    st.markdown("---")
    st.subheader(f"Sensor Catalog ({len(sensors)} Attributes)")
    st.dataframe(pd.DataFrame(sensors)[["id", "subsystem", "tag_name", "category", "unit", "full_af_path"]], use_container_width=True, height=350)
