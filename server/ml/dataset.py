"""เก็บข้อมูลสำหรับเทรนโมเดลจำแนกหมาก โดยติดป้าย (label) ให้อัตโนมัติจากสถานะเกม

แนวคิด: ระบบรู้ FEN ของเกมอยู่แล้ว ถ้าภาพกระดานจริงตรงกับ FEN ในจังหวะนั้น
ภาพหนึ่งภาพจะให้ข้อมูลที่ติดป้ายแล้ว 64 ตัวอย่าง (ช่องละหนึ่งตัวอย่าง) โดยไม่ต้องนั่งติดป้ายเอง

จังหวะที่มั่นใจว่าภาพตรงกับ FEN (และเก็บเฉพาะตอนนั้น):
    - กด New game ตอนจัดหมากตำแหน่งเริ่มต้นไว้แล้ว
    - กดเดินเสร็จ แล้วระบบหาตาเดินเจอ
    - กดปุ่ม "บันทึกภาพนี้" เอง (ผู้เล่นยืนยันว่ากระดานจริงตรงกับบนจอ)
ไม่เก็บตอนลากหมากบนจอ เพราะกระดานจริงอาจเดินไปหลายตาแล้ว ป้ายจะผิด

รูปแบบที่เก็บ (server/data/dataset/):
    boards/<id>.jpg   ภาพกระดานดัดตรง 800x800 ทั้งภาพ (ตัดเป็นช่องตอน export
                      จึงเปลี่ยนวิธีตัดภาพย้อนหลังได้)
    index.jsonl       หนึ่งบรรทัดต่อภาพ: {"id", "fen", "source", "time"}
"""

import json
import re
import threading
import time
from pathlib import Path

import chess
import cv2
import numpy as np

from server.config import DATA_DIR

DATASET_DIR = DATA_DIR / "dataset"
SAMPLE_ID = re.compile(r"\d{8}-\d{6}-\d{3}")


class DatasetRecorder:
    def __init__(self, root: Path = DATASET_DIR) -> None:
        self.root = root
        self.enabled = False
        self._lock = threading.Lock()

    @property
    def index_file(self) -> Path:
        return self.root / "index.jsonl"

    def _records(self) -> list[dict]:
        if not self.index_file.exists():
            return []
        with self.index_file.open(encoding="utf-8") as file:
            return [json.loads(line) for line in file if line.strip()]

    def stats(self) -> dict:
        """จำนวนภาพและจำนวนตัวอย่างแยกตามคลาส 3 กลุ่ม"""
        with self._lock:
            records = self._records()
        counts = {"empty": 0, "white": 0, "black": 0}
        for record in records:
            for piece in chess.Board(record["fen"]).piece_map().values():
                counts["white" if piece.color else "black"] += 1
        counts["empty"] = 64 * len(records) - counts["white"] - counts["black"]
        return {"enabled": self.enabled, "boards": len(records), "samples": 64 * len(records), "counts": counts}

    def save(self, board_image: np.ndarray, fen: str, source: str) -> str | None:
        """บันทึกภาพหนึ่งภาพพร้อม FEN คืน id (None ถ้าปิดการเก็บอยู่)"""
        if not self.enabled:
            return None
        chess.Board(fen)  # FEN ผิดรูปแบบ → ValueError ก่อนเขียนไฟล์
        with self._lock:
            (self.root / "boards").mkdir(parents=True, exist_ok=True)
            # id จากเวลา ถ้าบันทึกหลายภาพในมิลลิวินาทีเดียวกัน (เช่นตอนนำเข้ารูป) ให้รอจนได้ id ใหม่
            while True:
                now = time.time()
                sample_id = time.strftime("%Y%m%d-%H%M%S", time.localtime(now)) + f"-{int(now * 1000) % 1000:03d}"
                if not (self.root / "boards" / f"{sample_id}.jpg").exists():
                    break
                time.sleep(0.001)
            cv2.imwrite(str(self.root / "boards" / f"{sample_id}.jpg"), board_image,
                        [cv2.IMWRITE_JPEG_QUALITY, 92])
            record = {"id": sample_id, "fen": fen, "source": source,
                      "time": time.strftime("%Y-%m-%dT%H:%M:%S")}
            with self.index_file.open("a", encoding="utf-8") as file:
                file.write(json.dumps(record, ensure_ascii=False) + "\n")
        return sample_id

    def list_records(self) -> list[dict]:
        """รายการภาพทั้งหมด ใหม่สุดก่อน"""
        with self._lock:
            return list(reversed(self._records()))

    def image_path(self, sample_id: str) -> Path | None:
        """path ของภาพ (None ถ้า id ผิดรูปแบบหรือไม่มีไฟล์ กันการอ่านไฟล์นอกโฟลเดอร์)"""
        if not SAMPLE_ID.fullmatch(sample_id):
            return None
        path = self.root / "boards" / f"{sample_id}.jpg"
        return path if path.exists() else None

    def clear(self) -> int:
        """ลบข้อมูลทั้งหมด คืนจำนวนภาพที่ลบ"""
        with self._lock:
            records = self._records()
            for record in records:
                (self.root / "boards" / f"{record['id']}.jpg").unlink(missing_ok=True)
            self.index_file.unlink(missing_ok=True)
            return len(records)

    def remove(self, sample_id: str) -> bool:
        """ลบภาพที่เพิ่งเก็บ (ใช้ตอน Undo เพราะระบบอาจอ่านตาเดินผิด ป้ายของภาพนั้นจึงผิดด้วย)"""
        with self._lock:
            records = self._records()
            kept = [r for r in records if r["id"] != sample_id]
            if len(kept) == len(records):
                return False
            with self.index_file.open("w", encoding="utf-8") as file:
                file.writelines(json.dumps(r, ensure_ascii=False) + "\n" for r in kept)
            (self.root / "boards" / f"{sample_id}.jpg").unlink(missing_ok=True)
            return True


recorder = DatasetRecorder()
