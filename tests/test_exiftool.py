"""Verify argfile construction without requiring exiftool installed."""

import os
import tempfile
from datetime import datetime
from pathlib import Path

import pytest

from ente_exif.exiftool import TagSet, _write_args


class TestWriteArgs:
    def test_date_only(self, tmp_path):
        ts = TagSet(path=tmp_path / "photo.jpg", date=datetime(2023, 7, 15, 14, 30, 0))
        fd, argfile = tempfile.mkstemp(suffix=".txt", text=True)
        try:
            with os.fdopen(fd, "w") as f:
                _write_args(f, ts)
            content = Path(argfile).read_text()
            assert "-DateTimeOriginal=2023:07:15 14:30:00" in content
            assert "-CreateDate=2023:07:15 14:30:00" in content
            assert "-ModifyDate=2023:07:15 14:30:00" in content
            assert "GPS" not in content
            assert "-execute" in content
        finally:
            os.unlink(argfile)

    def test_with_gps(self, tmp_path):
        ts = TagSet(
            path=tmp_path / "photo.jpg",
            date=datetime(2023, 1, 1),
            latitude=37.7749,
            longitude=-122.4194,
        )
        fd, argfile = tempfile.mkstemp(suffix=".txt", text=True)
        try:
            with os.fdopen(fd, "w") as f:
                _write_args(f, ts)
            content = Path(argfile).read_text()
            assert "-GPSLatitude=37.7749" in content
            assert "-GPSLatitudeRef=N" in content
            assert "-GPSLongitude=122.4194" in content
            assert "-GPSLongitudeRef=W" in content
        finally:
            os.unlink(argfile)

    def test_southern_hemisphere(self, tmp_path):
        ts = TagSet(
            path=tmp_path / "photo.jpg",
            date=datetime(2023, 1, 1),
            latitude=-33.8688,
            longitude=151.2093,
        )
        fd, argfile = tempfile.mkstemp(suffix=".txt", text=True)
        try:
            with os.fdopen(fd, "w") as f:
                _write_args(f, ts)
            content = Path(argfile).read_text()
            assert "-GPSLatitudeRef=S" in content
            assert "-GPSLongitudeRef=E" in content
        finally:
            os.unlink(argfile)
