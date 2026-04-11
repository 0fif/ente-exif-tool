"""Parse Ente Photos JSON sidecar files.

Ente exports place a JSON sidecar for each media file under a metadata/
subdirectory that mirrors the album folder structure:

    Ente Photos/
    +-- Album/
    |   +-- photo.jpg
    |   +-- metadata/
    |       +-- photo.jpg.json

Each sidecar contains (at minimum):

    {
      "photoTakenTime": { "timestamp": "1672531200" },
      "geoData":        { "latitude": 37.7749, "longitude": -122.4194 }
    }

Timestamps are UTC epoch seconds stored as strings. GPS coordinates use
signed decimal degrees (negative = south / west).
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class MediaMeta:
    taken_utc: datetime
    latitude: Optional[float] = None
    longitude: Optional[float] = None

    @property
    def has_gps(self) -> bool:
        return self.latitude is not None and self.longitude is not None


def parse_sidecar(path: Path) -> Optional[MediaMeta]:
    """Read an Ente JSON sidecar and return structured metadata, or None."""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        log.debug("skipping unreadable sidecar %s: %s", path, exc)
        return None

    ts_str = _nested_get(data, "photoTakenTime", "timestamp")
    if not ts_str:
        log.debug("no photoTakenTime in %s", path)
        return None
    try:
        taken_utc = datetime.fromtimestamp(int(ts_str), tz=timezone.utc)
    except (ValueError, OSError, OverflowError):
        log.debug("invalid timestamp %r in %s", ts_str, path)
        return None

    lat = _nested_get(data, "geoData", "latitude")
    lng = _nested_get(data, "geoData", "longitude")
    if lat is not None and lng is not None:
        lat, lng = float(lat), float(lng)
        # Today we learn Ente uses (0, 0) to mean no GPS data...
        if lat == 0.0 and lng == 0.0:
            lat, lng = None, None
    else:
        lat, lng = None, None

    return MediaMeta(taken_utc=taken_utc, latitude=lat, longitude=lng)


def build_sidecar_index(
    export_root: Path,
) -> dict[str, tuple[Path, MediaMeta]]:
    """Map relative media paths to (sidecar_path, parsed_metadata).

    Keys are POSIX-style relative paths from export_root with the metadata/
    component removed. e.g. ``Album/metadata/photo.jpg.json`` -> ``Album/photo.jpg``.
    """
    index: dict[str, tuple[Path, MediaMeta]] = {}

    for sidecar_path in export_root.rglob("*.json"):
        if "metadata" not in sidecar_path.parts:
            continue

        meta = parse_sidecar(sidecar_path)
        if meta is None:
            continue

        try:
            rel = sidecar_path.relative_to(export_root)
        except ValueError:
            continue

        parts = list(rel.parts)
        try:
            parts.remove("metadata")
        except ValueError:
            continue

        # Sidecar filename is "original.ext.json" -- stem strips the .json
        media_rel = str(Path(*parts[:-1]) / sidecar_path.stem)
        media_rel = media_rel.replace("\\", "/")
        index[media_rel] = (sidecar_path, meta)

    return index


def _nested_get(data: dict, *keys: str):
    for k in keys:
        if not isinstance(data, dict):
            return None
        data = data.get(k)
        if data is None:
            return None
    return data
