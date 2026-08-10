import unittest

from blankfloat.__main__ import build_parser


class ParserTest(unittest.TestCase):
    def parse(self, argv):
        return build_parser().parse_args(argv)

    def test_no_arguments_runs_the_ui(self):
        args = self.parse([])
        self.assertIsNone(args.command)
        self.assertIsNone(args.mode)
        self.assertFalse(args.capture)

    def test_capture_flag_before_subcommand(self):
        args = self.parse(["--mode", "simple", "--capture", "run"])
        self.assertEqual(args.command, "run")
        self.assertEqual(args.mode, "simple")
        self.assertTrue(args.capture)

    def test_mode_flag_after_subcommand(self):
        args = self.parse(["analyze", "shot.png", "--mode", "complex"])
        self.assertEqual(args.mode, "complex")
        self.assertEqual(str(args.image), "shot.png")

    def test_subcommand_does_not_reset_earlier_flags(self):
        args = self.parse(["--mode", "complex", "analyze", "shot.png"])
        self.assertEqual(args.mode, "complex")
        self.assertFalse(args.raw)

    def test_capture_subcommand_is_the_hotkey_entry(self):
        args = self.parse(["capture"])
        self.assertEqual(args.command, "capture")
        self.assertIsNone(args.mode)

    def test_multi_subcommand(self):
        args = self.parse(["multi"])
        self.assertEqual(args.command, "multi")
        self.assertIsNone(args.mode)


if __name__ == "__main__":
    unittest.main()
