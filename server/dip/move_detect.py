"""หาว่าเดินหมากตาไหน จากภาพกระดาน "ก่อนเดิน" และ "หลังเดิน" (ไม่ใช้ ML)

ใช้เมื่อผู้เล่นกดปุ่ม "เดินเสร็จ" บนหน้า /board

ขั้นที่ 1: หาช่องที่เปลี่ยน (DIP)
    ทั้งสองภาพเป็นกระดานที่ดัดตรงแล้ว 800x800 (ช่องละ 100x100, ขาวอยู่ล่าง)
    1. แปลงเป็นปริภูมิสี CIELAB และเบลอ Gaussian 5x5 ลด noise
       ใช้ระยะห่างสี ΔE = √(ΔL² + Δa² + Δb²) แทนระดับเทา เพราะหมากดำบนช่องดำ
       (และหมากขาวบนช่องสว่าง) มีระดับเทาใกล้กันมาก แต่สี (a, b) ยังต่างกันบ้าง
    2. ต่อช่อง: ใช้เฉพาะ "บริเวณฐานหมาก" ไม่ใช้ทั้งช่อง
       กล้องมองเฉียง หมากที่ยืนอยู่จึงเอนไปทางที่ห่างจากกล้อง (หัวหมากล้ำไปช่องถัดไป)
       ส่วนที่ติดกระดานจริงคือฐานหมาก ซึ่งอยู่ครึ่งช่องฝั่งที่ใกล้กล้อง
       จึงวัดเฉพาะกรอบ 35%–90% ของช่องในแนวที่ห่างจากกล้อง และ 20%–80% ในแนวขวาง
       วัดจากภาพจริง 66 คู่: แยกช่องที่เปลี่ยนจริงออกจาก noise ได้ดีขึ้นเกือบเท่าตัว
       (คะแนน 5% ล่างของช่องที่เปลี่ยนจริง / noise p99: ระดับเทากลางช่อง 1.99 → LAB ฐานหมาก 2.90)
    3. d(ช่อง) = mean ΔE บนบริเวณฐานหมาก
    4. ปรับแสง: ถ้ากล้องปรับความสว่างอัตโนมัติ ทุกช่องจะต่างนิดหน่อยพร้อมกัน
       จึงลบด้วยค่ามัธยฐาน (median) ของทั้ง 64 ช่อง เพราะช่องส่วนใหญ่ไม่ได้เปลี่ยน
           score(ช่อง) = d(ช่อง) − median(d ทั้ง 64 ช่อง)
    5. ช่องที่ score ≥ T ถือว่า "เปลี่ยน"

ขั้นที่ 2: จับคู่กับตาเดินที่ถูกกติกา (ใช้ python-chess)
    แต่ละตาเดินทำให้ช่องเปลี่ยนเป็นชุดที่รู้ล่วงหน้า:
        เดินปกติ/กิน  : {ต้นทาง, ปลายทาง}                      2 ช่อง
        เข้าป้อม      : {คิงต้นทาง, คิงปลายทาง, เรือต้นทาง, เรือปลายทาง}  4 ช่อง
        กินผ่าน (en passant): {ต้นทาง, ปลายทาง, ช่องเบี้ยที่ถูกกิน}   3 ช่อง
    ตาเดินที่เป็นไปได้ = ทุกช่องในชุดต้อง "เปลี่ยน"
    เรียงโดย
        (1) อธิบายช่องที่เปลี่ยนได้มากที่สุด
            เช่น เข้าป้อม O-O (4 ช่องเปลี่ยน) ชนะ Kf1 (อธิบายได้แค่ 2 ช่อง)
        (2) score เฉลี่ยของชุดสูงสุด
    ถ้าอันดับ 1 กับ 2 สูสีกัน (score อันดับ 2 ≥ 80% ของอันดับ 1) ตัดสินด้วย
        "ช่องที่เปลี่ยนแรง (≥ 2T) แต่ตาเดินนั้นอธิบายไม่ได้" ตาที่เหลือน้อยกว่าชนะ
        ช่องถัดไปทางที่ห่างจากกล้องของแต่ละช่องในชุด ถือว่าอธิบายได้ เพราะหัวหมากล้ำไปตรงนั้น
        เช่น ม้า g8→f6: ช่องเปลี่ยน {g8 (~65), f7 (~60, หัวม้าบน f6 ล้ำไป f7), f6 (~27)}
             Nf6 เหลือ f7 ซึ่งเป็นช่องหัวหมาก → อธิบายได้หมด
             เบี้ย f7→f6 เหลือ g8 ซึ่งเปลี่ยนแรงและอธิบายไม่ได้ → แพ้
        ถ้ายังเท่ากันอีก → ไม่เดาให้ ให้ผู้เล่นลากหมากบนจอเอง
        (เช่น c7→c6 กับ Nb8→c6 ที่ c7 และ b8 เปลี่ยนอ่อนๆ พอๆ กัน: ภาพแยกไม่ออกจริงๆ)

ขั้นที่ 3: ตรวจว่ามีอะไรบังกระดานไหม (เช่น มือค้างนิ่งอยู่ในภาพ)
    วัดจากกระดานจริง: เดินปกติจะมีช่องเปลี่ยน "เกิน" มาแค่ 1–2 ช่อง และอยู่ติดกับช่องที่เดิน
    (หัวหมากตัวสูงล้ำไปช่องข้างบน, เงาหมาก) แต่ตอนมีมือบัง ช่องเปลี่ยน 8–20 ช่องกระจายทั่วกระดาน
    จึงยอมรับช่องเกินได้เฉพาะช่องที่อยู่ติดกับช่องของตาเดิน และไม่เกิน MAX_EXTRA ช่อง
    ไม่อย่างนั้นถือว่ามีอะไรบัง → ไม่เดินให้ (รอภาพนิ่งรอบถัดไปหลังเอามือออก)
"""

from dataclasses import dataclass, field

import chess
import cv2
import numpy as np

from server.config import MOVE_DIFF_THRESHOLD, SQUARE_PX
from server.dip.board_detector import square_name

AMBIGUOUS_RATIO = 0.8    # อันดับ 2 ได้ score ≥ 80% ของอันดับ 1 (และอธิบายได้เท่ากัน) = สูสี
MAX_EXTRA = 3            # ช่องที่เปลี่ยนเกินจากตาเดิน (ต้องอยู่ติดกับช่องของตาเดิน) ได้ไม่เกินนี้
STRONG_FACTOR = 2.0      # ตอนตัดสินเสมอ นับเฉพาะช่องที่อธิบายไม่ได้ซึ่งเปลี่ยนแรง (score ≥ 2T)
                         # ช่องที่เปลี่ยนอ่อนๆ อาจเป็นเงาหรือหัวหมาก ใช้แยกสองตาเดินไม่ได้

# บริเวณฐานหมากในช่อง (สัดส่วน 0–1): ตามแนวที่ห่างจากกล้อง (0 = ขอบไกลกล้อง) และแนวขวาง
BASE_ALONG = (0.35, 0.90)
BASE_ACROSS = (0.20, 0.80)

# ทิศ "ห่างจากกล้อง" ในภาพที่หมุนแล้ว (ขาวอยู่ล่าง) ตามฝั่งที่ขาวนั่งในภาพกล้อง
# กล้องอยู่ขอบล่างของภาพกล้องเสมอ หัวหมากจึงเอนไปทางขอบบนของภาพกล้อง
# แล้ว orient_board หมุนขอบบนนั้นไปอยู่: bottom→บน, top→ล่าง, left→ซ้าย, right→ขวา
#     ค่า = (Δfile, Δrank) ของช่องถัดไปทางที่ห่างจากกล้อง
AWAY_STEP = {"bottom": (0, 1), "top": (0, -1), "left": (-1, 0), "right": (1, 0)}


def _prepare(board: np.ndarray) -> np.ndarray:
    color = cv2.cvtColor(board, cv2.COLOR_GRAY2BGR) if board.ndim == 2 else board
    lab = cv2.cvtColor(color, cv2.COLOR_BGR2LAB)
    return cv2.GaussianBlur(lab, (5, 5), 0).astype(np.float32)


def _base_box(white_side: str) -> tuple[int, int, int, int]:
    """กรอบฐานหมากภายในช่อง 100x100 เป็น (y0, y1, x0, x1) ตามทิศที่ห่างจากกล้อง"""
    near0, near1 = (int(SQUARE_PX * v) for v in BASE_ALONG)       # วัดจากขอบไกลกล้อง
    far0, far1 = SQUARE_PX - near1, SQUARE_PX - near0              # วัดจากขอบใกล้กล้อง
    side0, side1 = (int(SQUARE_PX * v) for v in BASE_ACROSS)
    return {
        "bottom": (near0, near1, side0, side1),   # ไกลกล้อง = บน → ฐานอยู่ล่าง
        "top": (far0, far1, side0, side1),        # ไกลกล้อง = ล่าง → ฐานอยู่บน
        "left": (side0, side1, near0, near1),     # ไกลกล้อง = ซ้าย → ฐานอยู่ขวา
        "right": (side0, side1, far0, far1),      # ไกลกล้อง = ขวา → ฐานอยู่ซ้าย
    }[white_side]


def square_scores(before: np.ndarray, after: np.ndarray, white_side: str = "bottom") -> dict[str, float]:
    """ขั้นที่ 1: คะแนนการเปลี่ยนแปลงของทั้ง 64 ช่อง (หลังหักค่ามัธยฐานแล้ว)"""
    a, b = _prepare(before), _prepare(after)
    delta_e = np.sqrt(np.sum((b - a) ** 2, axis=2))
    y0, y1, x0, x1 = _base_box(white_side)
    raw: dict[str, float] = {}
    for row in range(8):
        for col in range(8):
            top, left = row * SQUARE_PX, col * SQUARE_PX
            raw[square_name(row, col)] = float(np.mean(delta_e[top + y0:top + y1, left + x0:left + x1]))
    baseline = float(np.median(list(raw.values())))
    return {name: round(value - baseline, 2) for name, value in raw.items()}


def head_squares(squares: set[str], white_side: str = "bottom") -> set[str]:
    """ช่องถัดไปทางที่ห่างจากกล้องของแต่ละช่อง: หัวหมากในช่องเหล่านั้นล้ำไปถึง"""
    step_file, step_rank = AWAY_STEP[white_side]
    heads = set()
    for name in squares:
        square = chess.parse_square(name)
        file, rank = chess.square_file(square) + step_file, chess.square_rank(square) + step_rank
        if 0 <= file < 8 and 0 <= rank < 8:
            heads.add(chess.square_name(chess.square(file, rank)))
    return heads


def move_squares(board: chess.Board, move: chess.Move) -> set[str]:
    """ชุดช่องที่ภาพจะเปลี่ยนเมื่อเดินตานี้"""
    squares = {move.from_square, move.to_square}
    if board.is_castling(move):
        rank = chess.square_rank(move.from_square)
        kingside = chess.square_file(move.to_square) > chess.square_file(move.from_square)
        rook_from = chess.square(7 if kingside else 0, rank)
        rook_to = chess.square(5 if kingside else 3, rank)
        squares |= {rook_from, rook_to}
    elif board.is_en_passant(move):
        squares.add(chess.square(chess.square_file(move.to_square), chess.square_rank(move.from_square)))
    return {chess.square_name(square) for square in squares}


@dataclass
class Candidate:
    uci: str
    san: str
    explained: int       # จำนวนช่องที่เปลี่ยนซึ่งตาเดินนี้อธิบายได้
    score: float         # score เฉลี่ยของช่องในชุด
    unexplained: int = 0 # ช่องที่เปลี่ยนแต่อธิบายไม่ได้ (ไม่นับช่องหัวหมาก)


@dataclass
class Detection:
    changed: list[str]                 # ช่องที่เปลี่ยน เรียงจากเปลี่ยนมากไปน้อย
    move: str | None                   # ตาเดินที่มั่นใจ (None = ไม่แน่ใจ/ไม่พบ)
    reason: str                        # คำอธิบายสำหรับแสดงบนหน้าเว็บ
    candidates: list[Candidate] = field(default_factory=list)
    scores: dict[str, float] = field(default_factory=dict)
    blocked: bool = False              # มีอะไรบังกระดาน (เช่น มือ) จึงไม่เดินให้


def unexplained_squares(changed: set[str], move_set: set[str]) -> tuple[list[str], list[str]]:
    """แยกช่องที่เปลี่ยนแต่ตาเดินอธิบายไม่ได้ เป็น (ติดกับช่องของตาเดิน, ไกลออกไป)"""
    near, far = [], []
    for name in sorted(changed - move_set):
        square = chess.parse_square(name)
        if any(chess.square_distance(square, chess.parse_square(m)) <= 1 for m in move_set):
            near.append(name)
        else:
            far.append(name)
    return near, far


def _is_close(first: Candidate, second: Candidate) -> bool:
    return second.explained == first.explained and second.score >= first.score * AMBIGUOUS_RATIO


def _break_close_tie(candidates: list[Candidate]) -> list[Candidate]:
    """อันดับ 1 กับ 2 สูสี: ให้ตาที่เหลือช่องอธิบายไม่ได้น้อยกว่าขึ้นก่อน

    ใช้เฉพาะตอนสูสี เพราะช่องหัวหมากบางครั้งเปลี่ยนแรงพอๆ กับช่องจริง
    ถ้าใช้เรียงทุกกรณี จะทำให้ e7→e5 ชนะ e7→e6 ได้ (ช่อง e6 จริงถูกนับว่าเป็นหัวหมากของ e5)
    """
    if len(candidates) < 2 or not _is_close(candidates[0], candidates[1]):
        return candidates
    close = [c for c in candidates if _is_close(candidates[0], c)]
    rest = candidates[len(close):]
    return sorted(close, key=lambda c: (c.unexplained, -c.score)) + rest


def infer_move(board: chess.Board, scores: dict[str, float], threshold: float = MOVE_DIFF_THRESHOLD,
               white_side: str = "bottom") -> Detection:
    """ขั้นที่ 2: เลือกตาเดินที่ถูกกติกาซึ่งตรงกับช่องที่เปลี่ยนมากที่สุด"""
    changed = sorted((name for name, value in scores.items() if value >= threshold),
                     key=lambda name: scores[name], reverse=True)
    if len(changed) < 2:
        return Detection(changed, None, "ไม่พบการเปลี่ยนแปลงบนกระดาน (ช่องที่เปลี่ยนน้อยกว่า 2 ช่อง)",
                         scores=scores)

    changed_set = set(changed)
    candidates: list[Candidate] = []
    for move in board.legal_moves:
        if move.promotion not in (None, chess.QUEEN):
            continue  # โปรโมตเดาจากภาพไม่ได้ว่าเป็นตัวไหน ถือเป็นควีน (เปลี่ยนเองได้ด้วยการลาก)
        squares = move_squares(board, move)
        if not squares <= changed_set:
            continue
        candidates.append(Candidate(
            uci=move.uci(),
            san=board.san(move),
            explained=len(squares),
            score=round(sum(scores[s] for s in squares) / len(squares), 2),
            unexplained=sum(1 for s in changed_set - squares - head_squares(squares, white_side)
                            if scores[s] >= threshold * STRONG_FACTOR),
        ))
    candidates.sort(key=lambda c: (c.explained, c.score), reverse=True)
    candidates = _break_close_tie(candidates)

    if not candidates:
        return Detection(changed, None, "ช่องที่เปลี่ยนไม่ตรงกับตาเดินที่ถูกกติกาตาไหนเลย", scores=scores)
    best = candidates[0]
    best_squares = move_squares(board, chess.Move.from_uci(best.uci))
    near, far = unexplained_squares(changed_set, best_squares)
    if far or len(near) > MAX_EXTRA:
        extra = far + near
        return Detection(changed, None,
                         f"มีอะไรบังกระดานหรือหมากตัวอื่นขยับ ({len(extra)} ช่อง: {', '.join(extra[:6])}) "
                         "เอามือออกแล้วรอสักครู่", candidates[:5], scores, blocked=True)
    if len(candidates) > 1:
        second = candidates[1]
        if _is_close(best, second) and second.unexplained == best.unexplained:
            return Detection(changed, None, f"ไม่แน่ใจระหว่าง {best.san} กับ {second.san}",
                             candidates[:5], scores)
    return Detection(changed, best.uci, f"ตรวจพบ {best.san}", candidates[:5], scores)
