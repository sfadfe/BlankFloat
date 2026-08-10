import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from blankfloat import capture, pipeline
from blankfloat.config import Config


class Completed:
    def __init__(self, returncode=0, stdout="", stderr=""):
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


class PortalRegionBackendTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.target = Path(self._tmp.name) / "shot.png"

    def tearDown(self):
        self._tmp.cleanup()

    def test_success_returns_true(self):
        def fake_run(args, **_kwargs):
            self.assertIn("blankfloat.portal_region", args)
            self.target.write_bytes(b"png")
            return Completed(0)

        with mock.patch.object(subprocess, "run", fake_run):
            self.assertTrue(capture._try_portal_region(self.target))

    def test_user_cancel_raises_cancelled(self):
        with mock.patch.object(subprocess, "run", return_value=Completed(2)):
            with self.assertRaises(capture.CaptureCancelled):
                capture._try_portal_region(self.target)


class PortalBackendTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.target = Path(self._tmp.name) / "shot.png"

    def tearDown(self):
        self._tmp.cleanup()

    def test_success_returns_true(self):
        def fake_run(*_args, **_kwargs):
            self.target.write_bytes(b"png")
            return Completed(0)

        with mock.patch.object(subprocess, "run", fake_run):
            self.assertTrue(capture._try_portal(self.target))

    def test_user_cancel_raises_cancelled(self):
        with mock.patch.object(subprocess, "run", return_value=Completed(2)):
            with self.assertRaises(capture.CaptureCancelled):
                capture._try_portal(self.target)

    def test_failure_raises_capture_error_with_stderr(self):
        with mock.patch.object(subprocess, "run", return_value=Completed(1, stderr="no portal\n")):
            with self.assertRaises(capture.CaptureError) as ctx:
                capture._try_portal(self.target)
        self.assertIn("no portal", str(ctx.exception))


class FlameshotBackendTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.target = Path(self._tmp.name) / "shot.png"

    def tearDown(self):
        self._tmp.cleanup()

    def test_success_returns_true(self):
        def fake_run(args, **_kwargs):
            self.assertEqual(args[0], "flameshot")
            self.target.write_bytes(b"png")
            return Completed(0)

        with mock.patch.object(capture.shutil, "which", return_value="/usr/bin/flameshot"):
            with mock.patch.object(subprocess, "run", fake_run):
                self.assertTrue(capture._try_flameshot(self.target))

    def test_abort_is_cancelled(self):
        with mock.patch.object(capture.shutil, "which", return_value="/usr/bin/flameshot"):
            with mock.patch.object(subprocess, "run", return_value=Completed(1)):
                with self.assertRaises(capture.CaptureCancelled):
                    capture._try_flameshot(self.target)


class BackendChainTest(unittest.TestCase):
    def test_cancel_stops_the_chain(self):
        def cancel(_target):
            raise capture.CaptureCancelled("취소")

        never = mock.Mock(side_effect=AssertionError("should not run after cancel"))
        with mock.patch.object(
            capture, "active_backends", return_value=(("portal", cancel), ("next", never))
        ):
            with self.assertRaises(capture.CaptureCancelled):
                capture.capture_region()
        never.assert_not_called()

    def test_falls_through_to_the_next_backend(self):
        def broken(_target):
            raise capture.CaptureError("portal unavailable")

        def working(target):
            target.write_bytes(b"png")
            return True

        with mock.patch.object(
            capture, "active_backends", return_value=(("portal", broken), ("grim", working))
        ):
            path = capture.capture_region()
        self.assertTrue(path.exists())
        path.unlink()

    def test_all_backends_missing_reports_every_error(self):
        def missing(_target):
            return False

        def broken(_target):
            raise capture.CaptureError("boom")

        with mock.patch.object(
            capture, "active_backends", return_value=(("a", missing), ("b", broken))
        ):
            with self.assertRaises(capture.CaptureError) as ctx:
                capture.capture_region()
        self.assertIn("boom", str(ctx.exception))

    def test_gnome_wayland_uses_portal_region_only(self):
        with mock.patch.dict(
            os.environ,
            {
                "XDG_CURRENT_DESKTOP": "ubuntu:GNOME",
                "XDG_SESSION_TYPE": "wayland",
                "WAYLAND_DISPLAY": "wayland-0",
            },
            clear=False,
        ):
            os.environ.pop("BLANKFLOAT_CAPTURE", None)
            names = [name for name, _ in capture.active_backends()]
        self.assertEqual(names, ["portal-region"])

    def test_capture_env_overrides_backends(self):
        with mock.patch.dict(os.environ, {"BLANKFLOAT_CAPTURE": "flameshot,xdg-portal"}):
            names = [name for name, _ in capture.active_backends()]
        self.assertEqual(names, ["flameshot", "xdg-portal"])


class PipelineCaptureTest(unittest.TestCase):
    def test_cancelled_capture_becomes_result_error(self):
        with mock.patch.object(
            capture, "capture_region", side_effect=capture.CaptureCancelled("캡처를 취소했습니다.")
        ):
            result = pipeline.capture_and_analyze("auto", Config())
        self.assertFalse(result.ok)
        self.assertTrue(result.cancelled)
        self.assertEqual(result.error, "캡처를 취소했습니다.")
        self.assertIsNone(result.image_path)


if __name__ == "__main__":
    unittest.main()
