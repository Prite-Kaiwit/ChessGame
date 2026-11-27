"""ใช้โมเดลที่เทรนจาก Colab (ONNX) จำแนกหมากทั้ง 64 ช่อง

ใช้ cv2.dnn ของ OpenCV โหลดโมเดล จึงไม่ต้องติดตั้ง PyTorch บนเครื่องนี้
(เครื่องนี้ Windows App Control บล็อก DLL บางตัว ติดตั้ง PyTorch ไม่ได้)

ไฟล์โมเดล (วางใน server/data/models/ หลังเทรนเสร็จ):
    piece_classifier.onnx   รับภาพ N x 3 x 96 x 64 (RGB, ค่า 0–1) คืนความน่าจะเป็นแต่ละคลาส (softmax แล้ว)
    labels.json             {"classes": ["empty", "white", "black"]}  หรือ 13 คลาส
"""

import json
import threading
from dataclasses import dataclass
from pathlib import Path

import chess
import cv2
import numpy as np

from server.config import DATA_DIR
from server.ml.crops import CROP_H, CROP_W, crop_all, label_of, to_color_label

MODEL_DIR = DATA_DIR / "models"
UNCERTAIN_BELOW = 0.8   # ความมั่นใจต่ำกว่านี้ถือว่า "ไม่แน่ใจ"


@dataclass
class BoardReading:
    labels: dict[str, str]         # ช่อง → คลาสที่ทาย
    confidence: dict[str, float]   # ช่อง → ความน่าจะเป็นของคลาสที่ทาย

    def uncertain(self) -> list[str]:
        return [square for square, p in self.confidence.items() if p < UNCERTAIN_BELOW]


class PieceClassifier:
    def __init__(self, model_dir: Path = MODEL_DIR) -> None:
        self.model_dir = model_dir
        self.net = None
        self.classes: list[str] = []
        self.error: str | None = None
        self._lock = threading.Lock()   # cv2.dnn.Net ใช้พร้อมกันหลายเธรดไม่ได้
        self.reload()

    @property
    def loaded(self) -> bool:
        return self.net is not None

    def reload(self) -> bool:
        """โหลดโมเดลจากไฟล์ (เรียกซ้ำได้หลังวางโมเดลใหม่) คืน True ถ้าสำเร็จ"""
        model, labels = self.model_dir / "piece_classifier.onnx", self.model_dir / "labels.json"
        with self._lock:
            self.net, self.classes, self.error = None, [], None
            if not model.exists() or not labels.exists():
                self.error = "ยังไม่มีไฟล์โมเดล"
                return False
            try:
                self.classes = json.loads(labels.read_text(encoding="utf-8"))["classes"]
                self.net = cv2.dnn.readNetFromONNX(str(model))
            except Exception as error:  # ไฟล์เสียหรือ opset ไม่รองรับ
                self.net, self.error = None, f"โหลดโมเดลไม่สำเร็จ: {error}"
                return False
        return True

    @property
    def name(self) -> str:
        return f"CNN {len(self.classes)} คลาส" if self.loaded else (self.error or "ยังไม่โหลด")

    def _forward(self, board_image: np.ndarray) -> np.ndarray:
        """ความน่าจะเป็นทุกคลาสของทั้ง 64 ช่อง (64 x จำนวนคลาส) เรียงตาม chess.SQUARES"""
        crops = crop_all(board_image)
        blob = cv2.dnn.blobFromImages(crops, scalefactor=1 / 255, size=(CROP_W, CROP_H), swapRB=True)
        with self._lock:
            if self.net is None:
                raise RuntimeError("ยังไม่ได้โหลดโมเดล")
            self.net.setInput(blob)
            return self.net.forward().reshape(64, -1)

    def square_probs(self, board_image: np.ndarray) -> dict[str, dict[str, float]]:
        """ช่อง → {คลาส: ความน่าจะเป็น} ใช้ช่วยตัดสินตาเดินที่ภาพแยกไม่ออก"""
        probs = self._forward(board_image)
        return {
            chess.square_name(square): {name: float(p) for name, p in zip(self.classes, probs[k])}
            for k, square in enumerate(chess.SQUARES)
        }

    def read_board(self, board_image: np.ndarray) -> BoardReading:
        """จำแนกทั้ง 64 ช่องในครั้งเดียว (batch 64)"""
        probs = self._forward(board_image)
        best = probs.argmax(axis=1)
        names = [chess.square_name(square) for square in chess.SQUARES]
        return BoardReading(
            labels={name: self.classes[i] for name, i in zip(names, best)},
            confidence={name: float(probs[k, i]) for k, (name, i) in enumerate(zip(names, best))},
        )

    def expected_labels(self, board: chess.Board) -> dict[str, str]:
        """ป้ายที่ "ควร" ทายได้จากสถานะเกม (ระดับเดียวกับคลาสของโมเดล)"""
        three = len(self.classes) == 3
        result = {}
        for square in chess.SQUARES:
            label = label_of(board.piece_at(square))
            result[chess.square_name(square)] = to_color_label(label) if three else label
        return result


classifier = PieceClassifier()
