from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


VIDEO_EXTENSIONS = {".mp4", ".mkv", ".mov", ".avi", ".webm", ".m4v"}


class CreatorSyncError(Exception):
    """Application error with a user-facing message."""


@dataclass
class Job:
    video_path: Path
    manifest_path: Path
    manifest: dict[str, Any]
    duration_seconds: float | None
    size_bytes: int

    @property
    def stem(self) -> str:
        return self.video_path.stem


@dataclass
class InboxEntry:
    video_path: Path
    manifest_path: Path
    has_manifest: bool
    manifest: dict[str, Any] | None
    duration_seconds: float | None
    size_bytes: int
    status: str
    error: str | None

    @property
    def stem(self) -> str:
        return self.video_path.stem


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def load_json(path: Path) -> dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise CreatorSyncError(f"missing file: {path}") from exc
    except json.JSONDecodeError as exc:
        raise CreatorSyncError(f"invalid JSON in {path}: {exc}") from exc


def project_root_from(config_path: Path) -> Path:
    return config_path.resolve().parent.parent


def resolve_path(project_root: Path, raw_path: str) -> Path:
    path = Path(raw_path)
    if path.is_absolute():
        return path
    return project_root / path


def load_config(config_path: Path) -> tuple[Path, dict[str, Any]]:
    config = load_json(config_path)
    project_root = project_root_from(config_path)
    return project_root, config


def ensure_dirs(paths: list[Path]) -> None:
    for path in paths:
        path.mkdir(parents=True, exist_ok=True)


def find_duration_seconds(video_path: Path) -> float | None:
    cmd = [
        "ffprobe",
        "-v",
        "error",
        "-show_entries",
        "format=duration",
        "-of",
        "default=noprint_wrappers=1:nokey=1",
        str(video_path),
    ]
    try:
        result = subprocess.run(
            cmd,
            check=True,
            capture_output=True,
            text=True,
        )
    except (OSError, subprocess.CalledProcessError):
        return None
    output = result.stdout.strip()
    if not output:
        return None
    try:
        return round(float(output), 3)
    except ValueError:
        return None


def scan_jobs(project_root: Path, config: dict[str, Any]) -> list[Job]:
    jobs: list[Job] = []
    for entry in scan_inbox(project_root, config):
        if entry.status != "ready" or not entry.manifest:
            continue
        jobs.append(
            Job(
                video_path=entry.video_path,
                manifest_path=entry.manifest_path,
                manifest=entry.manifest,
                duration_seconds=entry.duration_seconds,
                size_bytes=entry.size_bytes,
            )
        )
    return jobs


def scan_inbox(project_root: Path, config: dict[str, Any]) -> list[InboxEntry]:
    storage = config["storage"]
    inbox_dir = resolve_path(project_root, storage["inbox_dir"])
    entries: list[InboxEntry] = []
    for video_path in sorted(inbox_dir.iterdir()):
        if not video_path.is_file() or video_path.suffix.lower() not in VIDEO_EXTENSIONS:
            continue
        manifest_path = video_path.with_suffix(".json")
        size_bytes = video_path.stat().st_size
        duration_seconds = find_duration_seconds(video_path)
        if not manifest_path.exists():
            entries.append(
                InboxEntry(
                    video_path=video_path,
                    manifest_path=manifest_path,
                    has_manifest=False,
                    manifest=None,
                    duration_seconds=duration_seconds,
                    size_bytes=size_bytes,
                    status="missing_manifest",
                    error="Manifest file is missing.",
                )
            )
            continue
        try:
            manifest = load_json(manifest_path)
            validate_manifest(video_path, manifest)
            cover_path = manifest.get("cover_path")
            if cover_path:
                absolute_cover = resolve_path(project_root, cover_path)
                if not absolute_cover.exists():
                    raise CreatorSyncError(f"cover file not found: {absolute_cover}")
            entries.append(
                InboxEntry(
                    video_path=video_path,
                    manifest_path=manifest_path,
                    has_manifest=True,
                    manifest=manifest,
                    duration_seconds=duration_seconds,
                    size_bytes=size_bytes,
                    status="ready",
                    error=None,
                )
            )
        except CreatorSyncError as exc:
            manifest = None
            try:
                manifest = load_json(manifest_path)
            except CreatorSyncError:
                manifest = None
            entries.append(
                InboxEntry(
                    video_path=video_path,
                    manifest_path=manifest_path,
                    has_manifest=True,
                    manifest=manifest,
                    duration_seconds=duration_seconds,
                    size_bytes=size_bytes,
                    status="invalid_manifest",
                    error=str(exc),
                )
            )
    return entries


def validate_manifest(video_path: Path, manifest: dict[str, Any]) -> None:
    required_fields = ("title", "description", "tid")
    missing = [field for field in required_fields if field not in manifest or manifest[field] in ("", None)]
    if missing:
        raise CreatorSyncError(f"{video_path.name} is missing manifest fields: {', '.join(missing)}")
    if not isinstance(manifest.get("tags", []), list):
        raise CreatorSyncError(f"{video_path.name} manifest field 'tags' must be a list")


def build_context(project_root: Path, job: Job) -> dict[str, str]:
    tags = job.manifest.get("tags", [])
    cover_path = job.manifest.get("cover_path", "")
    absolute_cover_path = ""
    relative_cover_path = ""
    if cover_path:
        resolved_cover_path = resolve_path(project_root, cover_path).resolve()
        absolute_cover_path = str(resolved_cover_path)
        try:
            relative_cover_path = str(resolved_cover_path.relative_to(project_root.resolve()))
        except ValueError:
            relative_cover_path = ""
    return {
        "project_root": str(project_root.resolve()),
        "video_path": str(job.video_path.resolve()),
        "video_path_relative": str(job.video_path.resolve().relative_to(project_root.resolve())),
        "video_name": job.video_path.name,
        "video_stem": job.video_path.stem,
        "manifest_path": str(job.manifest_path.resolve()),
        "manifest_path_relative": str(job.manifest_path.resolve().relative_to(project_root.resolve())),
        "title": str(job.manifest["title"]),
        "description": str(job.manifest["description"]),
        "tid": str(job.manifest["tid"]),
        "tags_csv": ",".join(str(tag) for tag in tags),
        "source": str(job.manifest.get("source", "creator-owned")),
        "cover_path": absolute_cover_path,
        "cover_path_relative": relative_cover_path,
        "duration_seconds": "" if job.duration_seconds is None else str(job.duration_seconds),
        "size_bytes": str(job.size_bytes),
    }


def format_command(command_template: list[str], context: dict[str, str]) -> list[str]:
    try:
        return [part.format(**context) for part in command_template]
    except KeyError as exc:
        raise CreatorSyncError(f"uploader command references unknown placeholder: {exc}") from exc


def format_env(env_template: dict[str, str], context: dict[str, str]) -> dict[str, str]:
    env: dict[str, str] = {}
    for key, value in env_template.items():
        try:
            env[key] = value.format(**context)
        except KeyError as exc:
            raise CreatorSyncError(f"uploader env references unknown placeholder: {exc}") from exc
    return env


def copy_file_if_present(source: Path, destination_dir: Path) -> None:
    if source.exists():
        shutil.copy2(source, destination_dir / source.name)


def archive_job(project_root: Path, config: dict[str, Any], job: Job, succeeded: bool) -> Path:
    storage = config["storage"]
    base_dir = resolve_path(
        project_root,
        storage["processed_dir"] if succeeded else storage["failed_dir"],
    )
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    archive_dir = base_dir / f"{job.stem}_{timestamp}"
    archive_dir.mkdir(parents=True, exist_ok=False)

    shutil.move(str(job.video_path), archive_dir / job.video_path.name)
    shutil.move(str(job.manifest_path), archive_dir / job.manifest_path.name)

    cover_path = job.manifest.get("cover_path")
    if cover_path:
        absolute_cover = resolve_path(project_root, cover_path)
        if absolute_cover.exists() and absolute_cover.parent == job.video_path.parent:
            shutil.move(str(absolute_cover), archive_dir / absolute_cover.name)
        else:
            copy_file_if_present(absolute_cover, archive_dir)
    return archive_dir


def append_log(project_root: Path, config: dict[str, Any], payload: dict[str, Any]) -> None:
    log_dir = resolve_path(project_root, config["storage"]["logs_dir"])
    ensure_dirs([log_dir])
    log_path = log_dir / "runs.jsonl"
    with log_path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, ensure_ascii=False) + "\n")


def run_job(project_root: Path, config: dict[str, Any], job: Job, dry_run: bool) -> tuple[bool, str, list[str]]:
    uploader = config["uploader"]
    command_template = uploader.get("command", [])
    if not command_template:
        raise CreatorSyncError("config uploader.command must be a non-empty list")

    context = build_context(project_root, job)
    command = format_command(command_template, context)
    extra_env = format_env(uploader.get("env", {}), context)

    if dry_run:
        return True, "dry-run", command

    env = os.environ.copy()
    env.update(extra_env)

    result = subprocess.run(
        command,
        cwd=str(project_root),
        env=env,
        capture_output=True,
        text=True,
    )
    stdout = result.stdout.strip()
    stderr = result.stderr.strip()
    message = stdout or stderr or f"exit code {result.returncode}"
    return result.returncode == 0, message, command


def write_manifest_template(video_path: Path) -> Path:
    manifest_path = video_path.with_suffix(".json")
    if manifest_path.exists():
        return manifest_path

    template = {
        "title": video_path.stem,
        "description": "",
        "tid": 21,
        "tags": [],
        "source": "creator-owned",
        "cover_path": "",
    }
    manifest_path.write_text(json.dumps(template, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return manifest_path


def command_scan(args: argparse.Namespace) -> int:
    project_root, config = load_config(Path(args.config))
    storage = config["storage"]
    ensure_dirs(
        [
            resolve_path(project_root, storage["inbox_dir"]),
            resolve_path(project_root, storage["processed_dir"]),
            resolve_path(project_root, storage["failed_dir"]),
            resolve_path(project_root, storage["logs_dir"]),
        ]
    )
    jobs = scan_jobs(project_root, config)
    summary = []
    for job in jobs:
        summary.append(
            {
                "video": job.video_path.name,
                "title": job.manifest["title"],
                "tid": job.manifest["tid"],
                "duration_seconds": job.duration_seconds,
                "size_bytes": job.size_bytes,
            }
        )
    print(json.dumps({"jobs": summary, "count": len(summary)}, ensure_ascii=False, indent=2))
    return 0


def command_init_manifests(args: argparse.Namespace) -> int:
    project_root, config = load_config(Path(args.config))
    inbox_dir = resolve_path(project_root, config["storage"]["inbox_dir"])
    ensure_dirs([inbox_dir])

    created: list[str] = []
    for video_path in sorted(inbox_dir.iterdir()):
        if not video_path.is_file() or video_path.suffix.lower() not in VIDEO_EXTENSIONS:
            continue
        manifest_path = video_path.with_suffix(".json")
        if manifest_path.exists():
            continue
        created_path = write_manifest_template(video_path)
        created.append(created_path.name)

    print(json.dumps({"created": created, "count": len(created)}, ensure_ascii=False, indent=2))
    return 0


def command_run(args: argparse.Namespace) -> int:
    project_root, config = load_config(Path(args.config))
    storage = config["storage"]
    ensure_dirs(
        [
            resolve_path(project_root, storage["inbox_dir"]),
            resolve_path(project_root, storage["processed_dir"]),
            resolve_path(project_root, storage["failed_dir"]),
            resolve_path(project_root, storage["logs_dir"]),
        ]
    )
    jobs = scan_jobs(project_root, config)
    if not jobs:
        print("No ready jobs found in inbox.")
        return 0

    failures = 0
    for job in jobs:
        started_at = utc_now()
        succeeded = False
        archive_dir = ""
        message = ""
        command: list[str] = []
        try:
            succeeded, message, command = run_job(project_root, config, job, dry_run=args.dry_run)
            if not args.dry_run:
                archive_dir = str(archive_job(project_root, config, job, succeeded).resolve())
            if not succeeded:
                failures += 1
        except Exception as exc:
            failures += 1
            message = str(exc)
        payload = {
            "timestamp": started_at,
            "video": job.video_path.name,
            "title": job.manifest.get("title"),
            "status": "success" if succeeded else "failed",
            "dry_run": args.dry_run,
            "archive_dir": archive_dir,
            "command": command,
            "message": message,
        }
        append_log(project_root, config, payload)
        print(json.dumps(payload, ensure_ascii=False))

    return 1 if failures else 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Local-first video publishing workflow.")
    parser.add_argument(
        "--config",
        default="config/config.json",
        help="Path to the runtime config JSON file. Defaults to config/config.json",
    )

    subparsers = parser.add_subparsers(dest="command", required=True)

    scan_parser = subparsers.add_parser("scan", help="List ready upload jobs in the inbox.")
    scan_parser.set_defaults(func=command_scan)

    init_parser = subparsers.add_parser("init-manifests", help="Create JSON manifest templates for videos.")
    init_parser.set_defaults(func=command_init_manifests)

    run_parser = subparsers.add_parser("run", help="Run the upload pipeline for ready jobs.")
    run_parser.add_argument("--dry-run", action="store_true", help="Validate jobs and print commands without executing.")
    run_parser.set_defaults(func=command_run)

    return parser




def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except CreatorSyncError as exc:
        print(str(exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
