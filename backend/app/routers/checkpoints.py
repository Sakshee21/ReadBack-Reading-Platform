from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import get_current_user
from app.models import CheckpointAttempt, ComprehensionCheckpoint, User
from app.schemas import CheckpointOut, CheckpointResultOut, CheckpointSubmit
from app.services.checkpoint import score_attempt

router = APIRouter(prefix="/checkpoints", tags=["checkpoints"])


@router.get("/{checkpoint_id}", response_model=CheckpointOut)
def get_checkpoint(checkpoint_id: int, db: Session = Depends(get_db)):
    checkpoint = db.get(ComprehensionCheckpoint, checkpoint_id)
    if not checkpoint:
        raise HTTPException(status_code=404, detail="Checkpoint not found")
    return checkpoint


@router.post("/submit", response_model=CheckpointResultOut)
def submit_checkpoint(
    payload: CheckpointSubmit, db: Session = Depends(get_db), user: User = Depends(get_current_user)
):
    checkpoint = db.get(ComprehensionCheckpoint, payload.checkpoint_id)
    if not checkpoint:
        raise HTTPException(status_code=404, detail="Checkpoint not found")

    score, correct, total = score_attempt(checkpoint.questions, payload.answers)

    attempt = CheckpointAttempt(
        user_id=user.id,
        checkpoint_id=checkpoint.id,
        score=score,
    )
    db.add(attempt)
    db.commit()

    return CheckpointResultOut(checkpoint_id=checkpoint.id, score=score, correct=correct, total=total)
