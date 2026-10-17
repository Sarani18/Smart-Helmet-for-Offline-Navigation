import json
import time
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "results.jsonl"


class Handler(SimpleHTTPRequestHandler):
    extensions_map = {**SimpleHTTPRequestHandler.extensions_map,
                      ".mjs": "text/javascript", ".wasm": "application/wasm",
                      ".onnx": "application/octet-stream"}

    def __init__(self, *a, **kw):
        super().__init__(*a, directory=str(ROOT), **kw)

    def end_headers(self):
        self.send_header("Cache-Control", "no-store")
        self.send_header("Cross-Origin-Opener-Policy", "same-origin")
        self.send_header("Cross-Origin-Embedder-Policy", "require-corp")
        super().end_headers()

    def do_POST(self):
        if self.path != "/result":
            self.send_error(404)
            return
        body = self.rfile.read(int(self.headers.get("Content-Length", 0)))
        rec = json.loads(body or b"{}")
        rec["received_at"] = time.strftime("%Y-%m-%d %H:%M:%S")
        rec["client_ip"] = self.client_address[0]
        with OUT.open("a") as fh:
            fh.write(json.dumps(rec) + "\n")
        print("RESULT", json.dumps({k: v for k, v in rec.items() if k != "times_ms"}), flush=True)
        self.send_response(200)
        self.end_headers()


if __name__ == "__main__":
    import ssl
    import sys
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8765
    srv = ThreadingHTTPServer(("0.0.0.0", port), Handler)
    if port == 8766:
        ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        ctx.load_cert_chain(ROOT / "cert.pem", ROOT / "key.pem")
        srv.socket = ctx.wrap_socket(srv.socket, server_side=True)
    srv.serve_forever()
