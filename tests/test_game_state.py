import unittest

import chess

from server.game_state import GameState


class GameStateTests(unittest.TestCase):
    def test_random_move_tracks_san_and_returns_legal_recommendation(self) -> None:
        game = GameState()

        state = game.random_move()

        self.assertEqual(len(state["history"]), 1)
        initial_board = chess.Board()
        played_move = initial_board.parse_san(state["history"][0]["san"])
        self.assertEqual(state["last_move"], played_move.uci())
        initial_board.push(played_move)
        self.assertEqual(state["fen"], initial_board.fen())
        self.assertIn(chess.Move.from_uci(state["best_move"]), game.board.legal_moves)

    def test_reset_restores_starting_position_and_clears_history(self) -> None:
        game = GameState()
        game.random_move()

        state = game.reset()

        self.assertEqual(game.board, chess.Board())
        self.assertEqual(state["history"], [])
        self.assertIsNone(state["last_move"])
        # AI คิดตาแรกของขาวใหม่ทันที
        self.assertIn(chess.Move.from_uci(state["best_move"]), chess.Board().legal_moves)

    def test_undo_removes_last_move_and_recomputes_recommendation(self) -> None:
        game = GameState()
        game.random_move()
        game.random_move()

        state = game.undo()

        self.assertEqual(len(state["history"]), 1)
        self.assertEqual(state["turn"], "black")
        self.assertIn(chess.Move.from_uci(state["best_move"]), game.board.legal_moves)

    def test_ai_move_plays_recommended_move_and_reports_search(self) -> None:
        game = GameState(depth=2)
        recommended = game.analyze()["best_move"]

        state = game.ai_move()

        self.assertEqual(state["last_move"], recommended)
        self.assertEqual(state["depth"], 2)
        self.assertGreater(state["nodes"], 0)
        self.assertIsInstance(state["evaluation"], float)

    def test_undo_without_moves_raises(self) -> None:
        with self.assertRaises(ValueError):
            GameState().undo()


if __name__ == "__main__":
    unittest.main()
