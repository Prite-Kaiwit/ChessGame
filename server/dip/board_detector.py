"""ดัดภาพกระดานให้ตรง (perspective transform) แล้วตัดเป็น 64 ช่อง a1–h8

ขั้นตอน
    1. warp_board   : ใช้ 4 มุมที่ calibrate ไว้ คำนวณ homography H แล้วดัดภาพเป็น 800x800
    2. orient_board : หมุนภาพให้ฝั่งขาวอยู่ด้านล่างเสมอ (a1 อยู่มุมล่างซ้าย)
    3. split_squares: ตัดเป็นช่องละ 100x100 แล้วตั้งชื่อ a1–h8
    4. draw_grid    : วาดตาราง 8x8 พร้อมชื่อช่อง ไว้แสดงบนหน้า /board
"""

import cv2
import numpy as np

from server.config import BOARD_PX, SQUARE_PX

FILES = "abcdefgh"

# จุดปลายทางของ 4 มุม (ลำดับเดียวกับที่ผู้ใช้คลิก: ซ้ายบน, ขวาบน, ขวาล่าง, ซ้ายล่าง)
BOARD_DST = np.array(
    [[0, 0], [BOARD_PX, 0], [BOARD_PX, BOARD_PX], [0, BOARD_PX]], dtype=np.float32
)


def compute_homography(corners_px: np.ndarray) -> np.ndarray:
    """คำนวณเมทริกซ์ homography H (3x3) ที่แปลงมุมกระดานในภาพ → สี่เหลี่ยมจัตุรัส 800x800

    แบบจำลอง (พิกัดเอกพันธ์ homogeneous coordinates):

        [x']   [h11 h12 h13] [x]
        [y'] = [h21 h22 h23] [y]        u = x' / w'
        [w']   [h31 h32  1 ] [1]        v = y' / w'

    (x, y) = จุดในภาพกล้อง, (u, v) = จุดบนกระดานที่ดัดแล้ว
    กำหนด h33 = 1 จึงเหลือตัวแปรไม่ทราบค่า 8 ตัว จัดรูปเป็นสมการเชิงเส้นได้จุดละ 2 สมการ:

        h11·x + h12·y + h13 − h31·x·u − h32·y·u = u
        h21·x + h22·y + h23 − h31·x·v − h32·y·v = v

    4 มุม × 2 สมการ = 8 สมการ ตรงกับ 8 ตัวแปรพอดี → แก้ระบบ A·h = b ได้คำตอบเดียว
    (cv2.getPerspectiveTransform ทำขั้นตอนนี้ให้)
    """
    return cv2.getPerspectiveTransform(corners_px.astype(np.float32), BOARD_DST)


def warp_board(frame: np.ndarray, corners_px: np.ndarray) -> np.ndarray:
    """ดัดภาพกระดานให้เป็นมุมมองจากด้านบนตรงๆ ขนาด 800x800

    cv2.warpPerspective ใช้ "inverse mapping": สำหรับทุกพิกเซล (u, v) ของภาพปลายทาง
    หาตำแหน่งต้นทาง [x, y, w]ᵀ = H⁻¹ · [u, v, 1]ᵀ แล้วอ่านค่าสีที่ (x/w, y/w)
    ด้วย bilinear interpolation (เฉลี่ยถ่วงน้ำหนัก 4 พิกเซลรอบจุดนั้น)
    วิธีนี้ทำให้ภาพปลายทางไม่มีรูโหว่ ต่างจากการ map ไปข้างหน้าทีละพิกเซล
    """
    matrix = compute_homography(corners_px)
    return cv2.warpPerspective(frame, matrix, (BOARD_PX, BOARD_PX), flags=cv2.INTER_LINEAR)


def orient_board(warped: np.ndarray, white_side: str) -> np.ndarray:
    """หมุนภาพให้ฝั่งขาวอยู่ด้านล่าง เพื่อให้ช่อง a1 อยู่มุมล่างซ้ายเสมอ

    white_side = ฝั่งที่ผู้เล่นขาวนั่ง เมื่อมองจากภาพกล้อง
        bottom → ไม่ต้องหมุน
        top    → หมุน 180°
        left   → หมุนทวนเข็ม 90° (ขอบซ้ายย้ายลงไปเป็นขอบล่าง)
        right  → หมุนตามเข็ม 90° (ขอบขวาย้ายลงไปเป็นขอบล่าง)
    """
    rotations = {
        "bottom": None,
        "top": cv2.ROTATE_180,
        "left": cv2.ROTATE_90_COUNTERCLOCKWISE,
        "right": cv2.ROTATE_90_CLOCKWISE,
    }
    if white_side not in rotations:
        raise ValueError(f"white_side ไม่ถูกต้อง: {white_side}")
    rotation = rotations[white_side]
    return warped if rotation is None else cv2.rotate(warped, rotation)


def square_name(row: int, col: int) -> str:
    """แปลงตำแหน่งแถว/คอลัมน์ในภาพ (เริ่ม 0 ที่มุมซ้ายบน) เป็นชื่อช่อง

    ภาพที่หมุนแล้ว ฝั่งขาวอยู่ล่าง:  คอลัมน์ 0–7 = file a–h,  แถว 0 (บนสุด) = rank 8
        file = FILES[col],   rank = 8 − row
    เช่น row=7, col=0 → a1 (มุมล่างซ้าย),  row=0, col=7 → h8 (มุมบนขวา)
    """
    return f"{FILES[col]}{8 - row}"


def split_squares(board: np.ndarray) -> dict[str, np.ndarray]:
    """ตัดภาพกระดาน (หมุนแล้ว) เป็น 64 ช่อง คืน dict {"a1": ภาพ 100x100, ...}

    ช่องที่แถว row คอลัมน์ col ครอบคลุมพิกเซล
        y ∈ [row·100, (row+1)·100),   x ∈ [col·100, (col+1)·100)
    """
    squares: dict[str, np.ndarray] = {}
    for row in range(8):
        for col in range(8):
            y0, x0 = row * SQUARE_PX, col * SQUARE_PX
            squares[square_name(row, col)] = board[y0:y0 + SQUARE_PX, x0:x0 + SQUARE_PX]
    return squares


def draw_grid(board: np.ndarray) -> np.ndarray:
    """วาดเส้นตาราง 8x8 และชื่อช่องทับบนภาพ (ไม่แก้ภาพต้นฉบับ) ใช้ตรวจว่า calibrate ตรงไหม"""
    canvas = board.copy()
    color = (246, 130, 59)  # BGR ของสีเน้น #3B82F6
    for i in range(9):
        p = min(i * SQUARE_PX, BOARD_PX - 1)
        cv2.line(canvas, (p, 0), (p, BOARD_PX - 1), color, 2)
        cv2.line(canvas, (0, p), (BOARD_PX - 1, p), color, 2)
    for row in range(8):
        for col in range(8):
            origin = (col * SQUARE_PX + 6, row * SQUARE_PX + 24)
            cv2.putText(canvas, square_name(row, col), origin,
                        cv2.FONT_HERSHEY_SIMPLEX, 0.7, color, 2, cv2.LINE_AA)
    return canvas


def find_board_corners(frame: np.ndarray) -> np.ndarray | None:
    """หามุมกระดานอัตโนมัติ (ตัวเลือกเสริม) ดูรายละเอียดใน auto_corners.py"""
    from server.dip.auto_corners import detect_corners

    return detect_corners(frame)
