"""Fault-injecting fake IFS on several ports: 18110 slow, 18111 malformed JSON, 18112 endless pagination, 18113 HTTPS self-signed,
18114 redirect to internal host, 18115 huge body. usage: python faulty_ifs.py"""
import http.server, socketserver, threading, time, json, ssl, subprocess, os, sys
def person(i): return {"EmpNo": f"F{i:07d}", "FirstName": "F", "LastName": f"L{i}", "EmployeeStatus": "Active"}
class H(http.server.BaseHTTPRequestHandler):
    def log_message(self, *a): pass
    def _send(self, code, body, ct="application/json", headers=None):
        b = body if isinstance(body, bytes) else body.encode()
        self.send_response(code); self.send_header("Content-Type", ct); self.send_header("Content-Length", str(len(b)))
        for k, v in (headers or {}).items(): self.send_header(k, v)
        self.end_headers(); self.wfile.write(b)
    def do_GET(self):
        port = self.server.server_address[1]
        if port == 18110: time.sleep(8); self._send(200, json.dumps({"value": [person(1)]}))
        elif port == 18111: self._send(200, '{"value": [ {"EmpNo": "F1", "FirstName": ', )
        elif port == 18112:
            skip = int(self.path.split("skip=")[-1].split("&")[0]) if "skip=" in self.path else 0
            self._send(200, json.dumps({"value": [person(skip)], "@odata.nextLink": f"/PersonInfo?$top=1&$skip={skip+1}"}))
        elif port == 18113: self._send(200, json.dumps({"value": [person(1)]}))
        elif port == 18114: self._send(302, "", headers={"Location": "http://127.0.0.1:18701/health"})
        elif port == 18115: self._send(200, json.dumps({"value": [person(i) for i in range(60000)]}))
        else: self._send(404, "{}")
def serve(port, tls=False):
    class S(socketserver.ThreadingMixIn, http.server.HTTPServer): daemon_threads = True
    s = S(("127.0.0.1", port), H)
    if tls:
        ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER); ctx.load_cert_chain("/tmp/qa/selfsigned.pem", "/tmp/qa/selfsigned.key"); s.socket = ctx.wrap_socket(s.socket, server_side=True)
    threading.Thread(target=s.serve_forever, daemon=True).start()
if not os.path.exists("/tmp/qa/selfsigned.pem"):
    subprocess.run("openssl req -x509 -newkey rsa:2048 -nodes -keyout /tmp/qa/selfsigned.key -out /tmp/qa/selfsigned.pem -days 2 -subj /CN=localhost 2>/dev/null", shell=True)
for p in (18110, 18111, 18112, 18114, 18115): serve(p)
serve(18113, tls=True)
print("faulty ifs up", flush=True)
while True: time.sleep(3600)
