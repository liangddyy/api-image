from __future__ import annotations

import base64
import json
import os
import subprocess
import sys
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "generate_image.py"
PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+jRZkAAAAASUVORK5CYII="
)
TEST_KEY = "test-local-provider-secret"


class CliTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)

    def write_config(self, base_url):
        (self.root / "config.toml").write_text(
            'model_provider = "custom"\n'
            '[model_providers.custom]\n'
            f'base_url = "{base_url}"\n'
            f'experimental_bearer_token = "{TEST_KEY}"\n',
            encoding="utf-8",
        )

    def run_cli(self, *arguments):
        environment = os.environ.copy()
        environment.pop("OPENAI_API_KEY", None)
        environment["PYTHONUTF8"] = "1"
        return subprocess.run(
            [sys.executable, "-B", str(SCRIPT), "--codex-home", str(self.root), *arguments],
            cwd=self.root,
            env=environment,
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=15,
        )

    def test_check_config_needs_no_prompt_or_network_and_reveals_no_secret(self):
        self.write_config("https://does-not-exist.invalid/v1")
        before = {p.name: p.read_bytes() for p in self.root.iterdir()}
        result = self.run_cli("--check-config")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("experimental_bearer_token", result.stdout)
        self.assertIn("No request sent", result.stdout)
        self.assertNotIn(TEST_KEY, result.stdout + result.stderr)
        self.assertEqual(before, {p.name: p.read_bytes() for p in self.root.iterdir()})

    def test_check_config_missing_credentials_reports_failure(self):
        self.write_config("https://does-not-exist.invalid/v1")
        path = self.root / "config.toml"
        path.write_text(
            path.read_text(encoding="utf-8").replace(
                f'experimental_bearer_token = "{TEST_KEY}"\n', ""
            ),
            encoding="utf-8",
        )
        result = self.run_cli("--check-config")
        self.assertEqual(result.returncode, 1, result.stderr)
        self.assertIn("No image API key", result.stderr)
        self.assertNotIn("Traceback", result.stderr)

    def test_generation_and_edit_use_provider_token_end_to_end(self):
        requests = []

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self):
                body = self.rfile.read(int(self.headers["Content-Length"]))
                requests.append((self.path, self.headers.get("Authorization"), body))
                response = json.dumps({"data": [{"b64_json": base64.b64encode(PNG).decode()}]}).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(response)))
                self.end_headers()
                self.wfile.write(response)

            def log_message(self, format, *args):
                pass

        with HTTPServer(("127.0.0.1", 0), Handler) as server:
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                self.write_config(f"http://127.0.0.1:{server.server_port}/v1")
                source = self.root / "source.png"
                source.write_bytes(PNG)
                for mode, extra, endpoint in (
                    ("generate", [], "/v1/images/generations"),
                    ("edit", ["--image", str(source), "--image-role", "edit target"], "/v1/images/edits"),
                ):
                    with self.subTest(mode=mode):
                        output = self.root / f"{mode}.png"
                        result = self.run_cli(
                            "--prompt", "A simple blue circle", "--size", "1024x1024",
                            "--quality", "low", "--timeout", "10", "--out", str(output), *extra,
                        )
                        self.assertEqual(result.returncode, 0, result.stderr)
                        self.assertEqual(output.read_bytes(), PNG)
                        self.assertEqual(requests[-1][0], endpoint)
                        self.assertEqual(requests[-1][1], f"Bearer {TEST_KEY}")
                        self.assertNotIn(TEST_KEY, result.stdout + result.stderr)
                self.assertEqual(json.loads(requests[0][2])["prompt"], "A simple blue circle")
                self.assertIn(b'name="image[]"', requests[1][2])
            finally:
                server.shutdown()
                thread.join(timeout=5)


if __name__ == "__main__":
    unittest.main()
