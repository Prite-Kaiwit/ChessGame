# ChessGame

ต้นแบบระบบวิเคราะห์กระดานหมากรุกผ่านกล้องมือถือและหน้าเว็บบนคอมพิวเตอร์

## เริ่มใช้งาน

ต้องใช้ Python 3.14 ขึ้นไป (หรือ Python รุ่นที่ dependencies รองรับ)

```powershell
cd C:\Users\<ชื่อผู้ใช้>\Desktop\ChessGame
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
winget install --id Cloudflare.cloudflared -e   # ครั้งแรกครั้งเดียว
python -m server.main --tunnel
```

มีวิธีรัน 2 โหมด:

| โหมด | คำสั่ง | มือถือที่ใช้ได้ | ต้องมีอินเทอร์เน็ต |
|---|---|---|---|
| **Tunnel (แนะนำสำหรับเดโม)** | `python -m server.main --tunnel` | ทุกรุ่น รวมถึง iPhone | ต้องมี |
| LAN | `python -m server.main` | Android (Chrome) | ไม่ต้อง |

## รัน unit tests

```powershell
.\.venv\Scripts\python -m unittest discover -s tests -v
```

`tests/test_dip.py` ทดสอบ DIP ด้วยภาพกระดานสังเคราะห์ที่ถ่ายเฉียง (ดัดกลับ, ชื่อช่องทั้ง 4 ทิศ, ภาพนิ่ง, หามุมอัตโนมัติ)
`tests/test_integration.py` จะเปิดเซิร์ฟเวอร์ HTTPS จริงบนพอร์ต 8899 เอง (ใช้โฟลเดอร์ข้อมูลชั่วคราว) แล้วทดสอบหน้าเว็บ,
API, WebSocket, การทิ้งเฟรมเก่า, หน้า board หลุดกะทันหัน และ calibrate → ภาพดัดตรง → สถานะภาพนิ่ง

## เปิดกล้องบนมือถือ: โหมด Tunnel (แนะนำ)

Safari บน iPhone ไม่ยอมเปิดเว็บที่ใช้ self-signed certificate และไม่มีปุ่มให้กดผ่าน โหมดนี้จึงใช้
Cloudflare Quick Tunnel (`cloudflared`) สร้าง URL แบบ `https://<คำสุ่ม>.trycloudflare.com`
ซึ่งมี certificate ที่ถูกต้อง มือถือจึงเปิดกล้องได้ทันที ไม่ต้องติดตั้ง profile หรือ root CA

```text
มือถือ --HTTPS/WSS--> Cloudflare --tunnel--> cloudflared (คอม) --> https://127.0.0.1:8443 (FastAPI)
```

1. รัน `python -m server.main --tunnel` แล้วรอประมาณ 5–10 วินาที ระบบจะแสดง QR code
   และบรรทัด `Phone: https://....trycloudflare.com/camera`
2. ใช้กล้องของ iPhone สแกน QR (หรือพิมพ์ URL เอง) แล้วเปิดใน Safari
3. กด "เริ่มส่งภาพ" แล้วอนุญาตให้ใช้กล้อง
4. บนคอม เปิด `https://localhost:8443/board` (ยอมรับคำเตือน certificate บนคอมครั้งแรก)
   หรือจะเปิด URL ของ tunnel ตามด้วย `/board` ก็ได้

ข้อควรรู้:
- **URL จะเปลี่ยนทุกครั้งที่รันใหม่** ต้องสแกน QR ใหม่ทุกครั้ง
- มือถือกับคอมไม่ต้องอยู่ Wi-Fi วงเดียวกัน ทั้งสองแค่ต้องออกอินเทอร์เน็ตได้
  จึงใช้ได้แม้ Wi-Fi ของมหาวิทยาลัยจะกันอุปกรณ์ไม่ให้เห็นกัน (client isolation)
- ภาพวิ่งผ่าน Cloudflare จะหน่วงเพิ่มขึ้นประมาณ 0.1–0.2 วินาที (เฟรมขนาด 40KB วัดได้ราว 120–150 ms)
- ใครที่มี URL ก็เปิดหน้าเว็บได้ อย่าแชร์ URL นี้ออกไป และกด Ctrl+C ปิดเมื่อใช้เสร็จ
  (cloudflared จะปิดตามไปเอง)

## เปิดกล้องบนมือถือ: โหมด LAN (Android, ไม่ใช้อินเทอร์เน็ต)

1. ให้คอมกับมือถืออยู่ Wi-Fi วงเดียวกัน
2. รัน `python -m server.main` แล้วดู URL บรรทัด `Phone:` (`https://<IP>:8443/camera`)
3. ถ้า Windows ถามเรื่อง Firewall ให้กด Allow
4. เปิด URL บน Chrome ของ Android แล้วกด Advanced → Proceed
5. กด "เริ่มส่งภาพ" แล้วเปิด `https://<IP>:8443/board` บนคอม

เซิร์ฟเวอร์สร้าง self-signed certificate ใน `certs/` ให้อัตโนมัติ และสร้างใหม่ทุกครั้งที่ IP ของคอมเปลี่ยน
สั่งสร้างเองได้ด้วย `python -m server.gen_cert` (iPhone ใช้โหมดนี้ไม่ได้ ให้ใช้โหมด Tunnel แทน)

## โครงสร้างและสถานะ

- `server/`: FastAPI, WebSocket hub, สถานะเกม, สร้าง certificate, Cloudflare Tunnel (`tunnel.py`) DIP (OpenCV) และ stub ของ ML/AI
- `web/`: หน้า HTML/JavaScript ธรรมดา ไม่มีขั้นตอน build
- `certs/`: สร้างอัตโนมัติและไม่เก็บใน Git
- Chessground เวอร์ชัน `9.2.1` โหลดจากสำเนาในเครื่อง `web/static/vendor/`
  (JS, CSS, theme และ GPL-3.0-or-later license) จึงใช้งานได้แม้ไม่มีอินเทอร์เน็ต

```text
มือถือ /camera -- JPEG binary --> /ws/camera
                                      |
                                FastAPI Hub
                         เฟรมล่าสุด + สถานะเกม
                                      |
คอม /board <------ binary JPEG + JSON ------ /ws/board
```

Hub เก็บภาพล่าสุดเพียงภาพเดียว และแทนที่เฟรมที่ยังรอส่งในแต่ละหน้า board
ด้วยภาพใหม่ เพื่อไม่ให้ความหน่วงสะสม การประมวลผล DIP/ML/AI ยังเป็น stub
และยังไม่ได้วิเคราะห์ภาพจริง

## หน้าเว็บ

| หน้า | ใช้ทำอะไร |
|---|---|
| `/board` | ซ้าย: ภาพกล้องสดและภาพดัดตรง · กลาง: บอร์ดจำลองพร้อมลูกศรแนะนำ · ขวา: แผง AI, ML, ประวัติตาเดิน · ล่าง: ปุ่ม New game / Calibrate / Undo |
| `/camera` | เปิดบนมือถือ ใช้ส่งภาพกล้อง |
| `/calibrate` | คลิก/ลาก 4 มุมกระดาน เลือกฝั่งผู้เล่นขาว ดูตัวอย่างภาพดัดตรง แล้วบันทึก |

ธีม Nordic มินิมอล: สีทั้งหมดเก็บเป็น CSS variables 2 ชุด (Light / Dark) ใน `web/static/css/style.css`
สลับได้ที่ปุ่มมุมขวาบน ระบบจำค่าไว้ใน `localStorage` (`web/static/js/theme.js`)
ถ้ายังไม่เคยเลือก จะใช้ธีมตามการตั้งค่าของระบบปฏิบัติการ

## API

- `POST /api/game/new`: เริ่มเกมใหม่ (ปุ่ม New game)
- `POST /api/game/undo`: ย้อนกลับหนึ่งตา (ปุ่ม Undo) ถ้ายังไม่มีตาเดินจะตอบ 409
- `POST /api/test/random-move`: (โหมดทดสอบ) เดินตาสุ่มที่ถูกกฎหนึ่งตา แล้วสุ่มตาถัดไปเป็น `best_move`
  เพื่อแสดงลูกศร เป็นค่าจำลอง ไม่ได้มาจาก AI
- `POST /api/test/reset`: เหมือน `/api/game/new` คงไว้เพื่อให้โค้ดเดิมยังใช้ได้
- `GET /api/calibration` / `POST /api/calibration`: อ่าน/บันทึกมุมกระดานและฝั่งผู้เล่น
  (`{"corners": [[x, y] × 4], "white_side": "bottom|top|left|right"}` พิกัดเป็นสัดส่วน 0–1)
- `POST /api/calibration/preview`: ดัดภาพล่าสุดตามมุมที่ส่งมา คืน JPEG (ยังไม่บันทึก)
- `POST /api/calibration/auto`: หามุมอัตโนมัติด้วย Canny + Hough
- `GET /api/frame/latest.jpg`: ภาพล่าสุดจากกล้อง

## DIP (`server/dip/`)

| ไฟล์ | หน้าที่ |
|---|---|
| `calibration.py` | เก็บ 4 มุม (สัดส่วน 0–1) และฝั่งผู้เล่นขาว ใน `server/data/calibration.json` |
| `board_detector.py` | homography 3×3 → `warpPerspective` เป็น 800×800 → หมุนให้ขาวอยู่ล่าง → ตัด 64 ช่อง a1–h8 → วาดตาราง |
| `motion.py` | frame difference: `D = mean(|I_t − I_{t−1}|)` ถ้า `D < 4.0` ต่อเนื่อง 1 วินาที (นับเป็นเวลา ไม่ขึ้นกับ fps) ถือว่าภาพนิ่ง |
| `auto_corners.py` | (ทดลอง) Canny → HoughLinesP → เส้นนอกสุด 4 ด้าน → จุดตัดด้วยกฎของคราเมอร์ |
| `pipeline.py` | รวมทุกขั้น ทำงานใน background task ทุกครั้งที่มีเฟรมใหม่ |

สมการและเหตุผลของแต่ละขั้นอธิบายไว้ในคอมเมนต์ภาษาไทยของแต่ละไฟล์

**วิธี calibrate:** วางมือถือให้นิ่ง (ใช้ขาตั้งถ้ามี) เห็นกระดานครบทั้ง 4 มุม → เปิด `/calibrate` บนคอม →
คลิกมุมขอบนอกของช่องหมากรุก (ไม่รวมกรอบไม้) ตามลำดับ ซ้ายบน → ขวาบน → ขวาล่าง → ซ้ายล่าง →
เลือกว่าฝั่งขาวอยู่ด้านไหนของภาพ → ดูตัวอย่างว่าเส้นตารางตรงกับช่องจริง → บันทึก
ถ้าขยับกล้องหรือกระดาน ต้อง calibrate ใหม่

ข้อความ binary ที่ส่งไปหน้า board ขึ้นต้นด้วย 1 ไบต์บอกชนิด: `0x01` ภาพกล้อง, `0x02` ภาพดัดตรง

## ML: จำแนกหมาก (`server/ml/`, `training/`)

เครื่องนี้ติดตั้ง PyTorch ไม่ได้ (Windows App Control บล็อก DLL) จึงเทรนบน Google Colab
แล้วเอาโมเดล ONNX กลับมาใช้ผ่าน `cv2.dnn`

1. **เก็บข้อมูล**: ในหน้า /board ติ๊ก "เก็บข้อมูลเทรน" แล้วเล่นตามปกติ
   ระบบติดป้ายให้อัตโนมัติจาก FEN ของเกม (1 ภาพ = 64 ตัวอย่าง) โดยเก็บตอน New game
   และตอนกดเดินเสร็จแล้วระบบหาตาเดินเจอ (Undo จะลบภาพล่าสุด) ส่วน "บันทึกภาพนี้" ใช้เก็บเอง
   เมื่อกระดานจริงตรงกับบนจอ ควรเก็บ 30 ภาพขึ้นไป หลายสภาพแสง
2. **Export**: `python -m server.ml.export_dataset` ได้ `server/data/ml_dataset.zip`
3. **เทรน**: เปิด `training/train_piece_classifier.ipynb` ใน Colab (GPU) แล้ว Run all
   มี baseline (HSV histogram + SVM) เทียบกับ CNN, confusion matrix และแบ่งชุดข้อมูลตามภาพกระดาน
4. **ใช้งาน**: วาง `piece_classifier.onnx` และ `labels.json` ใน `server/data/models/`
   แล้วกด "โหลดโมเดลใหม่" ระบบจะอ่านกระดานทุกครั้งที่ภาพนิ่ง และแสดงช่องที่ไม่ตรงกับเกม

ภาพแต่ละช่อง (`crops.py`) ตัดเผื่อด้านบน 0.6 ช่อง เพราะกล้องถ่ายเฉียง หัวหมากจึงล้ำขึ้นไปช่องบน
