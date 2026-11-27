"""Endpoints สำหรับทดสอบ: สุ่มเดินเพื่อดูว่าบอร์ดและลูกศรบนหน้าเว็บอัปเดตได้"""

import asyncio

from fastapi import APIRouter, HTTPException

from server.game_state import game
from server.hub import hub

router = APIRouter(prefix="/api/test", tags=["test"])


@router.post("/random-move")
async def random_move() -> dict:
    """เดินหมาก legal แบบสุ่มและ broadcast สถานะใหม่"""
    try:
        state = await asyncio.to_thread(game.random_move)
    except ValueError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    hub.set_state(state)
    return state


@router.post("/reset")
async def reset_game() -> dict:
    """เริ่มเกมใหม่และ broadcast สถานะเริ่มต้น (คงไว้เพื่อความเข้ากันได้ ใช้ /api/game/new แทน)"""
    state = await asyncio.to_thread(game.reset)
    hub.set_state(state)
    return state
