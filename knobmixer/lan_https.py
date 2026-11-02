"""HTTPS for pages served to phones on the home network.

iPhones only allow some features (like keeping the screen awake) on https pages, and https
needs a certificate the phone trusts. This keeps a small private certificate authority in
%APPDATA%\\LanHttps, shared by every app that uses this module, so the phone only has to
trust it once. The CA is name-constrained to private network addresses and .local names,
so even if its key leaked it couldn't be used to impersonate real websites.

The server certificate is re-issued automatically when it's missing, about to expire, or
doesn't cover this PC's current LAN address (e.g. after the router hands out a new IP).

`DualProtocolServer` speaks http and https on the same port: https serves the app, and
plain http should serve `setup_page()`, which offers the certificate and forwards to https
as soon as the phone trusts it.

This file is shared verbatim between the soundboard and Knob Mixer projects.
"""
import contextlib
import datetime
import ipaddress
import os
import socket
import ssl
import time
from http.server import ThreadingHTTPServer

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID

DIR = os.path.join(os.environ.get("APPDATA") or os.path.expanduser("~"), "LanHttps")
CA_KEY, CA_CERT = os.path.join(DIR, "ca.key"), os.path.join(DIR, "ca.crt")
SERVER_KEY, SERVER_CERT = os.path.join(DIR, "server.key"), os.path.join(DIR, "server.crt")
CA_NAME = "Home LAN apps"
PRIVATE_NETS = ["10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16", "127.0.0.0/8"]
SERVER_DAYS = 397  # Apple rejects TLS server certificates valid for longer than this
RENEW_BEFORE = datetime.timedelta(days=30)


def lan_ip():
    """This PC's address on the local network (no packet is actually sent)."""
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
        try:
            s.connect(("192.0.2.1", 9))
            return s.getsockname()[0]
        except OSError:
            return "127.0.0.1"


@contextlib.contextmanager
def _lock():
    """Both apps start at login; make sure only one of them creates certificates."""
    os.makedirs(DIR, exist_ok=True)
    path = os.path.join(DIR, ".lock")
    deadline = time.monotonic() + 15
    while True:
        try:
            fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            break
        except FileExistsError:
            try:
                if time.time() - os.path.getmtime(path) > 60:
                    os.remove(path)  # left behind by a crash
                    continue
            except OSError:
                pass
            if time.monotonic() > deadline:
                raise TimeoutError(f"couldn't lock {path}")
            time.sleep(0.1)
    try:
        yield
    finally:
        os.close(fd)
        os.remove(path)


def _write(path, data):
    tmp = path + ".tmp"
    with open(tmp, "wb") as f:
        f.write(data)
    os.replace(tmp, path)


def _key_pem(key):
    return key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                             serialization.NoEncryption())


def _load_ca():
    if os.path.exists(CA_KEY) and os.path.exists(CA_CERT):
        with open(CA_KEY, "rb") as k, open(CA_CERT, "rb") as c:
            return serialization.load_pem_private_key(k.read(), None), x509.load_pem_x509_certificate(c.read())
    key = ec.generate_private_key(ec.SECP256R1())
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, f"{CA_NAME} ({socket.gethostname()})")])
    now = datetime.datetime.now(datetime.timezone.utc)
    cert = (
        x509.CertificateBuilder()
        .subject_name(name).issuer_name(name)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - datetime.timedelta(days=1))
        .not_valid_after(now + datetime.timedelta(days=3650))
        .add_extension(x509.BasicConstraints(ca=True, path_length=0), critical=True)
        .add_extension(x509.KeyUsage(digital_signature=True, key_cert_sign=True, crl_sign=True,
                                     content_commitment=False, key_encipherment=False, data_encipherment=False,
                                     key_agreement=False, encipher_only=False, decipher_only=False), critical=True)
        # Only valid for home-network addresses and local names, never for real websites
        .add_extension(x509.NameConstraints(
            permitted_subtrees=[x509.IPAddress(ipaddress.ip_network(n)) for n in PRIVATE_NETS]
                               + [x509.DNSName("local"), x509.DNSName("localhost")],
            excluded_subtrees=None), critical=True)
        .add_extension(x509.SubjectKeyIdentifier.from_public_key(key.public_key()), critical=False)
        .sign(key, hashes.SHA256())
    )
    _write(CA_KEY, _key_pem(key))
    _write(CA_CERT, cert.public_bytes(serialization.Encoding.PEM))
    return key, cert


def _server_cert_ok(ca_cert, ip):
    if not (os.path.exists(SERVER_KEY) and os.path.exists(SERVER_CERT)):
        return False
    with open(SERVER_CERT, "rb") as f:
        cert = x509.load_pem_x509_certificate(f.read())
    try:
        cert.verify_directly_issued_by(ca_cert)
        ips = cert.extensions.get_extension_for_class(x509.SubjectAlternativeName).value.get_values_for_type(x509.IPAddress)
    except Exception:
        return False
    fresh = cert.not_valid_after_utc - datetime.datetime.now(datetime.timezone.utc) > RENEW_BEFORE
    return fresh and ipaddress.ip_address(ip) in ips


def _issue_server_cert(ca_key, ca_cert, ip):
    key = ec.generate_private_key(ec.SECP256R1())
    now = datetime.datetime.now(datetime.timezone.utc)
    host = socket.gethostname().lower()
    names = [x509.IPAddress(ipaddress.ip_address(a)) for a in dict.fromkeys([ip, "127.0.0.1"])]
    names += [x509.DNSName("localhost"), x509.DNSName(f"{host}.local")]
    cert = (
        x509.CertificateBuilder()
        .subject_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "localhost")]))
        .issuer_name(ca_cert.subject)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - datetime.timedelta(days=1))
        .not_valid_after(now + datetime.timedelta(days=SERVER_DAYS))
        .add_extension(x509.SubjectAlternativeName(names), critical=False)
        .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
        .add_extension(x509.KeyUsage(digital_signature=True, key_cert_sign=False, crl_sign=False,
                                     content_commitment=False, key_encipherment=False, data_encipherment=False,
                                     key_agreement=False, encipher_only=False, decipher_only=False), critical=True)
        .add_extension(x509.ExtendedKeyUsage([ExtendedKeyUsageOID.SERVER_AUTH]), critical=False)
        .add_extension(x509.SubjectKeyIdentifier.from_public_key(key.public_key()), critical=False)
        .add_extension(x509.AuthorityKeyIdentifier.from_issuer_public_key(ca_cert.public_key()), critical=False)
        .sign(ca_key, hashes.SHA256())
    )
    _write(SERVER_KEY, _key_pem(key))
    _write(SERVER_CERT, cert.public_bytes(serialization.Encoding.PEM))


def ssl_context():
    """Make sure the CA and a server certificate for this PC exist, and return a server context."""
    with _lock():
        ca_key, ca_cert = _load_ca()
        ip = lan_ip()
        if not _server_cert_ok(ca_cert, ip):
            _issue_server_cert(ca_key, ca_cert, ip)
    ctx = ssl.create_default_context(ssl.Purpose.CLIENT_AUTH)
    ctx.load_cert_chain(SERVER_CERT, SERVER_KEY)
    return ctx


def ca_der():
    """The CA certificate in the form iOS installs as a profile (serve as application/x-x509-ca-cert)."""
    with open(CA_CERT, "rb") as f:
        return x509.load_pem_x509_certificate(f.read()).public_bytes(serialization.Encoding.DER)


def is_secure(handler):
    return isinstance(handler.connection, ssl.SSLSocket)


class DualProtocolServer(ThreadingHTTPServer):
    """Serves https and plain http on one port, telling them apart by the first byte."""
    daemon_threads = True

    def __init__(self, address, handler, context):
        self.ssl_context = context
        super().__init__(address, handler)

    def finish_request(self, request, client_address):
        conn = request
        try:
            request.settimeout(10)
            if request.recv(1, socket.MSG_PEEK) == b"\x16":  # TLS handshake record
                conn = self.ssl_context.wrap_socket(request, server_side=True)
            conn.settimeout(None)
        except (OSError, ssl.SSLError):
            return  # client gave up, or doesn't trust the certificate yet
        try:
            self.RequestHandlerClass(conn, client_address, self)
        finally:
            if conn is not request:
                with contextlib.suppress(OSError):
                    conn.close()


def setup_page(app_name):
    """Shown on plain http: install the certificate once, then it forwards to https by itself."""
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<meta name="theme-color" content="#0b0c10">
<title>{app_name}: secure connection setup</title>
<style>
  :root {{ --bg: #0b0c10; --card: #16181f; --line: #262a33; --text: #eef0f4; --muted: #8b91a0; --accent: #5b8cff; --ok: #3ecf8e; }}
  * {{ box-sizing: border-box; }}
  body {{ margin: 0; background: var(--bg); color: var(--text); font: 16px/1.45 -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
         padding: calc(20px + env(safe-area-inset-top)) 16px calc(24px + env(safe-area-inset-bottom)); }}
  main {{ max-width: 520px; margin: 0 auto; }}
  h1 {{ font-size: 21px; margin: 0 0 6px; }}
  p {{ margin: 0 0 14px; color: var(--muted); }}
  #check {{ display: flex; align-items: center; gap: 10px; padding: 12px 14px; border-radius: 12px;
           background: var(--card); border: 1px solid var(--line); margin: 16px 0 20px; font-size: 15px; }}
  #check::before {{ content: ""; width: 10px; height: 10px; border-radius: 50%; background: var(--muted); flex: none; }}
  #check.ok::before {{ background: var(--ok); }}
  ol {{ padding: 0; margin: 0; list-style: none; counter-reset: step; display: grid; gap: 12px; }}
  li {{ counter-increment: step; background: var(--card); border: 1px solid var(--line); border-radius: 14px;
       padding: 14px 14px 14px 52px; position: relative; }}
  li::before {{ content: counter(step); position: absolute; left: 14px; top: 13px; width: 26px; height: 26px;
               border-radius: 50%; background: var(--accent); color: #fff; font-weight: 700; font-size: 14px;
               display: grid; place-items: center; }}
  li b {{ color: var(--text); }}
  li span {{ color: var(--muted); font-size: 15px; }}
  .btn {{ display: block; margin-top: 10px; padding: 12px; border-radius: 12px; background: var(--accent);
         color: #fff; font-weight: 700; text-align: center; text-decoration: none; }}
</style>
</head>
<body>
<main>
  <h1>{app_name}</h1>
  <p>This page runs over a secure connection now, so it can keep your screen awake. Your phone needs to trust this PC once.
     It's the same certificate for every app on this PC, so if you've done it before, just wait a moment.</p>
  <div id="check">Checking whether your phone already trusts this PC…</div>
  <ol>
    <li><b>Download the certificate</b><br><span>Tap below, then tap <b>Allow</b>.</span>
      <a class="btn" href="/ca.cer">Download certificate</a></li>
    <li><b>Install it</b><br><span>Open Settings → <b>Profile Downloaded</b> (near the top) → Install.</span></li>
    <li><b>Trust it</b><br><span>Settings → General → About → <b>Certificate Trust Settings</b> → turn on
      <b>{CA_NAME}</b>.</span></li>
    <li><b>Come back here</b><br><span>This page switches to the secure version by itself. If you added it to your
      Home Screen before, add it again from the secure page.</span></li>
  </ol>
</main>
<script>
  const target = "https://" + location.host + "/";
  const check = document.getElementById("check");
  async function tryHttps() {{
    try {{
      await fetch(target, {{ mode: "no-cors", cache: "no-store" }});  // only succeeds if the certificate is trusted
      check.textContent = "Trusted. Opening the secure page…";
      check.className = "ok";
      location.replace(target);
    }} catch {{
      check.textContent = "Not trusted yet: follow the steps below.";
      setTimeout(tryHttps, 2000);
    }}
  }}
  tryHttps();
  document.addEventListener("visibilitychange", () => {{ if (!document.hidden) tryHttps(); }});
</script>
</body>
</html>
"""
