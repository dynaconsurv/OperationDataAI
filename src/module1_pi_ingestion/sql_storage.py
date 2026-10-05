"""SQL Storage Engine for GT-2420A Operating Parameters.
Handles database connectivity, table initialization, and deduplication logic:
Matches (af_path, type). If record exists and value is unchanged, skip insert.
Otherwise, insert new record. Supports MS SQL Server and SQLite fallback.
"""

from __future__ import annotations

import datetime as dt
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
import pandas as pd
import sqlalchemy as sa
from sqlalchemy import Column, DateTime, Float, Index, Integer, String, Table, create_engine, select
from sqlalchemy.orm import declarative_base, sessionmaker

from src.utils.logger import get_logger

logger = get_logger("SQLStorage")
Base = declarative_base()


class OperatingLimitRecord(Base):
    """SQLAlchemy model for operating_limits table."""

    __tablename__ = "operating_limits"

    id = Column(Integer, primary_key=True, autoincrement=True)
    af_path = Column(String(500), nullable=False)
    value = Column(Float, nullable=False)
    type = Column(String(50), nullable=False)
    updated_at = Column(DateTime, default=lambda: dt.datetime.now(dt.timezone.utc))

    __table_args__ = (
        Index("idx_path_type", "af_path", "type"),
    )


class SQLStorageManager:
    """Manages database connection and persistence of operating limits."""

    def __init__(self, config: Dict[str, Any]) -> None:
        self.config = config
        db_cfg = config.get("database", {})

        self.engine_type = db_cfg.get("engine", "mssql").lower()
        self.host = db_cfg.get("host", "localhost")
        self.port = db_cfg.get("port", 1433)
        self.database = db_cfg.get("database", "PTTEP_AI")
        self.user = db_cfg.get("user", "pi-ai")
        self.password = db_cfg.get("password", "Ptt3p@2026")
        self.driver = db_cfg.get("driver", "SQL Server")
        self.table_name = db_cfg.get("table_name", "operating_limits")
        self.use_sqlite_fallback = db_cfg.get("use_sqlite_fallback", True)

        raw_sqlite_path = db_cfg.get("sqlite_path", "data/operating_limits.db")
        p = Path(raw_sqlite_path)
        if not p.is_absolute():
            self.sqlite_path = Path(__file__).resolve().parent.parent.parent / p
        else:
            self.sqlite_path = p

        self.engine: Optional[sa.engine.Engine] = None
        self.active_backend: str = "unknown"
        self._initialize_engine()

    def _build_mssql_url(self) -> str:
        """Construct SQLAlchemy connection URL for MS SQL Server via pyodbc."""
        driver_encoded = self.driver.replace(" ", "+")
        # Format: mssql+pyodbc://user:password@host:port/database?driver=...
        return f"mssql+pyodbc://{self.user}:{self.password}@{self.host}:{self.port}/{self.database}?driver={driver_encoded}&TrustServerCertificate=yes"

    def _initialize_engine(self) -> None:
        """Initialize database engine with fallback to SQLite if MS SQL Server is unreachable."""
        if self.engine_type == "mssql":
            try:
                mssql_url = self._build_mssql_url()
                test_engine = create_engine(mssql_url, pool_pre_ping=True, connect_args={"timeout": 3})
                with test_engine.connect():
                    pass
                self.engine = test_engine
                self.active_backend = "mssql"
                logger.info(f"Connected to MS SQL Server at {self.host}:{self.port}/{self.database} as user '{self.user}'.")
            except Exception as e:
                logger.warning(f"Could not connect to MS SQL Server ({e}).")
                if self.use_sqlite_fallback:
                    logger.info(f"Engaging SQLite fallback database at: {self.sqlite_path}")
                    self.sqlite_path.parent.mkdir(parents=True, exist_ok=True)
                    sqlite_url = f"sqlite:///{self.sqlite_path}"
                    self.engine = create_engine(sqlite_url, pool_pre_ping=True)
                    self.active_backend = "sqlite"
                else:
                    raise
        else:
            self.sqlite_path.parent.mkdir(parents=True, exist_ok=True)
            sqlite_url = f"sqlite:///{self.sqlite_path}"
            self.engine = create_engine(sqlite_url, pool_pre_ping=True)
            self.active_backend = "sqlite"
            logger.info(f"Using SQLite database at {self.sqlite_path}")

        self.create_tables_if_not_exist()

    def create_tables_if_not_exist(self) -> None:
        """Create the operating_limits table if missing."""
        if self.engine is not None:
            Base.metadata.create_all(self.engine)

    def get_latest_limits_map(self) -> Dict[Tuple[str, str], float]:
        """Fetch the most recent value for each (af_path, type) from the database."""
        if self.engine is None:
            return {}

        Session = sessionmaker(bind=self.engine)
        session = Session()
        latest_map: Dict[Tuple[str, str], float] = {}

        try:
            # Query all records ordered by id asc, latest will overwrite earlier
            stmt = select(OperatingLimitRecord.af_path, OperatingLimitRecord.type, OperatingLimitRecord.value).order_by(OperatingLimitRecord.id.asc())
            rows = session.execute(stmt).fetchall()
            for af_path, param_type, val in rows:
                latest_map[(af_path, param_type)] = float(val)
        except Exception as e:
            logger.error(f"Error querying existing limits from DB: {e}")
        finally:
            session.close()

        return latest_map

    def save_limits(
        self, records: List[Dict[str, Any]], tolerance: float = 1e-4
    ) -> Tuple[int, int]:
        """Insert records with deduplication logic:
        For each (af_path, type), if record exists in SQL Table and value has NOT changed
        (within tolerance), skip insert.
        Else, insert new record.

        Parameters
        ----------
        records : list of dict
            Each dict has {"af_path": ..., "type": ..., "value": ...}.
        tolerance : float
            Float comparison tolerance.

        Returns
        -------
        Tuple[int, int]
            (inserted_count, skipped_count)
        """
        if self.engine is None or not records:
            return 0, 0

        existing_map = self.get_latest_limits_map()
        inserted_count = 0
        skipped_count = 0

        Session = sessionmaker(bind=self.engine)
        session = Session()

        new_objects: List[OperatingLimitRecord] = []
        now = dt.datetime.now(dt.timezone.utc)

        try:
            for rec in records:
                af_path = rec["af_path"]
                param_type = rec["type"]
                new_val = float(rec["value"])

                key = (af_path, param_type)
                if key in existing_map:
                    old_val = existing_map[key]
                    if abs(old_val - new_val) <= tolerance:
                        # Value exists and hasn't changed -> Skip insert
                        skipped_count += 1
                        continue

                # Record doesn't exist or value changed -> Insert new record
                obj = OperatingLimitRecord(
                    af_path=af_path,
                    value=new_val,
                    type=param_type,
                    updated_at=now,
                )
                new_objects.append(obj)
                existing_map[key] = new_val  # Update local cache
                inserted_count += 1

            if new_objects:
                session.bulk_save_objects(new_objects)
                session.commit()
                logger.info(f"Database sync complete: {inserted_count} records inserted, {skipped_count} skipped (unchanged).")
            else:
                logger.info(f"Database sync complete: All {skipped_count} records were unchanged (0 inserted).")

        except Exception as e:
            session.rollback()
            logger.error(f"Failed to persist operating limits into database: {e}")
            raise
        finally:
            session.close()

        return inserted_count, skipped_count

    def fetch_all_limits_dataframe(self) -> pd.DataFrame:
        """Fetch all stored operating limit records as a pandas DataFrame."""
        if self.engine is None:
            return pd.DataFrame()

        query = "SELECT id, af_path, value, type, updated_at FROM operating_limits ORDER BY id DESC"
        try:
            with self.engine.connect() as conn:
                df = pd.read_sql_query(query, conn)
            return df
        except Exception as e:
            logger.error(f"Error fetching limits DataFrame: {e}")
            return pd.DataFrame()

    def fetch_current_limits_pivot(self) -> pd.DataFrame:
        """Fetch current (most recent) limits pivoted by sensor and parameter type."""
        df = self.fetch_all_limits_dataframe()
        if df.empty:
            return pd.DataFrame()

        # Keep latest record per (af_path, type)
        df_latest = df.sort_values("id").groupby(["af_path", "type"]).last().reset_index()
        pivot_df = df_latest.pivot(index="af_path", columns="type", values="value").reset_index()

        cols = [c for c in ["af_path", "LL", "L", "Normal", "H", "HH"] if c in pivot_df.columns]
        return pivot_df[cols]
