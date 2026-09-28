"""Unit tests for node state machine and LIVE/PAUSED toggles."""

import unittest
from productify_node.state import NodeState


class TestNodeState(unittest.TestCase):

    def setUp(self):
        self.state = NodeState()

    def test_live_pause_toggle(self):
        self.state.set_live()
        self.assertTrue(self.state.is_live)
        self.assertFalse(self.state.is_paused)
        self.assertEqual(self.state.status, "LIVE")

        self.state.set_paused()
        self.assertFalse(self.state.is_live)
        self.assertTrue(self.state.is_paused)
        self.assertEqual(self.state.status, "PAUSED")

        # Toggle
        res = self.state.toggle_live_pause()
        self.assertEqual(res, "LIVE")

    def test_listeners(self):
        events = []
        callback = lambda s: events.append(s.status)
        self.state.add_listener(callback)

        self.state.set_live()
        self.assertIn("LIVE", events)

        self.state.set_paused()
        self.assertIn("PAUSED", events)


if __name__ == "__main__":
    unittest.main()
