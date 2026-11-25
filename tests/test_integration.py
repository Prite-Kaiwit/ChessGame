"""Integration test: เปิดเซิร์ฟเวอร์ HTTPS จริงในโปรเซสแยก แล้วทดสอบหน้าเว็บ, API และ WebSocket

ใช้พอร์ตทดสอบแยก (8899) เพื่อไม่ชนกับเซิร์ฟเวอร์ที่อาจเปิดใช้งานอยู่บนพอร์ต 8443
"""

import asyncio
import json
import os
import ssl
import subprocess
import sys
import tempfile
import time
import unittest
import urllib.error
import urllib.request
from pathlib import Path

import websockets

from server.config import CERT_FILE, KEY_FILE
from server.dip.pipeline import decode_jpeg, encode_jpeg
from server.gen_cert import ensure_certificate

try:  # รันผ่าน "python -m unittest discover -s tests" หรือ "python -m unittest tests.xxx" ได้ทั้งคู่
    from test_dip import camera_view, make_board, normalized_corners
except ImportError:
    from tests.test_dip import camera_view, make_board, normalized_corners

ROOT = Path(__file__).resolve().parent.parent
PORT = 8899
BASE = f"https://127.0.0.1:{PORT}"
WSS = f"wss://127.0.0.1:{PORT}"

# certificate เป็นแบบ self-signed จึงปิดการตรวจสอบเฉพาะในการทดสอบ
SSL_CTX = ssl.create_default_context()
SSL_CTX.check_hostname = False
SSL_CTX.verify_mode = ssl.CERT_NONE


def http(path: str, method: str = "GET", body: dict | None = None) -> tuple[int, bytes]:
    """ส่ง HTTP request (แนบ JSON ได้) แล้วคืน (status, body)"""
    data = None if body is None else json.dumps(body).encode()
    headers = {} if body is None else {"Content-Type": "application/json"}
    request = urllib.request.Request(BASE + path, data=data, method=method, headers=headers)
    with urllib.request.urlopen(request, context=SSL_CTX, timeout=10) as response:
        return response.status, response.read()


async def recv_json(ws, kind: str = "state") -> dict:
    """รับข้อความ JSON ถัดไปที่มี type ตรงกับ kind โดยข้ามภาพและข้อความชนิดอื่น"""
    while True:
        message = await asyncio.wait_for(ws.recv(), 5)
        if isinstance(message, str):
            data = json.loads(message)
            if data.get("type") == kind:
                return data


async def recv_image(ws, prefix: bytes) -> bytes:
    """รับภาพถัดไปที่ขึ้นต้นด้วย prefix (0x01 กล้อง, 0x02 ภาพดัดตรง) คืนเฉพาะ JPEG"""
    while True:
        message = await asyncio.wait_for(ws.recv(), 5)
        if isinstance(message, bytes) and message[:1] == prefix:
            return message[1:]


class LiveServerTests(unittest.TestCase):
    server: subprocess.Popen

    @classmethod
    def setUpClass(cls) -> None:
        ensure_certificate()
        # ใช้โฟลเดอร์ข้อมูลชั่วคราว: ไม่ไปทับค่า calibrate จริงใน server/data/
        cls.data_dir = tempfile.TemporaryDirectory()
        env = {**os.environ, "CHESS_DATA_DIR": cls.data_dir.name}
        cls.server = subprocess.Popen(
            [
                sys.executable, "-m", "uvicorn", "server.main:app",
                "--host", "127.0.0.1", "--port", str(PORT),
                "--ssl-certfile", str(CERT_FILE), "--ssl-keyfile", str(KEY_FILE),
                "--log-level", "warning",
            ],
            cwd=ROOT,
            env=env,
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
        cls.data_dir.cleanup()
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
                received = [await recv_image(board, b"\x01") for _ in range(2)]
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

    def test_05_calibration_and_dip_stream(self) -> None:
        asyncio.run(self._calibration_and_dip_stream())

    async def _calibration_and_dip_stream(self) -> None:
        # ใช้ภาพกระดานสังเคราะห์ที่ถ่ายเฉียงชุดเดียวกับ unit test ของ DIP
        jpeg = encode_jpeg(camera_view(make_board(), "bottom"), quality=90)

        # ค่าเริ่มต้น: ยังไม่ calibrate (ใช้โฟลเดอร์ข้อมูลชั่วคราว)
        self.assertFalse(json.loads(http("/api/calibration")[1])["calibrated"])

        async with websockets.connect(f"{WSS}/ws/camera", ssl=SSL_CTX) as camera:
            await camera.send(jpeg)
            await asyncio.sleep(0.3)

            # ภาพล่าสุดสำหรับหน้า calibrate
            status, body = await asyncio.to_thread(http, "/api/frame/latest.jpg")
            self.assertEqual((status, body), (200, jpeg))

            # หามุมอัตโนมัติ: ต้องใกล้มุมจริง (คลาดได้ไม่เกิน 2% ของขนาดภาพ)
            _, body = await asyncio.to_thread(http, "/api/calibration/auto", "POST")
            found = json.loads(body)["corners"]
            for got, expected in zip(found, normalized_corners()):
                self.assertAlmostEqual(got[0], expected[0], delta=0.02)
                self.assertAlmostEqual(got[1], expected[1], delta=0.02)

            # ค่าผิดรูปแบบต้องได้ 422
            with self.assertRaises(urllib.error.HTTPError) as caught:
                await asyncio.to_thread(
                    http, "/api/calibration", "POST", {"corners": [[0, 0]], "white_side": "bottom"}
                )
            self.assertEqual(caught.exception.code, 422)
            caught.exception.close()

            body = {"corners": normalized_corners(), "white_side": "bottom"}
            _, preview = await asyncio.to_thread(http, "/api/calibration/preview", "POST", body)
            self.assertEqual(decode_jpeg(preview).shape, (800, 800, 3))
            await asyncio.to_thread(http, "/api/calibration", "POST", body)

            # ส่งภาพเดิมซ้ำ: หน้า board ต้องได้ภาพดัดตรง และสถานะ "นิ่ง" ภายใน N เฟรม
            async with websockets.connect(f"{WSS}/ws/board", ssl=SSL_CTX) as board:
                still = False
                for _ in range(10):
                    await camera.send(jpeg)
                    dip = await recv_json(board, "dip")
                    self.assertTrue(dip["calibrated"])
                    if dip["still"]:
                        still = True
                        break
                    await asyncio.sleep(0.1)
                self.assertTrue(still, "สถานะ DIP ไม่เปลี่ยนเป็นนิ่ง")
                warped = await recv_image(board, b"\x02")
                self.assertEqual(decode_jpeg(warped).shape, (800, 800, 3))


if __name__ == "__main__":
    unittest.main()
