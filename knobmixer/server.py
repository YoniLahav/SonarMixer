"""Local web UI + JSON API (127.0.0.1 only)."""
import json
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

from . import config, inputs, keys, providers
from .providers import ProviderError

WEB = os.path.join(os.path.dirname(os.path.abspath(__file__)), "web")
PAGES = {"/": "index.html", "/settings": "settings.html"}


class Server(ThreadingHTTPServer):
    # On Windows SO_REUSEADDR lets a second instance bind the same port;
    # we rely on the bind failing to detect that we're already running.
    allow_reuse_address = False
    daemon_threads = True


def make_server(port, mixer, load_errors=()):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def _send(self, code, body, ctype="application/json"):
            data = body if isinstance(body, bytes) else (body if isinstance(body, str) else json.dumps(body)).encode()
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(data)

        def do_GET(self):
            url = urlparse(self.path)
            q = {k: v[0] for k, v in parse_qs(url.query).items()}
            if url.path in PAGES:
                with open(os.path.join(WEB, PAGES[url.path]), "rb") as f:
                    return self._send(200, f.read(), "text/html; charset=utf-8")
            if url.path == "/favicon.ico":
                with open(os.path.join(WEB, "icon.ico"), "rb") as f:
                    return self._send(200, f.read(), "image/x-icon")
            if url.path == "/api/state":
                return self._send(200, mixer.snapshot())
            if url.path == "/api/config":
                return self._send(200, {"config": mixer.cfg, "path": config.CONFIG_PATH,
                                        "loadErrors": list(load_errors)})
            if url.path == "/api/meta":
                return self._send(200, {"providers": providers.available(), "inputs": inputs.available(),
                                        "keys": list(keys.VK), "safeKeys": sorted(keys.SAFE_KEYS)})
            if url.path == "/api/channels":
                try:
                    opts = json.loads(q.get("options") or "{}")
                    return self._send(200, {"channels": mixer.list_channels(q.get("type", ""), opts)})
                except (ProviderError, ValueError) as e:
                    return self._send(200, {"channels": [], "error": str(e)})
            self._send(404, {})

        def do_POST(self):
            url = urlparse(self.path)
            q = {k: v[0] for k, v in parse_qs(url.query).items()}
            if url.path == "/api/knob":
                amount = float(q["amount"]) if "amount" in q else None
                mixer.dispatch(q.get("id"), q.get("action"), amount, source="ui")
                return self._send(200, mixer.snapshot())
            if url.path == "/api/config":
                length = int(self.headers.get("Content-Length") or 0)
                try:
                    raw = json.loads(self.rfile.read(length) or b"{}")
                except ValueError:
                    return self._send(400, {"errors": ["invalid JSON"]})
                cfg, errors = config.validate(raw)
                if errors:
                    return self._send(400, {"errors": errors})
                config.save(cfg)
                mixer.apply(cfg)
                return self._send(200, {"config": cfg, "state": mixer.snapshot()})
            if url.path == "/api/navigate":
                mixer.navigate = q.get("path", "/")
                return self._send(200, {})
            if url.path == "/api/inputs/pause":
                mixer.pause_inputs()
                return self._send(200, {})
            if url.path == "/api/inputs/resume":
                mixer.resume_inputs()
                return self._send(200, {})
            self._send(404, {})

    return Server(("127.0.0.1", port), Handler)
