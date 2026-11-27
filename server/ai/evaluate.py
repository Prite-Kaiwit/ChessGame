"""ฟังก์ชันประเมินตำแหน่งหมากรุก (evaluation function)

คะแนนหน่วยเป็น centipawn (1 เบี้ย = 100) ค่าบวก = ฝ่ายขาวได้เปรียบ ค่าลบ = ฝ่ายดำได้เปรียบ

คะแนน = ผลรวมของ (ค่าหมาก + คะแนนตำแหน่งจาก piece-square table) ของฝ่ายขาว
       - ผลรวมแบบเดียวกันของฝ่ายดำ

ค่าหมากและตารางตำแหน่งใช้ตาม "Simplified Evaluation Function" ของ Tomasz Michniewski
(chessprogramming.org) ซึ่งเป็นค่ามาตรฐานที่นิยมใช้สอน
"""

import chess

# ค่าหมากแต่ละชนิด (centipawn)
PIECE_VALUES = {
    chess.PAWN: 100,
    chess.KNIGHT: 320,
    chess.BISHOP: 330,
    chess.ROOK: 500,
    chess.QUEEN: 900,
    chess.KING: 0,  # คิงไม่มีค่าหมาก เพราะถ้าถูกกินเกมก็จบแล้ว (จัดการด้วยคะแนนรุกจน)
}

MATE_SCORE = 100_000  # คะแนนรุกจน สูงกว่าค่าหมากรวมทั้งกระดานมาก

# ---------- Piece-square tables ----------
# เขียนตารางจากมุมมองฝ่ายขาว แถวแรกคือแถว 8 (บนสุด) แถวสุดท้ายคือแถว 1 (ฝั่งขาว)
# อ่านง่ายเหมือนมองกระดานจริง แล้วค่อยแปลงเป็น index ของ python-chess (a1 = 0) ด้านล่าง

PAWN_TABLE = [
     0,   0,   0,   0,   0,   0,   0,   0,
    50,  50,  50,  50,  50,  50,  50,  50,
    10,  10,  20,  30,  30,  20,  10,  10,
     5,   5,  10,  25,  25,  10,   5,   5,
     0,   0,   0,  20,  20,   0,   0,   0,
     5,  -5, -10,   0,   0, -10,  -5,   5,
     5,  10,  10, -20, -20,  10,  10,   5,
     0,   0,   0,   0,   0,   0,   0,   0,
]

KNIGHT_TABLE = [
    -50, -40, -30, -30, -30, -30, -40, -50,
    -40, -20,   0,   0,   0,   0, -20, -40,
    -30,   0,  10,  15,  15,  10,   0, -30,
    -30,   5,  15,  20,  20,  15,   5, -30,
    -30,   0,  15,  20,  20,  15,   0, -30,
    -30,   5,  10,  15,  15,  10,   5, -30,
    -40, -20,   0,   5,   5,   0, -20, -40,
    -50, -40, -30, -30, -30, -30, -40, -50,
]

BISHOP_TABLE = [
    -20, -10, -10, -10, -10, -10, -10, -20,
    -10,   0,   0,   0,   0,   0,   0, -10,
    -10,   0,   5,  10,  10,   5,   0, -10,
    -10,   5,   5,  10,  10,   5,   5, -10,
    -10,   0,  10,  10,  10,  10,   0, -10,
    -10,  10,  10,  10,  10,  10,  10, -10,
    -10,   5,   0,   0,   0,   0,   5, -10,
    -20, -10, -10, -10, -10, -10, -10, -20,
]

ROOK_TABLE = [
     0,   0,   0,   0,   0,   0,   0,   0,
     5,  10,  10,  10,  10,  10,  10,   5,
    -5,   0,   0,   0,   0,   0,   0,  -5,
    -5,   0,   0,   0,   0,   0,   0,  -5,
    -5,   0,   0,   0,   0,   0,   0,  -5,
    -5,   0,   0,   0,   0,   0,   0,  -5,
    -5,   0,   0,   0,   0,   0,   0,  -5,
     0,   0,   0,   5,   5,   0,   0,   0,
]

QUEEN_TABLE = [
    -20, -10, -10,  -5,  -5, -10, -10, -20,
    -10,   0,   0,   0,   0,   0,   0, -10,
    -10,   0,   5,   5,   5,   5,   0, -10,
     -5,   0,   5,   5,   5,   5,   0,  -5,
      0,   0,   5,   5,   5,   5,   0,  -5,
    -10,   5,   5,   5,   5,   5,   0, -10,
    -10,   0,   5,   0,   0,   0,   0, -10,
    -20, -10, -10,  -5,  -5, -10, -10, -20,
]

# คิงช่วงกลางเกม: หลบอยู่หลังเบี้ย ใกล้ป้อม (หลังเข้าป้อม)
KING_MIDDLE_TABLE = [
    -30, -40, -40, -50, -50, -40, -40, -30,
    -30, -40, -40, -50, -50, -40, -40, -30,
    -30, -40, -40, -50, -50, -40, -40, -30,
    -30, -40, -40, -50, -50, -40, -40, -30,
    -20, -30, -30, -40, -40, -30, -30, -20,
    -10, -20, -20, -20, -20, -20, -20, -10,
     20,  20,   0,   0,   0,   0,  20,  20,
     20,  30,  10,   0,   0,  10,  30,  20,
]

# คิงช่วงท้ายเกม: หมากเหลือน้อย คิงควรออกมาช่วยกลางกระดาน
KING_END_TABLE = [
    -50, -40, -30, -20, -20, -30, -40, -50,
    -30, -20, -10,   0,   0, -10, -20, -30,
    -30, -10,  20,  30,  30,  20, -10, -30,
    -30, -10,  30,  40,  40,  30, -10, -30,
    -30, -10,  30,  40,  40,  30, -10, -30,
    -30, -10,  20,  30,  30,  20, -10, -30,
    -30, -30,   0,   0,   0,   0, -30, -30,
    -50, -30, -30, -30, -30, -30, -30, -50,
]


def _to_square_order(table: list[int]) -> list[int]:
    """แปลงตารางที่เขียนแบบแถว 8 อยู่บน ให้เป็นลำดับ a1..h8 ของ python-chess"""
    rows = [table[i * 8:(i + 1) * 8] for i in range(8)]
    return [value for row in reversed(rows) for value in row]


PST = {
    chess.PAWN: _to_square_order(PAWN_TABLE),
    chess.KNIGHT: _to_square_order(KNIGHT_TABLE),
    chess.BISHOP: _to_square_order(BISHOP_TABLE),
    chess.ROOK: _to_square_order(ROOK_TABLE),
    chess.QUEEN: _to_square_order(QUEEN_TABLE),
}
KING_MIDDLE = _to_square_order(KING_MIDDLE_TABLE)
KING_END = _to_square_order(KING_END_TABLE)


def is_endgame(board: chess.Board) -> bool:
    """ถือว่าเป็นท้ายเกมเมื่อไม่มีควีนทั้งสองฝ่าย หรือหมากใหญ่ (ไม่นับเบี้ย/คิง) เหลือน้อย"""
    queens = len(board.pieces(chess.QUEEN, chess.WHITE)) + len(board.pieces(chess.QUEEN, chess.BLACK))
    minor_major = sum(
        len(board.pieces(piece, color))
        for piece in (chess.KNIGHT, chess.BISHOP, chess.ROOK)
        for color in (chess.WHITE, chess.BLACK)
    )
    return queens == 0 or minor_major <= 2


def evaluate_board(board: chess.Board) -> int:
    """ประเมินตำแหน่งแบบคงที่ (ไม่ค้นหาต่อ) คืนค่า centipawn มุมมองฝ่ายขาว"""
    if board.is_checkmate():
        # ฝ่ายที่ถึงตาเดินถูกรุกจน
        return -MATE_SCORE if board.turn == chess.WHITE else MATE_SCORE
    if board.is_stalemate() or board.is_insufficient_material():
        return 0

    king_table = KING_END if is_endgame(board) else KING_MIDDLE
    score = 0
    for square, piece in board.piece_map().items():
        if piece.color == chess.WHITE:
            index = square
        else:
            # ฝ่ายดำใช้ตารางเดียวกันแต่กลับแนวตั้ง (a8 ของดำ = a1 ของขาว)
            index = chess.square_mirror(square)
        table = king_table if piece.piece_type == chess.KING else PST[piece.piece_type]
        value = PIECE_VALUES[piece.piece_type] + table[index]
        score += value if piece.color == chess.WHITE else -value
    return score
