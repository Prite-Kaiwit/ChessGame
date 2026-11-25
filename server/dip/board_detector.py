"""โครงสำหรับตรวจจับและปรับมุมมองกระดานหมากรุก"""

from typing import Any

import numpy as np


def find_board_corners(frame: np.ndarray) -> Any:
    """หาพิกัดมุมทั้งสี่ของกระดานจากภาพกล้อง."""
    raise NotImplementedError("การตรวจจับมุมกระดานยังไม่ถูกพัฒนา")


def warp_board(frame: np.ndarray) -> np.ndarray:
    """แปลงภาพกระดานให้เป็นมุมมองตรงขนาดมาตรฐาน."""
    raise NotImplementedError("การดัดภาพ perspective ยังไม่ถูกพัฒนา")


def split_squares(image: np.ndarray) -> list[np.ndarray]:
    """แบ่งภาพกระดานที่ดัดแล้วออกเป็นภาพ 64 ช่อง."""
    raise NotImplementedError("การแบ่งช่องกระดานยังไม่ถูกพัฒนา")
