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
STILL_FRAMES = 5               # N: ต้องนิ่งติดกัน 5 เฟรม (~1 วินาทีที่ 5 fps)
