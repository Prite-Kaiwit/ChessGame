"""เก็บ/โหลดค่าการปรับเทียบ (calibration): ตำแหน่ง 4 มุมกระดานในภาพ และฝั่งที่ผู้เล่นขาวนั่ง

พิกัดมุมเก็บแบบ "สัดส่วน" (normalized) 0–1 แทนพิกเซล:
    x_norm = x_px / ความกว้างภาพ,   y_norm = y_px / ความสูงภาพ
จึงใช้ได้แม้ความละเอียดกล้องเปลี่ยน (เช่น มือถือส่ง 640x480 วันนี้ 640x360 พรุ่งนี้)
"""

import json
from dataclasses import asdict, dataclass
from pathlib import Path

import numpy as np

# ฝั่งที่ผู้เล่นขาวนั่ง เทียบกับภาพจากกล้อง
WHITE_SIDES = ("bottom", "top", "left", "right")


@dataclass
class Calibration:
    # 4 มุมของกระดานตามลำดับที่เห็นในภาพ: ซ้ายบน, ขวาบน, ขวาล่าง, ซ้ายล่าง
    corners: list[list[float]]
    white_side: str = "bottom"

    def __post_init__(self) -> None:
        if len(self.corners) != 4 or any(len(point) != 2 for point in self.corners):
            raise ValueError("ต้องมีมุม 4 จุด แต่ละจุดเป็น [x, y]")
        if any(not 0.0 <= value <= 1.0 for point in self.corners for value in point):
            raise ValueError("พิกัดมุมต้องอยู่ในช่วง 0–1 (สัดส่วนของขนาดภาพ)")
        if self.white_side not in WHITE_SIDES:
            raise ValueError(f"white_side ต้องเป็นหนึ่งใน {WHITE_SIDES}")

    def corners_px(self, width: int, height: int) -> np.ndarray:
        """แปลงพิกัดสัดส่วนกลับเป็นพิกเซลของภาพขนาด width x height"""
        scale = np.array([width, height], dtype=np.float32)
        return np.array(self.corners, dtype=np.float32) * scale


def load_calibration(path: Path) -> Calibration | None:
    """อ่านค่าจากไฟล์ JSON คืน None ถ้ายังไม่เคย calibrate หรือไฟล์เสีย"""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return Calibration(corners=data["corners"], white_side=data.get("white_side", "bottom"))
    except (OSError, ValueError, KeyError, TypeError):
        return None


def save_calibration(path: Path, calibration: Calibration) -> None:
    """บันทึกค่าเป็น JSON (สร้างโฟลเดอร์ให้ถ้ายังไม่มี)"""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(asdict(calibration), indent=2), encoding="utf-8")
