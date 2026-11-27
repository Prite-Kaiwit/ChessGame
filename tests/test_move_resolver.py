import unittest

import chess

from server.ml.crops import CLASSES_3, label_of, to_color_label
from server.ml.move_resolver import pick_move

# ตำแหน่งจากเกมจริง: ดำเลือกได้ทั้ง ...c6 และ ...Nc6 ซึ่ง DIP แยกไม่ออก
BOARD = chess.Board("rnbqkbnr/ppp1pppp/8/3p4/3P4/2N5/PPP1PPPP/R1BQKBNR b KQkq - 1 2")
CANDIDATES = ["c7c6", "b8c6"]


def expected_3(board: chess.Board) -> dict[str, str]:
    return {chess.square_name(s): to_color_label(label_of(board.piece_at(s))) for s in chess.SQUARES}


def model_seeing(board: chess.Board, confidence: float = 0.95, overrides: dict | None = None):
    """โมเดลจำลอง: ทายถูกตามกระดาน board ด้วยความมั่นใจ confidence"""
    probs = {}
    for name, label in expected_3(board).items():
        rest = (1 - confidence) / (len(CLASSES_3) - 1)
        probs[name] = {c: (confidence if c == label else rest) for c in CLASSES_3}
    probs.update(overrides or {})
    return probs


def after(uci: str) -> chess.Board:
    board = BOARD.copy()
    board.push_uci(uci)
    return board


class PickMoveTests(unittest.TestCase):
    def test_knight_move_picked_when_b8_empty_and_c7_occupied(self) -> None:
        probs = model_seeing(after("b8c6"))
        self.assertEqual(pick_move(BOARD, CANDIDATES, probs, expected_3), "b8c6")

    def test_pawn_move_picked_when_c7_empty_and_b8_occupied(self) -> None:
        probs = model_seeing(after("c7c6"))
        self.assertEqual(pick_move(BOARD, CANDIDATES, probs, expected_3), "c7c6")

    def test_unsure_model_does_not_guess(self) -> None:
        # โมเดลไม่แน่ใจเลยที่ b8 และ c7 (50/50 ระหว่างว่างกับดำ)
        unsure = {"empty": 0.5, "white": 0.0, "black": 0.5}
        probs = model_seeing(after("b8c6"), overrides={"b8": unsure, "c7": unsure})
        self.assertIsNone(pick_move(BOARD, CANDIDATES, probs, expected_3))

    def test_model_disagreeing_with_every_candidate_does_not_guess(self) -> None:
        # โมเดลเห็นทั้ง b8 และ c7 ว่าง ซึ่งไม่ตรงกับตาไหนเลย → อย่าเดา
        empty = {"empty": 0.95, "white": 0.025, "black": 0.025}
        probs = model_seeing(after("b8c6"), overrides={"c7": empty})
        self.assertIsNone(pick_move(BOARD, CANDIDATES, probs, expected_3))

    def test_single_candidate_is_left_to_dip(self) -> None:
        self.assertIsNone(pick_move(BOARD, ["b8c6"], model_seeing(after("b8c6")), expected_3))


class ResolveInGameApiTests(unittest.TestCase):
    def test_ambiguous_dip_result_is_resolved_by_classifier(self) -> None:
        from types import SimpleNamespace
        from unittest import mock

        from server.dip.move_detect import infer_move
        from server.routes import game_api

        # คะแนน DIP จริงจากเกม: c6 แรง, c7 กับ b8 อ่อนพอๆ กัน → DIP ไม่เดา
        scores = {chess.square_name(s): 0.0 for s in chess.SQUARES}
        scores.update({"c6": 118.3, "c7": 15.4, "b8": 14.7})
        detection = infer_move(BOARD.copy(), scores)
        self.assertIsNone(detection.move)

        fake = SimpleNamespace(loaded=True, square_probs=lambda image: model_seeing(after("b8c6")),
                               expected_labels=expected_3)
        with mock.patch.object(game_api, "classifier", fake), \
                mock.patch.object(game_api, "game", SimpleNamespace(board=BOARD.copy())):
            game_api._resolve_with_classifier(detection, None)
        self.assertEqual(detection.move, "b8c6")
        self.assertIn("ML", detection.reason)


if __name__ == "__main__":
    unittest.main()
