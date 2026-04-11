from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from pathlib import Path
from typing import Optional

from tqdm import tqdm

from ente_exif import __version__
from ente_exif.exiftool import TagSet, WriteResult, find_exiftool, version, write_batch
from ente_exif.sidecar import MediaMeta, build_sidecar_index

log = logging.getLogger(__name__)

MEDIA_EXTENSIONS = {
    ".jpg", ".jpeg", ".jpe", ".png", ".gif", ".bmp", ".webp",
    ".tiff", ".tif", ".heic", ".heif", ".dng", ".cr2", ".nef", ".arw",
    ".mp4", ".avi", ".mov", ".mkv", ".wmv", ".flv", ".webm",
    ".m4v", ".mpeg", ".mpg", ".3gp",
}


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        prog="ente-exif",
        description=(
            "Write Ente Photos JSON metadata (dates, GPS) into image and "
            "video EXIF tags so they are readable by Apple Photos, Google "
            "Photos, and other apps."
        ),
    )
    parser.add_argument(
        "export_dir",
        type=Path,
        help="Path to the Ente Photos export directory.",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Actually write EXIF tags. Without this flag, runs in preview mode.",
    )
    parser.add_argument(
        "--update-mtime",
        action="store_true",
        help="Also set each file's filesystem modification time to match the photo-taken time.",
    )
    parser.add_argument(
        "--exiftool",
        metavar="PATH",
        help="Path to the exiftool binary (auto-detected if omitted).",
    )
    parser.add_argument(
        "--resume",
        metavar="FILE",
        type=Path,
        help="Path to a progress file for resuming interrupted runs.",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=200,
        metavar="N",
        help="Files per exiftool invocation (default: 200).",
    )
    parser.add_argument(
        "--utc",
        action="store_true",
        help=(
            "Write timestamps as UTC instead of converting to local time. "
            "Most photo apps expect local time."
        ),
    )
    parser.add_argument("-v", "--verbose", action="store_true")
    parser.add_argument("-q", "--quiet", action="store_true")
    parser.add_argument(
        "--version", action="version", version=f"%(prog)s {__version__}",
    )

    args = parser.parse_args(argv)
    _setup_logging(verbose=args.verbose, quiet=args.quiet)

    export_dir: Path = args.export_dir.resolve()
    if not export_dir.is_dir():
        print(f"error: {export_dir} is not a directory", file=sys.stderr)
        return 1

    if not args.apply:
        print("DRY RUN -- no files will be modified. Pass --apply to write.\n")

    try:
        exiftool_bin = find_exiftool(args.exiftool)
        print(f"exiftool {version(exiftool_bin)}")
    except FileNotFoundError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    print(f"Scanning sidecars in {export_dir} ...")
    index = build_sidecar_index(export_dir)
    print(f"Found {len(index)} sidecars with usable metadata.\n")
    if not index:
        print("Nothing to do.")
        return 0

    matched = _match_media(export_dir, index)
    print(f"Matched {len(matched)} media files to sidecars.\n")
    if not matched:
        print("No media files found that match sidecars.")
        return 0

    done: set[str] = set()
    if args.resume and args.resume.exists():
        done = _load_progress(args.resume)
        before = len(matched)
        matched = [(p, m) for p, m in matched if str(p) not in done]
        print(f"Resuming: {before - len(matched)} already done, {len(matched)} remaining.\n")

    if not args.apply:
        _print_preview(matched)
        return 0

    tag_sets = _build_tag_sets(matched, utc=args.utc)
    print(f"Writing EXIF tags to {len(tag_sets)} files ...")

    results = _write_with_progress(
        exiftool_bin, tag_sets, batch_size=args.batch_size, done=done,
        progress_file=args.resume,
    )

    succeeded = [r for r in results if r.success]
    failed = [r for r in results if not r.success]

    mtime_count = 0
    if args.update_mtime:
        print("Updating filesystem timestamps ...")
        for path, meta in tqdm(matched, desc="mtime", disable=args.quiet):
            if _update_mtime(path, meta):
                mtime_count += 1

    print(f"\n{'=' * 50}")
    print(f"  EXIF written:  {len(succeeded)}")
    print(f"  EXIF failed:   {len(failed)}")
    if args.update_mtime:
        print(f"  mtime updated: {mtime_count}")
    print(f"{'=' * 50}")

    if failed:
        print(f"\nFirst 10 failures:")
        for r in failed[:10]:
            print(f"  {r.path.name}: {r.message}")

    return 1 if failed else 0


def _match_media(
    export_dir: Path,
    index: dict[str, tuple],
) -> list[tuple[Path, MediaMeta]]:
    matched: list[tuple[Path, MediaMeta]] = []
    for file_path in export_dir.rglob("*"):
        if not file_path.is_file():
            continue
        if file_path.suffix.lower() not in MEDIA_EXTENSIONS:
            continue
        if "metadata" in file_path.parts:
            continue

        try:
            rel = str(file_path.relative_to(export_dir)).replace("\\", "/")
        except ValueError:
            continue

        entry = index.get(rel)
        if entry is not None:
            _, meta = entry
            matched.append((file_path, meta))

    return matched


def _build_tag_sets(
    matched: list[tuple[Path, MediaMeta]],
    *,
    utc: bool,
) -> list[TagSet]:
    tag_sets: list[TagSet] = []
    for path, meta in matched:
        if utc:
            dt = meta.taken_utc
        else:
            dt = meta.taken_utc.astimezone().replace(tzinfo=None)
        tag_sets.append(TagSet(
            path=path,
            date=dt,
            latitude=meta.latitude,
            longitude=meta.longitude,
        ))
    return tag_sets


def _write_with_progress(
    exiftool_bin: Path,
    tag_sets: list[TagSet],
    *,
    batch_size: int,
    done: set[str],
    progress_file: Optional[Path],
) -> list[WriteResult]:
    all_results: list[WriteResult] = []
    with tqdm(total=len(tag_sets), desc="Writing EXIF") as pbar:
        for start in range(0, len(tag_sets), batch_size):
            chunk = tag_sets[start : start + batch_size]
            results = write_batch(exiftool_bin, chunk, batch_size=len(chunk))
            all_results.extend(results)
            pbar.update(len(chunk))
            if progress_file:
                for r in results:
                    done.add(str(r.path))
                _save_progress(progress_file, done)
    return all_results


def _update_mtime(path: Path, meta: MediaMeta) -> bool:
    try:
        ts = meta.taken_utc.timestamp()
        os.utime(str(path), (ts, ts))
        return True
    except OSError:
        return False


def _print_preview(matched: list[tuple[Path, MediaMeta]]) -> None:
    with_gps = sum(1 for _, m in matched if m.has_gps)
    print(f"  Files to update:   {len(matched)}")
    print(f"  With GPS data:     {with_gps}")
    print(f"  Without GPS data:  {len(matched) - with_gps}")
    print()
    print("Sample (first 10):")
    for path, meta in matched[:10]:
        local = meta.taken_utc.astimezone().strftime("%Y-%m-%d %H:%M:%S")
        gps = ""
        if meta.has_gps:
            gps = f"  GPS: {meta.latitude:.4f}, {meta.longitude:.4f}"
        print(f"  {path.name}  ->  {local}{gps}")
    if len(matched) > 10:
        print(f"  ... and {len(matched) - 10} more.")
    print(f"\nPass --apply to write EXIF tags.")


def _load_progress(path: Path) -> set[str]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return set(data.get("done", []))
    except (json.JSONDecodeError, OSError):
        return set()


def _save_progress(path: Path, done: set[str]) -> None:
    path.write_text(
        json.dumps({"done": sorted(done)}, ensure_ascii=False),
        encoding="utf-8",
    )


def _setup_logging(*, verbose: bool, quiet: bool) -> None:
    level = logging.ERROR if quiet else logging.DEBUG if verbose else logging.WARNING
    logging.basicConfig(level=level, format="%(levelname)s: %(message)s")
