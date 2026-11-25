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

`tests/test_integration.py` จะเปิดเซิร์ฟเวอร์ HTTPS จริงบนพอร์ต 8899 เอง แล้วทดสอบหน้าเว็บ,
API ทดสอบ, WebSocket (รวมการทิ้งเฟรมเก่า) และกรณีหน้า board หลุดกะทันหัน

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

- `server/`: FastAPI, WebSocket hub, สถานะเกม, สร้าง certificate, Cloudflare Tunnel (`tunnel.py`) และ stub ของ DIP/ML/AI
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
| `/calibrate` | เลือก 4 มุมกระดาน (ตอนนี้ยังเป็นหน้าชั่วคราว ทำจริงในขั้น DIP) |

ธีม Nordic มินิมอล: สีทั้งหมดเก็บเป็น CSS variables 2 ชุด (Light / Dark) ใน `web/static/css/style.css`
สลับได้ที่ปุ่มมุมขวาบน ระบบจำค่าไว้ใน `localStorage` (`web/static/js/theme.js`)
ถ้ายังไม่เคยเลือก จะใช้ธีมตามการตั้งค่าของระบบปฏิบัติการ

## API

- `POST /api/game/new`: เริ่มเกมใหม่ (ปุ่ม New game)
- `POST /api/game/undo`: ย้อนกลับหนึ่งตา (ปุ่ม Undo) ถ้ายังไม่มีตาเดินจะตอบ 409
- `POST /api/test/random-move`: (โหมดทดสอบ) เดินตาสุ่มที่ถูกกฎหนึ่งตา แล้วสุ่มตาถัดไปเป็น `best_move`
  เพื่อแสดงลูกศร เป็นค่าจำลอง ไม่ได้มาจาก AI
- `POST /api/test/reset`: เหมือน `/api/game/new` คงไว้เพื่อให้โค้ดเดิมยังใช้ได้
