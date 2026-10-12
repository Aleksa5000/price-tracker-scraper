import csv
import sqlite3
from datetime import datetime, timezone

SCHEMA = """
CREATE TABLE IF NOT EXISTS price_history (
    id INTEGER PRIMARY KEY,
    run_id INTEGER NOT NULL,
    scraped_at TEXT NOT NULL,
    url TEXT NOT NULL,
    title TEXT NOT NULL,
    price REAL NOT NULL,
    availability TEXT,
    rating INTEGER
);
CREATE INDEX IF NOT EXISTS idx_url ON price_history (url, run_id);
"""


def connect(path):
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA)
    return conn


def save_run(conn, products):
    run_id = (conn.execute("SELECT MAX(run_id) FROM price_history").fetchone()[0] or 0) + 1
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    conn.executemany(
        "INSERT INTO price_history (run_id, scraped_at, url, title, price, availability, rating)"
        " VALUES (?, ?, ?, ?, ?, ?, ?)",
        [(run_id, now, p["url"], p["title"], p["price"], p["availability"], p["rating"]) for p in products],
    )
    conn.commit()
    return run_id


def price_changes(conn):
    """Products in the latest run whose price differs from their previous recorded price."""
    rows = conn.execute("""
        SELECT * FROM (
            SELECT title, url, run_id, price,
                   LAG(price) OVER (PARTITION BY url ORDER BY run_id) AS old_price
            FROM price_history)
        WHERE run_id = (SELECT MAX(run_id) FROM price_history)
          AND old_price IS NOT NULL AND price != old_price
    """).fetchall()
    return [
        {**dict(r), "pct": round((r["price"] - r["old_price"]) / r["old_price"] * 100, 1)}
        for r in rows
    ]


def export_csv(conn, path):
    rows = conn.execute(
        "SELECT title, price, availability, rating, url, scraped_at FROM price_history"
        " WHERE run_id = (SELECT MAX(run_id) FROM price_history) ORDER BY title"
    ).fetchall()
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["title", "price", "availability", "rating", "url", "scraped_at"])
        w.writerows(tuple(r) for r in rows)
    return len(rows)
