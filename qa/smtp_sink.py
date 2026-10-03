"""aiosmtpd sink: records every message to /tmp/qa/smtp_sink/*.eml. RCPT rules: reject-* -> 550, slow-* delay,
drop-* -> connection closed at DATA. usage: python smtp_sink.py PORT"""
import asyncio, sys, os, time, itertools
from aiosmtpd.controller import Controller
from aiosmtpd.smtp import SMTP
OUT = "/tmp/qa/smtp_sink"; os.makedirs(OUT, exist_ok=True)
cnt = itertools.count(1)
class H:
    async def handle_RCPT(self, server, session, envelope, address, rcpt_options):
        if address.startswith("reject"): return "550 5.1.1 mailbox unavailable"
        envelope.rcpt_tos.append(address); return "250 OK"
    async def handle_DATA(self, server, session, envelope):
        if any(r.startswith("drop") for r in envelope.rcpt_tos):
            server.transport.close(); return "421 bye"
        if any(r.startswith("slow") for r in envelope.rcpt_tos): await asyncio.sleep(3)
        n = next(cnt)
        open(f"{OUT}/{int(time.time()*1000)}-{n}.eml", "wb").write(envelope.original_content)
        open(f"{OUT}/{int(time.time()*1000)}-{n}.env", "w").write(f"FROM={envelope.mail_from}\nTO={','.join(envelope.rcpt_tos)}\n")
        return "250 OK queued"
if __name__ == "__main__":
    c = Controller(H(), hostname="127.0.0.1", port=int(sys.argv[1])); c.start()
    print("sink up", flush=True)
    try:
        while True: time.sleep(3600)
    except KeyboardInterrupt: c.stop()
