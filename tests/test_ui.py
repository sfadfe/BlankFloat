"""Widget-level smoke tests. Skipped when no display is available."""

import os
import tempfile
import unittest

from blankfloat.config import Config
from blankfloat.pipeline import Result
from blankfloat.routing import Analysis, Answer

try:
    import tkinter as tk

    _root = tk.Tk()
    _root.destroy()
    HAS_DISPLAY = True
except Exception:  # noqa: BLE001 - any Tk/display failure means skip
    HAS_DISPLAY = False


@unittest.skipUnless(HAS_DISPLAY, "no usable display")
class FloatingAppTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Keep the IPC socket out of the real runtime dir so a running instance
        # is not disturbed.
        cls._tmp = tempfile.TemporaryDirectory()
        cls._old_runtime = os.environ.get("XDG_RUNTIME_DIR")
        os.environ["XDG_RUNTIME_DIR"] = cls._tmp.name

    @classmethod
    def tearDownClass(cls):
        if cls._old_runtime is None:
            os.environ.pop("XDG_RUNTIME_DIR", None)
        else:
            os.environ["XDG_RUNTIME_DIR"] = cls._old_runtime
        cls._tmp.cleanup()

    def setUp(self):
        from blankfloat.ui.app import FloatingApp

        self.app = FloatingApp(Config())
        self.app.root.withdraw()

    def tearDown(self):
        if self.app.server:
            self.app.server.stop()
        self.app.root.destroy()

    def rendered(self) -> str:
        return self.app.text.get("1.0", "end")

    def test_idle_is_blank(self):
        self.assertEqual(self.rendered().strip(), "")

    def test_starts_withdrawn(self):
        self.assertFalse(self.app.root.winfo_viewable())

    def test_cancel_keeps_window_hidden(self):
        self.app.show()
        self.app._finish(Result(error="cancelled", cancelled=True))
        self.app.root.update_idletasks()
        self.assertFalse(self.app.root.winfo_viewable())

    def test_result_shows_window(self):
        self.app._finish(
            Result(analysis=Analysis(route="simple", answers=[Answer("1", "42")]), elapsed=0.5)
        )
        self.app.root.update_idletasks()
        self.assertTrue(self.app.root.winfo_viewable())

    def test_mode_can_be_set(self):
        self.app.set_mode("complex")
        self.assertEqual(self.app.mode, "complex")

    def test_simple_result_renders_answers_only(self):
        analysis = Analysis(
            route="simple",
            confidence=0.9,
            reason="fill_in_blank",
            answers=[Answer("1", "광합성"), Answer("2", "엽록체", uncertain=True)],
        )
        self.app._finish(Result(analysis=analysis, elapsed=3.2))

        text = self.rendered()
        self.assertIn("1) 광합성", text)
        self.assertIn("2) 엽록체", text)
        self.assertNotIn("확실하지 않음", text)
        self.assertNotIn("답\n", text)
        self.assertNotIn("간단", text)
        self.assertEqual(self.app.action_buttons, [])
        self.assertEqual(self.app.elapsed_label.cget("text"), "3s")

    def test_complex_result_renders_prompt_only(self):
        analysis = Analysis(
            route="complex",
            confidence=0.8,
            reason="essay_rubric",
            prompt="Final output language: Korean\nWrite about ...",
            outline=["도입", "본론", "결론"],
        )
        self.app._finish(Result(analysis=analysis, elapsed=2.0))

        text = self.rendered()
        self.assertIn("Final output language: Korean", text)
        self.assertNotIn("도입", text)
        self.assertNotIn("개요", text)
        self.assertNotIn("프롬프트", text)
        self.assertEqual(self.app.action_buttons, [])

    def test_error_result_shows_message_only(self):
        self.app._finish(Result(error="API 키가 없습니다."))
        self.assertEqual(self.rendered().strip(), "API 키가 없습니다.")
        self.assertEqual(self.app.action_buttons, [])

    def test_result_switch_clears_previous_content(self):
        self.app._finish(
            Result(analysis=Analysis(route="complex", prompt="x", outline=["a"]), elapsed=1.0)
        )
        self.app._finish(
            Result(analysis=Analysis(route="simple", answers=[Answer("1", "42")]), elapsed=1.0)
        )
        self.assertIn("1) 42", self.rendered())
        self.assertNotIn("개요", self.rendered())
        self.assertNotEqual(self.rendered().strip(), "x")

    def test_unreadable_result_is_minimal(self):
        self.app._finish(
            Result(analysis=Analysis(route="unreadable", reason="blurry_crop"), elapsed=0.5)
        )
        self.assertIn("다시 캡처", self.rendered())
        self.assertNotIn("blurry_crop", self.rendered())
        self.assertEqual(self.app.elapsed_label.cget("text"), "0s")

    def test_copy_to_clipboard(self):
        self.app._finish(
            Result(analysis=Analysis(route="simple", answers=[Answer("1", "광합성")]), elapsed=1.0)
        )
        self.app.copy_to_clipboard()
        self.app.root.update_idletasks()
        self.assertIn("1) 광합성", self.app.root.clipboard_get())

    def test_copy_button_exists(self):
        self.assertTrue(hasattr(self.app, "copy_btn"))
        self.assertEqual(str(self.app.copy_btn.cget("image")), str(self.app._copy_icon))

    def test_window_has_white_border(self):
        self.assertEqual(self.app.root.cget("bg"), "#ffffff")

    def test_fit_shrinks_for_short_answer(self):
        self.app._finish(
            Result(analysis=Analysis(route="simple", answers=[Answer("1", "42")]), elapsed=1.0)
        )
        self.app.root.update_idletasks()
        self.assertLess(self.app.root.winfo_height(), 400)
        self.assertLess(self.app.root.winfo_width(), 500)

    def test_ipc_commands(self):
        self.assertEqual(self.app._handle_ipc("ping"), "pong")
        self.assertEqual(self.app._handle_ipc("capture"), "ok")
        self.assertEqual(self.app._handle_ipc("multi"), "ok")
        self.assertEqual(self.app._handle_ipc("nope"), "unknown")

    def test_multi_append_keeps_card_hidden(self):
        from pathlib import Path

        self.app.multi_active = True
        self.app._finish(
            Result(image_path=Path("/tmp/shot1.png"), multi_appended=True)
        )
        self.app.root.update_idletasks()
        self.assertEqual(self.app.multi_paths, [Path("/tmp/shot1.png")])
        self.assertTrue(self.app.multi_active)
        self.assertFalse(self.app.root.winfo_viewable())

    def test_multi_cancel_keeps_session(self):
        self.app.multi_active = True
        self.app.multi_paths = []
        self.app._finish(Result(error="cancelled", cancelled=True))
        self.assertTrue(self.app.multi_active)
        self.assertFalse(self.app.root.winfo_viewable())

    def test_multi_finish_empty_stays_quiet(self):
        self.app.multi_active = True
        self.app.multi_paths = []
        self.app.toggle_multi()
        self.assertFalse(self.app.multi_active)
        self.assertFalse(self.app.busy)
        self.assertFalse(self.app.root.winfo_viewable())

    def test_multi_start_arms_without_capture(self):
        from unittest import mock

        with mock.patch.object(self.app, "start_capture") as capture:
            self.app.toggle_multi()
        self.assertTrue(self.app.multi_active)
        self.assertEqual(self.app.multi_paths, [])
        self.assertFalse(self.app.busy)
        capture.assert_not_called()

    def test_multi_finish_prompts_note_then_analyzes(self):
        from pathlib import Path
        from unittest import mock

        from blankfloat.ui.app import _HOTKEY_SETTLE_MS

        paths = [Path("/tmp/a.png"), Path("/tmp/b.png")]
        self.app.multi_active = True
        self.app.multi_paths = list(paths)
        pending = []
        orig_after = self.app.root.after

        def after_spy(ms, func=None, *args):
            if func is None:
                return orig_after(ms)
            if ms == _HOTKEY_SETTLE_MS:
                pending.append(func)
                return "settle"
            return orig_after(ms, func, *args)

        with mock.patch.object(self.app.root, "after", side_effect=after_spy):
            with mock.patch.object(self.app, "_prompt_multi_note") as prompt:
                self.app.toggle_multi()
                self.assertEqual(len(pending), 1)
                pending[0]()
        self.assertFalse(self.app.multi_active)
        self.assertEqual(self.app.multi_paths, [])
        self.assertTrue(self.app.busy)
        prompt.assert_called_once_with(paths)

    def test_multi_note_enter_spawns_analyze(self):
        from pathlib import Path
        from unittest import mock

        paths = [Path("/tmp/a.png")]
        self.app.busy = True
        with mock.patch.object(self.app, "_spawn_analyze_paths") as spawn:
            self.app._prompt_multi_note(paths)
            self.app.root.update()
            dlg = next(
                w for w in self.app.root.winfo_children() if isinstance(w, tk.Toplevel)
            )
            entry = None
            stack = [dlg]
            while stack:
                w = stack.pop()
                if isinstance(w, tk.Entry):
                    entry = w
                    break
                stack.extend(w.winfo_children())
            self.assertIsNotNone(entry)
            entry.insert(0, "힌트 있음")
            dlg._blankfloat_submit()
            self.app.root.update_idletasks()
        spawn.assert_called_once_with(paths, self.app.mode, extra_text="힌트 있음")

    def test_multi_note_esc_cancels(self):
        from pathlib import Path
        from unittest import mock

        paths = [Path("/tmp/a.png")]
        self.app.busy = True
        with mock.patch.object(self.app, "_spawn_analyze_paths") as spawn:
            self.app._prompt_multi_note(paths)
            self.app.root.update()
            dlg = next(
                w for w in self.app.root.winfo_children() if isinstance(w, tk.Toplevel)
            )
            dlg._blankfloat_cancel()
            self.app.root.update_idletasks()
        spawn.assert_not_called()
        self.assertFalse(self.app.busy)

    def test_complete_multi_note_none_clears_busy(self):
        from pathlib import Path

        self.app.busy = True
        self.app._complete_multi_note([Path("/tmp/a.png")], None)
        self.assertFalse(self.app.busy)


@unittest.skipUnless(HAS_DISPLAY, "no usable display")
class CombinedAppTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._tmp = tempfile.TemporaryDirectory()
        cls._old_runtime = os.environ.get("XDG_RUNTIME_DIR")
        os.environ["XDG_RUNTIME_DIR"] = cls._tmp.name

    @classmethod
    def tearDownClass(cls):
        if cls._old_runtime is None:
            os.environ.pop("XDG_RUNTIME_DIR", None)
        else:
            os.environ["XDG_RUNTIME_DIR"] = cls._old_runtime
        cls._tmp.cleanup()

    def setUp(self):
        from blankfloat.typer import TyperApp
        from blankfloat.ui.app import FloatingApp

        self.typer = TyperApp()
        self.app = FloatingApp(Config(), master=self.typer.root)
        self.app.root.withdraw()

    def tearDown(self):
        if self.app.server:
            self.app.server.stop()
        try:
            self.typer.root.destroy()
        except tk.TclError:
            pass

    def test_typer_visible_card_hidden(self):
        self.typer.root.update_idletasks()
        self.assertTrue(self.typer.root.winfo_viewable())
        self.assertFalse(self.app.root.winfo_viewable())
        self.assertIsInstance(self.app.root, tk.Toplevel)

    def test_result_shows_card_without_closing_typer(self):
        self.app._finish(
            Result(analysis=Analysis(route="simple", answers=[Answer("1", "42")]), elapsed=1.0)
        )
        self.typer.root.update_idletasks()
        self.assertTrue(self.app.root.winfo_viewable())
        self.assertTrue(self.typer.root.winfo_viewable())

    def test_typer_withdraws_on_confirm(self):
        from unittest import mock

        self.typer.text.insert("1.0", "hello")
        with mock.patch("threading.Thread") as thread_cls:
            thread_cls.return_value = mock.Mock()
            self.typer._on_confirm()
            self.typer.root.update_idletasks()
            self.assertFalse(self.typer.root.winfo_viewable())
            thread_cls.assert_called_once()
        self.typer._done(None)
        self.typer.root.update_idletasks()
        self.assertTrue(self.typer.root.winfo_viewable())


if __name__ == "__main__":
    unittest.main()
