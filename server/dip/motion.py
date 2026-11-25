"""ตรวจว่าภาพ "นิ่ง" แล้วหรือยัง ด้วย frame difference ก่อนส่งให้ ML อ่านกระดาน

เหตุผล: ขณะผู้เล่นยื่นมือเข้ามาเดินหมาก ภาพจะมีมือบังและหมากอยู่กลางทาง
ถ้าอ่านตอนนั้นจะได้ตำแหน่งผิด จึงรอจนภาพหยุดเปลี่ยนก่อน

วิธีคำนวณ (ทำบนภาพกระดานที่ดัดตรงแล้ว เพื่อดูเฉพาะบริเวณกระดาน):
    1. แปลงเป็นภาพระดับเทา (grayscale)
           I = 0.299·R + 0.587·G + 0.114·B
    2. ย่อเหลือ 200x200 และเบลอด้วย Gaussian 5x5 เพื่อลด noise จากกล้องและ JPEG
    3. ความต่างเฉลี่ยระหว่างเฟรมปัจจุบัน t กับเฟรมก่อนหน้า t−1
           D_t = (1 / (W·H)) · Σ_x Σ_y | I_t(x, y) − I_{t−1}(x, y) |
       (Mean Absolute Difference มีค่า 0–255)
    4. ถือว่า "นิ่ง" เมื่อ D_t < T ติดต่อกัน N เฟรม
           ค่าเริ่มต้น T = 4.0, N = 5 (ประมาณ 1 วินาทีที่ 5 fps)
       การรอ N เฟรมกันกรณีที่มือหยุดชั่วขณะแค่เฟรมเดียว
"""

from dataclasses import dataclass

import cv2
import numpy as np

from server.config import MOTION_SIZE, MOTION_THRESHOLD, STILL_FRAMES


def preprocess(board: np.ndarray, size: int = MOTION_SIZE) -> np.ndarray:
    """ขั้นที่ 1–2: เทา → ย่อ → เบลอ  คืนภาพ float32 เพื่อไม่ให้ลบกันแล้วติดลบล้น (uint8 underflow)"""
    gray = cv2.cvtColor(board, cv2.COLOR_BGR2GRAY) if board.ndim == 3 else board
    small = cv2.resize(gray, (size, size), interpolation=cv2.INTER_AREA)
    return cv2.GaussianBlur(small, (5, 5), 0).astype(np.float32)


def mean_abs_diff(current: np.ndarray, previous: np.ndarray) -> float:
    """ขั้นที่ 3: D = mean(|I_t − I_{t−1}|)"""
    return float(np.mean(np.abs(current - previous)))


@dataclass
class MotionResult:
    diff: float          # D_t ของเฟรมนี้ (เฟรมแรกยังไม่มีเฟรมก่อนหน้า จะเป็น inf)
    still: bool          # นิ่งครบ N เฟรมแล้วหรือยัง
    became_still: bool   # เพิ่งเปลี่ยนจาก "ขยับ" เป็น "นิ่ง" ในเฟรมนี้ (จังหวะที่ควรอ่านกระดาน)


class StillnessDetector:
    """จำเฟรมก่อนหน้าและนับจำนวนเฟรมนิ่งติดกัน"""

    def __init__(self, threshold: float = MOTION_THRESHOLD, frames_required: int = STILL_FRAMES):
        self.threshold = threshold
        self.frames_required = frames_required
        self._previous: np.ndarray | None = None
        self._still_count = 0
        self._was_still = False

    def reset(self) -> None:
        """ล้างสถานะ (เช่น หลัง calibrate ใหม่ ภาพกระดานเปลี่ยนทั้งภาพ)"""
        self._previous = None
        self._still_count = 0
        self._was_still = False

    def update(self, board: np.ndarray) -> MotionResult:
        current = preprocess(board)
        diff = float("inf") if self._previous is None else mean_abs_diff(current, self._previous)
        self._previous = current

        # ขั้นที่ 4: นับเฟรมที่ D < T ติดกัน ถ้าเฟรมไหนขยับ ให้เริ่มนับใหม่
        self._still_count = self._still_count + 1 if diff < self.threshold else 0
        still = self._still_count >= self.frames_required
        became_still = still and not self._was_still
        self._was_still = still
        return MotionResult(diff=diff, still=still, became_still=became_still)
