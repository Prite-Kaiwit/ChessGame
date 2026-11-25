"""Hub สำหรับกระจายภาพล่าสุดและสถานะเกมไปยังหน้า board"""

import asyncio
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class HubEvent:
    """ข้อมูลหนึ่งรายการที่รอส่งไปยัง WebSocket หน้า board"""

    kind: str
    data: bytes | dict[str, Any]


class Hub:
    """เก็บเฟรมล่าสุดและกระจาย event ให้ผู้ชมทุกคน"""

    def __init__(self) -> None:
        self.latest_frame: bytes | None = None
        self.state: dict[str, Any] = {}
        self._board_clients: set[asyncio.Queue[HubEvent]] = set()

    def subscribe(self) -> asyncio.Queue[HubEvent]:
        """ลงทะเบียนผู้ชมใหม่และคืน queue รับ event"""
        queue: asyncio.Queue[HubEvent] = asyncio.Queue()
        self._board_clients.add(queue)
        return queue

    def unsubscribe(self, queue: asyncio.Queue[HubEvent]) -> None:
        """ยกเลิกการลงทะเบียนผู้ชม"""
        self._board_clients.discard(queue)

    def set_state(self, state: dict[str, Any]) -> None:
        """บันทึกและส่งต่อสถานะเกมล่าสุด"""
        self.state = state
        for queue in self._board_clients:
            self._replace_queued_event(queue, "state", HubEvent("state", state))

    def publish_frame(self, frame: bytes) -> None:
        """เก็บและส่งต่อเฉพาะเฟรมล่าสุด โดยทิ้งเฟรมเก่าที่ยังรอส่ง"""
        self.latest_frame = frame
        for queue in self._board_clients:
            self._replace_queued_event(queue, "frame", HubEvent("frame", frame))

    @staticmethod
    def _replace_queued_event(
        queue: asyncio.Queue[HubEvent], kind: str, event: HubEvent
    ) -> None:
        """แทน event ชนิดเดียวกันที่ค้างอยู่ โดยเก็บ event ชนิดอื่นไว้"""
        pending: list[HubEvent] = []
        while True:
            try:
                queued = queue.get_nowait()
            except asyncio.QueueEmpty:
                break
            if queued.kind != kind:
                pending.append(queued)

        for queued in pending:
            queue.put_nowait(queued)
        queue.put_nowait(event)


hub = Hub()
