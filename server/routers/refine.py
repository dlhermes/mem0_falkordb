"""Recursive memory refinement: candidate discovery + candidate listing.

Batch scope: POST generates candidates (stale-memory discovery -> clustering ->
LLM proposal), GET lists them. Apply/rollback is a later batch — the LLM
output stays a proposal in memory_refine_candidates.suggested_text and is
never written to the vector store here.
"""

from datetime import datetime, timedelta, timezone
from typing import Optional

from auth import require_auth
from db import get_db
from fastapi import APIRouter, Depends
from models import EvolveSalience, MemoryRefineCandidate
from refine_memory import cluster_candidates, refine_group
from server_state import get_memory_instance
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

router = APIRouter(prefix="/memory/refine", tags=["refine"])

STATUS_PROPOSED = "proposed"
STALE_CUTOFF_DAYS = 14
MAX_STALE_SCAN = 500


def _serialize_candidate(row: MemoryRefineCandidate) -> dict:
    return {
        "id": row.id,
        "user_id": row.user_id,
        "memory_ids": row.memory_ids or [],
        "topic": row.topic,
        "status": row.status,
        "suggested_text": row.suggested_text or [],
        "refined_memory_id": row.refined_memory_id,
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
    }


def _collect_stale_items(memory, db: Session, user_id: str) -> list[dict]:
    """Fetch fragmented memory texts for stale (未召回) memories of a user."""
    cutoff = datetime.now(timezone.utc) - timedelta(days=STALE_CUTOFF_DAYS)
    stale_rows = db.execute(
        select(EvolveSalience.memory_id)
        .where(
            or_(
                EvolveSalience.last_access_at.is_(None),
                EvolveSalience.last_access_at < cutoff,
            )
        )
        .order_by(EvolveSalience.access_count.desc())
        .limit(MAX_STALE_SCAN)
    ).all()

    items: list[dict] = []
    for (mid,) in stale_rows:
        mid = str(mid)
        try:
            result = memory.vector_store.get(mid)
        except Exception:  # noqa: BLE001
            continue
        if result is None:
            continue
        payload = getattr(result, "payload", None) or {}
        if payload.get("user_id") != user_id:
            continue
        data = payload.get("data")
        if not data:
            continue
        items.append({"id": mid, "data": str(data)})
    return items


@router.post("/candidates")
def generate_refine_candidates(
    user_id: Optional[str] = None,
    _auth=Depends(require_auth),
    db: Session = Depends(get_db),
):
    """Discover fragmented-memory clusters and draft LLM refinement proposals."""
    effective_user = user_id or str(_auth.id)
    memory = get_memory_instance()

    items = _collect_stale_items(memory, db, effective_user)
    candidates = cluster_candidates(memory, items)

    created = []
    for cand in candidates:
        row = MemoryRefineCandidate(
            user_id=effective_user,
            memory_ids=cand["memory_ids"],
            topic=cand["topic"],
            status=STATUS_PROPOSED,
            suggested_text=[],
        )
        db.add(row)
        db.flush()
        outcome = refine_group(memory, {"memory_ids": cand["memory_ids"]})
        row.status = outcome["status"]
        row.suggested_text = outcome["suggested_text"]
        created.append(_serialize_candidate(row))
    db.commit()
    return {"candidates": created}


@router.get("/candidates")
def list_refine_candidates(
    status: Optional[str] = None,
    user_id: Optional[str] = None,
    _auth=Depends(require_auth),
    db: Session = Depends(get_db),
):
    """List refinement candidates, optionally filtered by status / user_id."""
    stmt = select(MemoryRefineCandidate).order_by(MemoryRefineCandidate.created_at.desc())
    if user_id:
        stmt = stmt.where(MemoryRefineCandidate.user_id == user_id)
    if status:
        stmt = stmt.where(MemoryRefineCandidate.status == status)
    rows = db.execute(stmt).scalars().all()
    return {"candidates": [_serialize_candidate(r) for r in rows]}
