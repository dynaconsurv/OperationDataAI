"""Unit tests for SQLStorageManager deduplication and schema."""

from pathlib import Path
from src.module1_pi_ingestion.sql_storage import SQLStorageManager


def test_sql_storage_deduplication(tmp_path: Path):
    db_file = tmp_path / "test_limits.db"
    config = {
        "database": {
            "engine": "sqlite",
            "sqlite_path": str(db_file),
            "use_sqlite_fallback": True,
        }
    }

    storage = SQLStorageManager(config)

    records = [
        {"af_path": r"MALAYSIA\BORF\GTG\GT-2420A\Air Filter System\Ambient Inlet Pressure", "type": "Normal", "value": 1.013},
        {"af_path": r"MALAYSIA\BORF\GTG\GT-2420A\Air Filter System\Ambient Inlet Pressure", "type": "HH", "value": 1.050},
        {"af_path": r"MALAYSIA\BORF\GTG\GT-2420A\Air Filter System\Ambient Inlet Pressure", "type": "LL", "value": 0.950},
    ]

    # Initial Insert: All 3 should be inserted
    inserted, skipped = storage.save_limits(records)
    assert inserted == 3
    assert skipped == 0

    # Second Insert with same values: All 3 should be skipped!
    inserted2, skipped2 = storage.save_limits(records)
    assert inserted2 == 0
    assert skipped2 == 3

    # Third Insert with 1 modified value and 2 identical values
    modified_records = [
        {"af_path": r"MALAYSIA\BORF\GTG\GT-2420A\Air Filter System\Ambient Inlet Pressure", "type": "Normal", "value": 1.013},  # Unchanged -> Skip
        {"af_path": r"MALAYSIA\BORF\GTG\GT-2420A\Air Filter System\Ambient Inlet Pressure", "type": "HH", "value": 1.080},      # Changed -> Insert!
        {"af_path": r"MALAYSIA\BORF\GTG\GT-2420A\Air Filter System\Ambient Inlet Pressure", "type": "LL", "value": 0.950},      # Unchanged -> Skip
    ]

    inserted3, skipped3 = storage.save_limits(modified_records)
    assert inserted3 == 1
    assert skipped3 == 2

    # Verify database contents
    df = storage.fetch_all_limits_dataframe()
    # Total inserted records in history = 3 + 0 + 1 = 4
    assert len(df) == 4

    # Verify latest pivoted limits
    pivot = storage.fetch_current_limits_pivot()
    assert len(pivot) == 1
    assert pivot.iloc[0]["HH"] == 1.080
    assert pivot.iloc[0]["Normal"] == 1.013


if __name__ == "__main__":
    import pytest
    pytest.main([__file__])
