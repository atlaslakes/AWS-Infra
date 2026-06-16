from pathlib import Path
import re

text = Path(r"c:\Users\aizen\Desktop\AWS\aws-infra\scripts\list.bundle.js").read_text(encoding="utf-8", errors="ignore")
print("len", len(text))

for term in [
    "frappe.get_user_settings",
    "user_settings",
    "fields",
    "columns",
    "total_fields",
    "add_fields",
    "set_user_settings",
    "save",
    "List",
    "list_settings",
    "in_list_view",
]:
    print(term, text.find(term))

patterns = [
    r"get_user_settings\([^\)]*\)",
    r"user_settings\[[^\]]+\]",
    r"\.save\([^\)]*user_settings[^\)]*\)",
    r"List",
    r"total_fields",
    r"fields_html",
]

for pat in patterns:
    print("\nPATTERN", pat)
    c = 0
    for m in re.finditer(pat, text):
        i = m.start()
        print("---", i, "---")
        print(text[max(0, i - 240): i + 420])
        c += 1
        if c >= 8:
            break
    print("shown", c)
