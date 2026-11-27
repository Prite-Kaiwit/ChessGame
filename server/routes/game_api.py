"""Endpoints ควบคุมเกมจากปุ่มด้านล่างหน้า /board (New game / Undo / AI เดิน)

ทุก endpoint ให้ AI คิดตาแนะนำใหม่ ซึ่งใช้ CPU นาน จึงรันในเธรดแยก (asyncio.to_thread)
เพื่อไม่ให้ภาพกล้องและ WebSocket ค้างระหว่างที่ AI คิด
"""

import asyncio

from dataclasses import asdict

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from server.dip.move_detect import infer_move, square_scores
from server.dip.pipeline import pipeline
from server.game_state import game
from server.hub import hub
from server.routes import ml_api


class MoveBody(BaseModel):
    uci: str   # เช่น "e2e4", โปรโมต "e7e8q"


class SettingsBody(BaseModel):
    player_color: str | None = None   # "white" | "black"
    auto_detect: bool | None = None


# กันการหาตาเดินซ้อนกัน (ปุ่มเดินเสร็จกับการตรวจจับอัตโนมัติทำงานพร้อมกัน → เดินซ้ำสองครั้ง)
_detect_lock = asyncio.Lock()


async def detect_and_apply(source: str) -> dict:
    """เทียบภาพก่อนเดินกับภาพปัจจุบัน หาตาเดิน แล้วเดินให้ถ้ามั่นใจ

    result:
        "moved"      หาตาเดินได้และเดินให้แล้ว
        "baseline"   ยังไม่มีภาพก่อนเดิน เก็บภาพตอนนี้ไว้แทน
        "unresolved" ไม่แน่ใจหรือหาไม่พบ (มี changed และ candidates ให้ดู)
    คืน dict ที่มี "error" ถ้ายังทำไม่ได้ (ไม่มีกล้อง/ภาพไม่นิ่ง ฯลฯ)
    """
    async with _detect_lock:
        if pipeline.calibration is None:
            return {"error": "ยังไม่ได้ calibrate กระดาน"}
        after, still = pipeline.current_board()
        if after is None:
            return {"error": "ยังไม่มีภาพจากกล้อง เปิดหน้า /camera บนมือถือก่อน"}
        if not still:
            return {"error": "ภาพยังไม่นิ่ง เอามือออกจากกระดานแล้วกดอีกครั้ง"}
        if game.board.is_game_over():
            return {"error": "เกมจบแล้ว"}

        before = pipeline.reference
        if before is None:
            pipeline.set_reference(after)
            return {"result": "baseline", "changed": [], "candidates": [],
                    "message": "เก็บภาพก่อนเดินแล้ว เดินหมากได้เลย"}

        white_side = pipeline.calibration.white_side
        scores = await asyncio.to_thread(square_scores, before, after, white_side)
        detection = infer_move(game.board.copy(), scores, white_side=white_side)
        report = {
            "changed": detection.changed,
            "candidates": [asdict(c) for c in detection.candidates],
            "message": detection.reason,
        }
        if detection.move is None:
            return {"result": "unresolved", **report}

        mover = "white" if game.board.turn else "black"
        state = await asyncio.to_thread(game.apply_move, detection.move)
        pipeline.set_reference(after)
        hub.set_state(state)
        await asyncio.to_thread(ml_api.record_sample, source)
        return {"result": "moved", "move": detection.move, "mover": mover, **report}


async def auto_detect() -> None:
    """เรียกจาก DIP loop ทุกครั้งที่ภาพเพิ่งนิ่ง: ถ้ามีหมากขยับ ให้หาตาเดินเอง"""
    if not game.auto_detect or pipeline.reference is None:
        return
    result = await detect_and_apply("auto_detect")
    # ไม่มีอะไรเปลี่ยน (เช่น มือผ่านแล้วออกไป) หรือยังทำไม่ได้ → ไม่ต้องแจ้ง
    if "error" in result or len(result.get("changed", [])) < 2:
        return
    hub.publish_detect(result)


def _after_board_change() -> str | None:
    """หลังกระดานในเกมเปลี่ยน ใช้ภาพปัจจุบันเป็นภาพ "ก่อนเดิน" ของตาถัดไป

    ถ้าภาพยังไม่นิ่งหรือยังไม่มีกล้อง จะล้างไว้ แล้วไปเก็บตอนกดเดินเสร็จครั้งถัดไปแทน
    """
    if pipeline.remember_current_as_reference():
        return None
    return "ยังไม่ได้เก็บภาพก่อนเดิน (ภาพไม่นิ่งหรือไม่มีกล้อง) ให้กดเดินเสร็จหนึ่งครั้งก่อนเดินตาถัดไป"

router = APIRouter(prefix="/api/game", tags=["game"])


@router.post("/new")
async def new_game() -> dict:
    """เริ่มเกมใหม่จากตำแหน่งเริ่มต้น แล้วแจ้งทุกหน้า board"""
    state = await asyncio.to_thread(game.reset)
    hub.set_state(state)
    # ผู้เล่นจัดหมากตำแหน่งเริ่มต้นแล้วค่อยกด New game: ภาพตอนนี้คือภาพก่อนเดินตาแรก
    _after_board_change()
    # ไม่เก็บภาพข้อมูลเทรนตรงนี้: ผู้เล่นมักกด New game ทั้งที่ยังจัดหมากจริงไม่เสร็จ ป้ายจะผิด
    # (ถ้าแน่ใจว่าจัดครบแล้ว ใช้ปุ่ม "บันทึกภาพนี้" แทน)
    return state


@router.post("/undo")
async def undo_move() -> dict:
    """ย้อนกลับหนึ่งตา แล้วแจ้งทุกหน้า board (409 ถ้ายังไม่มีตาเดิน)"""
    try:
        state = await asyncio.to_thread(game.undo)
    except ValueError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    hub.set_state(state)
    # กระดานจริงอาจยังไม่ได้ย้อนตาม ล้างภาพก่อนเดิน แล้วเก็บใหม่ตอนกดเดินเสร็จครั้งถัดไป
    pipeline.set_reference(None)
    ml_api.discard_last_auto_sample()
    return state


@router.post("/ai-move")
async def ai_move() -> dict:
    """ให้ AI เดินตาที่แนะนำหนึ่งตา (409 ถ้าเกมจบแล้ว)"""
    try:
        state = await asyncio.to_thread(game.ai_move)
    except ValueError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    hub.set_state(state)
    return state


@router.post("/move")
async def manual_move(body: MoveBody) -> dict:
    """เดินตาที่ผู้เล่นลากบนกระดานจำลอง (ใช้เมื่อระบบอ่านภาพไม่ได้หรืออ่านผิด)"""
    try:
        state = await asyncio.to_thread(game.apply_move, body.uci)
    except ValueError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    hub.set_state(state)
    return {**state, "notice": _after_board_change()}


@router.post("/move-done")
async def move_done() -> dict:
    """ปุ่ม "เดินเสร็จ": บังคับหาตาเดินจากภาพตอนนี้ (ใช้เมื่อปิดโหมดอัตโนมัติ หรือระบบยังไม่เดินให้)"""
    result = await detect_and_apply("move_done")
    if "error" in result:
        raise HTTPException(status_code=409, detail=result["error"])
    return {**result, "state": game.snapshot()}


@router.post("/settings")
async def update_settings(body: SettingsBody) -> dict:
    """เลือกสีที่เราเล่น และเปิด/ปิดการตรวจจับตาเดินอัตโนมัติ"""
    if body.player_color is not None:
        try:
            game.set_player_color(body.player_color)
        except ValueError as error:
            raise HTTPException(status_code=422, detail=str(error)) from error
    if body.auto_detect is not None:
        game.auto_detect = body.auto_detect
    state = game.snapshot()
    hub.set_state(state)
    return state
