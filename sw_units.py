"""魔灵清单：拆 JSON、筛属性/初始星/来源，直接写出 HTML。"""

from __future__ import annotations

import argparse
import html
import json
import re
import sys
import time
import urllib.request
import webbrowser
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

from constants import (
    ATTR,
    ATTR_CN,
    ATTRIBUTE_ALIAS,
    AVATAR_BY_MASTER_ID,
    EXCLUDE_SOURCE,
    EXTRA_NAMES,
    NON_SUMMON_MASTER_IDS,
    NON_SUMMON_NAMES,
    NAMES_BY_MASTER_ID,
    NATURAL_STAR_VALUES,
    NATURAL_STARS_BY_MASTER_ID,
    SOURCE,
    SOURCE_ALIAS,
)

HERE = Path(sys._MEIPASS) if getattr(sys, "frozen", False) else Path(__file__).resolve().parent
JSO = HERE.parent
DEFAULT_UNIT_LIST = JSO / "遇见丶小八-32521580" / "unit_list.json"

UA = {"User-Agent": "Mozilla/5.0 (compatible; sw-json-tools/1.0)"}
KST = timezone(timedelta(hours=9))
SWGT_MONSTER = "https://swgt.io/monsterSearch/?com2usID={mid}"
SWEX_MAPPING = "https://raw.githubusercontent.com/Xzandro/sw-exporter/master/app/mapping.js"
UNSAFE = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
STAR_SPAN = re.compile(
    r'class="[^"]*monster-profile-natural-stars[^"]*"[^>]*>(.*?)</span>',
    re.I | re.S,
)
PROFILE_IMG = re.compile(
    r'<img\b[^>]*\bclass="[^"]*\bmonster-profile-image\b[^"]*"[^>]*\bsrc="([^"]+)"'
    r'|<img\b[^>]*\bsrc="([^"]+)"[^>]*\bclass="[^"]*\bmonster-profile-image\b[^"]*"',
    re.I,
)
MATCH_ROW = re.compile(
    r'data-monsterelement="(\w+)" data-monsternaturalstars="(\d+)"'
    r'[\s\S]*?data-sort="(\d+)"[\s\S]*?alt="([^"]+)"'
)


ICON_BASE = "https://do9d4mpqk497d.cloudfront.net/common/images/monsters/"


def cache_dir() -> Path:
    d = HERE / ".cache"
    d.mkdir(exist_ok=True)
    return d


def load_icon_files() -> dict[int, str]:
    path = cache_dir() / "monster_icons.json"
    if not path.is_file():
        return {}
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
    if not isinstance(raw, dict):
        return {}
    table: dict[int, str] = {}
    for mid, name in raw.items():
        if not isinstance(name, str) or "/" in name or "\\" in name:
            continue
        if not name.startswith("unit_icon_") or not name.endswith(".png"):
            continue
        try:
            table[int(mid)] = name
        except ValueError:
            continue
    return table


ICON_FILES = load_icon_files()


def monster_avatar(mid: int) -> str:
    filename = ICON_FILES.get(int(mid))
    if filename:
        return ICON_BASE + filename
    return AVATAR_BY_MASTER_ID.get(mid) or ""


def load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def dump_json(path: Path, data) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def fetch(url: str, timeout: int = 30) -> str:
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read().decode("utf-8", "ignore")


def fetch_swgt_monster(mid: int, allow_network: bool = True) -> tuple[str, bool]:
    path = cache_dir() / "swgt" / f"{mid}.html"
    if path.exists():
        return path.read_text(encoding="utf-8"), True
    if not allow_network:
        return "", True
    text = fetch(SWGT_MONSTER.format(mid=mid))
    path.parent.mkdir(exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return text, False


def parse_natural_stars(page: str) -> int | None:
    m = STAR_SPAN.search(page)
    if not m:
        return None
    return m.group(1).count("fa-star")


def parse_avatar(page: str) -> str:
    m = PROFILE_IMG.search(page)
    if not m:
        return ""
    return m.group(1) or m.group(2) or ""


def parse_swgt_name(page: str) -> str:
    m = re.search(r'<h1[^>]*class="[^"]*monster[^"]*"[^>]*>\s*([^<]+)', page, re.I)
    if m:
        return m.group(1).strip()
    m = re.search(r"Collaboration[^<]*?((?:Light|Dark|Fire|Water|Wind)\s+[A-Za-z .'-]+)", page)
    if m:
        return m.group(1).strip()
    return ""


def load_swex_names() -> dict[int, str]:
    path = cache_dir() / "mapping.js"
    if not path.exists():
        path.write_text(fetch(SWEX_MAPPING), encoding="utf-8")
    js = path.read_text(encoding="utf-8")
    block = re.search(r"names:\s*\{([\s\S]*?)\n\s*\},", js)
    if not block:
        return {}
    return {int(i): n for i, n in re.findall(r"(\d+):\s*'([^']*)'", block.group(1))}


def monster_name(mid: int, swex: dict[int, str] | None = None) -> str:
    if mid in EXTRA_NAMES:
        return EXTRA_NAMES[mid]
    if mid in NAMES_BY_MASTER_ID:
        return NAMES_BY_MASTER_ID[mid]
    names = swex if swex is not None else {}
    if mid in names:
        return names[mid]
    if mid + 10 in names:
        return names[mid + 10]
    family = int(str(mid)[:3]) if mid >= 10000 else mid // 100
    attr = mid % 10
    if family in names:
        return f"{names[family]} ({ATTR.get(attr, attr)})"
    return ""


def kst_times(create_time: str) -> tuple[str, str, int]:
    created = datetime.strptime(create_time, "%Y-%m-%d %H:%M:%S").replace(tzinfo=KST)
    utc = created.astimezone(timezone.utc)
    return create_time, utc.strftime("%Y-%m-%d %H:%M:%S"), int(utc.timestamp())


def load_units(path: Path) -> list[dict]:
    data = load_json(path)
    if isinstance(data, list):
        return data
    if isinstance(data, dict) and "unit_list" in data:
        return data["unit_list"]
    raise TypeError(f"{path.name} 需要 unit_list 数组，或带 unit_list 字段的登录包")


def parse_attrs(raw: str) -> set[int] | None:
    text = (raw or "").strip()
    if not text or text.lower() in {"all", "全部", "*"}:
        return None
    parts = [p for p in re.split(r"[,，\s]+", text) if p]
    out: set[int] = set()
    for part in parts:
        key = part.lower()
        if key in ATTRIBUTE_ALIAS:
            out.add(ATTRIBUTE_ALIAS[key])
            continue
        for ch in part:
            if ch.lower() in ATTRIBUTE_ALIAS:
                out.add(ATTRIBUTE_ALIAS[ch.lower()])
            else:
                raise ValueError(f"无法识别属性: {part}")
    return out or None


def parse_stars(raw: str) -> set[int] | None:
    text = (raw or "").strip()
    if not text or text.lower() in {"all", "全部", "*"}:
        return None
    out: set[int] = set()
    for part in re.split(r"[,，\s]+", text):
        if not part:
            continue
        if "-" in part:
            a, b = part.split("-", 1)
            lo, hi = int(a), int(b)
            out.update(range(lo, hi + 1))
        else:
            out.add(int(part))
    bad = out - set(NATURAL_STAR_VALUES)
    if bad:
        raise ValueError(f"初始星只能是 {NATURAL_STAR_VALUES}，收到 {sorted(bad)}")
    return out or None


def parse_source(raw: str) -> str | set[int]:
    text = (raw or "").strip()
    if not text:
        return "summon"
    key = text.lower()
    if key in SOURCE_ALIAS:
        return SOURCE_ALIAS[key]
    nums = {int(p) for p in re.split(r"[,，\s]+", text) if p}
    return nums


def source_ok(row: dict, mode: str | set[int]) -> bool:
    if mode == "all":
        return True
    if mode == "summon":
        if row.get("name") in NON_SUMMON_NAMES:
            return False
        if row.get("unit_master_id") in NON_SUMMON_MASTER_IDS:
            return False
        if row.get("source") in EXCLUDE_SOURCE:
            return False
        return True
    return row.get("source") in mode


def to_row(unit: dict, swex: dict[int, str]) -> dict:
    mid = unit["unit_master_id"]
    attr = unit["attribute"]
    name = monster_name(mid, swex) or f"未知#{mid}"
    kst, utc, unix = kst_times(unit["create_time"])
    return {
        "name": name,
        "attribute": ATTR_CN.get(attr, str(attr)),
        "attribute_en": ATTR.get(attr, str(attr)),
        "attribute_id": attr,
        "create_time_kst": kst,
        "create_time_utc": utc,
        "unix": unix,
        "unit_master_id": mid,
        "natural_stars": NATURAL_STARS_BY_MASTER_ID.get(mid),
        "current_stars": unit["class"],
        "level": unit["unit_level"],
        "source": unit["source"],
        "source_label": SOURCE.get(unit["source"], str(unit["source"])),
        "unit_id": unit["unit_id"],
        "avatar": monster_avatar(mid),
    }


def fill_missing(rows: list[dict], fields: set[str], allow_network: bool = True) -> None:
    ids = sorted(
        {
            r["unit_master_id"]
            for r in rows
            if ("stars" in fields and not r.get("natural_stars"))
            or ("name" in fields and r["name"].startswith("未知#"))
            or ("avatar" in fields and not r.get("avatar"))
        }
    )
    if not ids:
        return
    print(f"SWGT 补全 {len(ids)} 个图鉴 ID")
    cache: dict[int, dict] = {}
    for i, mid in enumerate(ids, 1):
        try:
            page, cached = fetch_swgt_monster(mid, allow_network=allow_network)
            if not page:
                raise RuntimeError("无缓存且未联网")
            cache[mid] = {
                "stars": parse_natural_stars(page),
                "name": parse_swgt_name(page),
                "avatar": parse_avatar(page),
            }
        except Exception as exc:
            cache[mid] = {"stars": None, "name": "", "avatar": ""}
            print(f"失败 {mid}: {exc}")
            continue
        got = cache[mid]
        print(f"  {i}/{len(ids)} {mid} stars={got['stars']} avatar={bool(got['avatar'])} {got['name']}")
        if not cached:
            time.sleep(0.12)
    for r in rows:
        got = cache.get(r["unit_master_id"])
        if not got:
            continue
        if not r.get("natural_stars") and got["stars"]:
            r["natural_stars"] = got["stars"]
        if r["name"].startswith("未知#") and got["name"]:
            r["name"] = got["name"]
        if not r.get("avatar") and got["avatar"]:
            r["avatar"] = got["avatar"]


def filter_rows(
    units: list[dict],
    attrs: set[int] | None,
    stars: set[int] | None,
    source: str | set[int],
    fetch_missing: bool,
    swex: dict[int, str] | None = None,
) -> list[dict]:
    if swex is None:
        print("加载名称表 …")
        swex = load_swex_names() if fetch_missing else {}
    rows = []
    for u in units:
        if attrs is not None and u.get("attribute") not in attrs:
            continue
        rows.append(to_row(u, swex))
    rows.sort(key=lambda r: r["unix"], reverse=True)
    if fetch_missing:
        need_name_or_star = [
            r
            for r in rows
            if r["name"].startswith("未知#") or (stars is not None and not r.get("natural_stars"))
        ]
        fill_missing(need_name_or_star, {"name", "stars"}, allow_network=True)
    if stars is not None:
        rows = [r for r in rows if r.get("natural_stars") in stars]
    rows = [r for r in rows if source_ok(r, source)]
    fill_missing(rows, {"avatar"}, allow_network=fetch_missing)
    return rows


def render_html(rows: list[dict], title: str, subtitle: str) -> str:
    parts = [
        "<!DOCTYPE html><html lang='zh-CN'><head><meta charset='UTF-8'/>",
        f"<title>{html.escape(title)}</title><style>",
        "body{font-family:'Microsoft YaHei',sans-serif;background:#111;color:#eee;margin:24px}",
        "h1{font-size:20px} .sub{color:#888;font-size:13px;margin-bottom:16px}",
        ".row{display:flex;align-items:center;gap:14px;padding:10px 0;border-bottom:1px solid #333}",
        "img{width:64px;height:64px;border-radius:8px;background:#222;object-fit:contain}",
        ".name{font-size:16px;font-weight:700}.meta{font-size:13px;color:#aaa}",
        ".light{color:#e8d48b}.dark{color:#b39ddb}",
        ".water{color:#7ec8e3}.fire{color:#e88b8b}.wind{color:#8be89a}</style></head><body>",
        f"<h1>{html.escape(title)}（{len(rows)} 只）</h1>",
        f"<p class='sub'>{html.escape(subtitle)}</p>",
    ]
    cls_map = {"光": "light", "暗": "dark", "水": "water", "火": "fire", "风": "wind"}
    for r in rows:
        cls = cls_map.get(r["attribute"], "")
        src = html.escape(r.get("avatar") or "")
        name = html.escape(r["name"])
        src_label = html.escape(r.get("source_label") or str(r["source"]))
        parts.append(
            f"<div class='row'><img src='{src}' alt='{name}'/>"
            f"<div><div class='name {cls}'>{name}</div>"
            f"<div class='meta'>{html.escape(r['attribute'])} · {html.escape(r['create_time_kst'])} · "
            f"{r.get('natural_stars') or '-'}★→{r['current_stars']}★ Lv{r['level']} · "
            f"{src_label} ({r['source']})</div></div></div>"
        )
    parts.append("</body></html>")
    return "\n".join(parts)


def attr_title(attrs: set[int] | None) -> str:
    if attrs is None:
        return "全部属性"
    return "/".join(ATTR_CN[i] for i in sorted(attrs))


def stars_title(stars: set[int] | None) -> str:
    if stars is None:
        return "全部初始星"
    return "、".join(str(s) for s in sorted(stars)) + " 星"


def source_title(mode: str | set[int]) -> str:
    if mode == "all":
        return "全部来源"
    if mode == "summon":
        return "常规召唤"
    return "source " + ",".join(str(i) for i in sorted(mode))


def default_html_name(attrs: set[int] | None, stars: set[int] | None, source: str | set[int]) -> Path:
    a = "all" if attrs is None else "".join(ATTR_CN[i] for i in sorted(attrs))
    s = "all" if stars is None else "".join(str(i) for i in sorted(stars))
    src = "summon" if source == "summon" else ("all" if source == "all" else "src")
    return JSO / f"units_{a}_{s}star_{src}.html"


def cmd_html(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="sw_units.py", description="按属性 / 初始星 / 来源筛选并写出 HTML")
    parser.add_argument("unit_list", nargs="?", type=Path, default=DEFAULT_UNIT_LIST)
    parser.add_argument("--attr", default="光,暗", help="光,暗 / 4,5 / light / all")
    parser.add_argument("--stars", default="5", help="5 / 4,5 / 3-5 / all")
    parser.add_argument("--source", default="summon", help="summon（常规召唤）/ all / 5,42")
    parser.add_argument("-o", "--html", type=Path, help="输出 HTML 路径")
    parser.add_argument("--open", action="store_true", help="写完后用系统默认浏览器打开")
    parser.add_argument("--no-fetch", action="store_true", help="不请求 SWGT，只用已落地常量")
    args = parser.parse_args(argv)

    if not args.unit_list.exists():
        print(f"找不到 {args.unit_list}", file=sys.stderr)
        return 1
    try:
        attrs = parse_attrs(args.attr)
        stars = parse_stars(args.stars)
        source = parse_source(args.source)
    except ValueError as exc:
        print(exc, file=sys.stderr)
        return 1

    units = load_units(args.unit_list)
    rows = filter_rows(units, attrs, stars, source, fetch_missing=not args.no_fetch)
    title = f"{stars_title(stars)} · {attr_title(attrs)} · {source_title(source)}"
    extra = " 常规召唤已排除合成 / 人造 / 商店碎片 / 活动发放 / 赠送原皮与商店专买。" if source == "summon" else ""
    subtitle = (
        f"来自 {args.unit_list.name}。初始星用 constants.py（SWGT 图鉴），"
        f"时间是 create_time（KST / UTC+9）。{extra}"
    )
    out = args.html or default_html_name(attrs, stars, source)
    out.write_text(render_html(rows, title, subtitle), encoding="utf-8")
    print(f"保留 {len(rows)} 只 → {out}")
    for r in rows:
        print(f"  {r['source']} {r['attribute']} {r['name']} {r['create_time_kst']}")
    if args.open:
        webbrowser.open(out.resolve().as_uri())
    return 0


def safe_name(key: str) -> str:
    name = UNSAFE.sub("_", str(key)).strip(" .")
    return name or "_empty"


def split_file(src: Path, out_dir: Path | None = None) -> Path:
    src = src.resolve()
    if not src.is_file():
        raise FileNotFoundError(src)
    data = load_json(src)
    if not isinstance(data, dict):
        raise TypeError(f"{src.name} 根节点是 {type(data).__name__}，需要 object")
    dest = out_dir.resolve() if out_dir else src.with_suffix("")
    dest.mkdir(parents=True, exist_ok=True)
    used: dict[str, int] = {}
    for key, value in data.items():
        base = safe_name(key)
        n = used.get(base, 0)
        used[base] = n + 1
        filename = f"{base}.json" if n == 0 else f"{base}_{n}.json"
        dump_json(dest / filename, value)
        print(f"  {filename}")
    print(f"完成：{src.name} → {dest}（{len(data)} 个文件）")
    return dest


def cmd_split(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="sw_units.py split", description="按第一级 key 拆分 JSON")
    parser.add_argument("inputs", nargs="*", type=Path)
    parser.add_argument("-o", "--out", type=Path)
    args = parser.parse_args(argv)
    inputs = args.inputs or sorted(p for p in JSO.glob("*.json") if p.is_file())
    if not inputs:
        print("没有可拆分的 JSON", file=sys.stderr)
        return 1
    if args.out and len(inputs) > 1:
        print("-o 只能用于单个输入文件", file=sys.stderr)
        return 1
    for src in inputs:
        split_file(src, args.out)
    return 0


def cmd_match(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="sw_units.py match", description="对照 SWGT 召唤日志 HTML 与 unit_list")
    parser.add_argument("html", type=Path)
    parser.add_argument("unit_list", nargs="?", type=Path, default=DEFAULT_UNIT_LIST)
    args = parser.parse_args(argv)
    page = args.html.read_text(encoding="utf-8")
    rows = MATCH_ROW.findall(page)
    units = load_units(args.unit_list)
    by_time: dict[str, list] = defaultdict(list)
    for u in units:
        by_time[u["create_time"]].append(u)
    print(f"HTML 行 {len(rows)}")
    for el, stars, ts, name in rows:
        ts = int(ts)
        kst = datetime.fromtimestamp(ts, timezone.utc).astimezone(KST)
        key = kst.strftime("%Y-%m-%d %H:%M:%S")
        hits = by_time.get(key, [])
        print(f"{key}  {stars}★ {el:5} {name:20}  json命中 {len(hits)}")
        for u in hits:
            attr = ATTR_CN.get(u.get("attribute"), u.get("attribute"))
            print(
                f"    master={u['unit_master_id']} attr={attr} "
                f"class={u['class']} source={u['source']}"
            )
        if hits:
            continue
        nearest = min(
            by_time,
            key=lambda t: abs(
                datetime.strptime(t, "%Y-%m-%d %H:%M:%S").replace(tzinfo=KST).timestamp() - ts
            ),
        )
        delta = abs(
            datetime.strptime(nearest, "%Y-%m-%d %H:%M:%S").replace(tzinfo=KST).timestamp() - ts
        )
        print(f"    无精确命中，最近 {nearest}（差 {int(delta)} 秒）")
    return 0


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv and argv[0] in {"split", "match", "html"}:
        cmd = argv.pop(0)
        if cmd == "split":
            return cmd_split(argv)
        if cmd == "match":
            return cmd_match(argv)
    return cmd_html(argv)


if __name__ == "__main__":
    raise SystemExit(main())
