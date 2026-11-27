"""แปลงข้อมูลที่เก็บไว้เป็นไฟล์ zip สำหรับอัปโหลดไปเทรนบน Google Colab

รัน:  python -m server.ml.export_dataset
ได้:  server/data/ml_dataset.zip
      ├─ crops/<คลาส>/<board id>_<ช่อง>.png    ภาพช่องละ 64x96 (ตัดด้วย crops.py)
      └─ manifest.csv                          file, board_id, square, label13, label3

ใน Colab ต้องแบ่ง train/validation "ตามภาพกระดาน" (board_id) ไม่ใช่สุ่มทีละช่อง
เพราะช่องจากภาพเดียวกันแสงและมุมเหมือนกัน ถ้าแยกกันอยู่คนละชุด ความแม่นที่วัดได้จะสูงเกินจริง
"""

import csv
import io
import json
import sys
import zipfile
from pathlib import Path

import chess
import cv2

from server.config import DATA_DIR
from server.ml.crops import crop_all, label_of, to_color_label
from server.ml.dataset import DATASET_DIR


def export(dataset_dir: Path = DATASET_DIR, output: Path = DATA_DIR / "ml_dataset.zip") -> dict[str, int]:
    index = dataset_dir / "index.jsonl"
    if not index.exists():
        raise FileNotFoundError("ยังไม่มีข้อมูล เปิดการเก็บข้อมูลในหน้า /board ก่อน")
    records = [json.loads(line) for line in index.read_text(encoding="utf-8").splitlines() if line.strip()]

    counts: dict[str, int] = {}
    manifest = io.StringIO()
    writer = csv.writer(manifest)
    writer.writerow(["file", "board_id", "square", "label13", "label3"])
    with zipfile.ZipFile(output, "w", zipfile.ZIP_STORED) as archive:  # PNG บีบอัดแล้ว ไม่ต้องบีบซ้ำ
        for record in records:
            image = cv2.imread(str(dataset_dir / "boards" / f"{record['id']}.jpg"))
            if image is None:
                continue
            board = chess.Board(record["fen"])
            for square, crop in zip(chess.SQUARES, crop_all(image)):
                label = label_of(board.piece_at(square))
                name = f"crops/{label}/{record['id']}_{chess.square_name(square)}.png"
                archive.writestr(name, cv2.imencode(".png", crop)[1].tobytes())
                writer.writerow([name, record["id"], chess.square_name(square), label, to_color_label(label)])
                counts[label] = counts.get(label, 0) + 1
        archive.writestr("manifest.csv", manifest.getvalue())
    return counts


if __name__ == "__main__":
    try:
        result = export()
    except FileNotFoundError as error:
        sys.exit(str(error))
    for label, count in sorted(result.items()):
        print(f"{label:14s} {count}")
    print(f"รวม {sum(result.values())} ตัวอย่าง → {DATA_DIR / 'ml_dataset.zip'}")
