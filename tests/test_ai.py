import unittest

import chess

from server.ai.evaluate import MATE_SCORE, evaluate_board
from server.ai.search import search, search_best_move


class EvaluateTests(unittest.TestCase):
    def test_starting_position_is_equal(self) -> None:
        self.assertEqual(evaluate_board(chess.Board()), 0)

    def test_extra_queen_favours_its_owner(self) -> None:
        # ดำไม่มีควีน → ขาวได้เปรียบประมาณ 900
        board = chess.Board("rnb1kbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1")
        self.assertGreater(evaluate_board(board), 800)

    def test_mirrored_position_negates_score(self) -> None:
        board = chess.Board("r1bqkb1r/pppp1ppp/2n2n2/4p3/2B1P3/5N2/PPPP1PPP/RNBQK2R w KQkq - 4 4")
        self.assertEqual(evaluate_board(board), -evaluate_board(board.mirror()))

    def test_checkmate_scores_mate(self) -> None:
        # Fool's mate: ขาวถูกรุกจน
        board = chess.Board()
        for san in ("f3", "e5", "g4", "Qh4#"):
            board.push_san(san)
        self.assertEqual(evaluate_board(board), -MATE_SCORE)


class SearchTests(unittest.TestCase):
    def test_finds_mate_in_one_for_white(self) -> None:
        # Scholar's mate: Qxf7#
        board = chess.Board("r1bqkb1r/pppp1ppp/2n2n2/4p2Q/2B1P3/8/PPPP1PPP/RNB1K1NR w KQkq - 4 4")
        self.assertEqual(search_best_move(board, 2), chess.Move.from_uci("h5f7"))

    def test_finds_mate_in_one_for_black(self) -> None:
        board = chess.Board("rnbqkbnr/pppp1ppp/8/4p3/6P1/5P2/PPPPP2P/RNBQKBNR b KQkq - 0 2")
        result = search(board, 2)
        self.assertEqual(result.move, chess.Move.from_uci("d8h4"))
        self.assertLess(result.score, -MATE_SCORE + 10)

    def test_captures_hanging_queen(self) -> None:
        # ควีนดำที่ d4 ไม่มีใครป้องกัน ม้าขาว f3 กินได้
        board = chess.Board("rnb1kbnr/pppp1ppp/8/4p3/3q4/5N2/PPPPPPPP/RNBQKB1R w KQkq - 0 3")
        self.assertEqual(search_best_move(board, 2), chess.Move.from_uci("f3d4"))

    def test_alphabeta_matches_minimax_with_fewer_nodes(self) -> None:
        # alpha-beta ต้องได้คะแนนเท่า minimax เสมอ (ตัดเฉพาะกิ่งที่ไม่มีผล) แต่ค้นโหนดน้อยกว่า
        board = chess.Board("r1bqkbnr/pppp1ppp/2n5/4p3/4P3/5N2/PPPP1PPP/RNBQKB1R w KQkq - 2 3")
        plain = search(board, 3, use_alphabeta=False, quiescence_search=False)
        pruned = search(board, 3, use_alphabeta=True, quiescence_search=False)
        self.assertEqual(plain.score, pruned.score)
        self.assertLess(pruned.nodes, plain.nodes)

    def test_search_does_not_modify_board(self) -> None:
        board = chess.Board()
        search(board, 2)
        self.assertEqual(board, chess.Board())

    def test_game_over_returns_no_move(self) -> None:
        board = chess.Board()
        for san in ("f3", "e5", "g4", "Qh4#"):
            board.push_san(san)
        self.assertIsNone(search(board, 3).move)


if __name__ == "__main__":
    unittest.main()
