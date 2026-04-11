"""ExifTool integration -- argfile-based batch writing for performance."""

from __future__ import annotations

import logging
import os
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class WriteResult:
    path: Path
    success: bool
    message: str = ""


def find_exiftool(hint: Optional[str] = None) -> Path:
    """Locate exiftool: explicit path > $EXIFTOOL env var > $PATH."""
    candidates: list[str] = []
    if hint:
        candidates.append(hint)
    env = os.environ.get("EXIFTOOL")
    if env:
        candidates.append(env)
    candidates.append("exiftool")

    for candidate in candidates:
        path = shutil.which(candidate) or candidate
        try:
            r = subprocess.run(
                [path, "-ver"],
                capture_output=True,
                text=True,
                timeout=10,
            )
            if r.returncode == 0:
                log.info("using exiftool %s at %s", r.stdout.strip(), path)
                return Path(path)
        except (OSError, subprocess.TimeoutExpired):
            continue

    raise FileNotFoundError(
        "exiftool not found. Install it (https://exiftool.org) or pass "
        "--exiftool /path/to/exiftool."
    )


def version(exiftool: Path) -> str:
    r = subprocess.run(
        [str(exiftool), "-ver"],
        capture_output=True,
        text=True,
        timeout=10,
    )
    return r.stdout.strip()


@dataclass
class TagSet:
    path: Path
    date: datetime
    latitude: Optional[float] = None
    longitude: Optional[float] = None


def write_batch(
    exiftool: Path,
    tags: list[TagSet],
    *,
    batch_size: int = 200,
    timeout_per_batch: int = 600,
) -> list[WriteResult]:
    """Write EXIF tags to files. Falls back to per-file on partial failure."""
    results: list[WriteResult] = []
    for start in range(0, len(tags), batch_size):
        chunk = tags[start : start + batch_size]
        results.extend(_write_chunk(exiftool, chunk, timeout_per_batch))
    return results


def _write_chunk(
    exiftool: Path,
    chunk: list[TagSet],
    timeout: int,
) -> list[WriteResult]:
    argfile_fd, argfile_path = tempfile.mkstemp(suffix=".args", text=True)
    try:
        with os.fdopen(argfile_fd, "w", encoding="utf-8") as f:
            for ts in chunk:
                _write_args(f, ts)

        stdout = _run_exiftool(exiftool, argfile_path, timeout)
        if stdout is None:
            return [
                WriteResult(ts.path, False, "exiftool timed out or crashed")
                for ts in chunk
            ]

        updated = stdout.lower().count("image files updated")
        unchanged = stdout.lower().count("image files unchanged")
        if (updated + unchanged) >= len(chunk):
            return [WriteResult(ts.path, True) for ts in chunk]

        return [_write_single(exiftool, ts) for ts in chunk]
    finally:
        try:
            os.unlink(argfile_path)
        except OSError:
            pass


def _write_single(exiftool: Path, ts: TagSet) -> WriteResult:
    argfile_fd, argfile_path = tempfile.mkstemp(suffix=".args", text=True)
    try:
        with os.fdopen(argfile_fd, "w", encoding="utf-8") as f:
            _write_args(f, ts)

        stdout = _run_exiftool(exiftool, argfile_path, timeout=30)
        if stdout and "1 image files updated" in stdout:
            return WriteResult(ts.path, True)
        return WriteResult(ts.path, False, (stdout or "no output")[:200])
    finally:
        try:
            os.unlink(argfile_path)
        except OSError:
            pass


def _write_args(f, ts: TagSet) -> None:
    date_str = ts.date.strftime("%Y:%m:%d %H:%M:%S")
    f.write("-overwrite_original\n")
    f.write("-P\n")
    f.write(f"-DateTimeOriginal={date_str}\n")
    f.write(f"-CreateDate={date_str}\n")
    f.write(f"-ModifyDate={date_str}\n")
    if ts.latitude is not None and ts.longitude is not None:
        lat, lng = ts.latitude, ts.longitude
        f.write(f"-GPSLatitude={abs(lat)}\n")
        f.write(f"-GPSLatitudeRef={'N' if lat >= 0 else 'S'}\n")
        f.write(f"-GPSLongitude={abs(lng)}\n")
        f.write(f"-GPSLongitudeRef={'E' if lng >= 0 else 'W'}\n")
    f.write(f"{ts.path}\n")
    f.write("-execute\n")


def _run_exiftool(
    exiftool: Path, argfile: str, timeout: int
) -> Optional[str]:
    try:
        r = subprocess.run(
            [str(exiftool), "-@", argfile],
            capture_output=True,
            timeout=timeout,
        )
        return r.stdout.decode("utf-8", errors="replace")
    except (subprocess.TimeoutExpired, OSError) as exc:
        log.error("exiftool failed: %s", exc)
        return None
