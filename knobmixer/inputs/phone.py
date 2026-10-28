"""Phone remote: the knobs as a web page on your home network.

Only knob state, volume and mute are exposed. Settings stay on the PC-only server,
because they can load arbitrary Python modules.

Windows Firewall blocks the port for other devices until it's allowed once:
    tools/allow-phone-firewall.ps1   (run as admin)
"""
import json
import os
import socket
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

from .base import InputSource

WEB = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "web")
ACTIONS = ("up", "down", "set", "mute")


def lan_ip():
    """This PC's address on the local network (no packet is actually sent)."""
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
        try:
            s.connect(("192.0.2.1", 9))
            return s.getsockname()[0]
        except OSError:
            return "127.0.0.1"


class _Server(ThreadingHTTPServer):
    allow_reuse_address = False  # fail loudly if the port is taken, instead of sharing it
    daemon_threads = True


class PhoneInput(InputSource):
    label = "Phone remote"

    def __init__(self, knobs, options, dispatch):
        super().__init__(knobs, options, dispatch)
        self._server = None
        self._state = "starting"
        self._url = ""

    def start(self):
        port = int(self.options.get("port", 8771))
        try:
            self._server = _Server(("0.0.0.0", port), self._handler())
        except OSError as e:
            self._state = f"couldn't open port {port} ({e.strerror or e})"
            return
        self._url = f"http://{lan_ip()}:{port}/"
        self._state = f"open {self._url} on your phone"
        threading.Thread(target=self._server.serve_forever, daemon=True, name="phone").start()

    def stop(self):
        if self._server:
            self._server.shutdown()
            self._server.server_close()
            self._server = None
        self._state = "stopped"

    def status(self):
        return {"state": self._state, "url": self._url if self._server else ""}

    def _handler(self):
        source = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def _send(self, code, body, ctype="application/json"):
                data = body if isinstance(body, bytes) else json.dumps(body).encode()
                self.send_response(code)
                self.send_header("Content-Type", ctype)
                self.send_header("Content-Length", str(len(data)))
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
                self.wfile.write(data)

            def do_GET(self):
                path = urlparse(self.path).path
                if path in ("/", "/index.html"):
                    with open(os.path.join(WEB, "phone.html"), "rb") as f:
                        return self._send(200, f.read(), "text/html; charset=utf-8")
                if path == "/favicon.ico":
                    with open(os.path.join(WEB, "icon.ico"), "rb") as f:
                        return self._send(200, f.read(), "image/x-icon")
                if path == "/api/state":
                    return self._send(200, source.get_state())
                self._send(404, {})

            def do_POST(self):
                url = urlparse(self.path)
                q = {k: v[0] for k, v in parse_qs(url.query).items()}
                if url.path != "/api/knob" or q.get("action") not in ACTIONS:
                    return self._send(404, {})
                amount = None
                if q["action"] == "set":
                    try:
                        amount = min(1.0, max(0.0, float(q.get("amount", ""))))
                    except ValueError:
                        return self._send(400, {"error": "amount must be a number"})
                source.dispatch(q.get("id"), q["action"], amount, source="phone")
                self._send(200, source.get_state())

        return Handler
