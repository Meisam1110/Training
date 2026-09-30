import sys, tempfile
sys.path.insert(0, "/home/user/training/qa")
from openpyxl import Workbook
from synth import LEGACY_IDP_COLS
def idp_with_swapped_owner():
    wb = Workbook(); ws = wb.active; ws.title = "IDP"
    for _ in range(4): ws.append([])
    ws.append(LEGACY_IDP_COLS)
    # LMS-100001 was owned by 9000001 in the base workbook; this export lists it under 9000002
    ws.append(["9000002", "S", "", "D", "Effective Communication", "", "Approved", "", "Soft Skill", "-", "2026-11-01", "2026-11-02", "LMS-100001", "-"])
    with tempfile.NamedTemporaryFile(suffix=".xlsx") as f:
        wb.save(f.name); return open(f.name, "rb").read()
