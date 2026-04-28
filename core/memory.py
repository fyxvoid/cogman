import json
import sqlite3
import time
import logging
from typing import List, Dict, Optional
import core.config as _cfg
from core.config import MEMORY_COLLECTION, MAX_SHORT_TERM, TOP_K_MEMORIES

log = logging.getLogger("cogman.memory")


class ShortTermMemory:
    """In-process conversation ring buffer."""

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


class LongTermMemory:
    """SQLite-backed persistent memory + optional ChromaDB vector search."""

    def __init__(self, db_path: str = None):
        self._db = sqlite3.connect(db_path or _cfg.MEMORY_DB_PATH, check_same_thread=False)
        self._init_db()
        self._chroma = None
        self._collection = None
        self._try_init_chroma()

    def _init_db(self):
        self._db.execute("""
            CREATE TABLE IF NOT EXISTS memories (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp REAL,
                category TEXT,
                content TEXT,
                metadata TEXT
            )
        """)
        self._db.execute("""
            CREATE TABLE IF NOT EXISTS preferences (
                key TEXT PRIMARY KEY,
                value TEXT,
                updated REAL
            )
        """)
        self._db.commit()

    def _try_init_chroma(self):
        try:
            import chromadb
            client = chromadb.PersistentClient(path=_cfg.CHROMA_PATH)
            self._collection = client.get_or_create_collection(
                name=MEMORY_COLLECTION,
                metadata={"hnsw:space": "cosine"},
            )
            self._chroma = client
            log.info("ChromaDB vector memory initialized")
        except ImportError:
            log.warning("chromadb not installed — vector search disabled")
        except Exception as e:
            log.warning("ChromaDB init failed: %s", e)

    def save(self, content: str, category: str = "general", metadata: dict = None):
        ts = time.time()
        meta_str = json.dumps(metadata or {})
        cur = self._db.execute(
            "INSERT INTO memories (timestamp, category, content, metadata) VALUES (?,?,?,?)",
            (ts, category, content, meta_str),
        )
        self._db.commit()
        mem_id = str(cur.lastrowid)

        if self._collection is not None:
            try:
                self._collection.add(documents=[content], ids=[mem_id], metadatas=[{"category": category}])
            except Exception as e:
                log.debug("Chroma add failed: %s", e)

    def search(self, query: str, top_k: int = TOP_K_MEMORIES) -> List[str]:
        if self._collection is not None:
            try:
                results = self._collection.query(query_texts=[query], n_results=top_k)
                docs = results.get("documents", [[]])[0]
                if docs:
                    return docs
            except Exception as e:
                log.debug("Chroma search failed: %s", e)

        # Fallback: simple LIKE search
        cur = self._db.execute(
            "SELECT content FROM memories WHERE content LIKE ? ORDER BY timestamp DESC LIMIT ?",
            (f"%{query[:50]}%", top_k),
        )
        return [row[0] for row in cur.fetchall()]

    def set_preference(self, key: str, value: str):
        self._db.execute(
            "INSERT OR REPLACE INTO preferences (key, value, updated) VALUES (?,?,?)",
            (key, value, time.time()),
        )
        self._db.commit()

    def get_preference(self, key: str, default: str = "") -> str:
        cur = self._db.execute("SELECT value FROM preferences WHERE key=?", (key,))
        row = cur.fetchone()
        return row[0] if row else default

    def recent(self, n: int = 10, category: str = None) -> List[Dict]:
        if category:
            cur = self._db.execute(
                "SELECT timestamp, category, content FROM memories WHERE category=? ORDER BY timestamp DESC LIMIT ?",
                (category, n),
            )
        else:
            cur = self._db.execute(
                "SELECT timestamp, category, content FROM memories ORDER BY timestamp DESC LIMIT ?",
                (n,),
            )
        return [{"timestamp": r[0], "category": r[1], "content": r[2]} for r in cur.fetchall()]


class Memory:
    """Unified memory interface."""

    def __init__(self):
        self.short = ShortTermMemory()
        self.long = LongTermMemory()

    def add_message(self, role: str, content: str):
        self.short.add(role, content)

    def remember(self, content: str, category: str = "general", metadata: dict = None):
        self.long.save(content, category, metadata)

    def recall(self, query: str) -> List[str]:
        return self.long.search(query)

    def get_context(self) -> List[Dict]:
        return self.short.get()

    def set_pref(self, key: str, value: str):
        self.long.set_preference(key, value)

    def get_pref(self, key: str, default: str = "") -> str:
        return self.long.get_preference(key, default)
