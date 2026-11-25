import unittest

from server.hub import Hub


class HubTests(unittest.TestCase):
    def test_pending_frame_is_replaced_with_latest_frame(self) -> None:
        hub = Hub()
        queue = hub.subscribe()

        hub.publish_frame(b"old")
        hub.publish_frame(b"latest")

        event = queue.get_nowait()
        self.assertEqual(event.kind, "frame")
        self.assertEqual(event.data, b"latest")
        self.assertTrue(queue.empty())

    def test_state_and_latest_frame_are_both_preserved(self) -> None:
        hub = Hub()
        queue = hub.subscribe()

        hub.set_state({"fen": "position"})
        hub.publish_frame(b"latest")

        self.assertEqual(queue.get_nowait().kind, "state")
        self.assertEqual(queue.get_nowait().data, b"latest")


if __name__ == "__main__":
    unittest.main()
