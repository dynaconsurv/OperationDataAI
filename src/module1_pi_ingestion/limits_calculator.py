"""Operating Limits Statistical Engine.
Calculates Normal, High-High (HH), High (H), Low (L), and Low-Low (LL)
thresholds using historical time-series data via statistical parametric
(Mean, Std Dev) and non-parametric (Percentile) approaches.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple
import numpy as np
import pandas as pd

from src.utils.logger import get_logger

logger = get_logger("LimitsCalculator")


class LimitsCalculator:
    """Calculates statistical operating limits for sensor telemetry."""

    def __init__(self, config: Dict[str, Any]) -> None:
        self.config = config
        limits_cfg = config.get("operating_limits", {})

        self.method = limits_cfg.get("method", "percentile").lower()
        self.normal_stat = limits_cfg.get("normal_stat", "median").lower()

        # Sigma multipliers
        sigmas = limits_cfg.get("sigma_multipliers", {})
        self.sigma_hh = float(sigmas.get("hh", 3.0))
        self.sigma_h = float(sigmas.get("h", 2.0))
        self.sigma_l = float(sigmas.get("l", 2.0))
        self.sigma_ll = float(sigmas.get("ll", 3.0))

        # Percentile cutoffs
        pcts = limits_cfg.get("percentiles", {})
        self.pct_ll = float(pcts.get("ll", 1.0))
        self.pct_l = float(pcts.get("l", 5.0))
        self.pct_h = float(pcts.get("h", 95.0))
        self.pct_hh = float(pcts.get("hh", 99.0))

    def compute_sensor_limits(self, series: pd.Series) -> Dict[str, float]:
        """Compute the 5 operating limits (Normal, HH, H, L, LL) for a single sensor series."""
        clean = series.dropna()
        if len(clean) == 0:
            return {"Normal": 0.0, "HH": 0.0, "H": 0.0, "L": 0.0, "LL": 0.0}

        mean_val = float(clean.mean())
        std_val = float(clean.std())
        median_val = float(clean.median())

        # Determine Normal value
        normal_val = median_val if self.normal_stat == "median" else mean_val

        if self.method == "sigma":
            hh = mean_val + self.sigma_hh * std_val
            h = mean_val + self.sigma_h * std_val
            l = mean_val - self.sigma_l * std_val
            ll = mean_val - self.sigma_ll * std_val
        else:  # Percentile approach
            hh = float(np.percentile(clean, self.pct_hh))
            h = float(np.percentile(clean, self.pct_h))
            l = float(np.percentile(clean, self.pct_l))
            ll = float(np.percentile(clean, self.pct_ll))

        return {
            "Normal": round(normal_val, 4),
            "HH": round(hh, 4),
            "H": round(h, 4),
            "L": round(l, 4),
            "LL": round(ll, 4),
        }

    def compute_all_limits(
        self, df: pd.DataFrame
    ) -> Tuple[List[Dict[str, Any]], pd.DataFrame]:
        """Compute operating limits for all columns in the DataFrame.

        Parameters
        ----------
        df : pd.DataFrame
            Historical time-series data with columns as AF paths.

        Returns
        -------
        Tuple[List[Dict[str, Any]], pd.DataFrame]
            1. List of 5 rows per sensor: [{"af_path": ..., "type": "Normal"|"HH"|"H"|"L"|"LL", "value": ...}, ...]
            2. Summary DataFrame with one row per sensor for reporting.
        """
        records: List[Dict[str, Any]] = []
        summary_rows: List[Dict[str, Any]] = []

        logger.info(f"Computing operating limits using method='{self.method}' for {len(df.columns)} sensors...")

        for col in df.columns:
            series = df[col].dropna()
            if series.empty:
                continue

            limits = self.compute_sensor_limits(series)
            mean_val = float(series.mean())
            std_val = float(series.std())
            min_val = float(series.min())
            max_val = float(series.max())

            summary_rows.append({
                "af_path": col,
                "count": len(series),
                "mean": round(mean_val, 4),
                "std": round(std_val, 4),
                "min": round(min_val, 4),
                "LL": limits["LL"],
                "L": limits["L"],
                "Normal": limits["Normal"],
                "H": limits["H"],
                "HH": limits["HH"],
                "max": round(max_val, 4),
                "method": self.method,
            })

            for param_type in ["Normal", "HH", "H", "L", "LL"]:
                records.append({
                    "af_path": str(col),
                    "type": param_type,
                    "value": float(limits[param_type]),
                })

        summary_df = pd.DataFrame(summary_rows)
        logger.info(f"Calculated {len(records)} total operating parameter records across {len(summary_rows)} sensors.")
        return records, summary_df
