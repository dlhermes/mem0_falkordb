from datetime import datetime, timezone
from typing import Literal, Optional

from auth import verify_auth
from db import get_db
from fastapi import APIRouter, Depends
from models import EvolveFeedback, EvolveSalience, EvolveSalienceAdjustment
from pydantic import BaseModel
from sqlalchemy.orm import Session

router = APIRouter(prefix="/evolve", tags=["evolve"])

FeedbackType = Literal["useful", "useless", "correction"]
DELTAS: dict[str, float] = {"useful": 0.1, "useless": -0.15, "correction": -0.05}
MIN_SCORE = 0.05
MAX_SCORE = 1.0


class FeedbackRequest(BaseModel):
    memory_id: str
    feedback_type: FeedbackType
    source: str = "manual"
    note: Optional[str] = None


class FeedbackResponse(BaseModel):
    memory_id: str
    salience_score: float


@router.post("/feedback", response_model=FeedbackResponse)
def submit_feedback(
    body: FeedbackRequest,
    _auth=Depends(verify_auth),
    db: Session = Depends(get_db),
):
    """Record feedback for a memory and adjust its salience score.

    Adjusts only the salience score; memory content is never touched, so a
    misreport is reversible.
    """
    now = datetime.now(timezone.utc)
    feedback = EvolveFeedback(
        memory_id=body.memory_id,
        feedback_type=body.feedback_type,
        source=body.source,
        note=body.note,
        created_at=now,
    )
    db.add(feedback)
    db.flush()

    salience = db.get(EvolveSalience, body.memory_id)
    if salience is None:
        salience = EvolveSalience(memory_id=body.memory_id, salience_score=1.0, updated_at=now)
        db.add(salience)
    old_score = salience.salience_score
    new_score = round(min(max(old_score + DELTAS[body.feedback_type], MIN_SCORE), MAX_SCORE), 4)
    salience.salience_score = new_score
    salience.updated_at = now

    applied_delta = round(new_score - old_score, 4)
    db.add(
        EvolveSalienceAdjustment(
            memory_id=body.memory_id,
            delta=applied_delta,
            reason=body.feedback_type,
            feedback_id=feedback.id,
            created_at=now,
        )
    )
    db.commit()

    return FeedbackResponse(memory_id=body.memory_id, salience_score=new_score)
