# creator-sync

Local-first video publishing workflow for creator-owned media.

## Scope

This project is intended for:

- organizing locally stored videos
- preparing metadata for publishing
- uploading creator-owned or explicitly authorized videos to Bilibili

It is not intended for unauthorized downloading or reposting of third-party content.

## Current MVP

The first version provides:

- inbox scanning for local video files
- one JSON manifest per video
- command-based uploader integration
- JSONL run logs
- automatic archiving into `processed/` or `failed/`

The uploader itself is configurable. That lets you plug in an existing Bilibili uploader command without rewriting the queueing logic.

## Layout

- `config/`: local configuration files
- `data/inbox/`: videos waiting to be processed
- `data/processed/`: successful jobs
- `data/failed/`: failed jobs
- `logs/`: runtime logs
- `scripts/`: helper entrypoints
- `src/`: Python application code

## Config

Copy `config/example.json` to `config/config.json` and then replace `uploader.command` with your real uploader command.

Example:

```json
{
  "project_name": "creator-sync",
  "storage": {
    "inbox_dir": "data/inbox",
    "processed_dir": "data/processed",
    "failed_dir": "data/failed",
    "logs_dir": "logs"
  },
  "uploader": {
    "command": [
      "bash",
      "-lc",
      "printf 'upload %s\\n' \"{video_path}\""
    ],
    "env": {}
  }
}
```

Supported placeholders in `uploader.command` and `uploader.env`:

- `{video_path}`
- `{video_name}`
- `{video_stem}`
- `{manifest_path}`
- `{title}`
- `{description}`
- `{tid}`
- `{tags_csv}`
- `{source}`
- `{cover_path}`
- `{duration_seconds}`
- `{size_bytes}`

## Manifest Format

Each video in `data/inbox/` should have a same-name JSON file:

`demo.mp4`
`demo.json`

Example manifest:

```json
{
  "title": "Demo Title",
  "description": "Demo description",
  "tid": 21,
  "tags": ["demo", "creator-sync"],
  "source": "creator-owned",
  "cover_path": ""
}
```

Required fields:

- `title`
- `description`
- `tid`

## Usage

Create missing manifests:

```bash
python3 -m src.creator_sync.cli --config config/config.json init-manifests
```

Preview ready jobs:

```bash
python3 -m src.creator_sync.cli --config config/config.json scan
```

Validate and print uploader commands without executing:

```bash
python3 -m src.creator_sync.cli --config config/config.json run --dry-run
```

Run the pipeline:

```bash
python3 -m src.creator_sync.cli --config config/config.json run
```

Or use:

```bash
./scripts/run_pipeline.sh run --dry-run
```
