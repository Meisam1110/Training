"""FolderWatcher behaviour with a real file being written / replaced / locked (unit-level, real filesystem)."""
import sys, time, os, shutil, threading
sys.path.insert(0, "/home/user/training/backend"); sys.path.insert(0, "/home/user/training/qa")
from pathlib import Path
from app.integrations.excel.watcher import FolderWatcher
import synth
d = Path("/tmp/qa/watch"); shutil.rmtree(d, ignore_errors=True); d.mkdir()
w = FolderWatcher(d, debounce_s=0.3)
synth.build("/tmp/qa/w_full.xlsx", n_emp=10, n_idp=10, edge=False); data = open("/tmp/qa/w_full.xlsx", "rb").read()
# 1. partial write (half the bytes), then complete
p = d / "export.xlsx"
with open(p, "wb") as f:
    f.write(data[: len(data) // 2]); f.flush(); time.sleep(0.5); print("poll during partial write:", w.poll()); time.sleep(0.5); print("poll again (stable but incomplete zip):", w.poll())
    f.write(data[len(data) // 2:])
time.sleep(0.5); w.poll(); time.sleep(0.4); print("after completion:", [x.name for x in w.poll()])
time.sleep(0.4); print("no change -> no re-report:", w.poll())
os.utime(p, None); time.sleep(0.4); w.poll(); time.sleep(0.4); print("touch only (same content) -> no re-import:", w.poll())
# 2. atomic replace with different content
synth.build("/tmp/qa/w_full2.xlsx", n_emp=11, n_idp=10, edge=False); os.replace("/tmp/qa/w_full2.xlsx", p)
time.sleep(0.4); w.poll(); time.sleep(0.4); print("atomic replace -> reported:", [x.name for x in w.poll()])
# 3. Excel lock file + temp files
(d / "~$export.xlsx").write_bytes(b"lock"); (d / ".~lock.export.xlsx#").write_bytes(b"x"); (d / "up.xlsx.tmp").write_bytes(b"x")
time.sleep(0.4); w.poll(); time.sleep(0.4); print("lock/temp files ignored:", w.poll())
# 4. deleted then re-added identical content: re-reported?
p.unlink(); w.poll(); shutil.copy("/tmp/qa/w_full.xlsx", p); shutil.copy("/tmp/qa/w_full.xlsx", d / "second.xlsx")
time.sleep(0.4); w.poll(); time.sleep(0.4); print("re-added + second file:", sorted(x.name for x in w.poll()))
# 5. is the watcher used by the app at all?
import subprocess
print("references to FolderWatcher/EXCEL_WATCH_DIR outside excel package:", subprocess.run("grep -rn 'FolderWatcher\\|EXCEL_WATCH_DIR' /home/user/training/backend/app /home/user/training/deploy /home/user/training/compose.yaml /home/user/training/.env.example | grep -v 'integrations/excel/'", shell=True, capture_output=True, text=True).stdout.strip() or "none")
