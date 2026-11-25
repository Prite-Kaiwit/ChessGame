"""Integration test: เปิดเซิร์ฟเวอร์ HTTPS จริงในโปรเซสแยก แล้วทดสอบหน้าเว็บ, API และ WebSocket

ใช้พอร์ตทดสอบแยก (8899) เพื่อไม่ชนกับเซิร์ฟเวอร์ที่อาจเปิดใช้งานอยู่บนพอร์ต 8443
"""

import asyncio
import json
import ssl
import subprocess
import sys
import time
import unittest
import urllib.error
import urllib.request
from pathlib import Path

import websockets

from server.config import CERT_FILE, KEY_FILE
from server.gen_cert import ensure_certificate

ROOT = Path(__file__).resolve().parent.parent
PORT = 8899
BASE = f"https://127.0.0.1:{PORT}"
WSS = f"wss://127.0.0.1:{PORT}"

# certificate เป็นแบบ self-signed จึงปิดการตรวจสอบเฉพาะในการทดสอบ
SSL_CTX = ssl.create_default_context()
SSL_CTX.check_hostname = False
SSL_CTX.verify_mode = ssl.CERT_NONE


def http(path: str, method: str = "GET") -> tuple[int, bytes]:
    """ส่ง HTTP request แล้วคืน (status, body)"""
    request = urllib.request.Request(BASE + path, method=method)
    with urllib.request.urlopen(request, context=SSL_CTX, timeout=5) as response:
        return response.status, response.read()


async def recv_json(ws) -> dict:
    """รับข้อความถัดไปที่เป็น JSON โดยข้ามเฟรมภาพ (binary) ที่อาจค้างอยู่"""
    while True:
        message = await asyncio.wait_for(ws.recv(), 5)
        if isinstance(message, str):
            return json.loads(message)


class LiveServerTests(unittest.TestCase):
    server: subprocess.Popen

    @classmethod
    def setUpClass(cls) -> None:
        ensure_certificate()
        cls.server = subprocess.Popen(
            [
                sys.executable, "-m", "uvicorn", "server.main:app",
                "--host", "127.0.0.1", "--port", str(PORT),
                "--ssl-certfile", str(CERT_FILE), "--ssl-keyfile", str(KEY_FILE),
                "--log-level", "warning",
            ],
            cwd=ROOT,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
        )
        # รอจนเซิร์ฟเวอร์พร้อม (สูงสุด ~15 วินาที)
        for _ in range(60):
            try:
                http("/board")
                return
            except OSError:
                time.sleep(0.25)
        cls.server.kill()
        raise RuntimeError("เซิร์ฟเวอร์ทดสอบไม่เริ่มทำงาน")

    @classmethod
    def tearDownClass(cls) -> None:
        cls.server.terminate()
        output, _ = cls.server.communicate(timeout=10)
        # log ระดับ warning ขึ้นไปต้องไม่มี traceback (เช่นตอน client หลุดกะทันหัน)
        if "Traceback" in output:
            raise AssertionError("พบ traceback ใน log ของเซิร์ฟเวอร์:\n" + output)

    def test_01_pages_and_static_files(self) -> None:
        for path in [
            "/", "/camera", "/board", "/calibrate", "/static/js/board.js",
            "/static/js/camera.js", "/static/js/theme.js",
            "/static/css/style.css", "/static/vendor/chessground.min.js",
        ]:
            with self.subTest(path=path):
                self.assertEqual(http(path)[0], 200)

    def test_02_api_and_websockets(self) -> None:
        asyncio.run(self._api_and_websockets())

    async def _api_and_websockets(self) -> None:
        async with websockets.connect(f"{WSS}/ws/board", ssl=SSL_CTX) as board:
            # สถานะแรกที่ได้ตอนเชื่อมต่อต้องมี FEN
            self.assertIn("fen", await recv_json(board))

            # เริ่มเกมใหม่ แล้วสุ่มเดินหนึ่งตา: API และ broadcast ต้องได้ FEN ตรงกัน
            await asyncio.to_thread(http, "/api/test/reset", "POST")
            await recv_json(board)
            status, body = await asyncio.to_thread(http, "/api/test/random-move", "POST")
            state = json.loads(body)
            self.assertEqual(status, 200)
            self.assertEqual(len(state["history"]), 1)
            self.assertRegex(state["best_move"], r"^[a-h][1-8][a-h][1-8]")
            self.assertEqual((await recv_json(board))["fen"], state["fen"])

            # กล้องส่ง 5 เฟรมรวด: หน้า board ต้องได้เฟรมแรกกับเฟรมล่าสุด (เฟรมกลางถูกทิ้ง)
            async with websockets.connect(f"{WSS}/ws/camera", ssl=SSL_CTX) as camera:
                for i in range(5):
                    await camera.send(b"\xff\xd8frame%d" % i)
                await asyncio.sleep(0.3)
                received = [await asyncio.wait_for(board.recv(), 5) for _ in range(2)]
            self.assertEqual(received, [b"\xff\xd8frame0", b"\xff\xd8frame4"])

            # reset ต้องล้างประวัติ
            await asyncio.to_thread(http, "/api/test/reset", "POST")
            self.assertEqual((await recv_json(board))["history"], [])

    def test_03_new_game_and_undo(self) -> None:
        http("/api/game/new", "POST")
        # ยังไม่มีตาเดิน: undo ต้องตอบ 409
        with self.assertRaises(urllib.error.HTTPError) as caught:
            http("/api/game/undo", "POST")
        self.assertEqual(caught.exception.code, 409)
        caught.exception.close()

        http("/api/test/random-move", "POST")
        http("/api/test/random-move", "POST")
        status, body = http("/api/game/undo", "POST")
        self.assertEqual(status, 200)
        self.assertEqual(len(json.loads(body)["history"]), 1)

        status, body = http("/api/game/new", "POST")
        self.assertEqual(json.loads(body)["history"], [])

    def test_04_abrupt_board_disconnect(self) -> None:
        asyncio.run(self._abrupt_disconnect())

    async def _abrupt_disconnect(self) -> None:
        # หน้า board หลุดโดยไม่ส่ง close frame ขณะที่กล้องยังส่งภาพ: เซิร์ฟเวอร์ต้องไม่ล่ม
        board = await websockets.connect(f"{WSS}/ws/board", ssl=SSL_CTX)
        await board.recv()
        board.transport.abort()
        async with websockets.connect(f"{WSS}/ws/camera", ssl=SSL_CTX) as camera:
            for _ in range(10):
                await camera.send(b"\xff\xd8x")
                await asyncio.sleep(0.05)
        self.assertEqual(http("/board")[0], 200)


if __name__ == "__main__":
    unittest.main()
