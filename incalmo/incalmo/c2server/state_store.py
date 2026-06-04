import json
import os
import sqlite3


class StateStore:
    TABLE_NAME = "environment"
    DB_PATH = "state_store.db"

    @classmethod
    def _get_connection(cls) -> sqlite3.Connection:
        return sqlite3.connect(cls.DB_PATH)

    @classmethod
    def initialize(cls) -> None:
        "Delete existing DB file and create a new one."
        if os.path.exists(cls.DB_PATH):
            os.remove(cls.DB_PATH)

    @classmethod
    def set_hosts(cls, hosts: list[dict]) -> None:
        with cls._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                f"""
                CREATE TABLE IF NOT EXISTS {cls.TABLE_NAME} (
                    host_id TEXT PRIMARY KEY,
                    host TEXT
                )
                """
            )
            for host in hosts:
                cursor.execute(
                    f"""
                    INSERT OR REPLACE INTO {cls.TABLE_NAME} (host_id, host)
                    VALUES (?, ?)
                    """,
                    (host.get("host_id"), json.dumps(host)),
                )

    @classmethod
    def get_hosts(cls) -> list[dict]:
        with cls._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(f"SELECT host from {cls.TABLE_NAME}")
            rows = cursor.fetchall()
            return [json.loads(row[0]) for row in rows]
