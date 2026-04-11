# ente-exif-tool

Write [Ente Photos](https://ente.io) export metadata into image and video EXIF tags, making them fully readable by Immich, PhotoPrism, Apple Photos, Google Photos, and apps that read standard EXIF data.

## The problem

When you export from Ente Photos, your metadata (dates, GPS coordinates) lives in JSON sidecar files next to each image, unfortunately not embedded in the files themselves. Most photo apps don't support these files and ultimately end up ignoring the sidecars entirely.. so when you import your export into Apple Photos (or almost anything else), your photos lose their dates and locations. Everything lands in a heap with "today's date" as per Ente's seemingly current export process. 

Ente currently does not offer an "export with metadata embedded" option, and there's no built-in way to bake sidecar data back into your files. Whether you are using Windows, Mac, or Linux, your photo data are not likely to survive the export process. If you want your exported photos to work in another app, you're on your own. Additioanlly, some of Ente's competitors do not support the JSON format and prefer XMP (or others).

This tool is the solution, cleaned up and packaged so you don't have to do it yourself manually. 

## What this does

This tool scans your Ente export, matches each media file to its JSON sidecar, and writes the metadata directly into the file's EXIF tags using [ExifTool](https://exiftool.org):

- **DateTimeOriginal** / **CreateDate** / **ModifyDate**: photos sort correctly by date
- **GPSLatitude** / **GPSLongitude**: location data shows up on the map

After running this, you can drag the folder into your other app (or to nowhere!) and everything just works; injected with correct dates, locations, and sort order.

## Requirements

- **Python 3.9+**
- **[ExifTool](https://exiftool.org)** installed and on your PATH:
  - macOS: `brew install exiftool`
  - Linux: `sudo apt install libimage-exiftool-perl`
  - Windows: [download from exiftool.org](https://exiftool.org) and add to PATH, or pass `--exiftool /path/to/exiftool`

## Installation

```bash
pip install .
```

Or run directly without installing:

```bash
python -m ente_exif /path/to/export
```

## Usage

Your Ente export should look like this (this is the default export format as per December 9, 2025):

```
Ente Photos/
├── Album Name/
│   ├── photo.jpg
│   ├── video.mp4
│   └── metadata/
│       ├── photo.jpg.json
│       └── video.mp4.json
└── Another Album/
    └── ...
```

### Preview (Read-only run)

```bash
ente-exif "/path/to/Ente Photos"
```

Shows what would be written without touching or changing any files.

### Write EXIF tags

```bash
ente-exif "/path/to/Ente Photos" --apply
```

### Write EXIF + update filesystem timestamps

```bash
ente-exif "/path/to/Ente Photos" --apply --update-mtime
```

Ente sets file modification dates to the export time, not the photo-taken time, so this is extremely useful.

### Resume an interrupted run

For large libraries, you can use `--resume` to pick up where you left off:

```bash
ente-exif "/path/to/Ente Photos" --apply --resume progress.json
```

### All possible options

| Flag | Description |
|---|---|
| `--apply` | Write EXIF tags (default is dry run) |
| `--update-mtime` | Set filesystem modification time to photo-taken time |
| `--exiftool PATH` | Path to exiftool binary (auto-detected if omitted) |
| `--resume FILE` | Progress file for resuming interrupted runs |
| `--batch-size N` | Files per exiftool invocation (default: 200) |
| `--utc` | Write timestamps as UTC instead of local time |
| `-v` / `--verbose` | Verbose logging |
| `-q` / `--quiet` | Suppress all output except errors |

## Timestamps: UTC vs local time

Ente stores photo-taken times as UTC. By default, this tool converts them to your machine's local timezone before writing. The purpose of this was to match how most photo apps display dates.

You can use `--utc` if your photos span multiple timezones and you want to preserve UTC as the default time zone. Be aware that most photo apps will then display the raw UTC time rather than the wall-clock time the photo was taken at.

**Heads up:** If you've previously written EXIF data with a naive UTC-to-local conversion (e.g. a script that used `datetime.fromtimestamp()` without timezone awareness), photos taken outside your local timezone will have wrong dates. I learned this the hard way. This tool handles that correctly by using timezone-aware conversions throughout.

## Importing into Apple Photos (Should work for Google Photos and others)

After writing EXIF tags:

1. Open Apple Photos
2. File > Import > select your Ente export folder.
3. Photos will read the embedded EXIF dates and GPS data.
4. Everything appears in the correct chronological position and on the Places map.

## Background

This tool was born out of necessity, a single part of a larger project to clean up tens of thousands of photos exported from Ente, spanning over 20 years. Ente works great as a backup, but on the export side the sidecar-only metadata makes it painful to actually use the exported files anywhere else. At this time and the time of the project, there's no built-in "embed metadata on export" option, no scripting API, and no way to do this from within the app. If you've hit the same wall, this tool handles the EXIF part so you don't have to.

If you need help, feel free to reach out. If you like this tool, feel free to leave a star. 

Big shoutout to Phil Harvey for [exiftool](https://exiftool.org).

Another big shoutout to the Ente community. I encourage all Ente users to contribute suggestions and feedback to [Ente.io](https://github.com/ente-io/ente) it's a great piece of software and the developers have done a fantastic job, putting in great work into their product.

## License

MIT
