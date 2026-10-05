"""Unit tests for Correlation Engine and Clustering."""

import numpy as np
import pandas as pd
from src.module2_correlation.correlation_engine import CorrelationEngine
from src.module2_correlation.clustering import SensorClusterer


def test_correlation_matrix():
    np.random.seed(42)
    n = 100
    x = np.linspace(0, 10, n)
    y_pos = 2 * x + np.random.normal(0, 0.5, n)
    y_neg = -3 * x + np.random.normal(0, 0.5, n)
    noise = np.random.normal(0, 5, n)

    df = pd.DataFrame({
        "Tag_X": x,
        "Tag_Y_Pos": y_pos,
        "Tag_Y_Neg": y_neg,
        "Tag_Noise": noise,
    })

    engine = CorrelationEngine(method="pearson")
    corr = engine.compute_correlation_matrix(df)

    assert corr.shape == (4, 4)
    assert np.isclose(corr.loc["Tag_X", "Tag_X"], 1.0)
    assert corr.loc["Tag_X", "Tag_Y_Pos"] > 0.95
    assert corr.loc["Tag_X", "Tag_Y_Neg"] < -0.95

    # Test top pairs
    top_pairs = engine.extract_top_pairs(top_n=2, filter_mode="all")
    assert len(top_pairs) == 2
    assert top_pairs.iloc[0]["Abs_Correlation"] > 0.95


def test_sensor_clustering():
    np.random.seed(42)
    n = 50
    x1 = np.linspace(0, 10, n)
    x2 = x1 + np.random.normal(0, 0.1, n)
    y1 = np.sin(x1)
    y2 = np.sin(x1) + np.random.normal(0, 0.1, n)

    df = pd.DataFrame({"X1": x1, "X2": x2, "Y1": y1, "Y2": y2})
    engine = CorrelationEngine()
    corr = engine.compute_correlation_matrix(df)

    clusterer = SensorClusterer(n_clusters=2)
    labels = clusterer.fit(corr)

    assert len(labels) == 4
    # X1 and X2 should belong to the same cluster
    assert labels["X1"] == labels["X2"]
    # Y1 and Y2 should belong to the same cluster
    assert labels["Y1"] == labels["Y2"]


if __name__ == "__main__":
    import pytest
    pytest.main([__file__])
