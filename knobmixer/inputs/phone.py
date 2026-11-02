"""Phone remote: the knobs as a web page on your home network.

Only knob state, volume and mute are exposed. Settings stay on the PC-only server,
because they can load arbitrary Python modules.

It's served over https (see lan_https.py), so the page can keep the phone's screen awake.
Plain http on the same port shows a one-time page for trusting this PC's certificate.

Windows Firewall blocks the port for other devices until it's allowed once:
    tools/allow-phone-firewall.ps1   (run as admin)
"""
import json
import os
import threading
from http.server import BaseHTTPRequestHandler
from urllib.parse import parse_qs, urlparse

from .. import lan_https
from .base import InputSource

WEB = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "web")
ACTIONS = ("up", "down", "set", "mute")


class _Server(lan_https.DualProtocolServer):
    allow_reuse_address = False  # fail loudly if the port is taken, instead of sharing it


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
            context = lan_https.ssl_context()
        except Exception as e:
            self._state = f"couldn't set up the https certificate ({e})"
            return
        try:
            self._server = _Server(("0.0.0.0", port), self._handler(), context)
        except OSError as e:
            self._state = f"couldn't open port {port} ({e.strerror or e})"
            return
        self._url = f"https://{lan_https.lan_ip()}:{port}/"
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

    @property
    def shown(self):
        """Ids of the knobs ticked "Show on phone" in Settings."""
        return {k["id"] for k in self.knobs if k.get("phone", True)}

    def state(self):
        st = self.get_state()
        return {**st, "knobs": [k for k in st["knobs"] if k["id"] in self.shown]}

    def _handler(self):
        source = self

        class Handler(BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"  # keep connections open: no TLS handshake per poll
            timeout = 30                   # ...but close idle ones

            def log_message(self, *args):
                pass

            def _plain_http(self):
                """Plain http only offers the certificate setup; the mixer itself is https-only."""
                if lan_https.is_secure(self):
                    return False
                if self.command == "GET" and urlparse(self.path).path == "/ca.cer":
                    self._send(200, lan_https.ca_der(), "application/x-x509-ca-cert")
                elif self.command == "GET":
                    self._send(200, lan_https.setup_page("Knob Mixer").encode(), "text/html; charset=utf-8")
                else:
                    self._send(403, {"error": "use https"})
                return True

            def _send(self, code, body, ctype="application/json"):
                data = body if isinstance(body, bytes) else json.dumps(body).encode()
                self.send_response(code)
                self.send_header("Content-Type", ctype)
                self.send_header("Content-Length", str(len(data)))
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
                self.wfile.write(data)

            def do_GET(self):
                if self._plain_http():
                    return
                path = urlparse(self.path).path
                if path in ("/", "/index.html"):
                    with open(os.path.join(WEB, "phone.html"), "rb") as f:
                        return self._send(200, f.read(), "text/html; charset=utf-8")
                if path == "/favicon.ico":
                    with open(os.path.join(WEB, "icon.ico"), "rb") as f:
                        return self._send(200, f.read(), "image/x-icon")
                if path == "/api/state":
                    return self._send(200, source.state())
                self._send(404, {})

            def do_POST(self):
                if self._plain_http():
                    return
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
                if q.get("id") not in source.shown:
                    return self._send(404, {})
                source.dispatch(q["id"], q["action"], amount, source="phone")
                self._send(200, source.state())

        return Handler
