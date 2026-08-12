import logging
import os
import sqlite3
from contextlib import closing
from typing import Literal

from auth import require_admin, require_auth
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

router = APIRouter(prefix="/search-keywords", tags=["search-keywords"])

HISTORY_DB_PATH = os.environ.get("HISTORY_DB_PATH", "/app/history/history.db")

logger = logging.getLogger(__name__)

Category = Literal["minimal", "standard", "full"]
MatchType = Literal["exact", "contains"]
Lang = Literal["zh", "en"]


class SearchKeywordCreate(BaseModel):
    keyword: str
    category: Category
    match_type: MatchType = "exact"
    lang: Lang = "zh"


class SearchKeywordItem(BaseModel):
    id: int
    keyword: str
    category: str
    match_type: str
    lang: str


class DuplicateKeyword(Exception):
    pass


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(HISTORY_DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


@router.get("", response_model=list[SearchKeywordItem])
def list_search_keywords(_auth=Depends(require_auth)):
    """List all deep-routing keywords, ordered full > standard > minimal, then by id."""
    try:
        with closing(_connect()) as conn:
            rows = conn.execute(
                """
                SELECT id, keyword, category, match_type, lang
                FROM search_keywords
                ORDER BY CASE category
                    WHEN 'full' THEN 0
                    WHEN 'standard' THEN 1
                    ELSE 2
                END, id
                """
            ).fetchall()
    except sqlite3.OperationalError as exc:
        logger.warning("search_keywords table unavailable: %s", exc)
        return []
    return [dict(r) for r in rows]


@router.post("", response_model=SearchKeywordItem)
def create_search_keyword(
    body: SearchKeywordCreate,
    _auth=Depends(require_admin),
):
    """Create a deep-routing keyword. Returns 409 if the exact (category, keyword, match_type, lang) already exists."""
    try:
        with closing(_connect()) as conn, conn:
            cur = conn.execute(
                "INSERT OR IGNORE INTO search_keywords (category, keyword, match_type, lang) VALUES (?, ?, ?, ?)",
                (body.category, body.keyword, body.match_type, body.lang),
            )
            if cur.rowcount == 0:
                raise DuplicateKeyword
            new_id = cur.lastrowid
            row = conn.execute(
                "SELECT id, keyword, category, match_type, lang FROM search_keywords WHERE id = ?",
                (new_id,),
            ).fetchone()
    except DuplicateKeyword:
        raise HTTPException(
            status_code=409,
            detail=f"Keyword already exists for (category={body.category}, keyword={body.keyword}, match_type={body.match_type}, lang={body.lang}).",
        )
    except sqlite3.OperationalError as exc:
        logger.error("search_keywords write failed: %s", exc)
        raise HTTPException(status_code=500, detail="Failed to write to search_keywords table.")
    return dict(row)


@router.delete("/{keyword_id}")
def delete_search_keyword(
    keyword_id: int,
    _auth=Depends(require_admin),
):
    try:
        with closing(_connect()) as conn, conn:
            cur = conn.execute("DELETE FROM search_keywords WHERE id = ?", (keyword_id,))
    except sqlite3.OperationalError as exc:
        logger.error("search_keywords delete failed: %s", exc)
        raise HTTPException(status_code=500, detail="Failed to delete from search_keywords table.")
    if cur.rowcount == 0:
        raise HTTPException(status_code=404, detail="Keyword not found.")
    return {"id": keyword_id, "deleted": True}
