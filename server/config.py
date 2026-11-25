"""ค่าตั้งต้นของแอปพลิเคชัน"""

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
