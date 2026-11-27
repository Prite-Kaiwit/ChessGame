"""ค่าตั้งต้นของแอปพลิเคชัน"""

import os
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
HOST = "0.0.0.0"
PORT = 8443
TARGET_FPS = 5
FRAME_WIDTH = 640
CERT_DIR = ROOT_DIR / "certs"
CERT_FILE = CERT_DIR / "cert.pem"
KEY_FILE = CERT_DIR / "key.pem"
WEB_DIR = ROOT_DIR / "web"
STATIC_DIR = WEB_DIR / "static"

# ---------- DIP ----------
# โฟลเดอร์เก็บค่าที่ผู้ใช้ตั้ง เช่น มุมกระดาน (ตั้ง CHESS_DATA_DIR เพื่อแยกตอนทดสอบได้)
DATA_DIR = Path(os.environ.get("CHESS_DATA_DIR", ROOT_DIR / "server" / "data"))
CALIBRATION_FILE = DATA_DIR / "calibration.json"

BOARD_PX = 800                 # ขนาดภาพกระดานหลังดัดตรง (800x800)
SQUARE_PX = BOARD_PX // 8      # ช่องละ 100x100 พิกเซล

MOTION_SIZE = 200              # ย่อภาพกระดานเหลือ 200x200 ก่อนคำนวณ frame difference
MOTION_THRESHOLD = 4.0         # T: ค่าเฉลี่ยความต่างระดับเทา (0-255) ที่ถือว่า "นิ่ง"
STILL_SECONDS = 1.0            # ต้องนิ่งต่อเนื่อง 1 วินาที (คิดเป็นเวลา จึงไม่ขึ้นกับ fps ของกล้อง)

# ปุ่ม "เดินเสร็จ": ช่องที่ความต่างสีเฉลี่ย ΔE บนฐานหมาก (หลังหักค่ามัธยฐานของทั้งกระดาน) ≥ ค่านี้ ถือว่าเปลี่ยน
# เลือกจากภาพจริง 66 คู่: noise p99 ≈ 6 ส่วนช่องที่เปลี่ยนจริงต่ำสุด ≈ 11 (หมากดำบนช่องดำแถว 8)
MOVE_DIFF_THRESHOLD = 10.0

# ---------- AI ----------
AI_DEPTH = 3                   # ความลึกการค้นหา (ตา) · 3 ใช้เวลา < 1 วินาที, 4 อาจถึง 5 วินาที
