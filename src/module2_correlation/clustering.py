"""Sensor Correlation Clustering using Machine Learning / Hierarchical Clustering.
Groups sensors exhibiting high co-movement into functional clusters.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional
import numpy as np
import pandas as pd
from scipy.cluster.hierarchy import dendrogram, fcluster, linkage
from scipy.spatial.distance import squareform

from src.utils.logger import get_logger

logger = get_logger("SensorClustering")


class SensorClusterer:
    """Performs hierarchical clustering on sensor correlation matrices."""

    def __init__(self, n_clusters: int = 6) -> None:
        self.n_clusters = n_clusters
        self.linkage_matrix: Optional[np.ndarray] = None
        self.labels_: Optional[Dict[str, int]] = None

    def fit(self, corr_matrix: pd.DataFrame) -> Dict[str, int]:
        """Fit agglomerative clustering on the correlation matrix.

        Distance metric is defined as: distance = 1 - |correlation|
        """
        # Clean NaNs and clip correlations
        clean_corr = corr_matrix.fillna(0.0).clip(-1.0, 1.0)
        # Dissimilarity metric: 0 means perfectly correlated, 1 means uncorrelated
        dist_matrix = 1.0 - np.abs(clean_corr.values)
        np.fill_diagonal(dist_matrix, 0.0)

        # Convert square form to condensed 1D distance array
        condensed_dist = squareform(dist_matrix, checks=False)

        # Hierarchical ward or average linkage
        self.linkage_matrix = linkage(condensed_dist, method="average")
        cluster_assignments = fcluster(self.linkage_matrix, t=self.n_clusters, criterion="maxclust")

        self.labels_ = {
            col: int(cluster_assignments[i])
            for i, col in enumerate(clean_corr.columns)
        }
        logger.info(f"Clustered {len(clean_corr.columns)} sensors into {self.n_clusters} clusters.")
        return self.labels_

    def get_cluster_dataframe(self) -> pd.DataFrame:
        """Return a DataFrame of sensors and their assigned cluster IDs."""
        if not self.labels_:
            return pd.DataFrame()
        return pd.DataFrame([
            {"af_path": path, "cluster_id": cid}
            for path, cid in self.labels_.items()
        ]).sort_values("cluster_id").reset_index(drop=True)
