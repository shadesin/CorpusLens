"""Exercise the local HTTP workflow rather than only its internal helpers."""

import json
import tempfile
import threading
import time
import unittest
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from corpuslens.dashboard import create_dashboard_server


class DashboardTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.server = create_dashboard_server(0, self.root / "runs")
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.addCleanup(self.server.server_close)
        self.addCleanup(self.server.shutdown)
        self.base = f"http://127.0.0.1:{self.server.server_port}"

    def request_json(self, path, payload=None):
        body = None if payload is None else json.dumps(payload).encode("utf-8")
        request = Request(
            self.base + path,
            data=body,
            headers={"Content-Type": "application/json"} if body is not None else {},
        )
        with urlopen(request, timeout=5) as response:
            return json.load(response)

    def wait_for_completion(self):
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            state = self.request_json("/api/status")
            if state["status"] != "running":
                return state
            time.sleep(0.02)
        self.fail("Dashboard job did not finish within five seconds.")

    def test_preview_then_clean_uses_the_pipeline_and_exposes_reports(self):
        source = self.root / "corpus.txt"
        source.write_text("one useful record here\none useful record here\nsecond useful record here\n", encoding="utf-8")
        with urlopen(self.base, timeout=5) as response:
            self.assertIn("Know what your filter removes", response.read().decode("utf-8"))
        profiles = self.request_json("/api/meta")["profiles"]
        self.assertTrue(any(item["key"] == "bn" for item in profiles))

        started = self.request_json("/api/start", {"input_path": str(source), "mode": "preview", "max_records": 2})
        self.assertEqual(started["status"], "running")
        preview = self.wait_for_completion()
        self.assertEqual(preview["status"], "complete")
        self.assertEqual(preview["report"]["records_read"], 2)
        self.assertEqual(preview["report"]["findings_by_code"]["exact_duplicate"], 1)
        self.assertNotIn("cleaned_corpus", preview["report"]["outputs"])

        self.request_json("/api/start", {"input_path": str(source), "mode": "clean", "exact_dedup": True})
        cleaned = self.wait_for_completion()
        self.assertEqual(cleaned["status"], "complete")
        self.assertEqual(cleaned["report"]["records_kept"], 2)
        output_path = Path(cleaned["report"]["outputs"]["cleaned_corpus"])
        self.assertEqual(output_path.read_text(encoding="utf-8").splitlines(), ["one useful record here", "second useful record here"])
        with urlopen(self.base + "/report", timeout=5) as response:
            self.assertIn("CorpusLens report", response.read().decode("utf-8"))
        with urlopen(self.base + "/download/cleaned_corpus", timeout=5) as response:
            self.assertEqual(response.read().decode("utf-8").splitlines(), ["one useful record here", "second useful record here"])

    def test_rejects_bad_policy_and_foreign_origin(self):
        source = self.root / "corpus.txt"
        source.write_text("useful record\n", encoding="utf-8")
        with self.assertRaises(HTTPError) as invalid:
            self.request_json("/api/start", {"input_path": str(source), "min_script_ratio": 2})
        self.assertEqual(invalid.exception.code, 400)
        request = Request(
            self.base + "/api/start",
            data=json.dumps({"input_path": str(source)}).encode("utf-8"),
            headers={"Content-Type": "application/json", "Origin": "https://elsewhere.example"},
        )
        with self.assertRaises(HTTPError) as foreign:
            urlopen(request, timeout=5)
        self.assertEqual(foreign.exception.code, 403)


if __name__ == "__main__":
    unittest.main()
