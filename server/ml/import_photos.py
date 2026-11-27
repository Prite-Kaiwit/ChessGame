"""นำเข้ารูปกระดานที่ถ่ายเอง (จากมือถือ/กล้อง) เป็นข้อมูลเทรน ML

วิธีใช้
    1. ถ่ายรูปกระดาน (JPG/PNG) ใส่โฟลเดอร์  server/data/raw_photos/
    2. (ถ้ารูปไหนไม่ใช่ตำแหน่งเริ่มเกม) เขียนไฟล์  server/data/raw_photos/labels.csv
           file,fen
           IMG_0012.jpg,rnbqkbnr/pppppppp/8/8/4P3/8/PPPP1PPP/RNBQKBNR
       รูปที่ไม่มีในไฟล์นี้ = ตำแหน่งเริ่มเกม (ใส่แค่ส่วนแรกของ FEN ก็พอ)
    3. รัน   python -m server.ml.import_photos
       ตัวเลือก:  --calib            ใช้มุมจากการ calibrate แทนการหามุมอัตโนมัติ
                  --white-side top   ฝั่งขาวอยู่ด้านไหนของรูป (ค่าเริ่มต้นตามการ calibrate)
                  --folder <path>    โฟลเดอร์รูปอื่น
    4. เปิดหน้า /dataset ตรวจว่าเส้นตารางตรงช่องและป้ายตรงหมาก ภาพไหนผิดกดลบ

ขั้นตอนต่อรูป
    อ่านรูป → หามุมกระดาน (Canny + Hough ใน auto_corners.py ถ้าไม่เจอใช้มุมจากการ calibrate)
    → ดัดเป็น 800x800 ขาวอยู่ล่าง (ฟังก์ชันเดียวกับระบบกล้อง) → บันทึกพร้อม FEN
รูปที่นำเข้าแล้วจะถูกข้ามในการรันครั้งถัดไป (จำจากชื่อไฟล์)
"""

import argparse
import csv
import sys
from pathlib import Path

import chess
import cv2
import numpy as np

from server.config import CALIBRATION_FILE, DATA_DIR
from server.dip.auto_corners import detect_corners
from server.dip.board_detector import orient_board, warp_board
from server.dip.calibration import WHITE_SIDES, load_calibration
from server.ml.dataset import DatasetRecorder, recorder

RAW_DIR = DATA_DIR / "raw_photos"
IMAGE_TYPES = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}
SOURCE_PREFIX = "import:"
DETECT_MAX_SIDE = 1000   # ย่อรูปก่อนหามุม (ค่า threshold ของ Hough ตั้งไว้สำหรับภาพขนาดราวนี้)


def read_labels(folder: Path) -> dict[str, str]:
    """อ่าน labels.csv (file,fen) คืน {ชื่อไฟล์ตัวพิมพ์เล็ก: FEN เต็ม}"""
    path = folder / "labels.csv"
    if not path.exists():
        return {}
    labels: dict[str, str] = {}
    with path.open(encoding="utf-8-sig", newline="") as file:
        for row in csv.DictReader(file):
            name, fen = (row.get("file") or "").strip(), (row.get("fen") or "").strip()
            if not name or not fen:
                continue
            if fen.lower() in ("start", "เริ่ม"):
                fen = chess.STARTING_FEN
            elif len(fen.split()) == 1:          # ใส่มาแค่ตำแหน่งหมาก
                fen += " w - - 0 1"
            chess.Board(fen)                      # FEN ผิด → ValueError บอกชื่อไฟล์ด้านล่าง
            labels[name.lower()] = fen
    return labels


def find_corners(image: np.ndarray) -> np.ndarray | None:
    """หามุมอัตโนมัติบนรูปที่ย่อแล้ว แล้วขยายพิกัดกลับเป็นขนาดรูปจริง"""
    scale = min(1.0, DETECT_MAX_SIDE / max(image.shape[:2]))
    small = cv2.resize(image, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA) if scale < 1 else image
    corners = detect_corners(small)
    return None if corners is None else corners / scale


def import_folder(folder: Path, target: DatasetRecorder, use_calibration: bool = False,
                  white_side: str | None = None) -> list[tuple[str, str]]:
    """นำเข้าทุกรูปในโฟลเดอร์ คืนรายการ (ชื่อไฟล์, ผลลัพธ์) ไว้แสดง"""
    calibration = load_calibration(CALIBRATION_FILE)
    side = white_side or (calibration.white_side if calibration else "bottom")
    labels = read_labels(folder)
    done = {r["source"][len(SOURCE_PREFIX):].lower() for r in target.list_records()
            if r["source"].startswith(SOURCE_PREFIX)}

    results: list[tuple[str, str]] = []
    was_enabled, target.enabled = target.enabled, True
    try:
        for path in sorted(p for p in folder.iterdir() if p.suffix.lower() in IMAGE_TYPES):
            if path.name.lower() in done:
                results.append((path.name, "ข้าม (นำเข้าแล้ว)"))
                continue
            # imdecode อ่านไฟล์ชื่อภาษาไทยได้ (imread บน Windows อ่านไม่ได้) และ IMREAD_COLOR หมุนตาม EXIF ให้
            image = cv2.imdecode(np.fromfile(str(path), np.uint8), cv2.IMREAD_COLOR)
            if image is None:
                results.append((path.name, "อ่านไม่ได้ (ถ้าเป็น HEIC ให้แปลงเป็น JPG ก่อน)"))
                continue

            corners, method = (None, "") if use_calibration else (find_corners(image), "หามุมอัตโนมัติ")
            if corners is None:
                if calibration is None:
                    results.append((path.name, "หามุมไม่เจอ และยังไม่เคย calibrate"))
                    continue
                height, width = image.shape[:2]
                corners, method = calibration.corners_px(width, height), "ใช้มุมจาก calibrate"

            board = orient_board(warp_board(image, corners), side)
            fen = labels.get(path.name.lower(), chess.STARTING_FEN)
            target.save(board, fen, SOURCE_PREFIX + path.name)
            position = "เริ่มเกม" if fen == chess.STARTING_FEN else "จาก labels.csv"
            results.append((path.name, f"นำเข้าแล้ว ({method}, ตำแหน่ง{position})"))
    finally:
        target.enabled = was_enabled
    return results


def main() -> None:
    parser = argparse.ArgumentParser(description="นำเข้ารูปกระดานที่ถ่ายเองเป็นข้อมูลเทรน")
    parser.add_argument("--folder", type=Path, default=RAW_DIR)
    parser.add_argument("--calib", action="store_true", help="ใช้มุมจากการ calibrate ทุกรูป")
    parser.add_argument("--white-side", choices=WHITE_SIDES, help="ฝั่งขาวอยู่ด้านไหนของรูป")
    args = parser.parse_args()

    if not args.folder.is_dir():
        args.folder.mkdir(parents=True, exist_ok=True)
        print(f"สร้างโฟลเดอร์ {args.folder} แล้ว ใส่รูปแล้วรันใหม่")
        return
    try:
        results = import_folder(args.folder, recorder, args.calib, args.white_side)
    except ValueError as error:
        sys.exit(f"labels.csv มี FEN ผิด: {error}")
    for name, outcome in results:
        print(f"{name}: {outcome}")
    imported = sum(outcome.startswith("นำเข้าแล้ว") for _, outcome in results)
    print(f"\nนำเข้า {imported} รูป · ตรวจที่ https://localhost:8443/dataset ก่อน export")


if __name__ == "__main__":
    main()
