"""Inventory Skill — Control de stock compartido."""
import sqlite3
from pathlib import Path
from typing import Any

from skills.base_skill import BaseSkill


class InventorySkill(BaseSkill):
    def __init__(self) -> None:
        super().__init__("inventory")
        self.db_path = "/mnt/ssd_trabajo/sqlite/hermes.db"

    async def execute(self, **kwargs: Any) -> dict[str, Any]:
        action = kwargs.get("action", "get_stock")
        if action == "get_stock":
            return await self._get_stock(kwargs.get("product"))
        elif action == "add_stock":
            return await self._add_stock(
                kwargs.get("product", ""),
                kwargs.get("quantity", 0),
                kwargs.get("reason", ""),
            )
        elif action == "remove_stock":
            return await self._remove_stock(
                kwargs.get("product", ""),
                kwargs.get("quantity", 0),
                kwargs.get("reason", ""),
            )
        elif action == "check_alerts":
            return await self._check_alerts()
        return self._error(f"Acción no reconocida: {action}")

    def _get_conn(self) -> sqlite3.Connection:
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS inventory (
                product TEXT PRIMARY KEY, current_stock INTEGER DEFAULT 0,
                min_stock INTEGER DEFAULT 5, max_capacity INTEGER DEFAULT 100,
                unit TEXT DEFAULT 'unidad', last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS inventory_movements (
                id INTEGER PRIMARY KEY AUTOINCREMENT, product TEXT NOT NULL,
                movement_type TEXT NOT NULL, quantity INTEGER NOT NULL,
                reason TEXT, timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            INSERT OR IGNORE INTO inventory (product, current_stock)
            VALUES ('AGUA_20L', 50), ('HIELO_7KG', 20);
        """)
        conn.commit()
        return conn

    async def _get_stock(self, product: str | None = None) -> dict[str, Any]:
        conn = self._get_conn()
        if product:
            row = conn.execute("SELECT * FROM inventory WHERE product = ?", (product,)).fetchone()
            conn.close()
            return self._success({"product": dict(row)}) if row else self._error("No encontrado")
        rows = conn.execute("SELECT * FROM inventory").fetchall()
        conn.close()
        return self._success({"products": [dict(r) for r in rows]})

    async def _add_stock(self, product: str, quantity: int, reason: str) -> dict[str, Any]:
        conn = self._get_conn()
        conn.execute(
            "UPDATE inventory SET current_stock = current_stock + ? "
            "WHERE product = ?",
            (quantity, product),
        )
        conn.execute(
            "INSERT INTO inventory_movements VALUES (NULL, ?, 'entry', ?, ?)",
            (product, quantity, reason),
        )
        conn.commit()
        row = conn.execute("SELECT * FROM inventory WHERE product = ?", (product,)).fetchone()
        conn.close()
        return self._success({"product": dict(row)}) if row else self._error("No encontrado")

    async def _remove_stock(self, product: str, quantity: int, reason: str) -> dict[str, Any]:
        conn = self._get_conn()
        row = conn.execute("SELECT * FROM inventory WHERE product = ?", (product,)).fetchone()
        if not row or row["current_stock"] < quantity:
            conn.close()
            return self._error("Stock insuficiente")
        conn.execute(
            "UPDATE inventory SET current_stock = current_stock - ? "
            "WHERE product = ?",
            (quantity, product),
        )
        conn.execute(
            "INSERT INTO inventory_movements VALUES (NULL, ?, 'exit', ?, ?)",
            (product, quantity, reason),
        )
        conn.commit()
        row = conn.execute("SELECT * FROM inventory WHERE product = ?", (product,)).fetchone()
        conn.close()
        return self._success({"product": dict(row)})

    async def _check_alerts(self) -> dict[str, Any]:
        conn = self._get_conn()
        rows = conn.execute("SELECT * FROM inventory WHERE current_stock <= min_stock").fetchall()
        conn.close()
        return self._success({"alerts": [dict(r) for r in rows]})
