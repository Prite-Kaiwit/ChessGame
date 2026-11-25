"""จัดการกระดานและประวัติการเดินด้วย python-chess"""

import random
from typing import Any

import chess


class GameState:
    """เก็บตำแหน่งปัจจุบัน ประวัติ และตาแนะนำของเกม"""

    def __init__(self) -> None:
        self.board = chess.Board()
        self.best_move: str | None = None

    def snapshot(self) -> dict[str, Any]:
        """คืนสถานะกระดานในรูปแบบที่ส่งให้หน้าเว็บได้"""
        history: list[dict[str, Any]] = []
        replay = chess.Board()
        for index, move in enumerate(self.board.move_stack):
            san = replay.san(move)
            replay.push(move)
            history.append(
                {
                    "ply": index + 1,
                    "san": san,
                    "color": "white" if index % 2 == 0 else "black",
                }
            )
        return {
            "type": "state",
            "fen": self.board.fen(),
            "best_move": self.best_move,
            "last_move": self.board.peek().uci() if self.board.move_stack else None,
            "turn": "white" if self.board.turn else "black",
            "history": history,
            "is_game_over": self.board.is_game_over(),
        }

    def random_move(self) -> dict[str, Any]:
        """เดินหมาก legal แบบสุ่มหนึ่งตาและสุ่มตาแนะนำจากตำแหน่งใหม่"""
        legal_moves = list(self.board.legal_moves)
        if not legal_moves:
            raise ValueError("ไม่มี legal move ในตำแหน่งปัจจุบัน")

        selected = random.choice(legal_moves)
        self.board.push(selected)
        next_moves = list(self.board.legal_moves)
        self.best_move = random.choice(next_moves).uci() if next_moves else None
        return self.snapshot()

    def reset(self) -> dict[str, Any]:
        """เริ่มเกมใหม่จากตำแหน่งตั้งต้น"""
        self.board.reset()
        self.best_move = None
        return self.snapshot()

    def undo(self) -> dict[str, Any]:
        """ย้อนกลับหนึ่งตา (ใช้เมื่อระบบอ่านกระดานผิด หรือผู้เล่นขอคืนตา)

        ตาแนะนำเดิมคิดจากตำแหน่งที่ถูกย้อนไปแล้ว จึงล้างทิ้ง รอ AI คำนวณใหม่
        """
        if not self.board.move_stack:
            raise ValueError("ยังไม่มีตาเดินให้ย้อนกลับ")
        self.board.pop()
        self.best_move = None
        return self.snapshot()


# สถานะเกมกลางของเซิร์ฟเวอร์ (มีเกมเดียว ใช้ร่วมกันทุก route)
game = GameState()
