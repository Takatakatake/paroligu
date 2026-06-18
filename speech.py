from __future__ import annotations

import io
import os
import re
import shutil
import subprocess
import tempfile
import wave
from dataclasses import dataclass
from pathlib import Path


VOICE_PROFILE = "spomenka"
MAX_TEXT_CHARS = 20_000
SUPPORTED_SAMPLE_RATES = (16_000, 24_000)
COMMAND_CANDIDATES = ("RHVoice-test", "rhvoice-test", "rhvoice.test")


class RHVoiceError(RuntimeError):
    """Raised when RHVoice cannot synthesize audio."""


@dataclass(frozen=True)
class SynthesisOptions:
    rate: int = 100
    pitch: int = 100
    volume: int = 100
    sample_rate: int = 24_000

    def validate(self) -> None:
        for label, value in (
            ("rate", self.rate),
            ("pitch", self.pitch),
            ("volume", self.volume),
        ):
            if not 50 <= value <= 200:
                raise ValueError(f"{label} must be between 50 and 200.")

        if self.sample_rate not in SUPPORTED_SAMPLE_RATES:
            allowed = ", ".join(str(rate) for rate in SUPPORTED_SAMPLE_RATES)
            raise ValueError(f"sample_rate must be one of: {allowed}.")


def convert_x_system(text: str) -> str:
    replacements = {
        "c": "ĉ",
        "g": "ĝ",
        "h": "ĥ",
        "j": "ĵ",
        "s": "ŝ",
        "u": "ŭ",
    }

    def replace(match: re.Match[str]) -> str:
        base = match.group(1)
        converted = replacements[base.lower()]
        return converted.upper() if base.isupper() else converted

    return re.sub(r"([cghjsuCGHJSU])[xX]", replace, text)


def prepare_text(text: str, notation: str = "unicode") -> str:
    cleaned = text.strip()
    if notation == "x-system":
        cleaned = convert_x_system(cleaned)
    elif notation != "unicode":
        raise ValueError("notation must be 'unicode' or 'x-system'.")
    return cleaned


def find_rhvoice_command() -> str | None:
    env_command = os.environ.get("RHVOICE_TEST_BIN")
    candidates = (env_command, *COMMAND_CANDIDATES) if env_command else COMMAND_CANDIDATES

    for candidate in candidates:
        if not candidate:
            continue
        resolved = shutil.which(candidate)
        if resolved:
            return resolved
        candidate_path = Path(candidate)
        if candidate_path.exists() and os.access(candidate_path, os.X_OK):
            return str(candidate_path)

    return None


def build_rhvoice_command(
    command: str,
    input_path: Path,
    output_path: Path,
    options: SynthesisOptions,
) -> list[str]:
    options.validate()
    return [
        command,
        "--profile",
        VOICE_PROFILE,
        "--rate",
        str(options.rate),
        "--pitch",
        str(options.pitch),
        "--volume",
        str(options.volume),
        "--sample-rate",
        str(options.sample_rate),
        "--input",
        str(input_path),
        "--output",
        str(output_path),
    ]


def synthesize_wav(text: str, options: SynthesisOptions | None = None) -> bytes:
    options = options or SynthesisOptions()
    text = text.strip()

    if not text:
        raise ValueError("Text is empty.")
    if len(text) > MAX_TEXT_CHARS:
        raise ValueError(f"Text is too long. Maximum is {MAX_TEXT_CHARS:,} characters.")

    command = find_rhvoice_command()
    if command is None:
        raise RHVoiceError(
            "RHVoice-test was not found. Install the rhvoice and rhvoice-esperanto packages."
        )

    timeout = min(180, max(20, len(text) // 80 + 20))

    with tempfile.TemporaryDirectory(prefix="spomenka-") as tmp_dir:
        input_path = Path(tmp_dir) / "input.txt"
        output_path = Path(tmp_dir) / "speech.wav"
        input_path.write_text(text, encoding="utf-8")

        try:
            completed = subprocess.run(
                build_rhvoice_command(command, input_path, output_path, options),
                check=False,
                capture_output=True,
                text=True,
                timeout=timeout,
            )
        except subprocess.TimeoutExpired as exc:
            raise RHVoiceError(f"RHVoice timed out after {timeout} seconds.") from exc

        if completed.returncode != 0:
            stderr = completed.stderr.strip() or completed.stdout.strip()
            raise RHVoiceError(stderr or "RHVoice failed without an error message.")

        if not output_path.exists() or output_path.stat().st_size == 0:
            raise RHVoiceError("RHVoice did not create an audio file.")

        return output_path.read_bytes()


def wav_duration_seconds(wav_bytes: bytes) -> float:
    with wave.open(io.BytesIO(wav_bytes), "rb") as wav_file:
        frames = wav_file.getnframes()
        rate = wav_file.getframerate()
    return frames / float(rate)


def safe_wav_filename(value: str) -> str:
    stem = value.strip() or "spomenka"
    stem = re.sub(r"\.wav$", "", stem, flags=re.IGNORECASE)
    stem = re.sub(r"[/\\:*?\"<>|\x00-\x1f]+", "_", stem)
    stem = re.sub(r"\s+", "_", stem).strip("._- ")
    if not stem:
        stem = "spomenka"
    return f"{stem}.wav"
