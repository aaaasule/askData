"""Create a tiny SQLite business database for the AskData curl demo.

Usage:
    python scripts/seed_sample_sqlite.py /tmp/askdata-orders.db
"""

from __future__ import annotations

import sqlite3
import sys
from pathlib import Path


def main() -> None:
    dest = Path(sys.argv[1] if len(sys.argv) > 1 else "samples/orders.db")
    dest.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(dest)
    connection.execute("DROP TABLE IF EXISTS orders")
    connection.execute(
        "CREATE TABLE orders ("
        "id INTEGER PRIMARY KEY, name TEXT, amount REAL, created_at TEXT)"
    )
    connection.executemany(
        "INSERT INTO orders (id, name, amount, created_at) VALUES (?, ?, ?, ?)",
        [
            (1, "alpha", 10.5, "2026-01-01"),
            (2, "alpha", 7.0, "2026-01-02"),
            (3, "beta", 3.5, "2026-01-03"),
        ],
    )
    connection.commit()
    connection.close()
    print(dest.resolve())


if __name__ == "__main__":
    main()
