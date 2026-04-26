"""
logTable.py — prints every SQLite table in pawpal.db to the terminal.

Usage:
    python scripts/logTable.py
    python scripts/logTable.py users          # one specific table
    python scripts/logTable.py users tasks    # two specific tables
"""

import sqlite3
import sys
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent.parent / "pawpal.db"


def _col_widths(headers: list[str], rows: list[tuple]) -> list[int]:
    widths = [len(h) for h in headers]
    for row in rows:
        for i, cell in enumerate(row):
            widths[i] = max(widths[i], len(str(cell) if cell is not None else "NULL"))
    return widths


def print_table(con: sqlite3.Connection, table: str) -> None:
    cur = con.execute(f"SELECT * FROM {table}")
    rows = cur.fetchall()
    headers = [d[0] for d in cur.description]

    widths = _col_widths(headers, rows)
    divider = "+-" + "-+-".join("-" * w for w in widths) + "-+"
    row_fmt = "| " + " | ".join(f"{{:<{w}}}" for w in widths) + " |"

    print(f"\n{'─' * 4} {table} {'─' * max(0, 60 - len(table))}")
    print(f"  {len(rows)} row{'s' if len(rows) != 1 else ''}\n")
    print(divider)
    print(row_fmt.format(*headers))
    print(divider)
    if rows:
        for row in rows:
            print(row_fmt.format(*("NULL" if v is None else v for v in row)))
    else:
        empty_msg = "(empty table)"
        total_width = sum(widths) + 3 * (len(widths) - 1)
        print(f"| {empty_msg:<{total_width}} |")
    print(divider)


def main() -> None:
    if not DB_PATH.exists():
        print(f"Database not found: {DB_PATH}")
        print("Run the app first to initialise pawpal.db.")
        sys.exit(1)

    con = sqlite3.connect(DB_PATH)

    all_tables = [
        r[0] for r in con.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
        ).fetchall()
    ]

    requested = sys.argv[1:] if len(sys.argv) > 1 else all_tables

    for table in requested:
        if table not in all_tables:
            print(f"\nUnknown table: '{table}'. Available: {', '.join(all_tables)}")
            continue
        print_table(con, table)

    con.close()
    print()


if __name__ == "__main__":
    main()
