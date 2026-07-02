import json, openpyxl

with open("_barcodes.json") as f:
    bc = json.load(f)
print("ERPNext barcodes (first 10):")
for b in bc[:10]:
    print(f"  {b['item_code']:14} -> {repr(b['barcode'])}")

wb = openpyxl.load_workbook(r"aws-infra\Karavan Inventory-updated.xlsx", read_only=True, data_only=True)
ws = wb.active
rows = list(ws.iter_rows(values_only=True))
headers = [str(h).replace("\n"," ").strip() if h else "" for h in rows[0]]
print("\nExcel UPCs (first 10):")
for row in rows[1:11]:
    d = dict(zip(headers, row))
    upc = d.get("UPC","")
    print(f"  {str(d.get('Brand','') or ''):25} UPC={repr(upc)}  type={type(upc).__name__}")
