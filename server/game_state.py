"""จัดการกระดานและประวัติการเดินด้วย python-chess"""

import random
import threading
from typing import Any

import chess

from server.ai.search import search
from server.config import AI_DEPTH


class GameState:
    """เก็บตำแหน่งปัจจุบัน ประวัติ และตาแนะนำของเกม

    เมธอดที่เปลี่ยนกระดานจะให้ AI (Minimax + Alpha-Beta) คิดตาแนะนำใหม่ทันที
    การค้นหาใช้เวลาเป็นวินาที route จึงเรียกผ่าน asyncio.to_thread และใช้ lock
    กันสองคำขอแก้กระดานพร้อมกัน
    """

    def __init__(self, depth: int = AI_DEPTH) -> None:
        self.board = chess.Board()
        self.depth = depth
        self.best_move: str | None = None
        self.evaluation: float | None = None   # หน่วยเบี้ย (pawn) มุมมองฝ่ายขาว
        self.nodes: int | None = None
        self.search_ms: int | None = None
        # สีที่ "เรา" เล่น: หน้าเว็บหมุนกระดานให้ฝั่งเราอยู่ล่าง และแสดงตาแนะนำเฉพาะตาของเรา
        self.player_color = "white"
        # ตรวจจับตาเดินอัตโนมัติเมื่อภาพนิ่ง (ไม่ต้องกดปุ่มเดินเสร็จ)
        self.auto_detect = True
        self._lock = threading.RLock()

    def set_player_color(self, color: str) -> dict[str, Any]:
        if color not in ("white", "black"):
            raise ValueError("สีต้องเป็น white หรือ black")
        with self._lock:
            self.player_color = color
            return self.snapshot()

    def analyze(self) -> dict[str, Any]:
        """ให้ AI ค้นหาตาที่ดีที่สุดของฝ่ายที่ถึงตาเดิน แล้วคืนสถานะใหม่"""
        with self._lock:
            result = search(self.board, self.depth)
            self.best_move = result.move.uci() if result.move else None
            self.evaluation = round(result.score / 100, 2)
            self.nodes = result.nodes
            self.search_ms = round(result.seconds * 1000)
            return self.snapshot()

    def apply_move(self, uci: str) -> dict[str, Any]:
        """เดินตาที่ระบุ (จากปุ่มเดินเสร็จหรือการลากบนจอ) แล้วให้ AI คิดตาถัดไป"""
        with self._lock:
            try:
                move = chess.Move.from_uci(uci)
            except ValueError as error:
                raise ValueError(f"รูปแบบตาเดินไม่ถูกต้อง: {uci}") from error
            if move not in self.board.legal_moves:
                raise ValueError(f"{uci} ผิดกติกาในตำแหน่งนี้")
            self.board.push(move)
            return self.analyze()

    def ai_move(self) -> dict[str, Any]:
        """เดินตาที่ AI แนะนำหนึ่งตา (ใช้ทดสอบหรือเล่นกับ AI) แล้วคิดตาถัดไป"""
        with self._lock:
            if self.board.is_game_over():
                raise ValueError("เกมจบแล้ว")
            if self.best_move is None:
                self.analyze()
            self.board.push(chess.Move.from_uci(self.best_move))
            return self.analyze()

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
            "evaluation": self.evaluation,
            "depth": self.depth if self.best_move else None,
            "nodes": self.nodes,
            "search_ms": self.search_ms,
            "last_move": self.board.peek().uci() if self.board.move_stack else None,
            "turn": "white" if self.board.turn else "black",
            "player_color": self.player_color,
            "our_turn": (self.board.turn == chess.WHITE) == (self.player_color == "white"),
            "auto_detect": self.auto_detect,
            "history": history,
            "is_game_over": self.board.is_game_over(),
            # ให้หน้าเว็บรู้ว่าลากหมากตัวไหนไปไหนได้บ้าง
            "legal_moves": [move.uci() for move in self.board.legal_moves],
        }

    def random_move(self) -> dict[str, Any]:
        """เดินหมาก legal แบบสุ่มหนึ่งตา แล้วให้ AI คิดตาแนะนำจากตำแหน่งใหม่"""
        with self._lock:
            legal_moves = list(self.board.legal_moves)
            if not legal_moves:
                raise ValueError("ไม่มี legal move ในตำแหน่งปัจจุบัน")
            self.board.push(random.choice(legal_moves))
            return self.analyze()

    def reset(self) -> dict[str, Any]:
        """เริ่มเกมใหม่จากตำแหน่งตั้งต้น แล้วให้ AI คิดตาแรกของขาว"""
        with self._lock:
            self.board.reset()
            return self.analyze()

    def undo(self) -> dict[str, Any]:
        """ย้อนกลับหนึ่งตา (ใช้เมื่อระบบอ่านกระดานผิด หรือผู้เล่นขอคืนตา)

        ตาแนะนำเดิมคิดจากตำแหน่งที่ถูกย้อนไปแล้ว จึงให้ AI คำนวณใหม่
        """
        with self._lock:
            if not self.board.move_stack:
                raise ValueError("ยังไม่มีตาเดินให้ย้อนกลับ")
            self.board.pop()
            return self.analyze()


# สถานะเกมกลางของเซิร์ฟเวอร์ (มีเกมเดียว ใช้ร่วมกันทุก route)
game = GameState()
