import hashlib
import json
import logging
import sqlite3
import os
from datetime import datetime, timedelta, timezone

from src import config

logger = logging.getLogger(__name__)

MONTHLY_DOCS_FILE = os.path.join(config.DATA_DIR, "monthly_docs.json")


def _ensure_db() -> None:
    os.makedirs(config.DATA_DIR, exist_ok=True)


def _get_conn() -> sqlite3.Connection:
    _ensure_db()
    conn = sqlite3.connect(config.DB_PATH)
    conn.execute(
        "CREATE TABLE IF NOT EXISTS seen_urls ("
        "  url_hash TEXT PRIMARY KEY,"
        "  seen_at TEXT NOT NULL"
        ")"
    )
    conn.execute(
        "CREATE TABLE IF NOT EXISTS monthly_docs ("
        "  year_month TEXT PRIMARY KEY,"
        "  document_id TEXT NOT NULL,"
        "  document_url TEXT NOT NULL"
        ")"
    )
    conn.commit()
    return conn


def _read_monthly_docs_file() -> dict:
    """Read monthly docs from JSON file (persisted in repo across CI runs)."""
    if not os.path.exists(MONTHLY_DOCS_FILE):
        return {}
    try:
        with open(MONTHLY_DOCS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        logger.warning("Failed to read monthly_docs.json", exc_info=True)
        return {}


def _write_monthly_docs_file(data: dict) -> None:
    """Write monthly docs to JSON file."""
    _ensure_db()
    try:
        with open(MONTHLY_DOCS_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception:
        logger.warning("Failed to write monthly_docs.json", exc_info=True)


def is_seen(url: str) -> bool:
    url_hash = hashlib.sha256(url.encode()).hexdigest()
    cutoff = (datetime.now(timezone.utc) - timedelta(days=config.DEDUP_DAYS)).isoformat()
    try:
        conn = _get_conn()
        row = conn.execute(
            "SELECT 1 FROM seen_urls WHERE url_hash = ? AND seen_at >= ?",
            (url_hash, cutoff),
        ).fetchone()
        return row is not None
    except Exception:
        logger.warning("Dedup check failed for %s", url, exc_info=True)
        return False


def mark_seen(url: str) -> None:
    url_hash = hashlib.sha256(url.encode()).hexdigest()
    now = datetime.now(timezone.utc).isoformat()
    try:
        conn = _get_conn()
        conn.execute(
            "INSERT OR REPLACE INTO seen_urls (url_hash, seen_at) VALUES (?, ?)",
            (url_hash, now),
        )
        conn.commit()
    except Exception:
        logger.warning("Dedup mark failed for %s", url, exc_info=True)


def filter_duplicates(items: list) -> list:
    """Filter out previously seen items, mark the new ones as seen."""
    fresh: list = []
    for item in items:
        if not is_seen(item.url):
            fresh.append(item)
    removed = len(items) - len(fresh)
    if removed > 0:
        logger.info("Dedup: removed %d already-seen items", removed)
    return fresh


def get_monthly_doc(year_month: str) -> tuple[str, str] | None:
    """Return (document_id, document_url) for the given month, or None.

    Checks JSON file first (persisted in repo), then falls back to SQLite.
    """
    # Primary: JSON file (persists across CI runs via repo)
    docs = _read_monthly_docs_file()
    if year_month in docs:
        entry = docs[year_month]
        return (entry["document_id"], entry["document_url"])

    # Fallback: SQLite (local dev)
    try:
        conn = _get_conn()
        row = conn.execute(
            "SELECT document_id, document_url FROM monthly_docs WHERE year_month = ?",
            (year_month,),
        ).fetchone()
        if row:
            # Sync to JSON file
            docs[year_month] = {"document_id": row[0], "document_url": row[1]}
            _write_monthly_docs_file(docs)
            return (row[0], row[1])
    except Exception:
        logger.warning("Failed to get monthly doc from SQLite for %s", year_month, exc_info=True)

    return None


def save_monthly_doc(year_month: str, document_id: str, document_url: str) -> None:
    """Persist the monthly document ID to both JSON file (primary) and SQLite."""
    # Write to JSON file
    docs = _read_monthly_docs_file()
    docs[year_month] = {"document_id": document_id, "document_url": document_url}
    _write_monthly_docs_file(docs)

    # Also write to SQLite
    try:
        conn = _get_conn()
        conn.execute(
            "INSERT OR REPLACE INTO monthly_docs (year_month, document_id, document_url) VALUES (?, ?, ?)",
            (year_month, document_id, document_url),
        )
        conn.commit()
    except Exception:
        logger.warning("Failed to save monthly doc to SQLite for %s", year_month, exc_info=True)

    logger.info("Saved monthly doc for %s: %s", year_month, document_url)
