import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from ente_exif.sidecar import MediaMeta, build_sidecar_index, parse_sidecar


@pytest.fixture
def sidecar_data():
    return {
        "photoTakenTime": {"timestamp": "1672531200"},
        "geoData": {"latitude": 37.7749, "longitude": -122.4194},
    }


@pytest.fixture
def sidecar_file(tmp_path, sidecar_data):
    p = tmp_path / "photo.jpg.json"
    p.write_text(json.dumps(sidecar_data))
    return p


class TestParseSidecar:
    def test_full_metadata(self, sidecar_file):
        meta = parse_sidecar(sidecar_file)
        assert meta is not None
        assert meta.taken_utc == datetime(2023, 1, 1, tzinfo=timezone.utc)
        assert meta.latitude == pytest.approx(37.7749)
        assert meta.longitude == pytest.approx(-122.4194)
        assert meta.has_gps is True

    def test_no_gps(self, tmp_path):
        data = {"photoTakenTime": {"timestamp": "1672531200"}}
        p = tmp_path / "photo.jpg.json"
        p.write_text(json.dumps(data))
        meta = parse_sidecar(p)
        assert meta is not None
        assert meta.has_gps is False

    def test_zero_gps_treated_as_missing(self, tmp_path):
        data = {
            "photoTakenTime": {"timestamp": "1672531200"},
            "geoData": {"latitude": 0, "longitude": 0},
        }
        p = tmp_path / "photo.jpg.json"
        p.write_text(json.dumps(data))
        meta = parse_sidecar(p)
        assert meta is not None
        assert meta.has_gps is False

    def test_missing_timestamp(self, tmp_path):
        p = tmp_path / "photo.jpg.json"
        p.write_text(json.dumps({"geoData": {"latitude": 1, "longitude": 2}}))
        assert parse_sidecar(p) is None

    def test_corrupt_json(self, tmp_path):
        p = tmp_path / "photo.jpg.json"
        p.write_text("not json")
        assert parse_sidecar(p) is None

    def test_missing_file(self, tmp_path):
        p = tmp_path / "does_not_exist.json"
        assert parse_sidecar(p) is None


class TestBuildSidecarIndex:
    def test_basic_structure(self, tmp_path):
        album = tmp_path / "Album"
        meta_dir = album / "metadata"
        meta_dir.mkdir(parents=True)

        (album / "photo.jpg").write_bytes(b"\xff\xd8\xff")
        (meta_dir / "photo.jpg.json").write_text(json.dumps({
            "photoTakenTime": {"timestamp": "1672531200"},
            "geoData": {"latitude": 40.0, "longitude": -74.0},
        }))

        index = build_sidecar_index(tmp_path)
        assert "Album/photo.jpg" in index
        _, meta = index["Album/photo.jpg"]
        assert meta.taken_utc == datetime(2023, 1, 1, tzinfo=timezone.utc)
        assert meta.latitude == pytest.approx(40.0)

    def test_nested_albums(self, tmp_path):
        deep = tmp_path / "2023" / "Vacation"
        meta_dir = deep / "metadata"
        meta_dir.mkdir(parents=True)

        (deep / "sunset.heic").write_bytes(b"\x00")
        (meta_dir / "sunset.heic.json").write_text(json.dumps({
            "photoTakenTime": {"timestamp": "1672531200"},
        }))

        index = build_sidecar_index(tmp_path)
        assert "2023/Vacation/sunset.heic" in index

    def test_ignores_non_metadata_json(self, tmp_path):
        (tmp_path / "config.json").write_text('{"key": "value"}')
        index = build_sidecar_index(tmp_path)
        assert len(index) == 0
