"""Endpoints ควบคุมเกมจากปุ่มด้านล่างหน้า /board (New game / Undo)"""

from fastapi import APIRouter, HTTPException

from server.game_state import game
from server.hub import hub

router = APIRouter(prefix="/api/game", tags=["game"])


@router.post("/new")
async def new_game() -> dict:
    """เริ่มเกมใหม่จากตำแหน่งเริ่มต้น แล้วแจ้งทุกหน้า board"""
    state = game.reset()
    hub.set_state(state)
    return state


@router.post("/undo")
async def undo_move() -> dict:
    """ย้อนกลับหนึ่งตา แล้วแจ้งทุกหน้า board (409 ถ้ายังไม่มีตาเดิน)"""
    try:
        state = game.undo()
    except ValueError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    hub.set_state(state)
    return state
