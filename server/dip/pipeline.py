"""รวมขั้นตอน DIP ทั้งหมดสำหรับเฟรมจากกล้องหนึ่งเฟรม

    JPEG bytes ─► decode ─► warp_board (800x800) ─► orient_board (ขาวอยู่ล่าง)
              ─► StillnessDetector (frame difference)
              ─► ถ้าเพิ่งนิ่ง: split_squares → 64 ช่อง (ส่งต่อให้ ML ในขั้นถัดไป)
              ─► draw_grid ─► JPEG สำหรับแสดงบนหน้า /board
"""

import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import cv2
import numpy as np

from server.config import CALIBRATION_FILE
from server.dip.board_detector import draw_grid, orient_board, split_squares, warp_board
from server.dip.calibration import Calibration, load_calibration, save_calibration
from server.dip.motion import StillnessDetector


def decode_jpeg(data: bytes) -> np.ndarray | None:
    """แปลง JPEG bytes เป็นภาพ BGR คืน None ถ้าข้อมูลเสีย"""
    if not data:
        return None
    return cv2.imdecode(np.frombuffer(data, dtype=np.uint8), cv2.IMREAD_COLOR)


def encode_jpeg(image: np.ndarray, quality: int = 75) -> bytes:
    ok, buffer = cv2.imencode(".jpg", image, [cv2.IMWRITE_JPEG_QUALITY, quality])
    if not ok:
        raise RuntimeError("เข้ารหัส JPEG ไม่สำเร็จ")
    return buffer.tobytes()


def rectify(frame: np.ndarray, calibration: Calibration) -> np.ndarray:
    """ดัดภาพตามมุมที่ calibrate ไว้ แล้วหมุนให้ขาวอยู่ด้านล่าง"""
    height, width = frame.shape[:2]
    warped = warp_board(frame, calibration.corners_px(width, height))
    return orient_board(warped, calibration.white_side)


@dataclass
class DipOutput:
    status: dict[str, Any]          # สถานะสำหรับแผงบนหน้า /board
    warped_jpeg: bytes | None       # ภาพดัดตรง + ตาราง (None ถ้ายังไม่ calibrate)
    squares: dict[str, np.ndarray] | None = None  # 64 ช่อง เฉพาะจังหวะที่ภาพเพิ่งนิ่ง


class DipPipeline:
    def __init__(self, calibration_file: Path = CALIBRATION_FILE) -> None:
        self.calibration_file = calibration_file
        self.calibration = load_calibration(calibration_file)
        self.detector = StillnessDetector()
        self.reads = 0  # จำนวนครั้งที่ภาพนิ่งพร้อมอ่านกระดาน
        # สำหรับปุ่ม "เดินเสร็จ": ภาพกระดานล่าสุด (ดัดตรงแล้ว ไม่มีเส้นตาราง) และภาพก่อนเดิน
        self.latest_board: np.ndarray | None = None
        self.latest_still = False
        self.reference: np.ndarray | None = None
        # process() รันใน worker thread ส่วน set_calibration() มาจาก API: ใช้ lock กันชนกัน
        self._lock = threading.Lock()

    def set_calibration(self, calibration: Calibration) -> None:
        with self._lock:
            save_calibration(self.calibration_file, calibration)
            self.calibration = calibration
            self.detector.reset()
            # มุมกระดานเปลี่ยน ภาพเก่าเทียบกับภาพใหม่ไม่ได้แล้ว
            self.latest_board = None
            self.latest_still = False
            self.reference = None

    def current_board(self) -> tuple[np.ndarray | None, bool]:
        """ภาพกระดานล่าสุด (สำเนา) และภาพนิ่งหรือยัง"""
        with self._lock:
            board = None if self.latest_board is None else self.latest_board.copy()
            return board, self.latest_still

    def set_reference(self, board: np.ndarray | None) -> None:
        """ตั้งภาพ "ก่อนเดิน" สำหรับเทียบตอนกดเดินเสร็จครั้งถัดไป (None = ล้าง)"""
        with self._lock:
            self.reference = board

    def remember_current_as_reference(self) -> bool:
        """ใช้ภาพปัจจุบันเป็นภาพก่อนเดิน ได้เฉพาะเมื่อภาพนิ่ง คืน True ถ้าสำเร็จ"""
        with self._lock:
            ok = self.latest_board is not None and self.latest_still
            self.reference = self.latest_board.copy() if ok else None
            return ok

    def process(self, jpeg: bytes) -> DipOutput | None:
        frame = decode_jpeg(jpeg)
        if frame is None:
            return None
        with self._lock:
            if self.calibration is None:
                return DipOutput(status={"type": "dip", "calibrated": False}, warped_jpeg=None)

            board = rectify(frame, self.calibration)
            motion = self.detector.update(board)
            self.latest_board = board
            self.latest_still = motion.still

            squares = None
            if motion.became_still:
                # จังหวะเดียวที่ควรอ่านกระดาน: เพิ่งหยุดขยับครบ N เฟรม
                squares = split_squares(board)
                self.reads += 1
                # ยังไม่มีภาพก่อนเดิน (เพิ่งเปิดเซิร์ฟเวอร์/กล้อง หรือหลัง Undo):
                # ใช้ภาพที่เพิ่งนิ่งนี้เลย ผู้เล่นจึงเดินแล้วกดเดินเสร็จได้ทันที ไม่ต้องกดเก็บภาพก่อน
                if self.reference is None:
                    self.reference = board.copy()

            status = {
                "type": "dip",
                "calibrated": True,
                "still": motion.still,
                "diff": None if motion.diff == float("inf") else round(motion.diff, 2),
                "threshold": self.detector.threshold,
                "reads": self.reads,
                "has_reference": self.reference is not None,
            }
        return DipOutput(status=status, warped_jpeg=encode_jpeg(draw_grid(board)), squares=squares)


# ตัวประมวลผลกลางของเซิร์ฟเวอร์
pipeline = DipPipeline()
