"""WebSocket endpoints สำหรับกล้องและหน้าแสดงผล

รูปแบบข้อความที่ส่งไปหน้า board (/ws/board):
    binary : ไบต์แรกบอกชนิดภาพ แล้วตามด้วย JPEG
                0x01 = ภาพจากกล้อง,  0x02 = ภาพกระดานที่ดัดตรงแล้ว
    text   : JSON ที่มีฟิลด์ "type" = "state" (สถานะเกม) หรือ "dip" (สถานะ DIP)
"""

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from server.hub import HubEvent, hub

router = APIRouter()

# exception ที่เกิดได้เมื่อ client ปิดการเชื่อมต่อกะทันหัน
# - WebSocketDisconnect: client ปิดแบบปกติ
# - RuntimeError: Starlette แจ้งว่าส่งข้อมูลหลัง socket ปิดไปแล้ว
# - OSError: ระดับเครือข่าย เช่น ClientDisconnected ของ uvicorn หรือสายหลุด
CLIENT_GONE = (WebSocketDisconnect, RuntimeError, OSError)

# ไบต์นำหน้าของข้อความ binary แยกตามชนิดภาพ
IMAGE_PREFIX = {"frame": b"\x01", "warped": b"\x02"}


@router.websocket("/ws/camera")
async def camera_socket(websocket: WebSocket) -> None:
    """รับ JPEG binary จากมือถือและเผยแพร่เฟรมล่าสุด"""
    await websocket.accept()
    try:
        while True:
            frame = await websocket.receive_bytes()
            if frame:
                hub.publish_frame(frame)
    except CLIENT_GONE:
        # มือถือปิดหน้า/หยุดกล้อง ไม่ถือเป็นข้อผิดพลาด
        pass


async def _send_event(websocket: WebSocket, event: HubEvent) -> None:
    if event.kind in IMAGE_PREFIX:
        await websocket.send_bytes(IMAGE_PREFIX[event.kind] + event.data)
    else:
        await websocket.send_json(event.data)


@router.websocket("/ws/board")
async def board_socket(websocket: WebSocket) -> None:
    """ส่งภาพล่าสุดและสถานะต่างๆ ไปยังหน้า board"""
    await websocket.accept()
    queue = hub.subscribe()
    try:
        # หน้าที่เพิ่งเปิดได้ข้อมูลล่าสุดทุกชนิดทันที ไม่ต้องรอเฟรมถัดไป
        for event in hub.snapshot_events():
            await _send_event(websocket, event)
        while True:
            await _send_event(websocket, await queue.get())
    except CLIENT_GONE:
        # หน้า board ถูกปิดหรือขาดการเชื่อมต่อ ไม่ต้องพิมพ์ traceback ลง log
        pass
    finally:
        hub.unsubscribe(queue)
