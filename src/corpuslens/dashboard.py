"""Loopback-only dashboard backed by the same streaming pipeline as the CLI."""

from __future__ import annotations

import json
import secrets
import shutil
import threading
from datetime import datetime, timezone
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from importlib.resources import files
from pathlib import Path
from urllib.parse import urlsplit

from .cli import _policy, build_parser
from .pipeline import run_pipeline
from .profiles import PROFILES
from .readers import infer_format


INTEGER_SETTINGS = ("min_characters", "max_characters", "sample_limit")
FLOAT_SETTINGS = ("min_script_ratio", "max_symbol_ratio", "near_duplicate_threshold")
DOWNLOADABLE_OUTPUTS = {"json_report", "resolved_policy", "cleaned_corpus", "rejected_records"}


class DashboardState:
    """Keep one active job and its last report; guard access from HTTP threads."""

    def __init__(self, output_root: Path):
        self.output_root = output_root.resolve()
        self.lock = threading.Lock()
        self.job: dict[str, object] = {"status": "idle"}

    def snapshot(self) -> dict[str, object]:
        """Return the current small, JSON-ready job state."""
        with self.lock:
            return dict(self.job)

    def start(self, payload: dict[str, object]) -> dict[str, object]:
        """Validate a browser request and start a streaming job in the background."""
        input_value = payload.get("input_path")
        if not isinstance(input_value, str) or not input_value.strip():
            raise ValueError("Enter the path to a TXT, JSONL, or gzip corpus.")
        input_path = Path(input_value.strip()).expanduser().resolve()
        if not input_path.is_file():
            raise ValueError(f"Input file does not exist: {input_path}")

        mode = payload.get("mode", "preview")
        if not isinstance(mode, str) or mode not in {"preview", "analyze", "clean"}:
            raise ValueError("Choose preview, analyze, or clean.")
        arguments = build_parser().parse_args(["analyze", str(input_path)])
        profile = payload.get("profile", "generic")
        if not isinstance(profile, str):
            raise ValueError("Profile must be a language key.")
        arguments.profile = profile
        for name in INTEGER_SETTINGS:
            value = payload.get(name)
            if value is not None and value != "":
                if isinstance(value, bool) or not isinstance(value, (int, str)):
                    raise ValueError(f"{name} must be an integer.")
                try:
                    arguments.__dict__[name] = int(value)
                except ValueError as error:
                    raise ValueError(f"{name} must be an integer.") from error
        for name in FLOAT_SETTINGS:
            value = payload.get(name)
            if value is not None and value != "":
                if isinstance(value, bool) or not isinstance(value, (int, float, str)):
                    raise ValueError(f"{name} must be a number.")
                try:
                    arguments.__dict__[name] = float(value)
                except ValueError as error:
                    raise ValueError(f"{name} must be a number.") from error
        action = payload.get("low_script_action", "flag")
        if not isinstance(action, str) or action not in {"flag", "reject"}:
            raise ValueError("Script decision must be flag or reject.")
        arguments.low_script_action = action
        for name in ("exact_dedup", "near_dedup", "mask_pii"):
            if name in payload and not isinstance(payload[name], bool):
                raise ValueError(f"{name} must be true or false.")
        arguments.no_dedup = not payload.get("exact_dedup", True)
        arguments.near_dedup = payload.get("near_dedup", False)
        arguments.no_mask_pii = not payload.get("mask_pii", True)
        policy, language_profile = _policy(arguments, {})

        limit: int | None = None
        if mode == "preview":
            value = payload.get("max_records", 100_000)
            if isinstance(value, bool) or not isinstance(value, (int, str)):
                raise ValueError("Preview size must be a positive integer.")
            try:
                limit = int(value)
            except ValueError as error:
                raise ValueError("Preview size must be a positive integer.") from error
            if limit < 1:
                raise ValueError("Preview size must be a positive integer.")
        text_field = payload.get("text_field", "text")
        if not isinstance(text_field, str) or not text_field.strip():
            raise ValueError("JSONL text field cannot be empty.")
        format_name = payload.get("format", "auto")
        if not isinstance(format_name, str) or format_name not in {"auto", "txt", "jsonl"}:
            raise ValueError("Input format must be auto, txt, or jsonl.")
        input_format = infer_format(input_path, format_name)
        work_value = payload.get("work_dir")
        if work_value is not None and not isinstance(work_value, str):
            raise ValueError("Temporary index directory must be a path.")
        work_dir = Path(work_value).expanduser().resolve() if work_value else None
        if work_dir is not None and work_dir.exists() and not work_dir.is_dir():
            raise ValueError("Temporary index directory must be a directory.")

        job_id = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S") + "-" + secrets.token_hex(4)
        output_dir = self.output_root / job_id
        initial = {
            "status": "running",
            "mode": mode,
            "job_id": job_id,
            "input_path": str(input_path),
            "output_dir": str(output_dir),
            "records_read": 0,
            "records_kept": 0,
            "records_rejected": 0,
            "bytes_read": 0,
            "source_file_bytes": input_path.stat().st_size,
            "input_compression": "gzip" if input_path.suffix.casefold() == ".gz" else "none",
        }
        with self.lock:
            if self.job.get("status") == "running":
                raise ValueError("A corpus job is already running. Wait for it to finish.")
            self.job = initial

        worker = threading.Thread(
            target=self._run,
            args=(input_path, output_dir, mode, input_format, text_field.strip(), language_profile, policy, limit, work_dir),
            name=f"corpuslens-{job_id}",
            daemon=True,
        )
        worker.start()
        return dict(initial)

    def _run(self, input_path, output_dir, mode, input_format, text_field, profile, policy, limit, work_dir) -> None:
        """Execute the job and publish either its report or its error."""

        def progress(result) -> None:
            with self.lock:
                self.job.update({
                    "records_read": result.records_read,
                    "records_kept": result.records_kept,
                    "records_rejected": result.records_rejected,
                    "bytes_read": result.bytes_read,
                })

        try:
            result = run_pipeline(
                input_path=input_path,
                output_dir=output_dir,
                command="analyze" if mode == "preview" else mode,
                input_format=input_format,
                text_field=text_field,
                profile=profile,
                policy=policy,
                max_records=limit,
                work_dir=work_dir,
                progress_callback=progress,
            )
        except Exception as error:
            with self.lock:
                self.job.update({"status": "error", "error": str(error)})
            return
        with self.lock:
            self.job.update({
                "status": "complete",
                "records_read": result.records_read,
                "records_kept": result.records_kept,
                "records_rejected": result.records_rejected,
                "bytes_read": result.bytes_read,
                "report": result.to_dict(),
            })


class DashboardHandler(BaseHTTPRequestHandler):
    """Serve the dashboard and narrow JSON endpoints on localhost only."""

    server: ThreadingHTTPServer

    def log_message(self, format: str, *args: object) -> None:
        """Keep one-second status polling from flooding the user's terminal."""
        return

    def _headers(self, status: HTTPStatus, content_type: str, length: int) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(length))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.end_headers()

    def _json(self, value: object, status: HTTPStatus = HTTPStatus.OK) -> None:
        body = json.dumps(value, ensure_ascii=False).encode("utf-8")
        self._headers(status, "application/json; charset=utf-8", len(body))
        self.wfile.write(body)

    def _allowed_host(self) -> bool:
        """Reject rebinding through a foreign Host header."""
        host = self.headers.get("Host", "")
        try:
            parsed = urlsplit("//" + host)
            return parsed.hostname in {"127.0.0.1", "localhost"} and parsed.port == self.server.server_port
        except ValueError:
            return False

    def do_GET(self) -> None:
        if not self._allowed_host():
            self._json({"error": "Dashboard is available on localhost only."}, HTTPStatus.FORBIDDEN)
            return
        path = urlsplit(self.path).path
        if path == "/":
            body = files("corpuslens").joinpath("dashboard.html").read_bytes()
            self._headers(HTTPStatus.OK, "text/html; charset=utf-8", len(body))
            self.wfile.write(body)
        elif path == "/api/meta":
            self._json({"profiles": [{"key": key, "name": profile.name} for key, profile in PROFILES.items()]})
        elif path == "/api/status":
            self._json(self.server.dashboard_state.snapshot())
        elif path == "/report":
            state = self.server.dashboard_state.snapshot()
            if state.get("status") != "complete":
                self._json({"error": "No completed report is available."}, HTTPStatus.NOT_FOUND)
                return
            report_path = Path(state["output_dir"]) / "report.html"
            try:
                body = report_path.read_bytes()
            except OSError:
                self._json({"error": "The report file is no longer available."}, HTTPStatus.NOT_FOUND)
                return
            self._headers(HTTPStatus.OK, "text/html; charset=utf-8", len(body))
            self.wfile.write(body)
        elif path.startswith("/download/"):
            self._download(path.removeprefix("/download/"))
        else:
            self._json({"error": "Not found."}, HTTPStatus.NOT_FOUND)

    def _download(self, kind: str) -> None:
        """Stream only files produced by the most recently completed job."""
        state = self.server.dashboard_state.snapshot()
        if state.get("status") != "complete" or kind not in DOWNLOADABLE_OUTPUTS:
            self._json({"error": "That completed output is not available."}, HTTPStatus.NOT_FOUND)
            return
        output_path = state["report"]["outputs"].get(kind)
        if output_path is None:
            self._json({"error": "That output was not created by this run."}, HTTPStatus.NOT_FOUND)
            return
        file_path = Path(output_path)
        try:
            handle = file_path.open("rb")
        except OSError:
            self._json({"error": "The output file is no longer available."}, HTTPStatus.NOT_FOUND)
            return
        with handle:
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", "application/octet-stream")
            self.send_header("Content-Disposition", f'attachment; filename="{file_path.name}"')
            self.send_header("Content-Length", str(file_path.stat().st_size))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.end_headers()
            try:
                shutil.copyfileobj(handle, self.wfile, length=1024 * 1024)
            except (BrokenPipeError, ConnectionResetError):
                # A user may cancel a large browser download midway through.
                pass

    def do_POST(self) -> None:
        if not self._allowed_host():
            self._json({"error": "Dashboard is available on localhost only."}, HTTPStatus.FORBIDDEN)
            return
        origin = self.headers.get("Origin")
        if origin:
            try:
                parsed = urlsplit(origin)
                allowed_origin = parsed.scheme == "http" and parsed.hostname in {"127.0.0.1", "localhost"} and parsed.port == self.server.server_port
            except ValueError:
                allowed_origin = False
            if not allowed_origin:
                self._json({"error": "This request must come from the local dashboard."}, HTTPStatus.FORBIDDEN)
                return
        if urlsplit(self.path).path != "/api/start":
            self._json({"error": "Not found."}, HTTPStatus.NOT_FOUND)
            return
        if self.headers.get("Content-Type", "").split(";")[0].strip().lower() != "application/json":
            self._json({"error": "Send application/json."}, HTTPStatus.UNSUPPORTED_MEDIA_TYPE)
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            length = 0
        if not 0 < length <= 65_536:
            self._json({"error": "Request body must be 1–65,536 bytes."}, HTTPStatus.REQUEST_ENTITY_TOO_LARGE)
            return
        try:
            payload = json.loads(self.rfile.read(length))
            if not isinstance(payload, dict):
                raise ValueError("Request body must be a JSON object.")
            job = self.server.dashboard_state.start(payload)
        except (UnicodeError, json.JSONDecodeError, ValueError, OSError) as error:
            self._json({"error": str(error)}, HTTPStatus.BAD_REQUEST)
            return
        self._json(job, HTTPStatus.ACCEPTED)


def create_dashboard_server(port: int, output_root: Path) -> ThreadingHTTPServer:
    """Construct a loopback server; exposed separately for integration tests."""
    server = ThreadingHTTPServer(("127.0.0.1", port), DashboardHandler)
    server.dashboard_state = DashboardState(output_root)
    return server


def serve_dashboard(port: int, output_root: Path) -> None:
    """Start the local server until the user presses Ctrl+C."""
    server = create_dashboard_server(port, output_root)
    print(f"CorpusLens dashboard: http://127.0.0.1:{server.server_port}/")
    print("Press Ctrl+C to stop. Keep this process open while a corpus job runs.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping dashboard.")
    finally:
        server.server_close()
