"""
Session manager — inspired by Hermes + OpenClaw session patterns.

Features:
  - FTS5 full-text search across all sessions
  - Session branching (fork from current point)
  - Checkpoint/rollback
  - Auto-save on exit
  - Cross-session memory search
"""

from __future__ import annotations

import json
import logging
import sqlite3
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

log = logging.getLogger("cogman.session")

_COGMAN_HOME = Path.home() / ".cogman"
_SESSIONS_DIR = _COGMAN_HOME / "sessions"
_DB_PATH = _COGMAN_HOME / "sessions.db"


@dataclass
class Session:
    id: str
    title: str = ""
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    parent_id: Optional[str] = None  # for branches
    messages: List[Dict] = field(default_factory=list)
    checkpoints: List[Dict] = field(default_factory=list)  # rollback points


class SessionManager:
    """Manages session lifecycle with FTS5 search and branching."""

    def __init__(self, db_path: Optional[Path] = None):
        self._db_path = str(db_path or _DB_PATH)
        self._current_session: Optional[Session] = None
        _SESSIONS_DIR.mkdir(parents=True, exist_ok=True)
        _COGMAN_HOME.mkdir(parents=True, exist_ok=True)
        self._db = sqlite3.connect(self._db_path, check_same_thread=False)
        self._init_db()
        self.new_session()

    def _init_db(self):
        self._db.executescript("""
            CREATE TABLE IF NOT EXISTS sessions (
                id TEXT PRIMARY KEY,
                title TEXT,
                created_at REAL,
                updated_at REAL,
                parent_id TEXT,
                data TEXT
            );

            CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT,
                role TEXT,
                content TEXT,
                timestamp REAL,
                FOREIGN KEY (session_id) REFERENCES sessions(id)
            );

            CREATE VIRTUAL TABLE IF NOT EXISTS messages_fts USING fts5(
                content,
                session_id UNINDEXED,
                role UNINDEXED,
                content='messages',
                content_rowid='id'
            );

            CREATE TRIGGER IF NOT EXISTS messages_ai AFTER INSERT ON messages BEGIN
                INSERT INTO messages_fts(rowid, content, session_id, role)
                VALUES (new.id, new.content, new.session_id, new.role);
            END;

            CREATE TRIGGER IF NOT EXISTS messages_ad AFTER DELETE ON messages BEGIN
                INSERT INTO messages_fts(messages_fts, rowid, content, session_id, role)
                VALUES ('delete', old.id, old.content, old.session_id, old.role);
            END;
        """)
        self._db.commit()

    # ── Session lifecycle ─────────────────────────────────────────────────────

    def new_session(self, title: str = "") -> Session:
        """Start a new session."""
        session = Session(
            id=str(uuid.uuid4())[:8],
            title=title or f"Session {time.strftime('%Y-%m-%d %H:%M')}",
            created_at=time.time(),
            updated_at=time.time(),
        )
        self._current_session = session
        self._save_session(session)
        log.info("New session: %s", session.id)
        return session

    @property
    def current(self) -> Optional[Session]:
        return self._current_session

    @property
    def session_id(self) -> Optional[str]:
        return self._current_session.id if self._current_session else None

    def _save_session(self, session: Session):
        self._db.execute(
            """INSERT OR REPLACE INTO sessions
               (id, title, created_at, updated_at, parent_id, data)
               VALUES (?,?,?,?,?,?)""",
            (session.id, session.title, session.created_at, session.updated_at,
             session.parent_id, json.dumps({"checkpoints": session.checkpoints})),
        )
        self._db.commit()

    # ── Message tracking ──────────────────────────────────────────────────────

    def add_message(self, role: str, content: str):
        """Track a message in the current session (for FTS indexing)."""
        if not self._current_session:
            return
        sid = self._current_session.id
        self._db.execute(
            "INSERT INTO messages (session_id, role, content, timestamp) VALUES (?,?,?,?)",
            (sid, role, content, time.time()),
        )
        self._db.commit()
        self._current_session.updated_at = time.time()

    # ── FTS Search ────────────────────────────────────────────────────────────

    def search(self, query: str, limit: int = 10) -> List[Dict]:
        """Full-text search across all session messages."""
        try:
            cur = self._db.execute(
                """SELECT m.session_id, m.role, m.content, m.timestamp,
                          snippet(messages_fts, 0, '<b>', '</b>', '...', 20) AS snippet
                   FROM messages_fts
                   JOIN messages m ON messages_fts.rowid = m.id
                   WHERE messages_fts MATCH ?
                   ORDER BY rank
                   LIMIT ?""",
                (query, limit),
            )
            rows = cur.fetchall()
            return [
                {
                    "session_id": r[0],
                    "role": r[1],
                    "content": r[2],
                    "timestamp": r[3],
                    "snippet": r[4],
                }
                for r in rows
            ]
        except Exception as e:
            log.error("FTS search failed: %s", e)
            # Fallback to LIKE
            try:
                cur = self._db.execute(
                    "SELECT session_id, role, content, timestamp FROM messages "
                    "WHERE content LIKE ? ORDER BY timestamp DESC LIMIT ?",
                    (f"%{query}%", limit),
                )
                return [{"session_id": r[0], "role": r[1], "content": r[2],
                         "timestamp": r[3], "snippet": r[2][:100]} for r in cur.fetchall()]
            except Exception:
                return []

    # ── Branching ─────────────────────────────────────────────────────────────

    def branch(self, name: Optional[str] = None) -> str:
        """Fork the current session into a new branch. Returns new session ID."""
        if not self._current_session:
            return "No active session."

        parent = self._current_session
        branch = Session(
            id=str(uuid.uuid4())[:8],
            title=name or f"Branch of {parent.title}",
            created_at=time.time(),
            updated_at=time.time(),
            parent_id=parent.id,
        )

        # Copy messages from parent
        cur = self._db.execute(
            "SELECT role, content, timestamp FROM messages WHERE session_id=? ORDER BY timestamp",
            (parent.id,),
        )
        for role, content, ts in cur.fetchall():
            self._db.execute(
                "INSERT INTO messages (session_id, role, content, timestamp) VALUES (?,?,?,?)",
                (branch.id, role, content, ts),
            )
        self._db.commit()

        self._current_session = branch
        self._save_session(branch)
        log.info("Branched session %s → %s", parent.id, branch.id)
        return branch.id

    # ── Checkpoints / Rollback ────────────────────────────────────────────────

    def checkpoint(self, label: str = "") -> int:
        """Save a checkpoint at current message count."""
        if not self._current_session:
            return 0
        cur = self._db.execute(
            "SELECT COUNT(*) FROM messages WHERE session_id=?",
            (self._current_session.id,),
        )
        count = cur.fetchone()[0]
        cp = {
            "index": len(self._current_session.checkpoints),
            "label": label or f"Checkpoint {len(self._current_session.checkpoints)+1}",
            "message_count": count,
            "timestamp": time.time(),
        }
        self._current_session.checkpoints.append(cp)
        self._save_session(self._current_session)
        return cp["index"]

    def rollback(self, args: str = "") -> str:
        """List checkpoints or rollback to one."""
        if not self._current_session:
            return "No active session."

        checkpoints = self._current_session.checkpoints
        if not args or args.lower() == "list":
            if not checkpoints:
                return "No checkpoints. Save one first."
            lines = ["Checkpoints:"]
            for cp in checkpoints:
                ts = time.strftime("%H:%M:%S", time.localtime(cp["timestamp"]))
                lines.append(f"  [{cp['index']}] {cp['label']} — {ts} ({cp['message_count']} msgs)")
            return "\n".join(lines)

        try:
            idx = int(args)
        except ValueError:
            return f"Invalid checkpoint number: {args}"

        if idx < 0 or idx >= len(checkpoints):
            return f"Checkpoint {idx} not found. Valid: 0–{len(checkpoints)-1}"

        cp = checkpoints[idx]
        # Delete messages after checkpoint
        cur = self._db.execute(
            "SELECT id FROM messages WHERE session_id=? ORDER BY timestamp",
            (self._current_session.id,),
        )
        all_ids = [r[0] for r in cur.fetchall()]
        to_delete = all_ids[cp["message_count"]:]
        if to_delete:
            self._db.execute(
                f"DELETE FROM messages WHERE id IN ({','.join('?' * len(to_delete))})",
                to_delete,
            )
            self._db.commit()
        # Trim checkpoints list
        self._current_session.checkpoints = checkpoints[:idx+1]
        self._save_session(self._current_session)
        return f"Rolled back to checkpoint {idx}: {cp['label']} ({cp['message_count']} messages)"

    # ── Session list ──────────────────────────────────────────────────────────

    def list_sessions(self, limit: int = 20) -> List[Dict]:
        cur = self._db.execute(
            "SELECT id, title, created_at, updated_at, parent_id FROM sessions "
            "ORDER BY updated_at DESC LIMIT ?",
            (limit,),
        )
        return [
            {"id": r[0], "title": r[1], "created_at": r[2], "updated_at": r[3], "parent_id": r[4]}
            for r in cur.fetchall()
        ]

    def load_session(self, session_id: str) -> Optional[Session]:
        cur = self._db.execute(
            "SELECT id, title, created_at, updated_at, parent_id, data FROM sessions WHERE id=?",
            (session_id,),
        )
        row = cur.fetchone()
        if not row:
            return None
        data = json.loads(row[5]) if row[5] else {}
        return Session(
            id=row[0], title=row[1], created_at=row[2], updated_at=row[3],
            parent_id=row[4], checkpoints=data.get("checkpoints", []),
        )

    def auto_title(self, first_message: str) -> str:
        """Generate a short title from the first user message."""
        words = first_message.split()[:6]
        return " ".join(words).strip(".,!?")
