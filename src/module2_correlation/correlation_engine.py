"""Module 2: Multi-Sensor Many-to-Many Correlation Engine.
Calculates Pearson, Spearman, and Kendall correlation matrices across all sensors,
extracts top correlated pairs, and performs subsystem-to-subsystem cross analysis.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
import numpy as np
import pandas as pd

from src.utils.logger import get_logger

logger = get_logger("CorrelationEngine")


class CorrelationEngine:
    """Computes and analyzes Many-to-Many correlations between sensors."""

    def __init__(self, method: str = "pearson", min_periods: int = 24) -> None:
        self.method = method.lower()
        self.min_periods = min_periods
        self.correlation_matrix: Optional[pd.DataFrame] = None

    def compute_correlation_matrix(self, df: pd.DataFrame) -> pd.DataFrame:
        """Compute the full Many-to-Many correlation matrix across all numeric columns.

        Parameters
        ----------
        df : pd.DataFrame
            Sensor telemetry DataFrame indexed by timestamp.

        Returns
        -------
        pd.DataFrame
            Square symmetric correlation matrix (N x N).
        """
        logger.info(f"Computing {self.method} correlation matrix for {df.shape[1]} sensors ({df.shape[0]} samples)...")
        # Drop columns with zero variance to avoid NaN warnings
        numeric_df = df.select_dtypes(include=[np.number])
        valid_cols = [c for c in numeric_df.columns if numeric_df[c].std() > 1e-8]
        if len(valid_cols) < len(numeric_df.columns):
            logger.info(f"Filtered out {len(numeric_df.columns) - len(valid_cols)} zero-variance or constant columns.")

        effective_min = min(self.min_periods, max(5, len(numeric_df) // 3))
        corr_matrix = numeric_df[valid_cols].corr(method=self.method, min_periods=effective_min)
        self.correlation_matrix = corr_matrix
        return corr_matrix

    def extract_top_pairs(
        self,
        top_n: int = 20,
        filter_mode: str = "all",  # 'all', 'positive', 'negative', 'cross_subsystem'
        sensors_meta: Optional[List[Dict[str, Any]]] = None,
    ) -> pd.DataFrame:
        """Extract the strongest correlated pairs from the correlation matrix.

        Parameters
        ----------
        top_n : int
            Number of top pairs to return.
        filter_mode : str
            'all' (by absolute correlation), 'positive', 'negative', or 'cross_subsystem'.
        sensors_meta : list of dict, optional
            Sensor definitions for subsystem mapping.

        Returns
        -------
        pd.DataFrame
            Table with columns: ['Sensor_1', 'Sensor_2', 'Subsystem_1', 'Subsystem_2', 'Correlation', 'Abs_Correlation']
        """
        if self.correlation_matrix is None or self.correlation_matrix.empty:
            return pd.DataFrame()

        # Build subsystem lookup map
        subsystem_map = {}
        if sensors_meta:
            for s in sensors_meta:
                path = s.get("full_af_path", s.get("parent", ""))
                subsystem_map[path] = s.get("subsystem", "Unknown")

        corr = self.correlation_matrix
        cols = list(corr.columns)
        n = len(cols)

        pairs = []
        for i in range(n):
            for j in range(i + 1, n):
                val = corr.iloc[i, j]
                if pd.isna(val):
                    continue
                s1, s2 = cols[i], cols[j]
                sub1 = subsystem_map.get(s1, "Unknown")
                sub2 = subsystem_map.get(s2, "Unknown")

                if filter_mode == "cross_subsystem" and sub1 == sub2:
                    continue
                if filter_mode == "positive" and val <= 0:
                    continue
                if filter_mode == "negative" and val >= 0:
                    continue

                pairs.append({
                    "Sensor_1": s1,
                    "Sensor_2": s2,
                    "Subsystem_1": sub1,
                    "Subsystem_2": sub2,
                    "Correlation": round(float(val), 4),
                    "Abs_Correlation": round(abs(float(val)), 4),
                })

        if not pairs:
            return pd.DataFrame()

        pairs_df = pd.DataFrame(pairs)
        pairs_df = pairs_df.sort_values(by="Abs_Correlation", ascending=False).head(top_n).reset_index(drop=True)
        return pairs_df

    def get_subsystem_matrix(
        self, subsystem_1: str, subsystem_2: Optional[str] = None
    ) -> pd.DataFrame:
        """Extract a submatrix of correlations between one or two subsystems."""
        if self.correlation_matrix is None:
            return pd.DataFrame()

        cols1 = [c for c in self.correlation_matrix.columns if subsystem_1 in c]
        if subsystem_2 and subsystem_2 != subsystem_1:
            cols2 = [c for c in self.correlation_matrix.columns if subsystem_2 in c]
            return self.correlation_matrix.loc[cols1, cols2]
        return self.correlation_matrix.loc[cols1, cols1]

    def save_matrix_csv(self, file_path: Path) -> None:
        """Export full correlation matrix to CSV."""
        if self.correlation_matrix is not None:
            file_path.parent.mkdir(parents=True, exist_ok=True)
            self.correlation_matrix.to_csv(file_path)
            logger.info(f"Saved correlation matrix to {file_path}")
