import csv, re

def norm(v):
    return re.sub(r"\s+", " ", re.sub(r"[^\w\s]", " ", str(v).lower().strip())).strip()

brands_to_find = ["alwalimah","california garden","durra","freez","golden","hebron",
                  "pufak","shahia","ziyad","alkhityar","aldayaa","chips oman","barbican",
                  "freez mix","lays","molto","tam tam","tiger","sohar"]

with open("Data_06_23.csv", encoding="utf-8", errors="replace") as f:
    rows = list(csv.DictReader(f))

print(f"Total CSV rows: {len(rows)}\n")
for target in brands_to_find:
    matches = [r for r in rows if target in norm(r.get("Branddescription","")) or
               target in norm(r.get("Expandeddescription",""))]
    if matches:
        print(f"=== '{target}' ({len(matches)} rows) ===")
        for r in matches[:3]:
            price = r.get("Activeprice") or r.get("Price","")
            upc   = r.get("UPCcode","")
            print(f"  brand={r.get('Branddescription',''):25} expanded={r.get('Expandeddescription',''):40} size={r.get('Sizedescription',''):10} price={price} upc={upc}")
    else:
        print(f"  NOT FOUND: '{target}'")
