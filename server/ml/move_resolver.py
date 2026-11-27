"""ให้โมเดลจำแนกหมาก (ML) ช่วยตัดสินตาเดินที่ภาพ DIP แยกไม่ออก

ตัวอย่างจากเกมจริง: ...c6 (เบี้ย c7→c6) กับ ...Nc6 (ม้า b8→c6)
    DIP เห็น c6 เปลี่ยนแรง ส่วน c7 และ b8 เปลี่ยนอ่อนๆ พอๆ กัน จึงเลือกไม่ได้
    แต่ถ้าโมเดลบอกได้ว่า "b8 ว่าง และ c7 ยังมีหมากดำ" ก็รู้ทันทีว่าเป็น Nc6

วิธีคิด (maximum likelihood)
    1. ช่องที่ใช้ตัดสิน U = ยูเนียนของช่องที่ทุกตาเดินผู้สมัครแตะ  (เช่น {b8, c7, c6})
       ต้องดูทุกช่องใน U ไม่ใช่แค่ช่องของตาตัวเอง เพราะตาที่ไม่ได้แตะ b8 ก็ทำนายว่า b8 "ต้องยังเหมือนเดิม"
    2. ต่อตาเดิน m: เดิน m บนกระดานจำลอง ได้ป้ายที่ควรเห็น y(s) ของแต่ละช่อง
           log L(m) = Σ_{s ∈ U} log P(y(s) | ภาพช่อง s)
    3. เลือก m ที่ log L สูงสุด เฉพาะเมื่อ
       - ชนะอันดับ 2 ขาด: L(อันดับ 1) ≥ MIN_RATIO × L(อันดับ 2)
       - ทุกช่องใน U โมเดลเห็นด้วยพอ: P(y(s)) ≥ MIN_SQUARE_PROB
       ไม่อย่างนั้นยังไม่เดา (ให้ผู้เล่นลากเอง) เพราะเดาผิดแย่กว่าไม่เดา
    โมเดล 3 คลาส (ว่าง/ขาว/ดำ) ก็พอสำหรับกรณีส่วนใหญ่ เพราะต่างกันที่ "ช่องไหนว่าง"
"""

import math
from collections.abc import Callable

import chess

from server.dip.move_detect import move_squares

MIN_RATIO = 10.0          # อันดับ 1 ต้องน่าจะเป็นกว่าอันดับ 2 อย่างน้อย 10 เท่า
MIN_SQUARE_PROB = 0.5     # ทุกช่องที่ใช้ตัดสิน โมเดลต้องให้ป้ายที่คาดไว้ ≥ 0.5
_FLOOR = 1e-6             # กัน log(0)


def pick_move(board: chess.Board, ucis: list[str], square_probs: dict[str, dict[str, float]],
              expected_labels: Callable[[chess.Board], dict[str, str]]) -> str | None:
    """เลือกตาเดินจาก ucis ด้วยผลจำแนกหมากของภาพหลังเดิน คืน None ถ้ายังไม่มั่นใจ"""
    if len(ucis) < 2:
        return None
    moves = [chess.Move.from_uci(uci) for uci in ucis]
    union: set[str] = set()
    for move in moves:
        union |= move_squares(board, move)

    ranked: list[tuple[float, float, str]] = []   # (log L, P ต่ำสุดในช่อง U, uci)
    for move in moves:
        after = board.copy()
        after.push(move)
        expected = expected_labels(after)
        probs = [square_probs[s].get(expected[s], 0.0) for s in union]
        log_likelihood = sum(math.log(max(p, _FLOOR)) for p in probs)
        ranked.append((log_likelihood, min(probs), move.uci()))
    ranked.sort(reverse=True)

    (best_ll, best_min, best_uci), (second_ll, _, _) = ranked[0], ranked[1]
    if best_ll - second_ll < math.log(MIN_RATIO) or best_min < MIN_SQUARE_PROB:
        return None
    return best_uci
