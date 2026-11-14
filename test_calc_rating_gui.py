"""GUI protocol regression tests without opening extra windows."""
import queue
import threading
from types import SimpleNamespace
import unittest
from unittest.mock import Mock

import calc_rating_gui as gui


class GuiProtocolTests(unittest.TestCase):
    def make_controller(self):
        return SimpleNamespace(_closed=False, _run_id=3, _worker=object(), _poll_id=None,
            _result_queue=queue.Queue(), _cache={}, _render_report=Mock(), _busy=Mock(),
            status_var=Mock(), after=Mock(return_value="after-id"))

    def test_dead_thread_does_not_mean_result_consumed(self):
        controller = self.make_controller()
        gui.MatchedRatingApp._poll_worker(controller, 3)
        self.assertIsNotNone(controller._worker)
        controller.after.assert_called_once()
        controller._busy.assert_not_called()

    def test_only_current_terminal_event_completes(self):
        controller = self.make_controller()
        controller._result_queue.put(("result", 2, "old-key", "old-report"))
        controller._result_queue.put(("result", 3, "new-key", "new-report"))
        gui.MatchedRatingApp._poll_worker(controller, 3)
        controller._render_report.assert_called_once_with("new-report")
        self.assertIsNone(controller._worker)
        self.assertNotIn("old-key", controller._cache)
        controller._busy.assert_called_once_with(False)

    def test_old_poll_does_not_drain_new_run(self):
        controller = self.make_controller()
        controller._result_queue.put(("result", 3, "key", "report"))
        gui.MatchedRatingApp._poll_worker(controller, 2)
        self.assertEqual(controller._result_queue.qsize(), 1)
        controller._render_report.assert_not_called()

    def test_calculate_blocked_until_terminal_event(self):
        controller = self.make_controller()
        controller._worker = Mock()
        controller._worker.is_alive.return_value = False
        # No _read_inputs method is needed: a pending terminal event blocks starts.
        gui.MatchedRatingApp.calculate(controller)
        self.assertIsNotNone(controller._worker)

    def test_cancel_is_cooperative(self):
        controller = self.make_controller()
        controller._cancel_event = threading.Event()
        controller.cancel_button = Mock()
        gui.MatchedRatingApp.cancel(controller)
        self.assertTrue(controller._cancel_event.is_set())

    def test_nan_input_rejected(self):
        controller = SimpleNamespace(year_var=Mock(), qs6_var=Mock(), qs7_var=Mock())
        controller.year_var.get.return_value = "2025"
        controller.qs6_var.get.return_value = "nan"
        controller.qs7_var.get.return_value = "7.5"
        with self.assertRaises(ValueError):
            gui.MatchedRatingApp._read_inputs(controller)

    def test_percentage_input_under_one_is_percentage_in_gui(self):
        controller = SimpleNamespace(year_var=Mock(), qs6_var=Mock(), qs7_var=Mock(),
            bootstrap_var=Mock(), seed_var=Mock(), fuzzy_var=Mock(), years=[2025])
        for name, value in (("year_var", "2025"), ("qs6_var", "1"), ("qs7_var", "0.5"),
                            ("bootstrap_var", "0"), ("seed_var", "2026"), ("fuzzy_var", False)):
            getattr(controller, name).get.return_value = value
        _, percentages, _, _, _ = gui.MatchedRatingApp._read_inputs(controller)
        self.assertEqual(percentages, {6: .01, 7: .005})


if __name__ == "__main__":
    unittest.main()
