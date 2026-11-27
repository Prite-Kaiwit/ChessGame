import csv
import io
import tempfile
import unittest
import zipfile
from pathlib import Path

import chess
import cv2
import numpy as np

from server.ml.crops import CLASSES_13, CROP_H, CROP_W, crop_all, crop_square, label_of, square_box
from server.ml.dataset import DatasetRecorder
from server.ml.export_dataset import export
from server.ml.piece_classifier import PieceClassifier


def board_image() -> np.ndarray:
    """ภาพ 800x800 ที่แต่ละช่องมีสีไม่ซ้ำกัน (ใช้ตรวจว่าตัดถูกช่อง)"""
    image = np.zeros((800, 800, 3), np.uint8)
    for square in chess.SQUARES:
        row, col = 7 - chess.square_rank(square), chess.square_file(square)
        image[row * 100:(row + 1) * 100, col * 100:(col + 1) * 100] = (square * 3, 255 - square * 3, 100)
    return image


class CropTests(unittest.TestCase):
    def test_crop_size_and_count(self) -> None:
        crops = crop_all(board_image())
        self.assertEqual(len(crops), 64)
        self.assertTrue(all(c.shape == (CROP_H, CROP_W, 3) for c in crops))

    def test_crop_bottom_is_the_square_itself(self) -> None:
        image = board_image()
        crop = crop_square(image, chess.E4)
        # แถวล่างสุดของภาพตัด (กลางภาพ) ต้องเป็นสีของช่อง e4
        np.testing.assert_array_equal(crop[-3, CROP_W // 2], image[450, 450])

    def test_box_extends_upwards_into_square_above(self) -> None:
        x0, y0, x1, y1 = square_box(chess.A1)
        self.assertEqual((y1 - y0), 160)   # 100 + เผื่อ 60
        self.assertLess(x0, 0)             # เลยขอบซ้าย → เติมดำ
        self.assertEqual(crop_square(board_image(), chess.A8).shape, (CROP_H, CROP_W, 3))

    def test_labels(self) -> None:
        self.assertEqual(label_of(None), "empty")
        self.assertEqual(label_of(chess.Piece(chess.KNIGHT, chess.BLACK)), "black_knight")
        self.assertEqual(len(CLASSES_13), 13)


class DatasetTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name) / "dataset"
        self.recorder = DatasetRecorder(self.root)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_disabled_recorder_saves_nothing(self) -> None:
        self.assertIsNone(self.recorder.save(board_image(), chess.STARTING_FEN, "new_game"))
        self.assertEqual(self.recorder.stats()["boards"], 0)

    def test_save_stats_and_remove(self) -> None:
        self.recorder.enabled = True
        sample = self.recorder.save(board_image(), chess.STARTING_FEN, "new_game")
        stats = self.recorder.stats()
        self.assertEqual(stats["boards"], 1)
        self.assertEqual(stats["counts"], {"empty": 32, "white": 16, "black": 16})

        self.assertTrue(self.recorder.remove(sample))
        self.assertEqual(self.recorder.stats()["boards"], 0)
        self.assertFalse((self.root / "boards" / f"{sample}.jpg").exists())

    def test_list_image_path_and_clear(self) -> None:
        self.recorder.enabled = True
        first = self.recorder.save(board_image(), chess.STARTING_FEN, "manual")
        self.assertEqual([r["id"] for r in self.recorder.list_records()], [first])
        self.assertIsNotNone(self.recorder.image_path(first))
        # id แปลกๆ (เช่นพยายามอ่านไฟล์นอกโฟลเดอร์) ต้องไม่ได้ path
        self.assertIsNone(self.recorder.image_path("../../calibration"))
        self.assertEqual(self.recorder.clear(), 1)
        self.assertEqual(self.recorder.stats()["boards"], 0)
        self.assertIsNone(self.recorder.image_path(first))

    def test_export_writes_labelled_crops(self) -> None:
        self.recorder.enabled = True
        self.recorder.save(board_image(), chess.STARTING_FEN, "new_game")
        output = Path(self.tmp.name) / "out.zip"

        counts = export(self.root, output)

        self.assertEqual(counts["empty"], 32)
        self.assertEqual(counts["white_king"], 1)
        with zipfile.ZipFile(output) as archive:
            rows = list(csv.DictReader(io.StringIO(archive.read("manifest.csv").decode("utf-8"))))
            self.assertEqual(len(rows), 64)
            e1 = next(r for r in rows if r["square"] == "e1")
            self.assertEqual((e1["label13"], e1["label3"]), ("white_king", "white"))
            self.assertIn(e1["file"], archive.namelist())


class ImportPhotosTests(unittest.TestCase):
    def test_import_photos_with_labels_and_skip_repeats(self) -> None:
        from test_move_detect import render
        from server.ml.import_photos import import_folder

        with tempfile.TemporaryDirectory() as tmp:
            folder, recorder = Path(tmp) / "raw", DatasetRecorder(Path(tmp) / "dataset")
            folder.mkdir()
            # "รูปถ่าย": กระดานจำลองวางกลางพื้นหลังสีเทา (ให้หามุมอัตโนมัติได้)
            after_e4 = chess.Board()
            after_e4.push_san("e4")
            for name, board in (("start.jpg", chess.Board()), ("e4.png", after_e4)):
                photo = np.full((1200, 1600, 3), 90, np.uint8)
                photo[200:1000, 400:1200] = render(board)
                cv2.imwrite(str(folder / name), photo)
            (folder / "labels.csv").write_text(f"file,fen\ne4.png,{after_e4.board_fen()}\n", encoding="utf-8")

            results = dict(import_folder(folder, recorder, white_side="bottom"))
            self.assertTrue(all(r.startswith("นำเข้าแล้ว") for r in results.values()), results)
            fens = {r["source"]: r["fen"] for r in recorder.list_records()}
            self.assertEqual(fens["import:start.jpg"], chess.STARTING_FEN)
            self.assertTrue(fens["import:e4.png"].startswith(after_e4.board_fen()))
            self.assertFalse(recorder.enabled)

            again = dict(import_folder(folder, recorder, white_side="bottom"))
            self.assertTrue(all(r.startswith("ข้าม") for r in again.values()))
            self.assertEqual(recorder.stats()["boards"], 2)


class FakeNet:
    """แทน cv2.dnn.Net: ทายทุกช่องเป็น "white" ยกเว้นแถว 7–8 เป็น "black" ความมั่นใจ 0.9"""

    def setInput(self, blob) -> None:
        assert blob.shape == (64, 3, CROP_H, CROP_W)

    def forward(self):
        probs = np.zeros((64, 3), np.float32)
        for square in chess.SQUARES:
            probs[square, 2 if chess.square_rank(square) >= 6 else 1] = 0.9
        probs[chess.D4] = [0.5, 0.3, 0.2]   # ช่องที่ไม่แน่ใจ
        return probs


class ClassifierTests(unittest.TestCase):
    def test_missing_model_is_reported(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            classifier = PieceClassifier(Path(tmp))
        self.assertFalse(classifier.loaded)
        self.assertEqual(classifier.name, "ยังไม่มีไฟล์โมเดล")

    def test_read_board_with_fake_net(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            classifier = PieceClassifier(Path(tmp))
        classifier.net, classifier.classes = FakeNet(), ["empty", "white", "black"]

        reading = classifier.read_board(board_image())
        expected = classifier.expected_labels(chess.Board())

        self.assertEqual(reading.labels["e1"], "white")
        self.assertEqual(reading.labels["e8"], "black")
        self.assertEqual(reading.uncertain(), ["d4"])
        self.assertEqual(expected["e4"], "empty")
        self.assertEqual(expected["e2"], "white")


if __name__ == "__main__":
    unittest.main()
