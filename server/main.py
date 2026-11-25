"""จุดเริ่มต้น FastAPI และ HTTPS server"""

import sys

import uvicorn
from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from server.config import CERT_FILE, HOST, KEY_FILE, PORT, STATIC_DIR, WEB_DIR
from server.gen_cert import ensure_certificate
from server.game_state import game
from server.hub import hub
from server.routes.game_api import router as game_router
from server.routes.test_api import router as test_router
from server.routes.ws import router as ws_router

app = FastAPI(title="ChessGame")
app.include_router(ws_router)
app.include_router(game_router)
app.include_router(test_router)

# ตั้งสถานะเริ่มต้นของเกมไว้ใน hub ทันทีที่โหลดแอป
# หน้า board ที่เชื่อมต่อเข้ามาจะได้ FEN ตำแหน่งเริ่มต้นเสมอ ไม่ว่าจะรันผ่าน run() หรือ uvicorn โดยตรง
hub.set_state(game.snapshot())


@app.get("/", include_in_schema=False)
async def index() -> FileResponse:
    """เปิดหน้า board เป็นหน้าแรก"""
    return FileResponse(WEB_DIR / "board.html")


@app.get("/camera", include_in_schema=False)
async def camera_page() -> FileResponse:
    """ส่งหน้าเชื่อมต่อกล้องมือถือ"""
    return FileResponse(WEB_DIR / "camera.html")


@app.get("/board", include_in_schema=False)
async def board_page() -> FileResponse:
    """ส่งหน้าแสดงกระดานและผลวิเคราะห์"""
    return FileResponse(WEB_DIR / "board.html")


@app.get("/calibrate", include_in_schema=False)
async def calibrate_page() -> FileResponse:
    """ส่งหน้าปรับเทียบมุมกระดาน (เนื้อหาจริงทำในขั้น DIP)"""
    return FileResponse(WEB_DIR / "calibrate.html")


app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


def run(use_tunnel: bool = False) -> None:
    """สร้าง certificate หากยังไม่มีและเริ่ม Uvicorn ผ่าน HTTPS

    use_tunnel=True: เปิด Cloudflare Quick Tunnel เพิ่ม เพื่อให้ iPhone/มือถือทุกรุ่นเปิดกล้องได้
    โดยไม่ต้องยอมรับ self-signed certificate (ดู server/tunnel.py)
    """
    # console บางแบบบน Windows ใช้ cp1252 ซึ่งพิมพ์ภาษาไทย/QR ไม่ได้: บังคับเป็น UTF-8
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")

    ip_address = ensure_certificate()

    print("ChessGame is ready")
    if use_tunnel:
        from server.tunnel import print_qr, start_tunnel

        public_url = start_tunnel(PORT)
        print_qr(f"{public_url}/camera")
        print("Phone (สแกน QR หรือพิมพ์): {}/camera".format(public_url))
        print("Computer: https://localhost:{}/board  (หรือ {}/board)".format(PORT, public_url))
    else:
        print("Phone: https://{}:{}/camera".format(ip_address, PORT))
        print("Computer: https://{}:{}/board".format(ip_address, PORT))
    uvicorn.run(
        app,
        host=HOST,
        port=PORT,
        ssl_certfile=str(CERT_FILE),
        ssl_keyfile=str(KEY_FILE),
    )


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="ChessGame server")
    parser.add_argument(
        "--tunnel",
        action="store_true",
        help="เปิด Cloudflare Tunnel ให้มือถือเข้าผ่าน URL HTTPS จริง (แนะนำสำหรับ iPhone)",
    )
    run(use_tunnel=parser.parse_args().tunnel)
