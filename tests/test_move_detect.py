import unittest

import chess
import cv2
import numpy as np

from server.config import SQUARE_PX
from server.dip.move_detect import head_squares, infer_move, move_squares, square_scores
from server.game_state import GameState


def render(board: chess.Board, brightness: int = 0) -> np.ndarray:
    """วาดกระดานจำลอง 800x800 (ขาวอยู่ล่าง) หมากเป็นวงกลม สีต่างกันตามชนิด"""
    image = np.zeros((8 * SQUARE_PX, 8 * SQUARE_PX, 3), np.uint8)
    for row in range(8):
        for col in range(8):
            shade = 200 if (row + col) % 2 == 0 else 120
            image[row * SQUARE_PX:(row + 1) * SQUARE_PX, col * SQUARE_PX:(col + 1) * SQUARE_PX] = shade
    for square, piece in board.piece_map().items():
        row = 7 - chess.square_rank(square)
        col = chess.square_file(square)
        center = (col * SQUARE_PX + SQUARE_PX // 2, row * SQUARE_PX + SQUARE_PX // 2)
        color = (240, 240, 240) if piece.color == chess.WHITE else (20, 20, 20)
        cv2.circle(image, center, 25 + piece.piece_type * 2, color, -1)
    return cv2.add(image, np.full_like(image, brightness)) if brightness else image


def detect(board: chess.Board, move_san: str, brightness: int = 0):
    before = render(board)
    after_board = board.copy()
    after_board.push_san(move_san)
    after = render(after_board, brightness)
    return infer_move(board, square_scores(before, after))


class MoveDetectTests(unittest.TestCase):
    def test_simple_pawn_move(self) -> None:
        result = detect(chess.Board(), "e4")
        self.assertEqual(result.move, "e2e4")
        self.assertEqual(set(result.changed), {"e2", "e4"})

    def test_capture(self) -> None:
        board = chess.Board("rnbqkbnr/ppp1pppp/8/3p4/4P3/8/PPPP1PPP/RNBQKBNR w KQkq - 0 2")
        self.assertEqual(detect(board, "exd5").move, "e4d5")

    def test_castling_beats_plain_king_move(self) -> None:
        # ขาวเข้าป้อมฝั่งคิงได้ และ Kf1 ก็ถูกกติกา ต้องเลือกเข้าป้อมเพราะเปลี่ยน 4 ช่อง
        board = chess.Board("r1bqkbnr/pppp1ppp/2n5/4p3/2B1P3/5N2/PPPP1PPP/RNBQK2R w KQkq - 4 4")
        result = detect(board, "O-O")
        self.assertEqual(result.move, "e1g1")
        self.assertEqual(set(result.changed), {"e1", "f1", "g1", "h1"})

    def test_en_passant(self) -> None:
        board = chess.Board("rnbqkbnr/ppp1p1pp/8/3pPp2/8/8/PPPP1PPP/RNBQKBNR w KQkq f6 0 3")
        self.assertEqual(detect(board, "exf6").move, "e5f6")

    def test_global_brightness_change_is_ignored(self) -> None:
        # กล้องปรับแสงอัตโนมัติ ทุกช่องสว่างขึ้นพร้อมกัน ไม่ควรถูกนับเป็นช่องที่เปลี่ยน
        result = detect(chess.Board(), "Nf3", brightness=20)
        self.assertEqual(result.move, "g1f3")

    def test_no_change_returns_no_move(self) -> None:
        image = render(chess.Board())
        result = infer_move(chess.Board(), square_scores(image, image))
        self.assertIsNone(result.move)
        self.assertEqual(result.changed, [])

    def test_ambiguous_change_is_not_guessed(self) -> None:
        # ช่อง e2, e3, e4 เปลี่ยนเท่ากัน: e2e3 และ e2e4 อธิบายได้เท่ากัน → ไม่เดา
        scores = {chess.square_name(s): 0.0 for s in chess.SQUARES}
        scores.update({"e2": 40.0, "e3": 40.0, "e4": 40.0})
        result = infer_move(chess.Board(), scores)
        self.assertIsNone(result.move)
        self.assertGreaterEqual(len(result.candidates), 2)

    def test_hand_over_board_blocks_detection(self) -> None:
        # เดิน e4 แต่มีมือบังแถบกลางกระดาน (หลายช่องไกลจาก e2/e4 เปลี่ยน) → ต้องไม่เดินให้
        board = chess.Board()
        before = render(board)
        moved = board.copy()
        moved.push_san("e4")
        after = render(moved)
        after[300:420, 0:300] = (60, 90, 140)   # "มือ" สีผิว ทับช่อง a4–c5
        result = infer_move(board, square_scores(before, after))
        self.assertIsNone(result.move)
        self.assertTrue(result.blocked)

    def test_change_next_to_moved_piece_is_tolerated(self) -> None:
        # หัวหมากล้ำไปช่องติดกัน (ช่องเกิน 1 ช่องที่อยู่ติด f3) ยังต้องเดินให้ได้
        scores = {chess.square_name(s): 0.0 for s in chess.SQUARES}
        scores.update({"g1": 45.0, "f3": 25.0, "f4": 19.0})
        result = infer_move(chess.Board(), scores)
        self.assertEqual(result.move, "g1f3")
        self.assertFalse(result.blocked)

    def test_knight_head_over_pawn_square_picks_knight(self) -> None:
        # ข้อมูลจริง: ...Nf6 ทำให้ g8 และ f7 (หัวม้าบน f6 ล้ำไป) เปลี่ยนแรง → ต้องเป็น Nf6 ไม่ใช่ f6
        board = chess.Board("rnbqkbnr/pppppppp/8/8/8/5N2/PPPPPPPP/RNBQKB1R b KQkq - 1 1")
        scores = {chess.square_name(s): 0.0 for s in chess.SQUARES}
        scores.update({"g8": 66.9, "f7": 59.6, "f6": 30.0})
        self.assertEqual(infer_move(board, scores).move, "g8f6")

    def test_head_rule_does_not_override_clear_winner(self) -> None:
        # e6 เปลี่ยนแรงกว่า e5 มาก: ต้องเลือก e6 แม้ e6 จะเป็นช่องหัวหมากของ e5 ก็ตาม
        board = chess.Board("rnbqkbnr/pppppppp/8/8/3P4/8/PPP1PPPP/RNBQKBNR b KQkq - 0 1")
        scores = {chess.square_name(s): 0.0 for s in chess.SQUARES}
        scores.update({"e7": 20.0, "e6": 105.0, "e5": 12.0})
        self.assertEqual(infer_move(board, scores).move, "e7e6")

    def test_weak_leftovers_are_not_guessed(self) -> None:
        # ข้อมูลจริง: c7→c6 กับ Nb8→c6 ให้ c7 และ b8 เปลี่ยนอ่อนๆ พอๆ กัน → ไม่เดา
        board = chess.Board("rnbqkbnr/ppp1pppp/8/3p4/3P4/2N5/PPP1PPPP/R1BQKBNR b KQkq - 1 2")
        scores = {chess.square_name(s): 0.0 for s in chess.SQUARES}
        scores.update({"c6": 93.7, "c7": 16.7, "b8": 15.5})
        result = infer_move(board, scores)
        self.assertIsNone(result.move)
        self.assertEqual({c.uci for c in result.candidates[:2]}, {"c7c6", "b8c6"})

    def test_change_only_in_head_area_is_ignored(self) -> None:
        # มีอะไรเปลี่ยนเฉพาะส่วนบนของช่อง e4 (หัวหมากจาก e3 ล้ำมา) ไม่ใช่ฐานหมาก → e4 ไม่นับว่าเปลี่ยน
        before = render(chess.Board())
        after = before.copy()
        top, left = 4 * SQUARE_PX, 4 * SQUARE_PX          # ช่อง e4 (แถวที่ 4 จากบน, คอลัมน์ e)
        after[top:top + 25, left + 20:left + 80] = (240, 240, 240)
        scores = square_scores(before, after)
        self.assertLess(scores["e4"], 5.0)

    def test_base_area_follows_white_side(self) -> None:
        # ขาวนั่งฝั่งบนของภาพกล้อง → ภาพถูกหมุน 180° ฐานหมากจึงอยู่ครึ่งบนของช่องในภาพที่หมุนแล้ว
        before = render(chess.Board())
        after = before.copy()
        top, left = 4 * SQUARE_PX, 4 * SQUARE_PX
        after[top:top + 50, left + 20:left + 80] = (240, 240, 240)
        self.assertLess(square_scores(before, after, white_side="bottom")["e4"], 10.0)
        self.assertGreater(square_scores(before, after, white_side="top")["e4"], 10.0)

    def test_head_squares_direction(self) -> None:
        self.assertEqual(head_squares({"e4", "h8"}, "bottom"), {"e5"})
        self.assertEqual(head_squares({"e4"}, "top"), {"e3"})
        self.assertEqual(head_squares({"e4"}, "left"), {"d4"})
        self.assertEqual(head_squares({"e4"}, "right"), {"f4"})

    def test_move_squares_for_black_queenside_castle(self) -> None:
        board = chess.Board("r3kbnr/pppqpppp/2n5/3p1b2/3P1B2/2N5/PPPQPPPP/R3KBNR b KQkq - 6 5")
        self.assertEqual(move_squares(board, chess.Move.from_uci("e8c8")), {"e8", "c8", "a8", "d8"})


class ApplyMoveTests(unittest.TestCase):
    def test_apply_legal_move(self) -> None:
        game = GameState(depth=1)
        state = game.apply_move("e2e4")
        self.assertEqual(state["last_move"], "e2e4")
        self.assertIn(state["best_move"], state["legal_moves"])

    def test_apply_illegal_move_raises(self) -> None:
        with self.assertRaises(ValueError):
            GameState(depth=1).apply_move("e2e5")

    def test_apply_garbage_raises(self) -> None:
        with self.assertRaises(ValueError):
            GameState(depth=1).apply_move("hello")


if __name__ == "__main__":
    unittest.main()
