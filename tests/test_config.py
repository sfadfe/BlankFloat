import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from blankfloat import config


class DotenvTest(unittest.TestCase):
    def test_loads_key_without_overriding_existing_env(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / ".env"
            path.write_text(
                "BLANKFLOAT_API_KEY=from-file\nBLANKFLOAT_MODEL=from-file\n",
                encoding="utf-8",
            )
            with mock.patch.dict(os.environ, {"BLANKFLOAT_API_KEY": "from-shell"}, clear=False):
                os.environ.pop("BLANKFLOAT_MODEL", None)
                loaded = config.load_dotenv(path)
                self.assertEqual(loaded, path)
                self.assertEqual(os.environ["BLANKFLOAT_API_KEY"], "from-shell")
                self.assertEqual(os.environ["BLANKFLOAT_MODEL"], "from-file")

    def test_config_load_reads_quoted_key_from_dotenv(self):
        with tempfile.TemporaryDirectory() as tmp:
            env_path = Path(tmp) / ".env"
            env_path.write_text('BLANKFLOAT_API_KEY="quoted-key"\n', encoding="utf-8")
            missing = Path(tmp) / "missing.json"
            real_load = config.load_dotenv
            with mock.patch.dict(os.environ, {}, clear=False):
                for key in (*config._API_KEY_ENV, "BLANKFLOAT_MODEL", "BLANKFLOAT_BASE_URL"):
                    os.environ.pop(key, None)
                with mock.patch.object(
                    config, "load_dotenv", side_effect=lambda path=None: real_load(env_path)
                ):
                    with mock.patch.object(config, "config_path", return_value=missing):
                        cfg = config.Config.load()
                self.assertEqual(cfg.api_key, "quoted-key")


if __name__ == "__main__":
    unittest.main()
