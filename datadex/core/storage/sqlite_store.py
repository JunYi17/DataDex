"""
Ken — SQLite Register Store

Manages structured register data in SQLite.
Supports exact and LIKE-based lookups by register name or address.
"""

import os
import sqlite3
from typing import List, Optional

from ..ingestion.excel_parser import Register


class SQLiteStore:
    """SQLite-backed structured store for hardware register records."""

    def __init__(self, db_path: str):
        """Initialize SQLite store.

        Args:
            db_path: Path to the SQLite database file
        """
        os.makedirs(os.path.dirname(db_path), exist_ok=True)
        self.db_path = db_path
        self._init_db()

    def _get_conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self):
        """Create the registers table if it doesn't exist."""
        conn = self._get_conn()
        try:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS registers (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL,
                    address TEXT DEFAULT '',
                    bit_field TEXT DEFAULT '',
                    access TEXT DEFAULT '',
                    reset_value TEXT DEFAULT '',
                    description TEXT DEFAULT '',
                    source TEXT DEFAULT '',
                    workspace TEXT DEFAULT ''
                )
            """)
            conn.execute("CREATE INDEX IF NOT EXISTS idx_reg_name ON registers(name)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_reg_address ON registers(address)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_reg_workspace ON registers(workspace)")
            conn.commit()
        finally:
            conn.close()

    def clear_workspace(self, workspace: str):
        """Delete all register records for a workspace."""
        conn = self._get_conn()
        try:
            conn.execute("DELETE FROM registers WHERE workspace = ?", (workspace,))
            conn.commit()
        finally:
            conn.close()

    def insert_registers(self, workspace: str, registers: List[Register]):
        """Insert multiple register records for a workspace.

        Args:
            workspace: Workspace name
            registers: List of Register objects
        """
        conn = self._get_conn()
        try:
            data = [
                (r.name, r.address, r.bit_field, r.access,
                 r.reset_value, r.description, r.source, workspace)
                for r in registers
            ]
            conn.executemany(
                """INSERT INTO registers (name, address, bit_field, access,
                   reset_value, description, source, workspace)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                data,
            )
            conn.commit()
        finally:
            conn.close()

    def lookup_by_name(self, name: str, workspace: str) -> List[dict]:
        """Look up registers by name (LIKE match).

        Args:
            name: Register name or partial name (e.g., "I2C_CFG" or "I2C")
            workspace: Workspace name

        Returns:
            List of matching register records as dicts
        """
        conn = self._get_conn()
        try:
            cursor = conn.execute(
                """SELECT * FROM registers
                   WHERE workspace = ? AND (name LIKE ? OR name = ?)
                   ORDER BY name""",
                (workspace, f"%{name}%", name),
            )
            return [dict(row) for row in cursor.fetchall()]
        finally:
            conn.close()

    def lookup_by_address(self, address: str, workspace: str) -> List[dict]:
        """Look up registers by address.

        Args:
            address: Register address (e.g., "0xFC" or "FC")
            workspace: Workspace name

        Returns:
            List of matching register records as dicts
        """
        conn = self._get_conn()
        try:
            cursor = conn.execute(
                """SELECT * FROM registers
                   WHERE workspace = ? AND (address = ? OR address LIKE ?)
                   ORDER BY name""",
                (workspace, address, f"%{address}%"),
            )
            return [dict(row) for row in cursor.fetchall()]
        finally:
            conn.close()

    def lookup_all(self, workspace: str, limit: int = 50) -> List[dict]:
        """Get all registers for a workspace.

        Args:
            workspace: Workspace name
            limit: Maximum number of records to return

        Returns:
            List of register records as dicts
        """
        conn = self._get_conn()
        try:
            cursor = conn.execute(
                "SELECT * FROM registers WHERE workspace = ? ORDER BY name LIMIT ?",
                (workspace, limit),
            )
            return [dict(row) for row in cursor.fetchall()]
        finally:
            conn.close()

    def count(self, workspace: str) -> int:
        """Count registers in a workspace."""
        conn = self._get_conn()
        try:
            cursor = conn.execute(
                "SELECT COUNT(*) as cnt FROM registers WHERE workspace = ?",
                (workspace,),
            )
            row = cursor.fetchone()
            return row["cnt"] if row else 0
        finally:
            conn.close()
