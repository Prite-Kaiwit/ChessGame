"""จุดเริ่มต้น FastAPI และ HTTPS server"""

import asyncio
import contextlib
import logging
import sys

import uvicorn
from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from server.config import CERT_FILE, HOST, KEY_FILE, PORT, STATIC_DIR, WEB_DIR
from server.dip.pipeline import pipeline
from server.gen_cert import ensure_certificate
from server.game_state import game
from server.hub import hub
from server.routes.calibration_api import router as calibration_router
from server.routes.game_api import router as game_router
from server.routes import game_api, ml_api
from server.routes.ml_api import router as ml_router
from server.routes.test_api import router as test_router
from server.routes.ws import router as ws_router

logger = logging.getLogger("chessgame")


async def dip_loop() -> None:
    """งานเบื้องหลัง: ทุกครั้งที่มีเฟรมใหม่ ส่งเข้า DIP pipeline แล้วกระจายผลไปหน้า board

    - ประมวลผลเฉพาะเฟรมล่าสุด: ถ้ามีหลายเฟรมเข้ามาระหว่างประมวลผล จะข้ามไปเฟรมใหม่สุดเลย
    - ใช้ asyncio.to_thread ให้ OpenCV ทำงานใน thread แยก WebSocket จึงไม่สะดุด
    """
    while True:
        await hub.frame_event.wait()
        hub.frame_event.clear()
        try:
            output = await asyncio.to_thread(pipeline.process, hub.latest_frame or b"")
        except Exception:  # ภาพเสียหนึ่งเฟรมต้องไม่ทำให้ระบบหยุด
            logger.exception("DIP ประมวลผลเฟรมไม่สำเร็จ")
            continue
        if output is None:
            continue
        hub.publish_dip(output.status)
        if output.warped_jpeg is not None:
            hub.publish_warped(output.warped_jpeg)
        # ภาพเพิ่งนิ่ง: หาตาเดินอัตโนมัติ แล้วให้โมเดลอ่านกระดาน (ถ้ามีโมเดลแล้ว)
        if output.squares is not None:
            try:
                await game_api.auto_detect()
            except Exception:
                logger.exception("ตรวจจับตาเดินอัตโนมัติไม่สำเร็จ")
            try:
                if await asyncio.to_thread(ml_api.read_board_now) is not None:
                    ml_api.publish()
            except Exception:
                logger.exception("ML อ่านกระดานไม่สำเร็จ")


@contextlib.asynccontextmanager
async def lifespan(_: FastAPI):
    """เริ่ม dip_loop ตอนเซิร์ฟเวอร์เปิด และหยุดตอนปิด"""
    task = asyncio.create_task(dip_loop())
    yield
    task.cancel()
    with contextlib.suppress(asyncio.CancelledError):
        await task


app = FastAPI(title="ChessGame", lifespan=lifespan)
app.include_router(ws_router)
app.include_router(game_router)
app.include_router(calibration_router)
app.include_router(test_router)
app.include_router(ml_router)

# ตั้งสถานะเริ่มต้นของเกมไว้ใน hub ทันทีที่โหลดแอป
# หน้า board ที่เชื่อมต่อเข้ามาจะได้ FEN ตำแหน่งเริ่มต้นเสมอ ไม่ว่าจะรันผ่าน run() หรือ uvicorn โดยตรง
hub.set_state(game.analyze())  # ให้ AI คิดตาแรกไว้เลย
hub.publish_ml(ml_api.ml_status())
hub.publish_dip(
    {"type": "dip", "calibrated": False}
    if pipeline.calibration is None
    else {"type": "dip", "calibrated": True, "still": False, "diff": None}
)


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


@app.get("/dataset", include_in_schema=False)
async def dataset_page() -> FileResponse:
    """หน้าตรวจข้อมูลเทรน ML: ดูภาพพร้อมป้าย และลบภาพที่ป้ายผิด"""
    return FileResponse(WEB_DIR / "dataset.html")


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
