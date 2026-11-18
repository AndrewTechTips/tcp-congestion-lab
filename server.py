"""Interfata web. Porneste serverul si deschide http://localhost:8000

  python3 server.py
"""

import json
import os
import sys
import webbrowser
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer

from rdt.session import DEFAULTS, run_transfer

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "web")
ALLOWED = set(DEFAULTS) - {"data"}


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *a, **kw):
        super().__init__(*a, directory=ROOT, **kw)

    def log_message(self, fmt, *args):
        pass  # nu umplem terminalul cu fiecare cerere

    def do_POST(self):
        if self.path != "/api/run":
            self.send_error(404)
            return
        try:
            n = int(self.headers.get("Content-Length", 0))
            body = json.loads(self.rfile.read(n) or b"{}")
            params = {k: v for k, v in body.items() if k in ALLOWED}
            # sa nu blocheze cineva serverul cu un fisier de 1 GB
            params["size_kb"] = min(float(params.get("size_kb", 300)), 3000)
            result = run_transfer(**params)
            out = json.dumps(result).encode()
            self.send_response(200)
        except Exception as e:
            out = json.dumps({"error": str(e)}).encode()
            self.send_response(400)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(out)))
        self.end_headers()
        self.wfile.write(out)


def main():
    nums = [a for a in sys.argv[1:] if a.isdigit()]
    port = int(nums[0]) if nums else 8000
    srv = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    url = f"http://localhost:{port}"
    print("interfata e la", url, "(Ctrl+C ca sa opresti)")
    if "--no-browser" not in sys.argv:
        webbrowser.open(url)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print()


if __name__ == "__main__":
    main()
