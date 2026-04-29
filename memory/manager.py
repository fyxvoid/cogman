"""
Unified memory manager — short-term + long-term + session + context.

Inspired by Hermes Agent's MemoryManager with pluggable providers.
"""
from __future__ import annotations

import json
import logging
import sqlite3
import time
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Dict, List, Optional

import sys, os
sys.path.insert(0, str(Path(__file__).parent.parent))

import core.config as _cfg
from core.config import MEMORY_COLLECTION, MAX_SHORT_TERM, TOP_K_MEMORIES

log = logging.getLogger("cogman.memory")


# ── MemoryProvider ABC ────────────────────────────────────────────────────────

class MemoryProvider(ABC):
    name: str = "base"

    @abstractmethod
    def save(self, content: str, category: str = "general", metadata: Dict = None): ...

    @abstractmethod
    def search(self, query: str, top_k: int = 5) -> List[str]: ...

    def build_system_prompt(self) -> str:
        return ""


# ── Short-term ────────────────────────────────────────────────────────────────

class ShortTermMemory:
    def __init__(self, max_size: int = MAX_SHORT_TERM):
        self.max_size = max_size
        self._messages: List[Dict] = []

    def add(self, role: str, content: str):
        self._messages.append({"role": role, "content": content})
        if len(self._messages) > self.max_size:
            self._messages = self._messages[-self.max_size:]

    def get(self) -> List[Dict]:
        return list(self._messages)

    def clear(self):
        self._messages.clear()

    def __len__(self):
        return len(self._messages)


# ── Long-term (FTS5 + optional ChromaDB) ─────────────────────────────────────

class LongTermMemory:
    def __init__(self, db_path: str = None):
        self._db = sqlite3.connect(db_path or _cfg.MEMORY_DB_PATH, check_same_thread=False)
        self._db.row_factory = sqlite3.Row
        self._init_db()
        self._chroma = None
        self._collection = None
        self._try_init_chroma()
        self._providers: List[MemoryProvider] = []

    def _init_db(self):
        self._db.executescript("""
            CREATE TABLE IF NOT EXISTS memories (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp REAL, category TEXT, content TEXT, metadata TEXT
            );
            CREATE VIRTUAL TABLE IF NOT EXISTS memories_fts USING fts5(
                content, category UNINDEXED,
                content='memories', content_rowid='id'
            );
            CREATE TRIGGER IF NOT EXISTS memories_ai AFTER INSERT ON memories BEGIN
                INSERT INTO memories_fts(rowid, content, category) VALUES (new.id, new.content, new.category);
            END;
            CREATE TRIGGER IF NOT EXISTS memories_ad AFTER DELETE ON memories BEGIN
                INSERT INTO memories_fts(memories_fts, rowid, content, category)
                VALUES ('delete', old.id, old.content, old.category);
            END;
            CREATE TABLE IF NOT EXISTS preferences (key TEXT PRIMARY KEY, value TEXT, updated REAL);
            CREATE TABLE IF NOT EXISTS tool_stats (
                tool_name TEXT PRIMARY KEY, success_count INT DEFAULT 0,
                fail_count INT DEFAULT 0, last_used REAL
            );
            CREATE TABLE IF NOT EXISTS task_patterns (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                pattern TEXT, tool_sequence TEXT, count INT DEFAULT 1,
                last_seen REAL, created REAL
            );
        """)
        self._db.commit()

    def _try_init_chroma(self):
        try:
            import chromadb
            client = chromadb.PersistentClient(path=_cfg.CHROMA_PATH)
            self._collection = client.get_or_create_collection(
                name=MEMORY_COLLECTION, metadata={"hnsw:space": "cosine"},
            )
            self._chroma = client
            log.info("ChromaDB vector memory initialized")
        except ImportError:
            log.debug("chromadb not installed — using FTS5 only")
        except Exception as e:
            log.warning("ChromaDB init failed: %s", e)

    def add_provider(self, provider: MemoryProvider):
        self._providers = [p for p in self._providers if p.name != provider.name]
        self._providers.append(provider)

    def save(self, content: str, category: str = "general", metadata: Dict = None):
        ts = time.time()
        meta_str = json.dumps(metadata or {})
        cur = self._db.execute(
            "INSERT INTO memories (timestamp, category, content, metadata) VALUES (?,?,?,?)",
            (ts, category, content, meta_str),
        )
        self._db.commit()
        mem_id = str(cur.lastrowid)
        if self._collection:
            try:
                self._collection.add(documents=[content], ids=[mem_id], metadatas=[{"category": category}])
            except Exception as e:
                log.debug("Chroma add failed: %s", e)
        for p in self._providers:
            try:
                p.save(content, category, metadata)
            except Exception as e:
                log.debug("Provider %s save failed: %s", p.name, e)

    def search(self, query: str, top_k: int = TOP_K_MEMORIES) -> List[str]:
        if self._collection:
            try:
                results = self._collection.query(query_texts=[query], n_results=top_k)
                docs = results.get("documents", [[]])[0]
                if docs:
                    return docs
            except Exception:
                pass
        try:
            cur = self._db.execute(
                "SELECT m.content FROM memories_fts JOIN memories m ON memories_fts.rowid = m.id "
                "WHERE memories_fts MATCH ? ORDER BY rank LIMIT ?", (query, top_k),
            )
            results = [r[0] for r in cur.fetchall()]
            if results:
                return results
        except Exception:
            pass
        cur = self._db.execute(
            "SELECT content FROM memories WHERE content LIKE ? ORDER BY timestamp DESC LIMIT ?",
            (f"%{query[:50]}%", top_k),
        )
        return [r[0] for r in cur.fetchall()]

    def delete_matching(self, query: str) -> int:
        try:
            cur = self._db.execute(
                "SELECT memories.id FROM memories_fts JOIN memories ON memories_fts.rowid = memories.id "
                "WHERE memories_fts MATCH ?", (query,),
            )
            ids = [r[0] for r in cur.fetchall()]
        except Exception:
            cur = self._db.execute("SELECT id FROM memories WHERE content LIKE ?", (f"%{query}%",))
            ids = [r[0] for r in cur.fetchall()]
        if not ids:
            return 0
        ph = ",".join("?" * len(ids))
        self._db.execute(f"DELETE FROM memories WHERE id IN ({ph})", ids)
        self._db.commit()
        return len(ids)

    def set_preference(self, key: str, value: str):
        self._db.execute("INSERT OR REPLACE INTO preferences (key, value, updated) VALUES (?,?,?)",
                         (key, value, time.time()))
        self._db.commit()

    def get_preference(self, key: str, default: str = "") -> str:
        cur = self._db.execute("SELECT value FROM preferences WHERE key=?", (key,))
        row = cur.fetchone()
        return row[0] if row else default

    def record_tool_use(self, tool_name: str, success: bool):
        self._db.execute("""
            INSERT INTO tool_stats (tool_name, success_count, fail_count, last_used)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(tool_name) DO UPDATE SET
              success_count = success_count + ?,
              fail_count = fail_count + ?,
              last_used = ?
        """, (tool_name, 1 if success else 0, 0 if success else 1, time.time(),
              1 if success else 0, 0 if success else 1, time.time()))
        self._db.commit()

    def record_task_pattern(self, pattern: str, tool_sequence: List[str]) -> int:
        seq_str = ",".join(tool_sequence)
        cur = self._db.execute(
            "SELECT id, count FROM task_patterns WHERE pattern=?", (pattern[:200],)
        )
        row = cur.fetchone()
        if row:
            self._db.execute(
                "UPDATE task_patterns SET count=count+1, last_seen=?, tool_sequence=? WHERE id=?",
                (time.time(), seq_str, row[0]),
            )
            self._db.commit()
            return row[1] + 1
        else:
            self._db.execute(
                "INSERT INTO task_patterns (pattern, tool_sequence, count, last_seen, created) VALUES (?,?,1,?,?)",
                (pattern[:200], seq_str, time.time(), time.time()),
            )
            self._db.commit()
            return 1

    def get_frequent_patterns(self, min_count: int = 3, limit: int = 10) -> List[Dict]:
        cur = self._db.execute(
            "SELECT pattern, tool_sequence, count FROM task_patterns WHERE count>=? ORDER BY count DESC LIMIT ?",
            (min_count, limit),
        )
        return [{"pattern": r[0], "tool_sequence": r[1].split(","), "count": r[2]} for r in cur.fetchall()]

    def recent(self, n: int = 10, category: str = None) -> List[Dict]:
        if category:
            cur = self._db.execute(
                "SELECT timestamp, category, content FROM memories WHERE category=? ORDER BY timestamp DESC LIMIT ?",
                (category, n),
            )
        else:
            cur = self._db.execute(
                "SELECT timestamp, category, content FROM memories ORDER BY timestamp DESC LIMIT ?", (n,),
            )
        return [{"timestamp": r[0], "category": r[1], "content": r[2]} for r in cur.fetchall()]


# ── Unified Memory ────────────────────────────────────────────────────────────

class Memory:
    """Façade: short-term + long-term + session aware."""

    def __init__(self):
        self.short = ShortTermMemory()
        self.long = LongTermMemory()

    def add_message(self, role: str, content: str):
        self.short.add(role, content)

    def remember(self, content: str, category: str = "general", metadata: Dict = None):
        self.long.save(content, category, metadata)

    def recall(self, query: str) -> List[str]:
        return self.long.search(query)

    def get_context(self) -> List[Dict]:
        return self.short.get()

    def set_pref(self, key: str, value: str):
        self.long.set_preference(key, value)

    def get_pref(self, key: str, default: str = "") -> str:
        return self.long.get_preference(key, default)

    def clear_short(self):
        self.short.clear()
