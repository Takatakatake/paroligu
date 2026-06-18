from __future__ import annotations

import hashlib
import io
import os
import platform
import re
import shutil
import subprocess
import tarfile
import tempfile
import wave
from collections.abc import Iterable
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path
from urllib.error import URLError
from urllib.request import urlopen


VOICE_PROFILE = "spomenka"
MAX_TEXT_CHARS = 20_000
SUPPORTED_SAMPLE_RATES = (16_000, 24_000)
COMMAND_CANDIDATES = ("RHVoice-test", "rhvoice-test", "rhvoice.test")
RHVOICE_BUNDLE_VERSION = "trixie-1.14.0-2-amd64"
RHVOICE_BUNDLE_CACHE = Path.home() / ".cache" / "paroligu" / RHVOICE_BUNDLE_VERSION


@dataclass(frozen=True)
class DebPackage:
    name: str
    url: str
    sha256: str


RHVOICE_DEB_PACKAGES = (
    DebPackage(
        name="librhvoice-core10",
        url="https://deb.debian.org/debian/pool/non-free/r/rhvoice/librhvoice-core10_1.14.0-2_amd64.deb",
        sha256="c24f0fac284c4b1124641300c1da9600f2485f60d3de724eb9226baa6658f1af",
    ),
    DebPackage(
        name="librhvoice-audio2",
        url="https://deb.debian.org/debian/pool/non-free/r/rhvoice/librhvoice-audio2_1.14.0-2_amd64.deb",
        sha256="a88665b195049fd764e1ee0d2bd22c23b6148cd46133bcc51a637e36ed422ac0",
    ),
    DebPackage(
        name="rhvoice",
        url="https://deb.debian.org/debian/pool/non-free/r/rhvoice/rhvoice_1.14.0-2_amd64.deb",
        sha256="abb71e0750641ac80904dd589566a72ad45ddd65399a072bb7bbaae2172125d2",
    ),
    DebPackage(
        name="rhvoice-esperanto",
        url="https://deb.debian.org/debian/pool/non-free/r/rhvoice/rhvoice-esperanto_1.14.0-2_all.deb",
        sha256="ee5742cbb7559ef41feac7aba20026c8f260b43d9bfe3da4ba3b1f00a7262448",
    ),
)


class RHVoiceError(RuntimeError):
    """Raised when RHVoice cannot synthesize audio."""


@dataclass(frozen=True)
class RHVoiceRuntime:
    command: str
    env: dict[str, str]


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


def resolve_rhvoice_runtime() -> RHVoiceRuntime | None:
    env_command = os.environ.get("RHVOICE_TEST_BIN")
    candidates = (env_command, *COMMAND_CANDIDATES) if env_command else COMMAND_CANDIDATES

    if os.environ.get("PAROLIGU_FORCE_BUNDLED_RHVOICE") != "1":
        for candidate in candidates:
            if not candidate:
                continue
            resolved = shutil.which(candidate)
            if resolved:
                return RHVoiceRuntime(command=resolved, env={})
            candidate_path = Path(candidate)
            if candidate_path.exists() and os.access(candidate_path, os.X_OK):
                return RHVoiceRuntime(command=str(candidate_path), env={})

    bundled_runtime = ensure_bundled_rhvoice()
    if bundled_runtime:
        return bundled_runtime

    return None


def find_rhvoice_command() -> str | None:
    try:
        runtime = resolve_rhvoice_runtime()
    except RHVoiceError:
        return None
    return runtime.command if runtime else None


def ensure_bundled_rhvoice() -> RHVoiceRuntime | None:
    if platform.system() != "Linux" or platform.machine() not in {"x86_64", "AMD64"}:
        return None

    root_dir = RHVOICE_BUNDLE_CACHE / "root"
    command = root_dir / "usr" / "bin" / "RHVoice-test"
    lib_dir = root_dir / "usr" / "lib" / "x86_64-linux-gnu"
    data_dir = root_dir / "usr" / "share" / "RHVoice"
    config_dir = root_dir / "etc" / "RHVoice"
    marker = RHVOICE_BUNDLE_CACHE / ".complete"

    if not marker.exists() or not command.exists():
        install_bundled_rhvoice(root_dir, marker)

    if not command.exists():
        return None

    command.chmod(command.stat().st_mode | 0o755)
    env = {
        "LD_LIBRARY_PATH": _join_env_paths(lib_dir, os.environ.get("LD_LIBRARY_PATH")),
        "RHVOICEDATAPATH": str(data_dir),
        "RHVOICECONFIGPATH": str(config_dir),
    }
    return RHVoiceRuntime(command=str(command), env=env)


def install_bundled_rhvoice(root_dir: Path, marker: Path) -> None:
    cache_dir = root_dir.parent
    deb_dir = cache_dir / "debs"
    if root_dir.exists():
        shutil.rmtree(root_dir)
    root_dir.mkdir(parents=True, exist_ok=True)
    deb_dir.mkdir(parents=True, exist_ok=True)

    try:
        for package in RHVOICE_DEB_PACKAGES:
            deb_path = deb_dir / f"{package.name}.deb"
            download_verified(package, deb_path)
            extract_deb_data(deb_path, root_dir)
    except (OSError, tarfile.TarError, URLError) as exc:
        raise RHVoiceError(f"Bundled RHVoice setup failed: {exc}") from exc

    marker.write_text("ok\n", encoding="utf-8")


def download_verified(package: DebPackage, target: Path) -> None:
    if target.exists() and file_sha256(target) == package.sha256:
        return

    with urlopen(package.url, timeout=60) as response:
        data = response.read()

    digest = hashlib.sha256(data).hexdigest()
    if digest != package.sha256:
        raise RHVoiceError(
            f"Checksum mismatch for {package.name}: expected {package.sha256}, got {digest}."
        )

    target.write_bytes(data)


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def extract_deb_data(deb_path: Path, target_dir: Path) -> None:
    for name, data in iter_ar_members(deb_path.read_bytes()):
        if name.startswith("data.tar"):
            with tarfile.open(fileobj=BytesIO(data), mode="r:*") as archive:
                safe_extract_tar(archive, target_dir)
            return

    raise RHVoiceError(f"{deb_path.name} does not contain data.tar.")


def iter_ar_members(data: bytes) -> Iterable[tuple[str, bytes]]:
    if not data.startswith(b"!<arch>\n"):
        raise RHVoiceError("Invalid Debian package archive.")

    offset = 8
    while offset + 60 <= len(data):
        header = data[offset : offset + 60]
        offset += 60
        raw_name = header[:16].decode("utf-8").strip()
        size = int(header[48:58].decode("utf-8").strip())
        member_data = data[offset : offset + size]
        offset += size + (size % 2)
        name = raw_name.rstrip("/")
        yield name, member_data


def safe_extract_tar(archive: tarfile.TarFile, target_dir: Path) -> None:
    target_root = target_dir.resolve()
    for member in archive.getmembers():
        member_path = target_root / member.name.lstrip("./")
        if not member_path.resolve().is_relative_to(target_root):
            raise RHVoiceError(f"Unsafe path in archive: {member.name}")
        archive.extract(member, target_root)


def _join_env_paths(first: Path, existing: str | None) -> str:
    if existing:
        return f"{first}{os.pathsep}{existing}"
    return str(first)


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

    runtime = resolve_rhvoice_runtime()
    if runtime is None:
        raise RHVoiceError(
            "RHVoice-test was not found and the bundled RHVoice fallback is unavailable."
        )

    timeout = min(180, max(20, len(text) // 80 + 20))

    with tempfile.TemporaryDirectory(prefix="spomenka-") as tmp_dir:
        input_path = Path(tmp_dir) / "input.txt"
        output_path = Path(tmp_dir) / "speech.wav"
        input_path.write_text(text, encoding="utf-8")

        try:
            completed = subprocess.run(
                build_rhvoice_command(runtime.command, input_path, output_path, options),
                check=False,
                capture_output=True,
                env={**os.environ, **runtime.env},
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
