from __future__ import annotations

import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from speech import (
    RHVoiceError,
    SynthesisOptions,
    build_lame_command,
    build_rhvoice_command,
    convert_x_system,
    encode_mp3,
    ensure_bundled_rhvoice,
    find_mp3_encoder_command,
    prepare_text,
    safe_audio_filename,
    safe_mp3_filename,
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

    def test_safe_audio_filename_adjusts_extension(self) -> None:
        self.assertEqual(safe_audio_filename("mia voĉo.wav", "mp3"), "mia_voĉo.mp3")
        self.assertEqual(safe_mp3_filename("エスペラント 音声.mp3"), "エスペラント_音声.mp3")
        self.assertEqual(safe_wav_filename("spomenka.mp3"), "spomenka.wav")

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

    def test_build_lame_command(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            input_path = Path(tmp_dir) / "in.wav"
            output_path = Path(tmp_dir) / "out.mp3"
            command = build_lame_command("/usr/bin/lame", input_path, output_path, 128)

        self.assertEqual(
            command,
            [
                "/usr/bin/lame",
                "--quiet",
                "-b",
                "128",
                str(input_path),
                str(output_path),
            ],
        )

    def test_invalid_options_raise(self) -> None:
        with self.assertRaises(ValueError):
            SynthesisOptions(rate=20).validate()

        with self.assertRaises(ValueError):
            build_lame_command("lame", Path("in.wav"), Path("out.mp3"), 111)

    def test_unknown_notation_raises(self) -> None:
        with self.assertRaises(ValueError):
            prepare_text("Saluton", "unknown")

    @patch("speech.shutil.which", return_value="/mock/RHVoice-test")
    def test_find_command_env_precedence(self, _which) -> None:
        from speech import find_rhvoice_command

        with patch.dict(
            "speech.os.environ",
            {"PAROLIGU_USE_SYSTEM_RHVOICE": "1", "RHVOICE_TEST_BIN": "custom-rhvoice"},
        ):
            self.assertEqual(find_rhvoice_command(), "/mock/RHVoice-test")

    @patch("speech.shutil.which", return_value="/mock/lame")
    def test_find_mp3_encoder_env_precedence(self, _which) -> None:
        with patch.dict("speech.os.environ", {"LAME_BIN": "custom-lame"}):
            self.assertEqual(find_mp3_encoder_command(), "/mock/lame")

    @patch("speech.find_mp3_encoder_command", return_value=None)
    def test_encode_mp3_requires_lame(self, _find_command) -> None:
        with self.assertRaises(RHVoiceError):
            encode_mp3(b"RIFF")

    @patch("speech.find_mp3_encoder_command", return_value="/mock/lame")
    def test_encode_mp3_returns_output_bytes(self, _find_command) -> None:
        def fake_run(command, **_kwargs):
            Path(command[-1]).write_bytes(b"ID3mock-mp3")
            return subprocess.CompletedProcess(command, 0, "", "")

        with patch("speech.subprocess.run", side_effect=fake_run):
            self.assertEqual(encode_mp3(b"RIFFmock-wav", 128), b"ID3mock-mp3")

    def test_bundled_runtime_uses_rhvoice_env_names(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root_dir = Path(tmp_dir) / "root"
            required_paths = (
                root_dir / "usr" / "bin" / "RHVoice-test",
                root_dir / "usr" / "lib" / "x86_64-linux-gnu" / "libRHVoice_core.so.10",
                root_dir / "usr" / "lib" / "x86_64-linux-gnu" / "libRHVoice_audio.so.2",
                root_dir / "usr" / "share" / "RHVoice" / "languages" / "Esperanto" / "language.info",
                root_dir / "usr" / "share" / "RHVoice" / "voices" / "spomenka" / "voice.info",
            )
            for path in required_paths:
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text("ok\n", encoding="utf-8")
            (Path(tmp_dir) / ".complete").write_text("ok\n", encoding="utf-8")

            with (
                patch("speech.RHVOICE_BUNDLE_CACHE", Path(tmp_dir)),
                patch("speech.platform.system", return_value="Linux"),
                patch("speech.platform.machine", return_value="x86_64"),
            ):
                runtime = ensure_bundled_rhvoice()

        self.assertIsNotNone(runtime)
        assert runtime is not None
        self.assertIn("RHVOICE_DATA_PATH", runtime.env)
        self.assertIn("RHVOICE_CONFIG_PATH", runtime.env)
        self.assertNotIn("RHVOICEDATAPATH", runtime.env)


if __name__ == "__main__":
    unittest.main()
