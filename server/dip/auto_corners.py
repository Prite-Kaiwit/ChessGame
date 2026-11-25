"""หามุมกระดานอัตโนมัติด้วย Canny + Hough Transform (ตัวเลือกเสริม / ทดลอง)

ใช้เป็น "ค่าเริ่มต้น" ในหน้า /calibrate แล้วให้ผู้ใช้ลากปรับเอง เพราะอาจพลาดได้
เมื่อมีขอบโต๊ะ เงา หรือของวางอยู่ข้างกระดาน

ขั้นตอน
1. Canny edge detection
     - เบลอด้วย Gaussian ลด noise
     - หาเกรเดียนต์ด้วย Sobel:  G = √(Gx² + Gy²),  ทิศ θ = atan2(Gy, Gx)
     - Non-maximum suppression: เก็บเฉพาะพิกเซลที่ G สูงสุดตามแนว θ (ขอบบาง 1 พิกเซล)
     - Hysteresis: G > high = ขอบแน่นอน, low < G < high = ขอบเฉพาะเมื่อต่อกับขอบแน่นอน
2. Probabilistic Hough Transform (HoughLinesP)
     - เส้นตรงทุกเส้นเขียนได้เป็น  ρ = x·cosθ + y·sinθ
     - ทุกพิกเซลขอบ "โหวต" ให้ทุกคู่ (ρ, θ) ที่ผ่านตัวมัน คู่ที่ได้คะแนนเกิน threshold คือเส้นจริง
3. แยกเส้นเป็น 2 กลุ่มตามมุม: แนวนอน (|มุม| < 45°) และแนวตั้ง
4. เลือกเส้นนอกสุด: แนวนอนบนสุด/ล่างสุด, แนวตั้งซ้ายสุด/ขวาสุด → ขอบกระดาน 4 ด้าน
5. หาจุดตัดของเส้นคู่ที่ติดกัน → 4 มุม
     เส้นในรูป a·x + b·y = c สองเส้นตัดกันที่ (กฎของคราเมอร์ Cramer's rule)
         det = a1·b2 − a2·b1
         x = (c1·b2 − c2·b1) / det,   y = (a1·c2 − a2·c1) / det
"""

import cv2
import numpy as np

Line = tuple[float, float, float]  # (a, b, c) ของเส้น a·x + b·y = c


def _segment_to_line(x1: float, y1: float, x2: float, y2: float) -> Line:
    """เส้นตรงที่ผ่าน 2 จุด: a = y2 − y1, b = x1 − x2, c = a·x1 + b·y1"""
    a, b = y2 - y1, x1 - x2
    return a, b, a * x1 + b * y1


def _intersect(l1: Line, l2: Line) -> tuple[float, float] | None:
    """จุดตัดของ 2 เส้นด้วยกฎของคราเมอร์ คืน None ถ้าเส้นขนานกัน (det ≈ 0)"""
    a1, b1, c1 = l1
    a2, b2, c2 = l2
    det = a1 * b2 - a2 * b1
    if abs(det) < 1e-9:
        return None
    return (c1 * b2 - c2 * b1) / det, (a1 * c2 - a2 * c1) / det


def detect_corners(frame: np.ndarray) -> np.ndarray | None:
    """คืนมุม 4 จุด (พิกเซล) เรียง ซ้ายบน, ขวาบน, ขวาล่าง, ซ้ายล่าง หรือ None ถ้าหาไม่ได้"""
    height, width = frame.shape[:2]
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY) if frame.ndim == 3 else frame

    # ขั้นที่ 1: Canny (threshold ต่ำ/สูง = 50/150 อัตราส่วน 1:3 ตามที่ Canny แนะนำ)
    edges = cv2.Canny(cv2.GaussianBlur(gray, (5, 5), 0), 50, 150)

    # ขั้นที่ 2: Hough — ยอมรับเฉพาะเส้นที่ยาวอย่างน้อย 15% ของด้านที่สั้นกว่าของภาพ
    segments = cv2.HoughLinesP(
        edges, rho=1, theta=np.pi / 180, threshold=60,
        minLineLength=int(0.15 * min(width, height)), maxLineGap=12,
    )
    if segments is None:
        return None

    # ขั้นที่ 3: แยกกลุ่มแนวนอน/แนวตั้ง และเก็บตำแหน่งที่เส้นตัดแกนกลางภาพไว้ใช้เรียงลำดับ
    horizontal: list[tuple[float, Line]] = []  # (y ที่ x = กึ่งกลางภาพ, เส้น)
    vertical: list[tuple[float, Line]] = []    # (x ที่ y = กึ่งกลางภาพ, เส้น)
    # OpenCV 4 คืนรูปทรง (N, 1, 4) ส่วน OpenCV 5 คืน (N, 4): reshape ให้เป็น (N, 4) เสมอ
    for x1, y1, x2, y2 in segments.reshape(-1, 4):
        line = _segment_to_line(float(x1), float(y1), float(x2), float(y2))
        a, b, c = line
        angle = abs(np.degrees(np.arctan2(y2 - y1, x2 - x1))) % 180
        if angle < 45 or angle > 135:      # แนวนอน: b ≠ 0 แน่นอน
            horizontal.append(((c - a * width / 2) / b, line))
        else:                               # แนวตั้ง: a ≠ 0 แน่นอน
            vertical.append(((c - b * height / 2) / a, line))
    if len(horizontal) < 2 or len(vertical) < 2:
        return None

    # ขั้นที่ 4: เส้นนอกสุดของแต่ละกลุ่ม
    top = min(horizontal, key=lambda item: item[0])[1]
    bottom = max(horizontal, key=lambda item: item[0])[1]
    left = min(vertical, key=lambda item: item[0])[1]
    right = max(vertical, key=lambda item: item[0])[1]

    # ขั้นที่ 5: จุดตัด → มุม
    corners = [_intersect(top, left), _intersect(top, right),
               _intersect(bottom, right), _intersect(bottom, left)]
    if any(point is None for point in corners):
        return None
    quad = np.array(corners, dtype=np.float32)

    # ตรวจความสมเหตุสมผล: มุมต้องอยู่ในภาพ (เผื่อขอบ 2%), เป็นรูปนูน และใหญ่พอ (≥ 5% ของภาพ)
    margin = 0.02 * max(width, height)
    inside = np.all((quad[:, 0] >= -margin) & (quad[:, 0] <= width + margin)
                    & (quad[:, 1] >= -margin) & (quad[:, 1] <= height + margin))
    area = cv2.contourArea(quad)
    if not inside or not cv2.isContourConvex(quad.reshape(-1, 1, 2)) or area < 0.05 * width * height:
        return None

    quad[:, 0] = np.clip(quad[:, 0], 0, width - 1)
    quad[:, 1] = np.clip(quad[:, 1], 0, height - 1)
    return quad
