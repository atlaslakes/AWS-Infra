import requests
S = requests.Session()
S.headers.update({"Authorization": "token 647f56b706a1bea:6c615d3ea8cbd4d"})
url = "http://atlaslakeserp"
for name in ["Pangea A", "Pangea B", "Pangea C"]:
    r = S.get(f"{url}/api/resource/Customer/{requests.utils.quote(name)}", timeout=15)
    d = r.json()["data"]
    print(f"{name}: group={d.get('customer_group')} | price_list={d.get('default_price_list')} | tier={d.get('custom_tier')}")
