"""WebSocket endpoints สำหรับกล้องและหน้าแสดงผล"""

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from server.hub import HubEvent, hub

router = APIRouter()

# exception ที่เกิดได้เมื่อ client ปิดการเชื่อมต่อกะทันหัน
# - WebSocketDisconnect: client ปิดแบบปกติ
# - RuntimeError: Starlette แจ้งว่าส่งข้อมูลหลัง socket ปิดไปแล้ว
# - OSError: ระดับเครือข่าย เช่น ClientDisconnected ของ uvicorn หรือสายหลุด
CLIENT_GONE = (WebSocketDisconnect, RuntimeError, OSError)


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


@router.websocket("/ws/board")
async def board_socket(websocket: WebSocket) -> None:
    """ส่งภาพล่าสุดและสถานะเกมไปยังหน้า board"""
    await websocket.accept()
    queue = hub.subscribe()
    try:
        if hub.state:
            await websocket.send_json(hub.state)
        if hub.latest_frame is not None:
            await websocket.send_bytes(hub.latest_frame)

        while True:
            event: HubEvent = await queue.get()
            if event.kind == "frame":
                await websocket.send_bytes(event.data)
            else:
                await websocket.send_json(event.data)
    except CLIENT_GONE:
        # หน้า board ถูกปิดหรือขาดการเชื่อมต่อ ไม่ต้องพิมพ์ traceback ลง log
        pass
    finally:
        hub.unsubscribe(queue)
