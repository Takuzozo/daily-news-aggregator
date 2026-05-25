import hashlib
import logging
import sqlite3
import os
from datetime import datetime, timedelta, timezone

from src import config

logger = logging.getLogger(__name__)


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
    """Return (document_id, document_url) for the given month, or None."""
    try:
        conn = _get_conn()
        row = conn.execute(
            "SELECT document_id, document_url FROM monthly_docs WHERE year_month = ?",
            (year_month,),
        ).fetchone()
        return (row[0], row[1]) if row else None
    except Exception:
        logger.warning("Failed to get monthly doc for %s", year_month, exc_info=True)
        return None


def save_monthly_doc(year_month: str, document_id: str, document_url: str) -> None:
    """Persist the monthly document ID."""
    try:
        conn = _get_conn()
        conn.execute(
            "INSERT OR REPLACE INTO monthly_docs (year_month, document_id, document_url) VALUES (?, ?, ?)",
            (year_month, document_id, document_url),
        )
        conn.commit()
        logger.info("Saved monthly doc for %s: %s", year_month, document_url)
    except Exception:
        logger.warning("Failed to save monthly doc for %s", year_month, exc_info=True)
