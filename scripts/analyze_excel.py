import openpyxl
from collections import Counter

wb = openpyxl.load_workbook('C:/Users/aizen/Desktop/Pangea POS Data.xlsx')
ws = wb['Sheet1']

groups = Counter()
uoms = Counter()
missing_code = 0
missing_name = 0
missing_group = 0
missing_price = 0

for row in ws.iter_rows(min_row=2, values_only=True):
    code, name, group, price, uom = row
    if not code: missing_code += 1
    if not name: missing_name += 1
    if not group: missing_group += 1
    if not price: missing_price += 1
    groups[group] += 1
    uoms[uom] += 1

print("=== Item Groups ===")
for g, c in sorted(groups.items(), key=lambda x: -x[1]):
    print(f"  {c:5d}  {g}")

print("\n=== UOM Values ===")
for u, c in sorted(uoms.items(), key=lambda x: -x[1]):
    print(f"  {c:5d}  {u}")

print(f"\nMissing item code: {missing_code}")
print(f"Missing item name: {missing_name}")
print(f"Missing item group: {missing_group}")
print(f"Missing price: {missing_price}")
