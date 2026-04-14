from __future__ import annotations
"""
CrabRes Semantic Memory Search — FTS5 + keyword hybrid search

Replaces the naive "keyword in content" search in GrowthMemory
with a proper full-text search engine using SQLite FTS5.

Architecture:
- SQLite FTS5 for fast full-text search (no external dependencies!)
- BM25 ranking for relevance scoring
- Auto-indexes all memory files on first search
- Incremental re-indexing when files change
- Supports Chinese tokenization via unicode61

Why FTS5 over vector search:
- Zero dependencies (SQLite is built into Python)
- Works offline, no API calls
- Fast enough for <10K documents
- BM25 ranking is surprisingly good for growth domain
- Can upgrade to pgvector later when needed
"""

import json
import sqlite3
import time
import logging
import hashlib
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


class SemanticMemorySearch:
    """
    Full-text search over CrabRes memory using SQLite FTS5.
    
    Usage:
        searcher = SemanticMemorySearch(base_dir=".crabres/memory/user1")
        await searcher.index_all()  # First time, or after many changes
        results = await searcher.search("reddit growth strategy")
    """

    def __init__(self, base_dir: str = ".crabres/memory"):
        self.base_dir = Path(base_dir)
        self.db_path = self.base_dir / "_search.db"
        self._conn: Optional[sqlite3.Connection] = None
        self._ensure_db()

    def _ensure_db(self):
        """Create FTS5 tables if they don't exist"""
        self.base_dir.mkdir(parents=True, exist_ok=True)
        conn = self._get_conn()
        conn.executescript("""
            CREATE VIRTUAL TABLE IF NOT EXISTS memory_fts USING fts5(
                category,
                key,
                content,
                file_hash,
                indexed_at UNINDEXED,
                tokenize='unicode61'
            );
            
            CREATE TABLE IF NOT EXISTS index_meta (
                file_path TEXT PRIMARY KEY,
                file_hash TEXT,
                indexed_at REAL
            );
        """)
        conn.commit()

    def _get_conn(self) -> sqlite3.Connection:
        if self._conn is None:
            self._conn = sqlite3.connect(str(self.db_path))
            self._conn.row_factory = sqlite3.Row
        return self._conn

    def _file_hash(self, path: Path) -> str:
        """Quick hash to detect file changes"""
        try:
            stat = path.stat()
            return hashlib.md5(f"{stat.st_size}:{stat.st_mtime}".encode()).hexdigest()[:12]
        except Exception:
            return ""

    async def index_all(self, force: bool = False):
        """
        Index all memory files into FTS5.
        
        Incremental: only re-indexes files that changed since last index.
        Set force=True to rebuild from scratch.
        """
        conn = self._get_conn()
        
        if force:
            conn.execute("DELETE FROM memory_fts")
            conn.execute("DELETE FROM index_meta")
            conn.commit()

        categories = [
            "product", "goals", "research", "strategy",
            "execution", "feedback", "journal", "knowledge",
        ]
        
        indexed = 0
        skipped = 0

        for cat in categories:
            cat_dir = self.base_dir / cat
            if not cat_dir.exists():
                continue

            for path in cat_dir.glob("*.json"):
                file_path = str(path.relative_to(self.base_dir))
                current_hash = self._file_hash(path)

                if not force:
                    row = conn.execute(
                        "SELECT file_hash FROM index_meta WHERE file_path = ?",
                        (file_path,)
                    ).fetchone()
                    if row and row["file_hash"] == current_hash:
                        skipped += 1
                        continue

                # Read and flatten content
                try:
                    raw = path.read_text()
                    data = json.loads(raw)
                    content = self._flatten_to_text(data)
                except Exception:
                    content = raw[:5000] if len(raw) < 5000 else raw[:5000]

                # Remove old entry
                conn.execute(
                    "DELETE FROM memory_fts WHERE category = ? AND key = ?",
                    (cat, path.stem)
                )

                # Insert new
                conn.execute(
                    "INSERT INTO memory_fts (category, key, content, file_hash, indexed_at) VALUES (?, ?, ?, ?, ?)",
                    (cat, path.stem, content, current_hash, time.time())
                )

                # Update meta
                conn.execute(
                    "INSERT OR REPLACE INTO index_meta (file_path, file_hash, indexed_at) VALUES (?, ?, ?)",
                    (file_path, current_hash, time.time())
                )

                indexed += 1

            # Also index JSONL files (journal entries)
            for path in cat_dir.glob("*.jsonl"):
                file_path = str(path.relative_to(self.base_dir))
                current_hash = self._file_hash(path)

                if not force:
                    row = conn.execute(
                        "SELECT file_hash FROM index_meta WHERE file_path = ?",
                        (file_path,)
                    ).fetchone()
                    if row and row["file_hash"] == current_hash:
                        skipped += 1
                        continue

                try:
                    lines = path.read_text().strip().split("\n")
                    entries = [json.loads(l) for l in lines if l.strip()]
                    content = "\n".join(self._flatten_to_text(e) for e in entries)
                except Exception:
                    content = path.read_text()[:5000]

                conn.execute(
                    "DELETE FROM memory_fts WHERE category = ? AND key = ?",
                    (cat, path.stem)
                )
                conn.execute(
                    "INSERT INTO memory_fts (category, key, content, file_hash, indexed_at) VALUES (?, ?, ?, ?, ?)",
                    (cat, path.stem, content, current_hash, time.time())
                )
                conn.execute(
                    "INSERT OR REPLACE INTO index_meta (file_path, file_hash, indexed_at) VALUES (?, ?, ?)",
                    (file_path, current_hash, time.time())
                )
                indexed += 1

        conn.commit()
        logger.info(f"Memory indexed: {indexed} new/updated, {skipped} unchanged")
        return {"indexed": indexed, "skipped": skipped}

    async def search(
        self,
        query: str,
        categories: list[str] = None,
        limit: int = 10,
    ) -> list[dict]:
        """
        Search memory using FTS5 BM25 ranking.
        
        Returns list of {category, key, snippet, rank} sorted by relevance.
        """
        conn = self._get_conn()

        # Auto-index if empty
        count = conn.execute("SELECT COUNT(*) as c FROM memory_fts").fetchone()["c"]
        if count == 0:
            await self.index_all()

        # Build query
        # FTS5 query syntax: simple words are OR'd, use quotes for phrases
        fts_query = self._build_fts_query(query)

        try:
            if categories:
                placeholders = ",".join("?" for _ in categories)
                sql = f"""
                    SELECT category, key, snippet(memory_fts, 2, '>>>', '<<<', '...', 64) as snippet,
                           rank
                    FROM memory_fts
                    WHERE memory_fts MATCH ? AND category IN ({placeholders})
                    ORDER BY rank
                    LIMIT ?
                """
                rows = conn.execute(sql, [fts_query] + categories + [limit]).fetchall()
            else:
                sql = """
                    SELECT category, key, snippet(memory_fts, 2, '>>>', '<<<', '...', 64) as snippet,
                           rank
                    FROM memory_fts
                    WHERE memory_fts MATCH ?
                    ORDER BY rank
                    LIMIT ?
                """
                rows = conn.execute(sql, [fts_query, limit]).fetchall()

            return [
                {
                    "category": row["category"],
                    "key": row["key"],
                    "snippet": row["snippet"],
                    "rank": row["rank"],
                }
                for row in rows
            ]

        except sqlite3.OperationalError as e:
            # FTS5 query syntax error — fallback to simple LIKE
            logger.warning(f"FTS5 query failed ({e}), falling back to LIKE search")
            return await self._fallback_search(query, categories, limit)

    async def search_for_prompt(
        self,
        query: str,
        categories: list[str] = None,
        max_chars: int = 2000,
    ) -> str:
        """
        Search and format results as injectable prompt text.
        
        This is what gets prepended to expert/pipeline system prompts
        to give the agent "memory".
        """
        results = await self.search(query, categories, limit=5)
        if not results:
            return ""

        lines = ["## RELEVANT MEMORIES (from past sessions)"]
        total_chars = 0
        for r in results:
            snippet = r["snippet"].replace(">>>", "**").replace("<<<", "**")
            entry = f"\n- [{r['category']}/{r['key']}] {snippet}"
            if total_chars + len(entry) > max_chars:
                break
            lines.append(entry)
            total_chars += len(entry)

        lines.append("\nUse these memories to maintain continuity with past conversations.")
        return "\n".join(lines)

    async def _fallback_search(self, query: str, categories: list[str] = None, limit: int = 10) -> list[dict]:
        """Fallback: simple LIKE search when FTS5 fails"""
        conn = self._get_conn()
        words = query.lower().split()[:5]
        conditions = " OR ".join(f"LOWER(content) LIKE '%' || ? || '%'" for _ in words)
        
        if categories:
            cat_filter = "AND category IN ({})".format(",".join("?" for _ in categories))
            sql = f"SELECT category, key, SUBSTR(content, 1, 200) as snippet FROM memory_fts WHERE ({conditions}) {cat_filter} LIMIT ?"
            params = words + categories + [limit]
        else:
            sql = f"SELECT category, key, SUBSTR(content, 1, 200) as snippet FROM memory_fts WHERE ({conditions}) LIMIT ?"
            params = words + [limit]

        rows = conn.execute(sql, params).fetchall()
        return [{"category": r["category"], "key": r["key"], "snippet": r["snippet"], "rank": 0} for r in rows]

    def _build_fts_query(self, query: str) -> str:
        """
        Convert natural language query to FTS5 query syntax.
        
        "reddit growth strategy" → "reddit OR growth OR strategy"
        "AI resume optimizer" → "AI OR resume OR optimizer"
        """
        words = query.strip().split()
        # Filter out very short words and common stop words
        stop_words = {"the", "a", "an", "is", "are", "was", "were", "in", "on", "at", "to", "for", "of", "and", "or", "not", "with"}
        filtered = [w for w in words if len(w) > 1 and w.lower() not in stop_words]
        
        if not filtered:
            return query.strip()

        # Use OR for broad matching
        return " OR ".join(filtered)

    def _flatten_to_text(self, data) -> str:
        """Recursively flatten a JSON structure into searchable text"""
        if isinstance(data, str):
            return data
        elif isinstance(data, (int, float, bool)):
            return str(data)
        elif isinstance(data, list):
            return " ".join(self._flatten_to_text(item) for item in data)
        elif isinstance(data, dict):
            parts = []
            for k, v in data.items():
                if k.startswith("_"):  # Skip metadata fields
                    continue
                parts.append(f"{k}: {self._flatten_to_text(v)}")
            return " ".join(parts)
        return ""

    def close(self):
        if self._conn:
            self._conn.close()
            self._conn = None

    def __del__(self):
        self.close()
