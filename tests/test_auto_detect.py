import asyncio
import unittest

import chess

from server.dip.calibration import Calibration
from server.dip.pipeline import pipeline
from server.game_state import GameState, game
from server.routes import game_api
from test_move_detect import render


class PlayerColorTests(unittest.TestCase):
    def test_our_turn_follows_player_color(self) -> None:
        state = GameState(depth=1)
        self.assertTrue(state.snapshot()["our_turn"])            # ขาวเดิน เราเป็นขาว
        snapshot = state.set_player_color("black")
        self.assertEqual(snapshot["player_color"], "black")
        self.assertFalse(snapshot["our_turn"])                   # ขาวเดิน เราเป็นดำ → รอฝั่งตรงข้าม

    def test_invalid_color_rejected(self) -> None:
        with self.assertRaises(ValueError):
            GameState(depth=1).set_player_color("red")


class DetectAndApplyTests(unittest.TestCase):
    """จำลองภาพจากกล้องโดยใส่ภาพลงใน pipeline ตรงๆ แล้วเรียก detect_and_apply"""

    def setUp(self) -> None:
        self.saved = (pipeline.calibration, pipeline.latest_board, pipeline.latest_still,
                      pipeline.reference, game.depth, game.player_color, game.auto_detect)
        pipeline.calibration = Calibration(corners=[[0, 0], [1, 0], [1, 1], [0, 1]])   # ถือว่า calibrate แล้ว (ขาวอยู่ล่าง)
        game.depth = 1
        game.reset()

    def tearDown(self) -> None:
        (pipeline.calibration, pipeline.latest_board, pipeline.latest_still,
         pipeline.reference, game.depth, game.player_color, game.auto_detect) = self.saved
        game.reset()

    def show(self, board: chess.Board, still: bool = True) -> None:
        pipeline.latest_board, pipeline.latest_still = render(board), still

    def test_opponent_move_is_applied_automatically(self) -> None:
        game.set_player_color("black")         # เราเป็นดำ ฝั่งตรงข้าม (ขาว) เดินก่อน
        start = chess.Board()
        pipeline.reference = render(start)
        moved = start.copy()
        moved.push_san("e4")
        self.show(moved)

        asyncio.run(game_api.auto_detect())

        self.assertEqual(game.board.peek().uci(), "e2e4")
        state = game.snapshot()
        self.assertTrue(state["our_turn"])     # ถึงตาเรา AI แนะนำได้
        self.assertIsNotNone(state["best_move"])

    def test_nothing_happens_when_board_unchanged(self) -> None:
        pipeline.reference = render(chess.Board())
        self.show(chess.Board())
        asyncio.run(game_api.auto_detect())
        self.assertEqual(len(game.board.move_stack), 0)

    def test_auto_detect_off_does_nothing(self) -> None:
        game.auto_detect = False
        pipeline.reference = render(chess.Board())
        moved = chess.Board()
        moved.push_san("d4")
        self.show(moved)
        asyncio.run(game_api.auto_detect())
        self.assertEqual(len(game.board.move_stack), 0)

    def test_moving_board_is_rejected(self) -> None:
        pipeline.reference = render(chess.Board())
        self.show(chess.Board(), still=False)
        result = asyncio.run(game_api.detect_and_apply("move_done"))
        self.assertIn("error", result)

    def test_two_moves_in_a_row(self) -> None:
        board = chess.Board()
        pipeline.reference = render(board)
        for san in ("e4", "e5"):
            board.push_san(san)
            self.show(board)
            result = asyncio.run(game_api.detect_and_apply("move_done"))
            self.assertEqual(result["result"], "moved")
        self.assertEqual([m.uci() for m in game.board.move_stack], ["e2e4", "e7e5"])


if __name__ == "__main__":
    unittest.main()
