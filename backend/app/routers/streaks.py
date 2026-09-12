import datetime as dt

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import get_current_user
from app.models import User
from app.schemas import StreakOut
from app.services.streak import streak_after_gap

router = APIRouter(prefix="/streaks", tags=["streaks"])


@router.get("/me", response_model=StreakOut)
def my_streak(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    today = dt.datetime.utcnow().date()
    live_streak = streak_after_gap(user.current_streak, user.last_read_date, today)
    if live_streak != user.current_streak:
        user.current_streak = live_streak
        db.commit()

    return StreakOut(
        current_streak=user.current_streak,
        longest_streak=user.longest_streak,
        last_read_date=user.last_read_date,
    )
