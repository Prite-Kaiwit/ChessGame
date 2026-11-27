"""ค้นหาตาเดินที่ดีที่สุดด้วย Minimax + Alpha-Beta pruning

แนวคิด:
  - Minimax: ฝ่ายขาวพยายามทำคะแนนให้ "มากที่สุด" ฝ่ายดำพยายามทำให้ "น้อยที่สุด"
    ไล่ต้นไม้ตาเดินลงไป depth ชั้น แล้วใช้ evaluate_board() ให้คะแนนที่ใบ
  - Alpha-Beta: ตัดกิ่งที่พิสูจน์แล้วว่าไม่มีทางถูกเลือก ได้ผลลัพธ์เท่า Minimax ทุกประการ
    แต่ตรวจโหนดน้อยกว่ามาก
      alpha = คะแนนดีที่สุดที่ฝ่ายขาวการันตีได้แล้ว
      beta  = คะแนนดีที่สุดที่ฝ่ายดำการันตีได้แล้ว
      ถ้า alpha >= beta แปลว่าคู่ต่อสู้จะไม่ยอมให้เกมเดินมาทางนี้ → ตัดกิ่งทิ้ง (cutoff)
  - Move ordering: ลองตาที่น่าจะดีก่อน (กินหมากใหญ่ด้วยหมากเล็ก, โปรโมต, รุก)
    ทำให้ alpha-beta ตัดกิ่งได้เร็วขึ้นมาก
  - Quiescence search: ที่ความลึกสุดท้าย ถ้ายังมีการกินหมากค้างอยู่ จะค้นต่อเฉพาะตากิน
    กันปัญหา horizon effect เช่น เห็นว่ากินควีนได้ แต่ไม่เห็นว่าโดนกินคืน
"""

import math
import time
from dataclasses import dataclass

import chess

from server.ai.evaluate import MATE_SCORE, PIECE_VALUES, evaluate_board

QUIESCENCE_MAX_DEPTH = 6  # จำกัดความลึกของการค้นตากินต่อ กันค้นนานเกินไป


@dataclass
class SearchResult:
    """ผลการค้นหา ใช้แสดงบนหน้าเว็บและใช้เปรียบเทียบในรายงาน"""

    move: chess.Move | None
    score: int          # centipawn มุมมองฝ่ายขาว
    depth: int
    nodes: int          # จำนวนตำแหน่งที่ตรวจ (ใช้วัดผลของ alpha-beta)
    seconds: float


class _Counter:
    """ข้อมูลที่ใช้ร่วมกันระหว่างการค้นหาหนึ่งครั้ง"""

    def __init__(self, quiescence_depth: int) -> None:
        self.nodes = 0
        self.quiescence_depth = quiescence_depth


def _move_priority(board: chess.Board, move: chess.Move) -> int:
    """คะแนนสำหรับเรียงลำดับตาเดิน ยิ่งมากยิ่งลองก่อน"""
    priority = 0
    if board.is_capture(move):
        # MVV-LVA: เหยื่อมีค่ามาก (Most Valuable Victim) กินด้วยหมากค่าน้อย (Least Valuable Attacker)
        victim = board.piece_type_at(move.to_square) or chess.PAWN  # en passant → เบี้ย
        attacker = board.piece_type_at(move.from_square)
        priority += 10 * PIECE_VALUES[victim] - PIECE_VALUES[attacker]
        priority += 10_000
    if move.promotion:
        priority += 9_000 + PIECE_VALUES[move.promotion]
    if board.gives_check(move):
        priority += 500
    return priority


def order_moves(board: chess.Board, moves) -> list[chess.Move]:
    return sorted(moves, key=lambda move: _move_priority(board, move), reverse=True)


def _terminal_score(board: chess.Board, ply: int) -> int | None:
    """คะแนนเมื่อเกมจบ ถ้ายังไม่จบคืน None

    รุกจนได้คะแนน MATE_SCORE - ply เพื่อให้ AI เลือกรุกจนที่เร็วที่สุด
    """
    if board.is_checkmate():
        return -(MATE_SCORE - ply) if board.turn == chess.WHITE else MATE_SCORE - ply
    if board.is_stalemate() or board.is_insufficient_material() or board.can_claim_fifty_moves():
        return 0
    if board.is_repetition(3):
        return 0
    return None


def quiescence(board: chess.Board, alpha: float, beta: float, ply: int, qdepth: int, counter: _Counter) -> int:
    """ค้นต่อเฉพาะตากินหมาก จนตำแหน่ง "สงบ" แล้วค่อยประเมิน"""
    counter.nodes += 1
    terminal = _terminal_score(board, ply)
    if terminal is not None:
        return terminal

    # stand pat: ฝ่ายที่ถึงตาเลือก "ไม่กิน" ได้เสมอ จึงใช้คะแนนปัจจุบันเป็นขั้นต่ำ
    stand_pat = evaluate_board(board)
    if qdepth == 0:
        return stand_pat
    maximizing = board.turn == chess.WHITE
    if maximizing:
        if stand_pat >= beta:
            return stand_pat
        alpha = max(alpha, stand_pat)
    else:
        if stand_pat <= alpha:
            return stand_pat
        beta = min(beta, stand_pat)

    best = stand_pat
    for move in order_moves(board, board.generate_legal_captures()):
        board.push(move)
        score = quiescence(board, alpha, beta, ply + 1, qdepth - 1, counter)
        board.pop()
        if maximizing:
            best = max(best, score)
            alpha = max(alpha, score)
        else:
            best = min(best, score)
            beta = min(beta, score)
        if alpha >= beta:
            break
    return best


def alphabeta(board: chess.Board, depth: int, alpha: float, beta: float, ply: int, counter: _Counter) -> int:
    """Minimax พร้อม Alpha-Beta pruning คืนคะแนนมุมมองฝ่ายขาว"""
    counter.nodes += 1
    terminal = _terminal_score(board, ply)
    if terminal is not None:
        return terminal
    if depth == 0:
        return quiescence(board, alpha, beta, ply, counter.quiescence_depth, counter)

    if board.turn == chess.WHITE:  # ขาว = ผู้หาค่ามากสุด (MAX)
        best = -math.inf
        for move in order_moves(board, board.legal_moves):
            board.push(move)
            best = max(best, alphabeta(board, depth - 1, alpha, beta, ply + 1, counter))
            board.pop()
            alpha = max(alpha, best)
            if alpha >= beta:
                break  # beta cutoff: ดำมีทางเลือกที่ดีกว่านี้อยู่แล้ว จะไม่ยอมให้มาถึงตรงนี้
        return best

    best = math.inf  # ดำ = ผู้หาค่าน้อยสุด (MIN)
    for move in order_moves(board, board.legal_moves):
        board.push(move)
        best = min(best, alphabeta(board, depth - 1, alpha, beta, ply + 1, counter))
        board.pop()
        beta = min(beta, best)
        if alpha >= beta:
            break  # alpha cutoff: ขาวมีทางเลือกที่ดีกว่านี้อยู่แล้ว
    return best


def minimax(board: chess.Board, depth: int, ply: int, counter: _Counter) -> int:
    """Minimax แบบไม่ตัดกิ่ง (ไม่มี quiescence) ใช้เปรียบเทียบจำนวนโหนดกับ alpha-beta เท่านั้น"""
    counter.nodes += 1
    terminal = _terminal_score(board, ply)
    if terminal is not None:
        return terminal
    if depth == 0:
        return evaluate_board(board)
    scores = []
    for move in board.legal_moves:
        board.push(move)
        scores.append(minimax(board, depth - 1, ply + 1, counter))
        board.pop()
    return max(scores) if board.turn == chess.WHITE else min(scores)


def search(board: chess.Board, depth: int, use_alphabeta: bool = True, quiescence_search: bool = True) -> SearchResult:
    """หาตาเดินที่ดีที่สุดของฝ่ายที่ถึงตาเดิน

    use_alphabeta=False จะใช้ minimax ล้วน (ช้ามาก ใช้ทดลองเปรียบเทียบเท่านั้น)
    quiescence_search=False ปิดการค้นตากินต่อ (ใช้เทียบกับ minimax ให้ยุติธรรม)
    """
    board = board.copy()  # ไม่แตะกระดานจริงของเกม (ค้นในเธรดแยกได้ปลอดภัย)
    counter = _Counter(QUIESCENCE_MAX_DEPTH if quiescence_search else 0)
    started = time.perf_counter()
    maximizing = board.turn == chess.WHITE
    best_move: chess.Move | None = None
    best_score = -math.inf if maximizing else math.inf
    alpha, beta = -math.inf, math.inf

    for move in order_moves(board, board.legal_moves):
        board.push(move)
        if use_alphabeta:
            score = alphabeta(board, depth - 1, alpha, beta, 1, counter)
        else:
            score = minimax(board, depth - 1, 1, counter)
        board.pop()
        if (maximizing and score > best_score) or (not maximizing and score < best_score):
            best_score, best_move = score, move
        if use_alphabeta:
            if maximizing:
                alpha = max(alpha, best_score)
            else:
                beta = min(beta, best_score)

    if best_move is None:  # ไม่มีตาเดิน (เกมจบแล้ว)
        best_score = _terminal_score(board, 0) or evaluate_board(board)
    return SearchResult(
        move=best_move,
        score=int(best_score),
        depth=depth,
        nodes=counter.nodes,
        seconds=time.perf_counter() - started,
    )


def search_best_move(board: chess.Board, depth: int) -> chess.Move | None:
    """หาตาเดินที่ดีที่สุดด้วย Minimax + Alpha-Beta pruning"""
    return search(board, depth).move
