import openpyxl, re
from difflib import SequenceMatcher

wb = openpyxl.load_workbook(r"aws-infra\Karavan Inventory-updated.xlsx", read_only=True, data_only=True)
ws = wb.active
rows = list(ws.iter_rows(values_only=True))
headers = [str(h).replace("\n", " ").strip() if h else "" for h in rows[0]]

print("Headers:", headers)
print("\n=== All Excel rows (brand | description | size | cases) ===")
for row in rows[1:]:
    d = dict(zip(headers, row))
    brand = str(d.get("Brand") or "").strip()
    desc  = str(d.get("Description") or "").strip()
    size  = str(d.get("Size") or "").strip()
    cases = 0
    for k, v in d.items():
        if "cases" in k.lower() and "hand" in k.lower():
            try: cases = float(v) if v else 0
            except: cases = 0
    print(f"  {brand:25} | {desc:45} | {size:12} | {cases}")
