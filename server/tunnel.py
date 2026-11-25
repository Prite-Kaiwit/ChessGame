"""เปิด Cloudflare Quick Tunnel เพื่อให้มือถือเข้าเว็บผ่าน HTTPS ที่มี certificate จริง

ทำไมต้องใช้:
- Safari บน iPhone ไม่ยอมรับ self-signed certificate จึงเปิดกล้องผ่าน https://<IP LAN> ไม่ได้
- cloudflared สร้าง URL แบบ https://<คำสุ่ม>.trycloudflare.com ที่มี certificate ถูกต้อง
  มือถือทุกรุ่นเปิดได้ทันทีโดยไม่ต้องติดตั้ง profile
- การเชื่อมต่อออกจากคอมไปที่ Cloudflare จึงใช้ได้แม้ Wi-Fi จะกันอุปกรณ์ไม่ให้เห็นกัน (client isolation)

เส้นทางข้อมูล:
    มือถือ --HTTPS/WSS--> Cloudflare --tunnel--> cloudflared บนคอม --HTTPS--> 127.0.0.1:8443 (FastAPI)
"""

import atexit
import re
import shutil
import subprocess
import threading
from pathlib import Path

# ตำแหน่งที่ winget/ตัวติดตั้ง MSI วาง cloudflared.exe ไว้ (เผื่อกรณีที่ PATH ยังไม่อัปเดต)
_WINDOWS_PATHS = [
    Path(r"C:\Program Files (x86)\cloudflared\cloudflared.exe"),
    Path(r"C:\Program Files\cloudflared\cloudflared.exe"),
]
_URL_PATTERN = re.compile(r"https://[a-z0-9-]+\.trycloudflare\.com")


def find_cloudflared() -> str:
    """หาไฟล์ cloudflared จาก PATH ก่อน แล้วค่อยดูตำแหน่งติดตั้งมาตรฐานบน Windows"""
    found = shutil.which("cloudflared")
    if found:
        return found
    for path in _WINDOWS_PATHS:
        if path.exists():
            return str(path)
    raise FileNotFoundError(
        "ไม่พบ cloudflared ติดตั้งด้วย: winget install --id Cloudflare.cloudflared -e"
    )


def start_tunnel(local_port: int, timeout: float = 30.0) -> str:
    """เริ่ม cloudflared แล้วรอจนได้ URL สาธารณะ คืนค่า URL นั้น

    - --url https://127.0.0.1:<port> : ส่งต่อทราฟฟิกเข้าเซิร์ฟเวอร์ในเครื่อง
    - --no-tls-verify : เซิร์ฟเวอร์ในเครื่องใช้ self-signed cert จึงให้ cloudflared ข้ามการตรวจ
      (ช่วงนี้อยู่ภายในเครื่องเดียวกัน ส่วนช่วงมือถือ↔Cloudflare ยังเข้ารหัสด้วย cert จริง)
    """
    process = subprocess.Popen(
        [
            find_cloudflared(), "tunnel",
            "--url", f"https://127.0.0.1:{local_port}",
            "--no-tls-verify", "--no-autoupdate",
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    # ปิด tunnel อัตโนมัติเมื่อเซิร์ฟเวอร์หยุด (Ctrl+C)
    atexit.register(process.terminate)

    found = threading.Event()
    result: dict[str, str] = {}

    def read_log() -> None:
        # cloudflared พิมพ์ log (รวมถึง URL) ออกทาง stderr: อ่านไปเรื่อยๆ เพื่อไม่ให้ pipe เต็ม
        assert process.stderr is not None
        for line in process.stderr:
            match = _URL_PATTERN.search(line)
            if match and not found.is_set():
                result["url"] = match.group(0)
                found.set()

    threading.Thread(target=read_log, daemon=True).start()
    if not found.wait(timeout):
        process.terminate()
        raise RuntimeError("cloudflared ไม่ส่ง URL กลับมา ตรวจสอบการเชื่อมต่ออินเทอร์เน็ต")
    return result["url"]


def print_qr(url: str) -> None:
    """พิมพ์ QR code ลงหน้าจอ terminal ให้มือถือสแกนได้ทันที ไม่ต้องพิมพ์ URL ยาวๆ เอง"""
    try:
        import qrcode

        qr = qrcode.QRCode(border=2)
        qr.add_data(url)
        qr.print_ascii(invert=True)
    except (ImportError, UnicodeEncodeError):
        # ไม่มีไลบรารี หรือ console แสดงอักขระบล็อกไม่ได้: ข้ามไป ใช้ URL แทน
        pass
