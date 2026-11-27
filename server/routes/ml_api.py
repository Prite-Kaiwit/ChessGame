"""Endpoints ของแผง ML บนหน้า /board และหน้า /dataset: เก็บข้อมูล, ตรวจ/ลบภาพ, โหลดโมเดลใหม่"""

import asyncio
from typing import Any

import chess
import cv2

from fastapi import APIRouter, HTTPException, Response
from pydantic import BaseModel

from server.config import SQUARE_PX
from server.dip.board_detector import draw_grid
from server.dip.pipeline import encode_jpeg, pipeline
from server.game_state import game
from server.hub import hub
from server.ml.dataset import recorder
from server.ml.piece_classifier import classifier

router = APIRouter(prefix="/api/ml", tags=["ml"])

# ผลการอ่านกระดานครั้งล่าสุด (ส่งไปพร้อมสถานะ ML)
_last_reading: dict[str, Any] | None = None
# ภาพที่เก็บอัตโนมัติครั้งล่าสุด ถ้ากด Undo จะลบทิ้ง (ป้ายอาจผิดเพราะระบบอ่านตาเดินผิด)
_last_auto_sample: str | None = None


def ml_status() -> dict[str, Any]:
    return {
        "type": "ml",
        "model": classifier.name,
        "loaded": classifier.loaded,
        "dataset": recorder.stats(),
        "reading": _last_reading,
    }


def publish() -> dict[str, Any]:
    status = ml_status()
    hub.publish_ml(status)
    return status


def record_sample(source: str) -> str | None:
    """เก็บภาพปัจจุบันพร้อม FEN ของเกม (เฉพาะเมื่อเปิดการเก็บและภาพนิ่ง)"""
    global _last_auto_sample
    image, still = pipeline.current_board()
    if image is None or not still or not recorder.enabled:
        return None
    sample_id = recorder.save(image, game.board.fen(), source)
    _last_auto_sample = sample_id if source != "manual" else None
    publish()
    return sample_id


def discard_last_auto_sample() -> None:
    """เรียกตอน Undo"""
    global _last_auto_sample
    if _last_auto_sample and recorder.remove(_last_auto_sample):
        publish()
    _last_auto_sample = None


def read_board_now() -> dict[str, Any] | None:
    """ให้โมเดลอ่านภาพกระดานปัจจุบัน แล้วเทียบกับสถานะเกม (รันในเธรดแยก)"""
    global _last_reading
    image, _ = pipeline.current_board()
    if image is None or not classifier.loaded:
        return None
    reading = classifier.read_board(image)
    expected = classifier.expected_labels(game.board)
    mismatches = sorted(sq for sq, label in reading.labels.items() if label != expected[sq])
    confidences = list(reading.confidence.values())
    _last_reading = {
        "mean_confidence": round(sum(confidences) / len(confidences), 3),
        "uncertain": sorted(reading.uncertain()),
        "mismatches": mismatches,     # ช่องที่โมเดลทายไม่ตรงกับสถานะเกม
        "labels": reading.labels,
    }
    return _last_reading


class CollectBody(BaseModel):
    enabled: bool


@router.get("/status")
async def get_status() -> dict:
    return ml_status()


@router.post("/collect")
async def set_collect(body: CollectBody) -> dict:
    recorder.enabled = body.enabled
    return publish()


@router.post("/capture")
async def capture() -> dict:
    """ผู้เล่นยืนยันว่ากระดานจริงตรงกับบนจอ → เก็บภาพนี้เป็นข้อมูลเทรน"""
    if not recorder.enabled:
        raise HTTPException(status_code=409, detail="เปิด \"เก็บข้อมูล\" ก่อน")
    image, still = pipeline.current_board()
    if image is None:
        raise HTTPException(status_code=409, detail="ยังไม่มีภาพจากกล้อง หรือยังไม่ได้ calibrate")
    if not still:
        raise HTTPException(status_code=409, detail="ภาพยังไม่นิ่ง เอามือออกจากกระดานแล้วกดอีกครั้ง")
    await asyncio.to_thread(record_sample, "manual")
    return ml_status()


@router.post("/reload")
async def reload_model() -> dict:
    """โหลดโมเดลใหม่หลังวางไฟล์ใน server/data/models/ (ไม่ต้องรีสตาร์ตเซิร์ฟเวอร์)"""
    await asyncio.to_thread(classifier.reload)
    if classifier.loaded:
        await asyncio.to_thread(read_board_now)
    return publish()


# ---------- หน้า /dataset: ตรวจและลบภาพที่ป้ายผิด ----------

def _overlay(image_path) -> bytes:
    """ภาพกระดาน + ตาราง + ป้ายที่ติดไว้ (วงกลมขาว/ดำพร้อมตัวอักษร ที่ฐานของแต่ละช่อง)

    ให้ตรวจด้วยตาว่าหมากในภาพตรงกับป้ายไหม: วงกลมต้องอยู่ใต้หมากทุกตัว และช่องว่างต้องไม่มีวงกลม
    """
    record_id = image_path.stem
    fen = next(r["fen"] for r in recorder.list_records() if r["id"] == record_id)
    canvas = draw_grid(cv2.imread(str(image_path)))
    for square, piece in chess.Board(fen).piece_map().items():
        cx = chess.square_file(square) * SQUARE_PX + SQUARE_PX // 2
        cy = (8 - chess.square_rank(square)) * SQUARE_PX - 22
        fill, ink = ((255, 255, 255), (0, 0, 0)) if piece.color else ((0, 0, 0), (255, 255, 255))
        cv2.circle(canvas, (cx, cy), 17, fill, -1)
        cv2.circle(canvas, (cx, cy), 17, (0, 0, 255), 2)
        cv2.putText(canvas, piece.symbol().upper(), (cx - 8, cy + 8), cv2.FONT_HERSHEY_SIMPLEX, 0.7, ink, 2)
    return encode_jpeg(canvas, quality=80)


@router.get("/samples")
async def list_samples() -> dict:
    return {**recorder.stats(), "items": recorder.list_records()}


@router.get("/samples/{sample_id}/image")
async def sample_image(sample_id: str) -> Response:
    path = recorder.image_path(sample_id)
    if path is None:
        raise HTTPException(status_code=404, detail="ไม่พบภาพ")
    jpeg = await asyncio.to_thread(_overlay, path)
    return Response(jpeg, media_type="image/jpeg", headers={"Cache-Control": "no-store"})


@router.delete("/samples/{sample_id}")
async def delete_sample(sample_id: str) -> dict:
    if recorder.image_path(sample_id) is None or not recorder.remove(sample_id):
        raise HTTPException(status_code=404, detail="ไม่พบภาพ")
    return publish()


@router.delete("/samples")
async def delete_all_samples() -> dict:
    removed = recorder.clear()
    return {**publish(), "removed": removed}
