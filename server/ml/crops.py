"""ตัดภาพทีละช่องจากกระดานที่ดัดตรงแล้ว สำหรับเทรนและใช้งานโมเดลจำแนกหมาก

ใช้ฟังก์ชันเดียวกันทั้งตอนเตรียมข้อมูลเทรนและตอนใช้งานจริง ภาพที่โมเดลเห็นจึงตรงกันเสมอ

ทำไมไม่ตัดแค่ 100x100 พอดีช่อง:
    กล้องถ่ายเฉียงจากฝั่งผู้เล่น หลังดัดภาพแล้วหมากตัวสูง (คิง ควีน ม้า) จะ "ล้ม" ขึ้นไปทับช่องด้านบน
    ฐานหมากอยู่ในช่องของมัน แต่หัวหมากอยู่ช่องถัดขึ้นไป จึงตัดเผื่อด้านบน 0.6 ช่อง
    และเผื่อซ้ายขวาข้างละ 0.1 ช่อง ส่วนที่เลยขอบกระดานเติมสีดำ

    ┌────────┐  ← เผื่อด้านบน 60 px (เห็นหัวหมาก)
    │ ┌────┐ │
    │ │ช่อง│ │  ← ช่องจริง 100x100
    │ └────┘ │
    └────────┘
    แล้วย่อเป็น CROP_W x CROP_H = 64 x 96 พิกเซล
"""

import chess
import cv2
import numpy as np

from server.config import SQUARE_PX

CROP_W, CROP_H = 64, 96
EXTEND_UP = 0.6     # เผื่อด้านบน (เท่าของขนาดช่อง)
EXTEND_SIDE = 0.1   # เผื่อซ้าย/ขวา

# ชื่อคลาส 13 คลาส (ใช้ชื่อเต็ม ไม่ใช้ P/p เพราะ Windows แยกตัวพิมพ์เล็ก/ใหญ่ในชื่อโฟลเดอร์ไม่ได้)
PIECE_NAMES = {
    chess.PAWN: "pawn", chess.KNIGHT: "knight", chess.BISHOP: "bishop",
    chess.ROOK: "rook", chess.QUEEN: "queen", chess.KING: "king",
}
CLASSES_13 = ["empty"] + [f"{color}_{PIECE_NAMES[p]}" for color in ("white", "black") for p in PIECE_NAMES]
CLASSES_3 = ["empty", "white", "black"]


def label_of(piece: chess.Piece | None) -> str:
    """ป้ายคลาส 13 คลาสของหมากในช่อง (None = ช่องว่าง)"""
    if piece is None:
        return "empty"
    return f"{'white' if piece.color == chess.WHITE else 'black'}_{PIECE_NAMES[piece.piece_type]}"


def to_color_label(label: str) -> str:
    """ย่อป้าย 13 คลาสเหลือ 3 คลาส: empty / white / black"""
    return label.split("_")[0]


def square_box(square: chess.Square) -> tuple[int, int, int, int]:
    """กรอบ (x0, y0, x1, y1) ของช่องบนภาพ 800x800 ที่ขาวอยู่ล่าง รวมส่วนเผื่อแล้ว"""
    col = chess.square_file(square)
    row = 7 - chess.square_rank(square)
    up, side = int(SQUARE_PX * EXTEND_UP), int(SQUARE_PX * EXTEND_SIDE)
    return (col * SQUARE_PX - side, row * SQUARE_PX - up,
            (col + 1) * SQUARE_PX + side, (row + 1) * SQUARE_PX)


def crop_square(board: np.ndarray, square: chess.Square) -> np.ndarray:
    """ภาพของช่องเดียว ขนาด CROP_H x CROP_W (BGR)"""
    x0, y0, x1, y1 = square_box(square)
    # เติมขอบดำรอบกระดานก่อน กรอบที่เลยขอบภาพจึงตัดได้โดยไม่ต้องตรวจทีละกรณี
    pad = int(SQUARE_PX * max(EXTEND_UP, EXTEND_SIDE)) + 1
    padded = cv2.copyMakeBorder(board, pad, pad, pad, pad, cv2.BORDER_CONSTANT, value=(0, 0, 0))
    patch = padded[y0 + pad:y1 + pad, x0 + pad:x1 + pad]
    return cv2.resize(patch, (CROP_W, CROP_H), interpolation=cv2.INTER_AREA)


def crop_all(board: np.ndarray) -> list[np.ndarray]:
    """ภาพทั้ง 64 ช่อง เรียงตาม python-chess (a1, b1, ..., h8)"""
    return [crop_square(board, square) for square in chess.SQUARES]
