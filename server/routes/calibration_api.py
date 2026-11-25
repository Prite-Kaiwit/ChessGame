"""Endpoints สำหรับหน้า /calibrate: ดึงภาพล่าสุด, หามุมอัตโนมัติ, ดูตัวอย่าง และบันทึก"""

import asyncio

from fastapi import APIRouter, HTTPException, Response
from pydantic import BaseModel

from server.dip.auto_corners import detect_corners
from server.dip.board_detector import draw_grid
from server.dip.calibration import Calibration
from server.dip.pipeline import decode_jpeg, encode_jpeg, pipeline, rectify
from server.hub import hub

router = APIRouter(prefix="/api", tags=["calibration"])
NO_CACHE = {"Cache-Control": "no-store"}


class CalibrationBody(BaseModel):
    corners: list[list[float]]   # 4 จุด [x, y] แบบสัดส่วน 0–1: ซ้ายบน, ขวาบน, ขวาล่าง, ซ้ายล่าง
    white_side: str = "bottom"   # ฝั่งที่ผู้เล่นขาวนั่ง: bottom | top | left | right


def _to_calibration(body: CalibrationBody) -> Calibration:
    try:
        return Calibration(corners=body.corners, white_side=body.white_side)
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error


def _latest_frame():
    """ภาพล่าสุดจากกล้องแบบถอดรหัสแล้ว (409 ถ้ายังไม่มีมือถือส่งภาพมา)"""
    frame = decode_jpeg(hub.latest_frame or b"")
    if frame is None:
        raise HTTPException(status_code=409, detail="ยังไม่มีภาพจากกล้อง เปิดหน้า /camera บนมือถือก่อน")
    return frame


@router.get("/calibration")
async def get_calibration() -> dict:
    calibration = pipeline.calibration
    if calibration is None:
        return {"calibrated": False}
    return {"calibrated": True, "corners": calibration.corners, "white_side": calibration.white_side}


@router.post("/calibration")
async def save_calibration(body: CalibrationBody) -> dict:
    """บันทึกมุมและฝั่งผู้เล่น ลงไฟล์ server/data/calibration.json แล้วใช้ทันที"""
    calibration = _to_calibration(body)
    pipeline.set_calibration(calibration)
    # แจ้งหน้า board ทันที ไม่ต้องรอเฟรมถัดไป (ตัวตรวจภาพนิ่งเริ่มนับใหม่ จึงยังไม่นิ่ง)
    hub.publish_dip({"type": "dip", "calibrated": True, "still": False, "diff": None})
    return {"calibrated": True, "corners": calibration.corners, "white_side": calibration.white_side}


@router.get("/frame/latest.jpg")
async def latest_frame() -> Response:
    """ภาพล่าสุดจากกล้อง สำหรับให้ผู้ใช้คลิกมุมบนหน้า /calibrate"""
    if not hub.latest_frame:
        raise HTTPException(status_code=404, detail="ยังไม่มีภาพจากกล้อง")
    return Response(hub.latest_frame, media_type="image/jpeg", headers=NO_CACHE)


@router.post("/calibration/auto")
async def auto_detect() -> dict:
    """หามุมอัตโนมัติด้วย Canny + Hough บนภาพล่าสุด คืนพิกัดแบบสัดส่วน"""
    frame = _latest_frame()
    quad = await asyncio.to_thread(detect_corners, frame)
    if quad is None:
        raise HTTPException(status_code=422, detail="หามุมกระดานอัตโนมัติไม่พบ กรุณาคลิกเลือกเอง")
    height, width = frame.shape[:2]
    corners = [[round(float(x) / width, 4), round(float(y) / height, 4)] for x, y in quad]
    return {"corners": corners}


@router.post("/calibration/preview")
async def preview(body: CalibrationBody) -> Response:
    """ดัดภาพล่าสุดตามมุมที่ส่งมา (ยังไม่บันทึก) เพื่อให้ผู้ใช้ตรวจว่าตารางตรงกับช่องจริงไหม"""
    calibration = _to_calibration(body)
    frame = _latest_frame()
    board = await asyncio.to_thread(rectify, frame, calibration)
    return Response(encode_jpeg(draw_grid(board)), media_type="image/jpeg", headers=NO_CACHE)
