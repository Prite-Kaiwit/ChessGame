"""Hub สำหรับกระจายภาพล่าสุดและสถานะต่างๆ ไปยังหน้า board

ชนิดของ event (kind):
    "frame"  : ภาพ JPEG จากกล้องมือถือ
    "warped" : ภาพกระดานที่ดัดตรงแล้ว + ตาราง 8x8 (จาก DIP)
    "dip"    : สถานะ DIP (calibrate แล้วหรือยัง, ภาพนิ่งไหม, ค่า frame difference)
    "state"  : สถานะเกม (FEN, ตาแนะนำ, ประวัติ)
    "ml"     : สถานะ ML (โมเดล, ข้อมูลที่เก็บ, ผลอ่านกระดานล่าสุด)
    "detect" : ผลการหาตาเดินจากภาพ (แจ้งครั้งเดียว ไม่ส่งซ้ำให้หน้าที่เพิ่งเปิด)

หลักการ "เก็บแค่ล่าสุด": ถ้าหน้า board ยังส่งของเก่าไม่ทัน แล้วมี event ชนิดเดียวกันมาใหม่
จะแทนที่ของเก่าในคิวทันที ภาพจึงไม่ค้างสะสมจนดีเลย์
"""

import asyncio
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class HubEvent:
    """ข้อมูลหนึ่งรายการที่รอส่งไปยัง WebSocket หน้า board"""

    kind: str
    data: bytes | dict[str, Any]


class Hub:
    """เก็บข้อมูลล่าสุดของแต่ละชนิด และกระจาย event ให้ผู้ชมทุกคน"""

    def __init__(self) -> None:
        self.latest_frame: bytes | None = None
        self.latest_warped: bytes | None = None
        self.dip_status: dict[str, Any] = {}
        self.state: dict[str, Any] = {}
        self.ml_status: dict[str, Any] = {}
        # สัญญาณ "มีเฟรมใหม่" ให้ DIP loop ตื่นมาประมวลผล
        self.frame_event = asyncio.Event()
        self._board_clients: set[asyncio.Queue[HubEvent]] = set()

    def subscribe(self) -> asyncio.Queue[HubEvent]:
        """ลงทะเบียนผู้ชมใหม่และคืน queue รับ event"""
        queue: asyncio.Queue[HubEvent] = asyncio.Queue()
        self._board_clients.add(queue)
        return queue

    def unsubscribe(self, queue: asyncio.Queue[HubEvent]) -> None:
        """ยกเลิกการลงทะเบียนผู้ชม"""
        self._board_clients.discard(queue)

    def snapshot_events(self) -> list[HubEvent]:
        """ข้อมูลล่าสุดทุกชนิด สำหรับส่งให้หน้า board ที่เพิ่งเชื่อมต่อ"""
        events = []
        if self.state:
            events.append(HubEvent("state", self.state))
        if self.dip_status:
            events.append(HubEvent("dip", self.dip_status))
        if self.ml_status:
            events.append(HubEvent("ml", self.ml_status))
        if self.latest_frame is not None:
            events.append(HubEvent("frame", self.latest_frame))
        if self.latest_warped is not None:
            events.append(HubEvent("warped", self.latest_warped))
        return events

    def set_state(self, state: dict[str, Any]) -> None:
        """บันทึกและส่งต่อสถานะเกมล่าสุด"""
        self.state = state
        self._broadcast(HubEvent("state", state))

    def publish_frame(self, frame: bytes) -> None:
        """เก็บและส่งต่อเฉพาะเฟรมกล้องล่าสุด แล้วปลุก DIP loop"""
        self.latest_frame = frame
        self._broadcast(HubEvent("frame", frame))
        self.frame_event.set()

    def publish_warped(self, jpeg: bytes) -> None:
        """ส่งต่อภาพกระดานที่ดัดตรงแล้ว"""
        self.latest_warped = jpeg
        self._broadcast(HubEvent("warped", jpeg))

    def publish_ml(self, status: dict[str, Any]) -> None:
        """ส่งต่อสถานะ ML"""
        self.ml_status = status
        self._broadcast(HubEvent("ml", status))

    def publish_detect(self, result: dict[str, Any]) -> None:
        """แจ้งผลการหาตาเดินจากภาพ"""
        self._broadcast(HubEvent("detect", {"type": "detect", **result}))

    def publish_dip(self, status: dict[str, Any]) -> None:
        """ส่งต่อสถานะ DIP"""
        self.dip_status = status
        self._broadcast(HubEvent("dip", status))

    def _broadcast(self, event: HubEvent) -> None:
        for queue in self._board_clients:
            self._replace_queued_event(queue, event)

    @staticmethod
    def _replace_queued_event(queue: asyncio.Queue[HubEvent], event: HubEvent) -> None:
        """แทน event ชนิดเดียวกันที่ค้างอยู่ โดยเก็บ event ชนิดอื่นไว้ตามลำดับเดิม"""
        pending: list[HubEvent] = []
        while True:
            try:
                queued = queue.get_nowait()
            except asyncio.QueueEmpty:
                break
            if queued.kind != event.kind:
                pending.append(queued)

        for queued in pending:
            queue.put_nowait(queued)
        queue.put_nowait(event)


hub = Hub()
