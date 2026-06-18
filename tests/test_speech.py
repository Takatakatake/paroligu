from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from speech import (
    SynthesisOptions,
    build_rhvoice_command,
    convert_x_system,
    prepare_text,
    safe_wav_filename,
)


class SpeechTests(unittest.TestCase):
    def test_convert_x_system(self) -> None:
        self.assertEqual(
            convert_x_system("Cxu gxi sxangxigxas? Aux jes."),
            "Ĉu ĝi ŝanĝiĝas? Aŭ jes.",
        )

    def test_prepare_text_strips_and_converts(self) -> None:
        self.assertEqual(prepare_text("  Sxi parolas.  ", "x-system"), "Ŝi parolas.")

    def test_safe_wav_filename(self) -> None:
        self.assertEqual(safe_wav_filename(" mia voĉo.wav "), "mia_voĉo.wav")
        self.assertEqual(safe_wav_filename("エスペラント 音声.wav"), "エスペラント_音声.wav")
        self.assertEqual(safe_wav_filename("..."), "spomenka.wav")

    def test_build_rhvoice_command(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            input_path = Path(tmp_dir) / "in.txt"
            output_path = Path(tmp_dir) / "out.wav"
            command = build_rhvoice_command(
                "/usr/bin/RHVoice-test",
                input_path,
                output_path,
                SynthesisOptions(rate=90, pitch=105, volume=120, sample_rate=16_000),
            )

        self.assertEqual(command[0], "/usr/bin/RHVoice-test")
        self.assertIn("--profile", command)
        self.assertIn("spomenka", command)
        self.assertIn("--sample-rate", command)
        self.assertIn("16000", command)

    def test_invalid_options_raise(self) -> None:
        with self.assertRaises(ValueError):
            SynthesisOptions(rate=20).validate()

    def test_unknown_notation_raises(self) -> None:
        with self.assertRaises(ValueError):
            prepare_text("Saluton", "unknown")

    @patch("speech.shutil.which", return_value="/mock/RHVoice-test")
    def test_find_command_env_precedence(self, _which) -> None:
        from speech import find_rhvoice_command

        with patch.dict("speech.os.environ", {"RHVOICE_TEST_BIN": "custom-rhvoice"}):
            self.assertEqual(find_rhvoice_command(), "/mock/RHVoice-test")


if __name__ == "__main__":
    unittest.main()
