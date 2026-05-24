from __future__ import annotations

import sqlite3
import sys
from pathlib import Path


def main() -> None:
    base_dir = Path(__file__).resolve().parents[1]

    if str(base_dir) not in sys.path:
        sys.path.insert(0, str(base_dir))

    from config import DATABASE_PATH

    migration_path = base_dir / "database" / "migrations" / "002_lightweight_analytics.sql"
    DATABASE_PATH.parent.mkdir(parents=True, exist_ok=True)

    with sqlite3.connect(DATABASE_PATH) as conn:
        conn.executescript(migration_path.read_text(encoding="utf-8"))
        conn.commit()

    print(f"Migration applied: {migration_path}")
    print(f"Database: {DATABASE_PATH}")


if __name__ == "__main__":
    main()
