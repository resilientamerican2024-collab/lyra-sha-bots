#!/usr/bin/env python3
"""
drafts_store.py — Shared store for AI-suggested reply drafts (Reddit, Yelp, etc.).

Platforms that cannot auto-post (Yelp) or that we keep human-in-the-loop
(Reddit, by default) write their suggested replies here. The Flask app exposes
them at /drafts so Ingrid can review, copy, and post them manually.

Uses the same SQLite file as the review_request_bot so everything lives together.
"""

import logging
import os
import sqlite3
from datetime import datetime
from pathlib import Path

HERE    = Path(__file__).parent
# Match review_request_bot: same DB file on the Railway volume so drafts persist.
DATA_DIR = Path(os.environ.get("RAILWAY_VOLUME_MOUNT_PATH", str(HERE)))
DB_PATH = DATA_DIR / "review_requests.db"

log = logging.getLogger(__name__)


def init_drafts_db():
    with sqlite3.connect(str(DB_PATH)) as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS reply_drafts (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                platform        TEXT NOT NULL,          -- reddit | yelp
                client          TEXT DEFAULT '',        -- which business this is for
                source_id       TEXT NOT NULL,          -- platform id of the review/comment (dedupe key)
                source_url      TEXT DEFAULT '',        -- direct link to the item
                author          TEXT DEFAULT '',
                original_text   TEXT DEFAULT '',        -- the review/comment we're replying to
                suggested_reply TEXT NOT NULL,
                status          TEXT DEFAULT 'pending',  -- pending | posted | dismissed
                created_at      TEXT DEFAULT (datetime('now','localtime'))
            );
            CREATE UNIQUE INDEX IF NOT EXISTS idx_drafts_source
                ON reply_drafts (platform, source_id);
        """)
    log.info("Drafts table ready.")


def already_drafted(platform: str, source_id: str) -> bool:
    with sqlite3.connect(str(DB_PATH)) as conn:
        row = conn.execute(
            "SELECT 1 FROM reply_drafts WHERE platform=? AND source_id=? LIMIT 1",
            (platform, source_id),
        ).fetchone()
    return row is not None


def save_draft(platform, client, source_id, suggested_reply,
               source_url="", author="", original_text=""):
    """Insert a draft. Ignores duplicates (same platform+source_id)."""
    try:
        with sqlite3.connect(str(DB_PATH)) as conn:
            conn.execute(
                """INSERT OR IGNORE INTO reply_drafts
                   (platform, client, source_id, source_url, author,
                    original_text, suggested_reply, created_at)
                   VALUES (?,?,?,?,?,?,?,?)""",
                (platform, client, source_id, source_url, author,
                 original_text, suggested_reply,
                 datetime.now().strftime("%Y-%m-%d %H:%M:%S")),
            )
        return True
    except Exception as e:
        log.warning(f"save_draft failed: {e}")
        return False


def list_drafts(status="pending", limit=200):
    with sqlite3.connect(str(DB_PATH)) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT * FROM reply_drafts WHERE status=? ORDER BY id DESC LIMIT ?",
            (status, limit),
        ).fetchall()
    return [dict(r) for r in rows]


def set_status(draft_id: int, status: str):
    with sqlite3.connect(str(DB_PATH)) as conn:
        conn.execute("UPDATE reply_drafts SET status=? WHERE id=?", (status, draft_id))
