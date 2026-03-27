from __future__ import annotations

import argparse
import json
from html import escape
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, quote_plus, urlparse

from .cli import (
    CreatorSyncError,
    append_log,
    archive_job,
    ensure_dirs,
    load_config,
    resolve_path,
    run_job,
    scan_inbox,
    scan_jobs,
    utc_now,
    write_manifest_template,
)


def read_recent_logs(project_root: Path, config: dict, limit: int = 30) -> list[dict]:
    log_path = resolve_path(project_root, config["storage"]["logs_dir"]) / "runs.jsonl"
    if not log_path.exists():
        return []
    lines = log_path.read_text(encoding="utf-8").splitlines()
    items: list[dict] = []
    for line in lines[-limit:]:
        try:
            items.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return list(reversed(items))


def save_manifest(video_path: Path, form: dict[str, str]) -> None:
    tags = [tag.strip() for tag in form.get("tags", "").split(",") if tag.strip()]
    manifest = {
        "title": form.get("title", "").strip(),
        "description": form.get("description", "").strip(),
        "tid": int(form.get("tid", "21").strip() or "21"),
        "tags": tags,
        "source": form.get("source", "creator-owned").strip() or "creator-owned",
        "cover_path": form.get("cover_path", "").strip(),
    }
    manifest_path = video_path.with_suffix(".json")
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def nav_html() -> str:
    return (
        "<nav>"
        "<a href='/'>Dashboard</a>"
        "<a href='/logs'>Logs</a>"
        "</nav>"
    )


def page_html(title: str, body: str) -> bytes:
    html = f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{escape(title)}</title>
  <style>
    :root {{
      --bg: #f4efe6;
      --panel: #fffaf2;
      --panel-2: #f0e5d3;
      --text: #1d1b17;
      --muted: #6a6256;
      --accent: #1e6b52;
      --accent-2: #c96c2c;
      --danger: #9b2c2c;
      --border: #d9cbb3;
      --shadow: 0 16px 40px rgba(49, 35, 11, 0.08);
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      font-family: Georgia, "Noto Serif SC", serif;
      color: var(--text);
      background:
        radial-gradient(circle at top left, rgba(201,108,44,0.16), transparent 26%),
        radial-gradient(circle at top right, rgba(30,107,82,0.12), transparent 24%),
        linear-gradient(180deg, #f8f2e8 0%, var(--bg) 100%);
    }}
    .shell {{
      max-width: 1200px;
      margin: 0 auto;
      padding: 32px 20px 48px;
    }}
    nav {{
      display: flex;
      gap: 12px;
      margin-bottom: 24px;
    }}
    nav a {{
      color: var(--text);
      text-decoration: none;
      background: rgba(255,250,242,0.86);
      border: 1px solid var(--border);
      padding: 10px 14px;
      border-radius: 999px;
    }}
    h1 {{
      font-size: clamp(32px, 4vw, 52px);
      margin: 0 0 8px;
      line-height: 0.98;
    }}
    p.lead {{
      color: var(--muted);
      max-width: 760px;
      margin: 0 0 24px;
    }}
    .grid {{
      display: grid;
      gap: 18px;
    }}
    .summary {{
      grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
      margin-bottom: 20px;
    }}
    .cards {{
      grid-template-columns: repeat(auto-fit, minmax(320px, 1fr));
    }}
    .card {{
      background: rgba(255,250,242,0.94);
      border: 1px solid var(--border);
      border-radius: 22px;
      box-shadow: var(--shadow);
      padding: 18px;
    }}
    .metric {{
      font-size: 30px;
      margin-top: 8px;
      font-weight: 700;
    }}
    .eyebrow {{
      text-transform: uppercase;
      letter-spacing: 0.12em;
      color: var(--muted);
      font-size: 12px;
    }}
    .status {{
      display: inline-block;
      padding: 6px 10px;
      border-radius: 999px;
      font-size: 12px;
      margin-bottom: 10px;
      background: var(--panel-2);
    }}
    .status.ready {{ background: rgba(30,107,82,0.13); color: var(--accent); }}
    .status.missing_manifest, .status.invalid_manifest {{ background: rgba(155,44,44,0.1); color: var(--danger); }}
    .actions {{
      display: flex;
      flex-wrap: wrap;
      gap: 10px;
      margin-top: 14px;
    }}
    form.inline {{ display: inline; }}
    button, .button {{
      appearance: none;
      border: 0;
      cursor: pointer;
      color: white;
      background: linear-gradient(135deg, var(--accent), #154a39);
      padding: 10px 14px;
      border-radius: 12px;
      text-decoration: none;
      font: inherit;
    }}
    button.alt, .button.alt {{
      background: linear-gradient(135deg, var(--accent-2), #9a4d19);
    }}
    button.ghost, .button.ghost {{
      color: var(--text);
      background: transparent;
      border: 1px solid var(--border);
    }}
    dl {{
      display: grid;
      grid-template-columns: 110px 1fr;
      gap: 6px 12px;
      margin: 0;
    }}
    dt {{ color: var(--muted); }}
    dd {{ margin: 0; word-break: break-word; }}
    textarea, input {{
      width: 100%;
      border-radius: 12px;
      border: 1px solid var(--border);
      padding: 10px 12px;
      font: inherit;
      background: white;
    }}
    label {{
      display: block;
      margin: 12px 0 6px;
      color: var(--muted);
    }}
    .flash {{
      background: rgba(30,107,82,0.1);
      border: 1px solid rgba(30,107,82,0.24);
      padding: 12px 14px;
      border-radius: 14px;
      margin-bottom: 18px;
    }}
    .error {{
      background: rgba(155,44,44,0.08);
      border-color: rgba(155,44,44,0.24);
    }}
    table {{
      width: 100%;
      border-collapse: collapse;
    }}
    th, td {{
      text-align: left;
      padding: 10px 8px;
      border-bottom: 1px solid var(--border);
      vertical-align: top;
    }}
    code {{
      white-space: pre-wrap;
      word-break: break-word;
    }}
    @media (max-width: 720px) {{
      .shell {{ padding: 20px 14px 40px; }}
      dl {{ grid-template-columns: 1fr; }}
    }}
  </style>
</head>
<body>
  <div class="shell">
    {nav_html()}
    {body}
  </div>
</body>
</html>"""
    return html.encode("utf-8")


def build_dashboard(project_root: Path, config: dict, flash: str = "", error: str = "") -> bytes:
    entries = scan_inbox(project_root, config)
    ready_count = sum(1 for entry in entries if entry.status == "ready")
    missing_count = sum(1 for entry in entries if entry.status == "missing_manifest")
    invalid_count = sum(1 for entry in entries if entry.status == "invalid_manifest")

    summary = f"""
    <h1>Creator Sync Console</h1>
    <p class="lead">Manage local videos, edit Bilibili metadata, preview uploader commands, and run the publishing pipeline from one local page.</p>
    """
    if flash:
        summary += f"<div class='flash'>{escape(flash)}</div>"
    if error:
        summary += f"<div class='flash error'>{escape(error)}</div>"

    summary += f"""
    <div class="grid summary">
      <section class="card"><div class="eyebrow">Inbox Videos</div><div class="metric">{len(entries)}</div></section>
      <section class="card"><div class="eyebrow">Ready Jobs</div><div class="metric">{ready_count}</div></section>
      <section class="card"><div class="eyebrow">Missing Manifest</div><div class="metric">{missing_count}</div></section>
      <section class="card"><div class="eyebrow">Invalid Manifest</div><div class="metric">{invalid_count}</div></section>
    </div>
    <div class="grid cards">
    """

    cards = []
    for entry in entries:
        manifest = entry.manifest or {}
        tags_value = ", ".join(str(tag) for tag in manifest.get("tags", []))
        description = manifest.get("description", "")
        cards.append(
            f"""
            <section class="card">
              <div class="status {escape(entry.status)}">{escape(entry.status.replace('_', ' '))}</div>
              <h2>{escape(entry.video_path.name)}</h2>
              <dl>
                <dt>Size</dt><dd>{entry.size_bytes} bytes</dd>
                <dt>Duration</dt><dd>{escape(str(entry.duration_seconds))}</dd>
                <dt>Manifest</dt><dd>{escape(entry.manifest_path.name)}</dd>
                <dt>Error</dt><dd>{escape(entry.error or '-')}</dd>
              </dl>
              <div class="actions">
                <form class="inline" method="post" action="/init-manifest">
                  <input type="hidden" name="video" value="{escape(entry.video_path.name)}">
                  <button class="ghost" type="submit">Init Manifest</button>
                </form>
                <a class="button ghost" href="/edit?video={escape(entry.video_path.name)}">Edit Metadata</a>
                <form class="inline" method="post" action="/run">
                  <input type="hidden" name="video" value="{escape(entry.video_path.name)}">
                  <input type="hidden" name="dry_run" value="1">
                  <button class="alt" type="submit">Dry Run</button>
                </form>
                <form class="inline" method="post" action="/run">
                  <input type="hidden" name="video" value="{escape(entry.video_path.name)}">
                  <button type="submit">Run</button>
                </form>
              </div>
              <label>Title</label>
              <input value="{escape(str(manifest.get('title', '')))}" readonly>
              <label>Description</label>
              <textarea rows="4" readonly>{escape(str(description))}</textarea>
              <label>Tags</label>
              <input value="{escape(tags_value)}" readonly>
            </section>
            """
        )

    if not cards:
        cards.append("<section class='card'><h2>No videos found</h2><p>Add local video files into <code>data/inbox/</code> first.</p></section>")

    summary += "".join(cards) + "</div>"
    return page_html("Creator Sync Console", summary)


def build_edit_page(project_root: Path, config: dict, video_name: str, flash: str = "", error: str = "") -> bytes:
    inbox_dir = resolve_path(project_root, config["storage"]["inbox_dir"])
    video_path = inbox_dir / video_name
    if not video_path.exists():
        raise CreatorSyncError(f"video not found: {video_name}")
    manifest_path = write_manifest_template(video_path)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    tags = ", ".join(str(tag) for tag in manifest.get("tags", []))
    body = f"""
    <h1>Edit Metadata</h1>
    <p class="lead">{escape(video_name)}</p>
    {f"<div class='flash'>{escape(flash)}</div>" if flash else ""}
    {f"<div class='flash error'>{escape(error)}</div>" if error else ""}
    <section class="card">
      <form method="post" action="/save">
        <input type="hidden" name="video" value="{escape(video_name)}">
        <label>Title</label>
        <input name="title" value="{escape(str(manifest.get('title', '')))}">
        <label>Description</label>
        <textarea name="description" rows="8">{escape(str(manifest.get('description', '')))}</textarea>
        <label>TID</label>
        <input name="tid" value="{escape(str(manifest.get('tid', 21)))}">
        <label>Tags</label>
        <input name="tags" value="{escape(tags)}">
        <label>Source</label>
        <input name="source" value="{escape(str(manifest.get('source', 'creator-owned')))}">
        <label>Cover Path</label>
        <input name="cover_path" value="{escape(str(manifest.get('cover_path', '')))}">
        <div class="actions">
          <button type="submit">Save Manifest</button>
          <a class="button ghost" href="/">Back</a>
        </div>
      </form>
    </section>
    """
    return page_html(f"Edit {video_name}", body)


def build_logs_page(project_root: Path, config: dict) -> bytes:
    rows = []
    for item in read_recent_logs(project_root, config):
        command = " ".join(item.get("command", []))
        rows.append(
            "<tr>"
            f"<td>{escape(str(item.get('timestamp', '')))}</td>"
            f"<td>{escape(str(item.get('video', '')))}</td>"
            f"<td>{escape(str(item.get('status', '')))}</td>"
            f"<td>{escape(str(item.get('message', '')))}</td>"
            f"<td><code>{escape(command)}</code></td>"
            "</tr>"
        )
    body = (
        "<h1>Run Logs</h1>"
        "<p class='lead'>Recent pipeline events from logs/runs.jsonl.</p>"
        "<section class='card'><table><thead><tr><th>Time</th><th>Video</th><th>Status</th><th>Message</th><th>Command</th></tr></thead>"
        f"<tbody>{''.join(rows) or '<tr><td colspan=5>No logs yet.</td></tr>'}</tbody></table></section>"
    )
    return page_html("Run Logs", body)


def parse_form_data(handler: BaseHTTPRequestHandler) -> dict[str, str]:
    length = int(handler.headers.get("Content-Length", "0"))
    data = handler.rfile.read(length).decode("utf-8")
    parsed = parse_qs(data, keep_blank_values=True)
    return {key: values[0] for key, values in parsed.items()}


def redirect(handler: BaseHTTPRequestHandler, location: str) -> None:
    handler.send_response(HTTPStatus.SEE_OTHER)
    handler.send_header("Location", location)
    handler.end_headers()


def make_handler(config_path: Path):
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            parsed = urlparse(self.path)
            try:
                project_root, config = load_config(config_path)
                ensure_dirs(
                    [
                        resolve_path(project_root, config["storage"]["inbox_dir"]),
                        resolve_path(project_root, config["storage"]["processed_dir"]),
                        resolve_path(project_root, config["storage"]["failed_dir"]),
                        resolve_path(project_root, config["storage"]["logs_dir"]),
                    ]
                )
                if parsed.path == "/":
                    flash = parse_qs(parsed.query).get("flash", [""])[0]
                    error = parse_qs(parsed.query).get("error", [""])[0]
                    self.respond(build_dashboard(project_root, config, flash=flash, error=error))
                    return
                if parsed.path == "/edit":
                    query = parse_qs(parsed.query)
                    video_name = query.get("video", [""])[0]
                    if not video_name:
                        raise CreatorSyncError("missing video parameter")
                    flash = query.get("flash", [""])[0]
                    error = query.get("error", [""])[0]
                    self.respond(build_edit_page(project_root, config, video_name, flash=flash, error=error))
                    return
                if parsed.path == "/logs":
                    self.respond(build_logs_page(project_root, config))
                    return
                self.send_error(HTTPStatus.NOT_FOUND)
            except CreatorSyncError as exc:
                self.respond(page_html("Error", f"<h1>Error</h1><div class='flash error'>{escape(str(exc))}</div>"), status=400)

        def do_POST(self) -> None:
            parsed = urlparse(self.path)
            form = parse_form_data(self)
            try:
                project_root, config = load_config(config_path)
                inbox_dir = resolve_path(project_root, config["storage"]["inbox_dir"])
                if parsed.path == "/init-manifest":
                    video_name = form.get("video", "")
                    if not video_name:
                        raise CreatorSyncError("missing video parameter")
                    write_manifest_template(inbox_dir / video_name)
                    redirect(self, "/?flash=Manifest+created")
                    return
                if parsed.path == "/save":
                    video_name = form.get("video", "")
                    if not video_name:
                        raise CreatorSyncError("missing video parameter")
                    save_manifest(inbox_dir / video_name, form)
                    redirect(self, f"/edit?video={quote_plus(video_name)}&flash=Manifest+saved")
                    return
                if parsed.path == "/run":
                    video_name = form.get("video", "")
                    dry_run = form.get("dry_run") == "1"
                    if video_name:
                        jobs = [job for job in scan_jobs(project_root, config) if job.video_path.name == video_name]
                    else:
                        jobs = scan_jobs(project_root, config)
                    if not jobs:
                        raise CreatorSyncError("no ready jobs matched the request")
                    job = jobs[0]
                    started_at = utc_now()
                    succeeded = False
                    archive_dir = ""
                    command: list[str] = []
                    message = ""
                    try:
                        succeeded, message, command = run_job(project_root, config, job, dry_run=dry_run)
                        if not dry_run:
                            archive_dir = str(archive_job(project_root, config, job, succeeded).resolve())
                    except Exception as exc:
                        message = str(exc)
                    payload = {
                        "timestamp": started_at,
                        "video": job.video_path.name,
                        "title": job.manifest.get("title"),
                        "status": "success" if succeeded else "failed",
                        "dry_run": dry_run,
                        "archive_dir": archive_dir,
                        "command": command,
                        "message": message,
                    }
                    append_log(project_root, config, payload)
                    status_label = "Dry run finished" if dry_run else "Run finished"
                    body = (
                        f"<h1>{escape(status_label)}</h1>"
                        "<p class='lead'>Pipeline result</p>"
                        f"<section class='card'>{render_result_table(payload)}</section>"
                        "<p><a class='button ghost' href='/'>Back</a></p>"
                    )
                    self.respond(page_html(status_label, body))
                    return
                self.send_error(HTTPStatus.NOT_FOUND)
            except CreatorSyncError as exc:
                redirect(self, f"/?error={quote_plus(str(exc))}")

        def log_message(self, format: str, *args) -> None:
            return

        def respond(self, content: bytes, status: int = 200) -> None:
            self.send_response(status)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(content)))
            self.end_headers()
            self.wfile.write(content)

    return Handler


def render_result_table(payload: dict) -> str:
    rows = []
    for key in ("timestamp", "video", "title", "status", "dry_run", "archive_dir", "message"):
        rows.append(f"<tr><th>{escape(str(key))}</th><td>{escape(str(payload.get(key, '')))}</td></tr>")
    rows.append(f"<tr><th>command</th><td><code>{escape(' '.join(payload.get('command', [])))}</code></td></tr>")
    return "<table>" + "".join(rows) + "</table>"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run the creator-sync local web console.")
    parser.add_argument("--config", default="config/config.json")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8714)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    server = ThreadingHTTPServer((args.host, args.port), make_handler(Path(args.config)))
    print(f"creator-sync web console listening on http://{args.host}:{args.port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
