import json
import re
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

KST = timezone(timedelta(hours=9))
units = json.loads(Path(r"d:\self\s\jso\遇见丶小八-32521580\unit_list.json").read_text(encoding="utf-8"))
ld = json.loads(Path(r"d:\self\s\jso\light_dark_units.json").read_text(encoding="utf-8"))

print("all source", Counter(u.get("source") for u in units))
print("class by source 5", Counter(u.get("class") for u in units if u.get("source") == 5))
print("class by source 42", Counter(u.get("class") for u in units if u.get("source") == 42))
print("attr by source 5", Counter(u.get("attribute") for u in units if u.get("source") == 5))
print("attr by source 42", Counter(u.get("attribute") for u in units if u.get("source") == 42))

print("\nLD natural_stars source 5", Counter(r.get("natural_stars") for r in ld if r.get("source") == 5))
print("LD natural_stars source 42", Counter(r.get("natural_stars") for r in ld if r.get("source") == 42))

print("\nsource 5 LD sample")
for r in ld:
    if r.get("source") == 5:
        print(" ", r.get("natural_stars"), r["attribute"], r["name"], r["create_time_kst"])

print("\nsource 42 nat5 LD")
for r in ld:
    if r.get("source") == 42 and r.get("natural_stars") == 5:
        print(" ", r["attribute"], r["name"], r["create_time_kst"])

html = Path(r"d:\self\s\jso\aaa.html").read_text(encoding="utf-8")
rows = re.findall(
    r'data-monsterelement="(\w+)" data-monsternaturalstars="(\d+)"'
    r'[\s\S]*?data-sort="(\d+)"[\s\S]*?alt="([^"]+)"',
    html,
)
by_time = defaultdict(list)
for u in units:
    by_time[u["create_time"]].append(u)
print("\nSWGT recent summon log vs json source")
for el, stars, ts, name in rows:
    ts = int(ts)
    kst = datetime.fromtimestamp(ts, timezone.utc).astimezone(KST).strftime("%Y-%m-%d %H:%M:%S")
    hits = by_time.get(kst, [])
    srcs = [h.get("source") for h in hits]
    print(f"  {kst} {stars}★ {el:5} {name:22} source={srcs}")
