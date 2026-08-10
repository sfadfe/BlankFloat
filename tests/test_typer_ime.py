#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from __future__ import annotations

import unittest
from unittest import mock

from blankfloat.typer import ime
from blankfloat.typer.uinput_typer import hangul_to_qwerty, type_payload


class ScriptRunsTest(unittest.TestCase):
    def test_latin_only(self):
        self.assertEqual(ime.script_runs("Hello"), [("latin", "Hello")])

    def test_hangul_only(self):
        self.assertEqual(ime.script_runs("안녕"), [("hangul", "안녕")])

    def test_mixed_attaches_space_to_previous(self):
        self.assertEqual(
            ime.script_runs("안녕 hello"),
            [("hangul", "안녕 "), ("latin", "hello")],
        )
        self.assertEqual(
            ime.script_runs("hello 안녕"),
            [("latin", "hello "), ("hangul", "안녕")],
        )

    def test_leading_neutrals_join_first_language(self):
        self.assertEqual(
            ime.script_runs("  안녕"),
            [("hangul", "  안녕")],
        )

    def test_all_neutral_defaults_latin(self):
        self.assertEqual(ime.script_runs("123\n"), [("latin", "123\n")])

    def test_empty(self):
        self.assertEqual(ime.script_runs(""), [])


class ImeControllerTest(unittest.TestCase):
    def test_set_mode_fcitx5_switches_and_dedupes(self):
        calls: list[list[str]] = []

        def fake_run(cmd, **_kwargs):
            calls.append(cmd)
            return mock.Mock(returncode=0, stdout="hangul\n", stderr="")

        with mock.patch.object(ime, "_run", side_effect=fake_run):
            with mock.patch.object(ime.time, "sleep") as sleep:
                ctl = ime.ImeController(settle_secs=0.05)
                ctl._backend = "fcitx5"
                ctl._hangul = "hangul"
                ctl._latin = "keyboard-us"
                ctl.set_mode("hangul")
                ctl.set_mode("hangul")  # dedupe
                ctl.set_mode("latin")

        self.assertEqual(
            [c for c in calls if c[:2] == ["fcitx5-remote", "-s"]],
            [
                ["fcitx5-remote", "-s", "hangul"],
                ["fcitx5-remote", "-s", "keyboard-us"],
            ],
        )
        self.assertEqual(sleep.call_count, 2)

    def test_restore_previous_engine(self):
        calls: list[list[str]] = []

        def fake_run(cmd, **_kwargs):
            calls.append(cmd)
            return mock.Mock(returncode=0, stdout="keyboard-us\n", stderr="")

        with mock.patch.object(ime, "_run", side_effect=fake_run):
            with mock.patch.object(ime.time, "sleep"):
                ctl = ime.ImeController(settle_secs=0)
                ctl._backend = "fcitx5"
                snap = ime.ImeSnapshot(backend="fcitx5", name="keyboard-us")
                ctl.set_mode("hangul")
                ctl.restore(snap)

        self.assertIn(["fcitx5-remote", "-s", "hangul"], calls)
        self.assertIn(["fcitx5-remote", "-s", "keyboard-us"], calls)


class TypePayloadImeTest(unittest.TestCase):
    def test_switches_per_script_run(self):
        modes: list[str] = []
        typed: list[str] = []

        class FakeIme:
            def snapshot(self):
                return ime.ImeSnapshot(backend="fcitx5", name="keyboard-us")

            def set_mode(self, mode):
                modes.append(mode)

            def restore(self, snap):
                modes.append(f"restore:{snap.name}")

        fake_ui = object()
        with mock.patch("blankfloat.typer.uinput_typer.type_text", side_effect=lambda ui, text, **k: typed.append(text)):
            type_payload(
                "Hi 안녕",
                countdown_secs=0,
                settle_secs=0,
                ui=fake_ui,
                ime=FakeIme(),
            )

        self.assertEqual(modes, ["latin", "hangul", "restore:keyboard-us"])
        self.assertEqual(typed, ["Hi ", hangul_to_qwerty("안녕")])


if __name__ == "__main__":
    unittest.main()
