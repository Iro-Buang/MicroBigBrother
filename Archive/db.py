# db.py (MicroBB v1 - minimal, content-only fields + state deltas)
from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any, Optional, List, Dict
import time


# -----------------------------
# Connection + PRAGMAs
# -----------------------------

def connect(db_path: str | Path) -> sqlite3.Connection:
    db_path = str(db_path)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row

    # Reasonable defaults for a local sim
    conn.execute("PRAGMA foreign_keys = ON;")
    conn.execute("PRAGMA journal_mode = WAL;")
    conn.execute("PRAGMA synchronous = NORMAL;")
    conn.execute("PRAGMA temp_store = MEMORY;")
    conn.execute("PRAGMA busy_timeout = 5000;")
    return conn


# -----------------------------
# Schema (minimal v1)
# -----------------------------

DDL_EVENTS = """
CREATE TABLE IF NOT EXISTS events (
    event_id     INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id   TEXT NOT NULL,
    turn_id      INTEGER NOT NULL,
    ts_unix      INTEGER NOT NULL,
    actor        TEXT NOT NULL,               -- system/world/human/anna/kevin
    event_type   TEXT NOT NULL,               -- move/talk/request/reject/task/etc
    content      TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_events_session_turn
ON events(session_id, turn_id);

CREATE INDEX IF NOT EXISTS idx_events_session_actor
ON events(session_id, actor);
"""

DDL_PERCEIVED = """
CREATE TABLE IF NOT EXISTS perceived_events (
    perceived_id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id   TEXT NOT NULL,
    turn_id      INTEGER NOT NULL,
    npc_id       TEXT NOT NULL,               -- anna/kevin/...
    event_id     INTEGER NOT NULL,
    content      TEXT NOT NULL,

    FOREIGN KEY(event_id) REFERENCES events(event_id)
        ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_perceived_session_turn_npc
ON perceived_events(session_id, turn_id, npc_id);

CREATE INDEX IF NOT EXISTS idx_perceived_event
ON perceived_events(event_id);
"""

DDL_EPISODES = """
CREATE TABLE IF NOT EXISTS episodes (
    episode_id   INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id   TEXT NOT NULL,
    turn_id      INTEGER NOT NULL,
    npc_id       TEXT NOT NULL,
    content      TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_episodes_session_npc_turn
ON episodes(session_id, npc_id, turn_id);
"""

DDL_SEMANTIC = """
CREATE TABLE IF NOT EXISTS semantic_memory (
    mem_id       INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id   TEXT NOT NULL,
    npc_id       TEXT NOT NULL,
    turn_id      INTEGER NOT NULL,

    scope        TEXT NOT NULL,               -- self/other_npc/world/goal/rule
    subject      TEXT NOT NULL,               -- kevin/anna/house/task/etc
    content      TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_semantic_session_npc_turn
ON semantic_memory(session_id, npc_id, turn_id);

CREATE INDEX IF NOT EXISTS idx_semantic_session_npc_scope_subject
ON semantic_memory(session_id, npc_id, scope, subject);
"""

# NEW: Minimal state delta log (v1)
DDL_STATE_DELTAS = """
CREATE TABLE IF NOT EXISTS state_deltas (
    delta_id    INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id  TEXT NOT NULL,
    turn_id     INTEGER NOT NULL,

    scope       TEXT NOT NULL,      -- world | npc
    owner_id    TEXT NOT NULL,      -- "world" or npc_id (anna/kevin)

    key         TEXT NOT NULL,      -- e.g. "location.anna", "task.clean_living_room.done"
    op          TEXT NOT NULL,      -- set | inc | append | remove
    content     TEXT NOT NULL       -- store primitives or JSON string
);

CREATE INDEX IF NOT EXISTS idx_state_session_turn
ON state_deltas(session_id, turn_id);

CREATE INDEX IF NOT EXISTS idx_state_session_owner
ON state_deltas(session_id, scope, owner_id);
"""

# Optional FTS (for “search my memories” later). OFF by default.
DDL_FTS = """
-- Episodes full-text search
CREATE VIRTUAL TABLE IF NOT EXISTS episodes_fts
USING fts5(
    session_id,
    npc_id,
    content,
    content='episodes',
    content_rowid='episode_id'
);

CREATE TRIGGER IF NOT EXISTS episodes_ai AFTER INSERT ON episodes BEGIN
  INSERT INTO episodes_fts(rowid, session_id, npc_id, content)
  VALUES (new.episode_id, new.session_id, new.npc_id, new.content);
END;

CREATE TRIGGER IF NOT EXISTS episodes_ad AFTER DELETE ON episodes BEGIN
  INSERT INTO episodes_fts(episodes_fts, rowid, session_id, npc_id, content)
  VALUES ('delete', old.episode_id, old.session_id, old.npc_id, old.content);
END;

CREATE TRIGGER IF NOT EXISTS episodes_au AFTER UPDATE ON episodes BEGIN
  INSERT INTO episodes_fts(episodes_fts, rowid, session_id, npc_id, content)
  VALUES ('delete', old.episode_id, old.session_id, old.npc_id, old.content);
  INSERT INTO episodes_fts(rowid, session_id, npc_id, content)
  VALUES (new.episode_id, new.session_id, new.npc_id, new.content);
END;


-- Semantic memory full-text search
CREATE VIRTUAL TABLE IF NOT EXISTS semantic_memory_fts
USING fts5(
    session_id,
    npc_id,
    scope,
    subject,
    content,
    content='semantic_memory',
    content_rowid='mem_id'
);

CREATE TRIGGER IF NOT EXISTS semantic_ai AFTER INSERT ON semantic_memory BEGIN
  INSERT INTO semantic_memory_fts(rowid, session_id, npc_id, scope, subject, content)
  VALUES (new.mem_id, new.session_id, new.npc_id, new.scope, new.subject, new.content);
END;

CREATE TRIGGER IF NOT EXISTS semantic_ad AFTER DELETE ON semantic_memory BEGIN
  INSERT INTO semantic_memory_fts(semantic_memory_fts, rowid, session_id, npc_id, scope, subject, content)
  VALUES ('delete', old.mem_id, old.session_id, old.npc_id, old.scope, old.subject, old.content);
END;

CREATE TRIGGER IF NOT EXISTS semantic_au AFTER UPDATE ON semantic_memory BEGIN
  INSERT INTO semantic_memory_fts(semantic_memory_fts, rowid, session_id, npc_id, scope, subject, content)
  VALUES ('delete', old.mem_id, old.session_id, old.npc_id, old.scope, old.subject, old.content);
  INSERT INTO semantic_memory_fts(rowid, session_id, npc_id, scope, subject, content)
  VALUES (new.mem_id, new.session_id, new.npc_id, new.scope, new.subject, new.content);
END;
"""


def init_db(conn: sqlite3.Connection, *, enable_fts: bool = False) -> None:
    """
    Initialize minimal MicroBB v1 tables.
    Set enable_fts=True if you want FTS5 search for episodes + semantic memory.
    """
    conn.executescript(DDL_EVENTS)
    conn.executescript(DDL_PERCEIVED)
    conn.executescript(DDL_EPISODES)
    conn.executescript(DDL_SEMANTIC)
    conn.executescript(DDL_STATE_DELTAS)

    if enable_fts:
        conn.executescript(DDL_FTS)

    conn.commit()


# -----------------------------
# Inserts (simple)
# -----------------------------

def now_unix() -> int:
    return int(time.time())


def add_event(
    conn: sqlite3.Connection,
    *,
    session_id: str,
    turn_id: int,
    actor: str,
    event_type: str,
    content: str,
    ts_unix: Optional[int] = None,
) -> int:
    ts_unix = now_unix() if ts_unix is None else int(ts_unix)
    cur = conn.execute(
        """
        INSERT INTO events(session_id, turn_id, ts_unix, actor, event_type, content)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (session_id, turn_id, ts_unix, actor, event_type, content),
    )
    conn.commit()
    return int(cur.lastrowid)


def add_perceived_event(
    conn: sqlite3.Connection,
    *,
    session_id: str,
    turn_id: int,
    npc_id: str,
    event_id: int,
    content: str,
) -> int:
    cur = conn.execute(
        """
        INSERT INTO perceived_events(session_id, turn_id, npc_id, event_id, content)
        VALUES (?, ?, ?, ?, ?)
        """,
        (session_id, turn_id, npc_id, event_id, content),
    )
    conn.commit()
    return int(cur.lastrowid)


def add_episode(
    conn: sqlite3.Connection,
    *,
    session_id: str,
    turn_id: int,
    npc_id: str,
    content: str,
) -> int:
    cur = conn.execute(
        """
        INSERT INTO episodes(session_id, turn_id, npc_id, content)
        VALUES (?, ?, ?, ?)
        """,
        (session_id, turn_id, npc_id, content),
    )
    conn.commit()
    return int(cur.lastrowid)


def add_semantic_memory(
    conn: sqlite3.Connection,
    *,
    session_id: str,
    npc_id: str,
    turn_id: int,
    scope: str,
    subject: str,
    content: str,
) -> int:
    cur = conn.execute(
        """
        INSERT INTO semantic_memory(session_id, npc_id, turn_id, scope, subject, content)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (session_id, npc_id, turn_id, scope, subject, content),
    )
    conn.commit()
    return int(cur.lastrowid)


def add_state_delta(
    conn: sqlite3.Connection,
    *,
    session_id: str,
    turn_id: int,
    scope: str,          # "world" | "npc"
    owner_id: str,       # "world" | npc_id (anna/kevin)
    key: str,            # "location.anna", "task.clean_living_room.done", "pending_talk.anna"
    op: str,             # "set" | "inc" | "append" | "remove"
    content: str,        # primitives or JSON string
) -> int:
    cur = conn.execute(
        """
        INSERT INTO state_deltas(session_id, turn_id, scope, owner_id, key, op, content)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (session_id, turn_id, scope, owner_id, key, op, content),
    )
    conn.commit()
    return int(cur.lastrowid)


# -----------------------------
# Retrieval (prompt building)
# -----------------------------

def get_recent_episodes(
    conn: sqlite3.Connection,
    *,
    session_id: str,
    npc_id: str,
    limit: int = 6,
) -> List[sqlite3.Row]:
    cur = conn.execute(
        """
        SELECT episode_id, session_id, turn_id, npc_id, content
        FROM episodes
        WHERE session_id = ? AND npc_id = ?
        ORDER BY turn_id DESC
        LIMIT ?
        """,
        (session_id, npc_id, int(limit)),
    )
    return list(cur.fetchall())[::-1]  # oldest -> newest


def get_recent_semantic_memory(
    conn: sqlite3.Connection,
    *,
    session_id: str,
    npc_id: str,
    limit: int = 10,
) -> List[sqlite3.Row]:
    cur = conn.execute(
        """
        SELECT mem_id, session_id, npc_id, turn_id, scope, subject, content
        FROM semantic_memory
        WHERE session_id = ? AND npc_id = ?
        ORDER BY turn_id DESC, mem_id DESC
        LIMIT ?
        """,
        (session_id, npc_id, int(limit)),
    )
    return list(cur.fetchall())[::-1]


def get_state_deltas(
    conn: sqlite3.Connection,
    *,
    session_id: str,
    scope: str,
    owner_id: str,
    since_turn: int = 0,
) -> List[sqlite3.Row]:
    cur = conn.execute(
        """
        SELECT delta_id, session_id, turn_id, scope, owner_id, key, op, content
        FROM state_deltas
        WHERE session_id = ? AND scope = ? AND owner_id = ? AND turn_id >= ?
        ORDER BY turn_id ASC, delta_id ASC
        """,
        (session_id, scope, owner_id, int(since_turn)),
    )
    return list(cur.fetchall())


def get_latest_state_deltas(
    conn: sqlite3.Connection,
    *,
    session_id: str,
    scope: str,
    owner_id: str,
    limit: int = 50,
) -> List[sqlite3.Row]:
    """
    Useful for debugging or building a tiny "recent state changes" block.
    This does NOT compute final state; it just returns recent deltas.
    """
    cur = conn.execute(
        """
        SELECT delta_id, session_id, turn_id, scope, owner_id, key, op, content
        FROM state_deltas
        WHERE session_id = ? AND scope = ? AND owner_id = ?
        ORDER BY turn_id DESC, delta_id DESC
        LIMIT ?
        """,
        (session_id, scope, owner_id, int(limit)),
    )
    return list(cur.fetchall())[::-1]


# -----------------------------
# Optional search (FTS)
# -----------------------------

def search_episodes(
    conn: sqlite3.Connection,
    *,
    session_id: str,
    npc_id: str,
    query: str,
    limit: int = 10,
) -> List[sqlite3.Row]:
    """
    Requires enable_fts=True at init.
    """
    cur = conn.execute(
        """
        SELECT e.episode_id, e.turn_id, e.content
        FROM episodes_fts f
        JOIN episodes e ON e.episode_id = f.rowid
        WHERE f.session_id = ? AND f.npc_id = ? AND episodes_fts MATCH ?
        ORDER BY rank
        LIMIT ?
        """,
        (session_id, npc_id, query, int(limit)),
    )
    return list(cur.fetchall())


def search_semantic_memory(
    conn: sqlite3.Connection,
    *,
    session_id: str,
    npc_id: str,
    query: str,
    limit: int = 10,
) -> List[sqlite3.Row]:
    """
    Requires enable_fts=True at init.
    """
    cur = conn.execute(
        """
        SELECT s.mem_id, s.turn_id, s.scope, s.subject, s.content
        FROM semantic_memory_fts f
        JOIN semantic_memory s ON s.mem_id = f.rowid
        WHERE f.session_id = ? AND f.npc_id = ? AND semantic_memory_fts MATCH ?
        ORDER BY rank
        LIMIT ?
        """,
        (session_id, npc_id, query, int(limit)),
    )
    return list(cur.fetchall())


# -----------------------------
# Convenience: build prompt blocks
# -----------------------------

def build_prompt_context(
    conn: sqlite3.Connection,
    *,
    session_id: str,
    npc_id: str,
    episode_limit: int = 6,
    semantic_limit: int = 10,
) -> Dict[str, Any]:
    """
    Returns small curated slices for prompt injection.
    Keep it minimal: last N episodes + last K beliefs.
    """
    episodes = get_recent_episodes(conn, session_id=session_id, npc_id=npc_id, limit=episode_limit)
    semantics = get_recent_semantic_memory(conn, session_id=session_id, npc_id=npc_id, limit=semantic_limit)

    return {
        "episodes": [
            {"turn_id": int(r["turn_id"]), "content": str(r["content"])}
            for r in episodes
        ],
        "beliefs": [
            {
                "turn_id": int(r["turn_id"]),
                "scope": str(r["scope"]),
                "subject": str(r["subject"]),
                "content": str(r["content"]),
            }
            for r in semantics
        ],
    }
