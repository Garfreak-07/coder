from __future__ import annotations

import threading
import time
import unittest

from coder_workbench.runtime_kernel import RunControl


class RunPauseResumeTests(unittest.TestCase):
    def test_pause_and_resume_at_checkpoint(self) -> None:
        control = RunControl()
        reached_after_pause = threading.Event()
        completed = threading.Event()

        def worker() -> None:
            control.checkpoint("before_pause")
            control.checkpoint("paused_location")
            reached_after_pause.set()
            completed.set()

        control.request_pause()
        thread = threading.Thread(target=worker)
        thread.start()
        time.sleep(0.05)

        self.assertTrue(control.paused)
        self.assertFalse(reached_after_pause.is_set())

        control.request_resume()
        thread.join(timeout=1)

        self.assertTrue(completed.is_set())
        self.assertFalse(control.paused)
        self.assertEqual(control.location, "paused_location")


if __name__ == "__main__":
    unittest.main()
