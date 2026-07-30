from __future__ import annotations

import logging
from contextlib import contextmanager
from threading import Lock
from typing import Any, Iterator

from app.config import Settings

logger = logging.getLogger(__name__)


class HanaClient:
    """Small lazy HANA adapter that keeps external-service failure non-fatal."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._available: bool | None = None
        self._lock = Lock()

    @property
    def configured(self) -> bool:
        return self.settings.hana_configured

    def _connect(self):
        from hdbcli import dbapi

        kwargs: dict[str, Any] = {
            "address": self.settings.hana_host,
            "port": self.settings.hana_port,
            "user": self.settings.hana_user,
            "password": self.settings.hana_password,
            "encrypt": True,
        }
        if not self.settings.hana_validate_certificate:
            kwargs["sslValidateCertificate"] = False
        return dbapi.connect(**kwargs)

    @contextmanager
    def connection(self) -> Iterator[Any]:
        connection = self._connect()
        try:
            yield connection
        finally:
            connection.close()

    def ping(self, refresh: bool = False) -> bool:
        if self._available is not None and not refresh:
            return self._available
        if not self.configured:
            self._available = False
            return False
        with self._lock:
            try:
                with self.connection() as connection:
                    cursor = connection.cursor()
                    cursor.execute("SELECT 1 FROM DUMMY")
                    cursor.fetchone()
                self._available = True
            except Exception as exc:  # external service boundary
                logger.warning("SAP HANA is unavailable: %s", exc)
                self._available = False
        return self._available

    def query(self, sql: str, parameters: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
        with self.connection() as connection:
            cursor = connection.cursor()
            cursor.execute(sql, parameters)
            columns = [description[0].lower() for description in cursor.description]
            return [dict(zip(columns, row, strict=True)) for row in cursor.fetchall()]

    def execute(self, sql: str, parameters: tuple[Any, ...] = ()) -> None:
        with self.connection() as connection:
            cursor = connection.cursor()
            cursor.execute(sql, parameters)
            connection.commit()

    def discover_tables(self) -> dict[str, list[str]]:
        schema = self.settings.reference_schema.upper()
        rows = self.query(
            """
            SELECT TABLE_NAME, COLUMN_NAME
            FROM SYS.TABLE_COLUMNS
            WHERE SCHEMA_NAME = ?
            ORDER BY TABLE_NAME, POSITION
            """,
            (schema,),
        )
        result: dict[str, list[str]] = {}
        for row in rows:
            result.setdefault(str(row["table_name"]), []).append(str(row["column_name"]))
        return result
