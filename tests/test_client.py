import base64
import io
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from PIL import Image

from blankfloat import client, pipeline
from blankfloat.config import Config


def write_png(path: Path, size=(2400, 1200)) -> Path:
    Image.new("RGB", size, (200, 210, 220)).save(path)
    return path


class EncodeImageTest(unittest.TestCase):
    def test_downscales_to_max_px(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = write_png(Path(tmp) / "shot.png")
            encoded = client.encode_image(path, max_px=800)
            with Image.open(io.BytesIO(base64.b64decode(encoded))) as img:
                self.assertEqual(max(img.size), 800)

    def test_keeps_small_images_untouched(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = write_png(Path(tmp) / "shot.png", size=(400, 300))
            encoded = client.encode_image(path, max_px=1600)
            with Image.open(io.BytesIO(base64.b64decode(encoded))) as img:
                self.assertEqual(img.size, (400, 300))


class MessageShapeTest(unittest.TestCase):
    def test_base64_style_sends_bare_string(self):
        messages = client._messages("AAAA", "auto", False, "base64")
        self.assertEqual(messages[1]["content"][0]["image_url"]["url"], "AAAA")

    def test_data_url_style_prefixes(self):
        messages = client._messages("AAAA", "auto", False, "data_url")
        self.assertTrue(
            messages[1]["content"][0]["image_url"]["url"].startswith("data:image/png;base64,")
        )

    def test_forced_mode_reaches_the_model(self):
        messages = client._messages("AAAA", "complex", False, "base64")
        self.assertIn("COMPLEX mode", messages[1]["content"][1]["text"])

    def test_retry_adds_json_only_reminder(self):
        messages = client._messages("AAAA", "auto", True, "base64")
        self.assertIn("valid JSON object", messages[1]["content"][1]["text"])

    def test_multi_images_are_separate_parts(self):
        messages = client._messages(["AAA", "BBB"], "auto", False, "base64")
        content = messages[1]["content"]
        self.assertEqual(len(content), 3)
        self.assertEqual(content[0]["image_url"]["url"], "AAA")
        self.assertEqual(content[1]["image_url"]["url"], "BBB")
        self.assertIn("2 sequential screenshots", content[2]["text"])

    def test_extra_text_appended_to_user_message(self):
        messages = client._messages("AAAA", "auto", False, "base64", extra_text="  객관식만  ")
        text = messages[1]["content"][1]["text"]
        self.assertIn("Additional user note:", text)
        self.assertIn("객관식만", text)

    def test_blank_extra_text_is_ignored(self):
        messages = client._messages("AAAA", "auto", False, "base64", extra_text="  \n")
        self.assertNotIn("Additional user note:", messages[1]["content"][1]["text"])


class PipelineErrorTest(unittest.TestCase):
    def test_missing_api_key_becomes_result_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = write_png(Path(tmp) / "shot.png", size=(100, 100))
            result = pipeline.analyze_image(path, "auto", Config(api_key=""))
        self.assertFalse(result.ok)
        self.assertIn("API 키", result.error)
        self.assertIsNone(result.analysis)

    def test_analyze_images_empty_list(self):
        result = pipeline.analyze_images([], "auto", Config(api_key="test"))
        self.assertFalse(result.ok)
        self.assertIn("이미지", result.error)

    def test_analyze_images_passes_all_paths(self):
        with tempfile.TemporaryDirectory() as tmp:
            paths = [
                write_png(Path(tmp) / "a.png", size=(100, 100)),
                write_png(Path(tmp) / "b.png", size=(100, 100)),
            ]
            with mock.patch.object(client, "analyze", return_value='{"route":"simple","answers":[]}') as analyze:
                with mock.patch.object(pipeline.routing, "normalize") as normalize:
                    from blankfloat.routing import Analysis

                    normalize.return_value = Analysis(route="simple")
                    with mock.patch.object(pipeline.routing, "apply_guards", side_effect=lambda a, **_k: a):
                        with mock.patch.object(pipeline.routing, "extract_json", return_value={"route": "simple"}):
                            result = pipeline.analyze_images(paths, "auto", Config(api_key="test"))
            self.assertTrue(result.ok)
            analyze.assert_called_once()
            self.assertEqual(analyze.call_args.args[0], paths)


class OverloadRetryTest(unittest.TestCase):
    def test_retries_overload_then_succeeds(self):
        class FakeResponse:
            def __init__(self, status_code, payload):
                self.status_code = status_code
                self.ok = status_code == 200
                self._payload = payload
                self.text = str(payload)

            def json(self):
                return self._payload

        calls = {"n": 0}

        def fake_post(_cfg, _messages):
            calls["n"] += 1
            if calls["n"] < 3:
                return FakeResponse(
                    429,
                    {"error": {"code": "1305", "message": "The service may be temporarily overloaded"}},
                )
            return FakeResponse(
                200,
                {"choices": [{"message": {"content": '{"route":"simple"}'}}]},
            )

        with tempfile.TemporaryDirectory() as tmp:
            path = write_png(Path(tmp) / "shot.png", size=(100, 100))
            with mock.patch.object(client, "_post", fake_post):
                with mock.patch.object(client, "OVERLOAD_BACKOFF_SECONDS", (0.01, 0.01, 0.01, 0.01)):
                    text = client.analyze(path, "auto", Config(api_key="test-key"))
        self.assertIn("simple", text)
        self.assertEqual(calls["n"], 3)

    def test_balance_429_is_not_retried_as_overload(self):
        class FakeResponse:
            def __init__(self):
                self.status_code = 429
                self.ok = False
                self.text = "balance"

            def json(self):
                return {"error": {"code": "1113", "message": "Insufficient balance or no resource package"}}

        with tempfile.TemporaryDirectory() as tmp:
            path = write_png(Path(tmp) / "shot.png", size=(100, 100))
            with mock.patch.object(client, "_post", return_value=FakeResponse()):
                with self.assertRaises(client.ApiError) as ctx:
                    client.analyze(path, "auto", Config(api_key="test-key"))
        self.assertIn("잔액", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
