from __future__ import annotations

from fastapi import APIRouter, Depends, Request

from src.ui.api.auth import get_current_user

router = APIRouter()


@router.get("/")
async def get_ranking(
    request: Request, user: dict = Depends(get_current_user)
) -> dict:
    app = request.app.state.app
    entries = await app.ranking_repo.get_ranking(
        requesting_user_id=user["id"]
    )

    my_rank = None
    for entry in entries:
        if entry.is_me:
            my_rank = entry.rank
            break

    return {
        "rankings": [
            {
                "rank": e.rank,
                "user_id": e.user_id,
                "nickname": e.nickname,
                "return_pct": str(e.return_pct),
                "win_rate": str(e.win_rate),
                "total_trades": e.total_trades,
                "max_drawdown_pct": str(e.max_drawdown_pct),
                "daily_equities": [str(d) for d in e.daily_equities],
                "is_me": e.is_me,
            }
            for e in entries
        ],
        "my_rank": my_rank,
        "total_users": len(entries),
    }
