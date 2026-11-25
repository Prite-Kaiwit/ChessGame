"""ทดสอบ DIP ด้วยภาพกระดานสังเคราะห์ที่รู้คำตอบล่วงหน้า"""

import tempfile
import unittest
from pathlib import Path

import cv2
import numpy as np

from server.dip.auto_corners import detect_corners
from server.dip.board_detector import split_squares, square_name
from server.dip.calibration import Calibration, load_calibration, save_calibration
from server.dip.motion import StillnessDetector
from server.dip.pipeline import DipPipeline, decode_jpeg, encode_jpeg, rectify

CAMERA_SIZE = (1000, 750)  # (กว้าง, สูง) ของภาพกล้องจำลอง
# ตำแหน่งมุมกระดานในภาพกล้อง (มองเฉียง): ซ้ายบน, ขวาบน, ขวาล่าง, ซ้ายล่าง
CAMERA_CORNERS = np.array([[220, 120], [790, 150], [880, 640], [120, 600]], dtype=np.float32)
RED = (0, 0, 230)
GREEN = (0, 200, 0)


def make_board() -> np.ndarray:
    """กระดาน 800x800 ฝั่งขาวอยู่ล่าง: ใส่วงกลมแดงที่ a1 (มุมล่างซ้าย) และเขียวที่ h8 (มุมบนขวา)"""
    board = np.zeros((800, 800, 3), dtype=np.uint8)
    for row in range(8):
        for col in range(8):
            color = (200, 205, 210) if (row + col) % 2 == 0 else (120, 100, 80)
            board[row * 100:(row + 1) * 100, col * 100:(col + 1) * 100] = color
    cv2.circle(board, (50, 750), 30, RED, -1)
    cv2.circle(board, (750, 50), 30, GREEN, -1)
    return board


def camera_view(board: np.ndarray, white_side: str) -> np.ndarray:
    """จำลองภาพที่กล้องเห็น: หมุนกระดานตามฝั่งที่ขาวนั่ง แล้วบิดมุมมองเหมือนถ่ายเฉียง"""
    rotation = {
        "bottom": None,
        "top": cv2.ROTATE_180,
        "left": cv2.ROTATE_90_CLOCKWISE,          # ขอบล่าง (ฝั่งขาว) ไปอยู่ซ้าย
        "right": cv2.ROTATE_90_COUNTERCLOCKWISE,  # ขอบล่าง (ฝั่งขาว) ไปอยู่ขวา
    }[white_side]
    view = board if rotation is None else cv2.rotate(board, rotation)
    src = np.array([[0, 0], [800, 0], [800, 800], [0, 800]], dtype=np.float32)
    matrix = cv2.getPerspectiveTransform(src, CAMERA_CORNERS)
    return cv2.warpPerspective(view, matrix, CAMERA_SIZE, borderValue=(40, 40, 40))


def normalized_corners() -> list[list[float]]:
    return (CAMERA_CORNERS / np.array(CAMERA_SIZE, dtype=np.float32)).tolist()


def color_ratio(square: np.ndarray, bgr: tuple[int, int, int]) -> float:
    """สัดส่วนพิกเซลในช่องที่มีสีใกล้ bgr"""
    distance = np.linalg.norm(square.astype(np.int32) - np.array(bgr), axis=2)
    return float(np.mean(distance < 80))


class BoardDetectorTests(unittest.TestCase):
    def test_square_names_follow_white_at_bottom(self) -> None:
        self.assertEqual(square_name(7, 0), "a1")
        self.assertEqual(square_name(0, 7), "h8")
        self.assertEqual(square_name(0, 0), "a8")
        self.assertEqual(square_name(7, 7), "h1")
        names = split_squares(make_board()).keys()
        self.assertEqual(len(names), 64)

    def test_rectify_recovers_board_for_every_white_side(self) -> None:
        board = make_board()
        for side in ("bottom", "top", "left", "right"):
            with self.subTest(white_side=side):
                frame = camera_view(board, side)
                result = rectify(frame, Calibration(normalized_corners(), side))

                self.assertEqual(result.shape, (800, 800, 3))
                # ภาพที่ดัดกลับต้องใกล้ต้นฉบับ (ต่างกันได้เล็กน้อยจาก interpolation ตามขอบ)
                self.assertLess(np.mean(cv2.absdiff(result, board)), 10)
                squares = split_squares(result)
                self.assertGreater(color_ratio(squares["a1"], RED), 0.2)
                self.assertGreater(color_ratio(squares["h8"], GREEN), 0.2)
                self.assertLess(color_ratio(squares["h1"], RED), 0.01)


class MotionTests(unittest.TestCase):
    def test_still_after_n_identical_frames_and_fires_once(self) -> None:
        detector = StillnessDetector(threshold=4.0, frames_required=3)
        board = make_board()
        results = [detector.update(board) for _ in range(6)]

        # เฟรมแรกไม่มีเฟรมก่อนหน้า (diff = inf) จึงนับนิ่งได้ตั้งแต่เฟรมที่ 2: นิ่งครบ 3 ที่เฟรมที่ 4
        self.assertEqual([r.still for r in results], [False, False, False, True, True, True])
        self.assertEqual(sum(r.became_still for r in results), 1)

    def test_small_noise_is_still_but_hand_is_motion(self) -> None:
        detector = StillnessDetector(threshold=4.0, frames_required=1)
        board = make_board()
        detector.update(board)

        # noise แบบ Gaussian σ = 3 จำลอง noise ของกล้อง/JPEG
        # (ใช้ cv2.randn แทน numpy.random เพราะ Windows App Control บล็อก DLL ของ numpy.random)
        noise = np.zeros(board.shape, dtype=np.float32)
        cv2.randn(noise, 0, 3)
        noisy = np.clip(board + noise, 0, 255).astype(np.uint8)
        self.assertTrue(detector.update(noisy).still)

        hand = board.copy()
        cv2.rectangle(hand, (250, 250), (550, 700), (60, 120, 190), -1)  # "มือ" บังกลางกระดาน
        result = detector.update(hand)
        self.assertFalse(result.still)
        self.assertGreater(result.diff, 4.0)


class AutoCornerTests(unittest.TestCase):
    def test_detects_board_corners_on_plain_background(self) -> None:
        frame = camera_view(make_board(), "bottom")
        quad = detect_corners(frame)

        self.assertIsNotNone(quad)
        error = np.linalg.norm(quad - CAMERA_CORNERS, axis=1)
        self.assertLess(float(error.max()), 15, f"มุมคลาดเคลื่อน {error}")

    def test_returns_none_without_board(self) -> None:
        self.assertIsNone(detect_corners(np.full((480, 640, 3), 90, dtype=np.uint8)))


class CalibrationAndPipelineTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / "calibration.json"

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_calibration_roundtrip_and_validation(self) -> None:
        self.assertIsNone(load_calibration(self.path))
        save_calibration(self.path, Calibration(normalized_corners(), "left"))
        loaded = load_calibration(self.path)
        self.assertEqual(loaded.white_side, "left")
        np.testing.assert_allclose(loaded.corners, normalized_corners())

        with self.assertRaises(ValueError):
            Calibration([[0, 0], [1, 0], [1, 1]])            # มุมไม่ครบ 4
        with self.assertRaises(ValueError):
            Calibration(normalized_corners(), "diagonal")    # ฝั่งไม่ถูกต้อง
        with self.assertRaises(ValueError):
            Calibration([[0, 0], [1.5, 0], [1, 1], [0, 1]])  # เกินช่วง 0–1

    def test_pipeline_end_to_end(self) -> None:
        pipeline = DipPipeline(self.path)
        jpeg = encode_jpeg(camera_view(make_board(), "bottom"), quality=90)

        self.assertIsNone(pipeline.process(b"not a jpeg"))
        self.assertEqual(pipeline.process(jpeg).status, {"type": "dip", "calibrated": False})

        pipeline.set_calibration(Calibration(normalized_corners(), "bottom"))
        self.assertTrue(self.path.exists())
        outputs = [pipeline.process(jpeg) for _ in range(6)]

        self.assertTrue(outputs[-1].status["still"])
        self.assertEqual(outputs[-1].status["reads"], 1)
        # ได้ 64 ช่องเฉพาะเฟรมที่เพิ่งนิ่ง
        with_squares = [o for o in outputs if o.squares is not None]
        self.assertEqual(len(with_squares), 1)
        self.assertEqual(len(with_squares[0].squares), 64)
        self.assertEqual(decode_jpeg(outputs[-1].warped_jpeg).shape, (800, 800, 3))


if __name__ == "__main__":
    unittest.main()
