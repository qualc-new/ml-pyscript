"""本地网页：导入登录包，查看字段、召唤记录，并配置符文。

在 jso/pyscript 下执行::

    python web/server.py
    python web/server.py --open
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import threading
import time
import webbrowser
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse

ROOT = Path(__file__).resolve().parent
PYSCRIPT = ROOT.parent
STATIC = ROOT / "static"
sys.path.insert(0, str(PYSCRIPT))

from constants import ATTR_CN, NATURAL_STARS_BY_MASTER_ID, SOURCE  # noqa: E402
from sw_runes import (  # noqa: E402
    FOUR_OPTIONS,
    INTANGIBLE,
    PREMIUM,
    PREMIUM_IDS,
    SET_NAME,
    STAT_KEYS,
    STAT_LABEL,
    TWO_OPTIONS,
    SetRequest,
    add_vec,
    bonus_vector,
    broken_rule_text,
    fmt_eff,
    fmt_sub,
    panel_value,
    parse_rune,
    rune_kind,
    solve_sequence,
    sum_stats,
)
from sw_units import filter_rows, to_row  # noqa: E402

# 登录包里的 con 要乘 15 才是面板白字生命；攻击、防御、速度不用乘。
HP_FACTOR = 15


def percent_ceil(base: int, percent: int) -> int:
    """游戏面板上的百分比加成向上取整。115 的迅速 25% 是 29。"""
    if base <= 0 or percent <= 0:
        return 0
    return (base * percent + 99) // 100


# 荣耀建筑（deco master_id）每级的面板加成。数组下标是等级 - 1。
# 速度图腾用千分比（15% = 150），只在战斗速度里生效，不写入魔灵面板速度。
# 其余是整数百分比。只含全地图生效的属性建筑。
GLORY_PERCENT: dict[int, tuple[str, tuple[int, ...]]] = {
    8: ("hp", tuple(range(1, 21))),
    9: ("atk", tuple(range(1, 21))),
    4: ("def", tuple(range(1, 21))),
    31: ("cd", (1, 2, 3, 5, 6, 7, 8, 9, 10, 12, 13, 15, 16, 17, 18, 20, 21, 22, 23, 25)),
    6: (
        "spd",
        (10, 20, 25, 30, 40, 50, 55, 60, 70, 80, 85, 90, 100, 110, 115, 120, 130, 140, 145, 150),
    ),
}
SANCTUARY: dict[int, int] = {15: 2, 16: 1, 17: 3, 18: 4, 19: 5}
SANCTUARY_ATK = tuple(range(2, 22))
ARTIFACT_FLAT = {100: "hp", 101: "atk", 102: "def"}
PANEL_KEYS = ("hp", "atk", "def")
PANEL_INPUT = {"hp": "生命", "atk": "攻击", "def": "防御"}
STAT_HINT = {
    "hp": "绿字",
    "atk": "绿字",
    "def": "绿字",
    "spd": "符文速度",
    "cr": "百分比",
    "cd": "百分比",
    "acc": "百分比",
    "res": "百分比",
}
# 竞技场常见队长加成。id 是「属性:百分比」。
LEADER_OPTIONS = (
    ("spd", 15, "速度 15%"),
    ("spd", 19, "速度 19%"),
    ("spd", 24, "速度 24%"),
    ("spd", 33, "速度 33%"),
    ("hp", 15, "生命 15%"),
    ("hp", 21, "生命 21%"),
    ("hp", 25, "生命 25%"),
    ("hp", 33, "生命 33%"),
    ("atk", 15, "攻击 15%"),
    ("atk", 21, "攻击 21%"),
    ("atk", 25, "攻击 25%"),
    ("atk", 33, "攻击 33%"),
    ("def", 15, "防御 15%"),
    ("def", 21, "防御 21%"),
    ("def", 25, "防御 25%"),
    ("def", 33, "防御 33%"),
    ("cr", 15, "暴击 15%"),
    ("cr", 23, "暴击 23%"),
    ("acc", 30, "命中 30%"),
    ("acc", 41, "命中 41%"),
    ("acc", 55, "命中 55%"),
    ("res", 30, "抵抗 30%"),
    ("res", 41, "抵抗 41%"),
    ("res", 55, "抵抗 55%"),
)

PANEL_LABEL = {
    "hp": "生命",
    "atk": "攻击",
    "def": "防御",
    "spd": "速度",
    "cr": "暴击%",
    "cd": "爆伤%",
    "acc": "命中%",
    "res": "抵抗%",
}
MAX_BODY = 200 * 1024 * 1024
REDACT = {"session_key", "session_key_node"}
TIME_FMT = "%Y-%m-%d %H:%M:%S"

# 字段中文说明。没列到的归到「其他」。
KEY_INFO: dict[str, tuple[str, str]] = {
    "command": ("账号", "接口名，完整登录包一般是 HubUserLogin"),
    "ret_code": ("账号", "返回码，0 表示成功"),
    "wizard_id": ("账号", "角色 ID"),
    "wizard_info": ("账号", "昵称、等级、魔力、水晶、能量"),
    "wizard_skill_info": ("账号", "召唤师技能"),
    "wizard_skill_list": ("账号", "召唤师技能列表"),
    "wizard_extra_data": ("账号", "角色附加数据"),
    "account_info": ("账号", "Hive、设备、版本、国家"),
    "account_config_info": ("账号", "账号配置"),
    "session_key": ("账号", "会话密钥（预览已隐藏）"),
    "session_key_node": ("账号", "会话密钥节点（预览已隐藏）"),
    "webcash_info": ("账号", "网页商店点券"),
    "country": ("账号", "国家"),
    "reqid": ("账号", "请求 ID"),
    "this_server_id": ("账号", "服务器 ID"),
    "play_start_timestamp": ("账号", "本次登录开始时间"),
    "user_reference_date_info": ("账号", "账号基准日期"),
    "tvalue": ("账号", "服务器时间"),
    "ts_val": ("账号", "服务器时间"),
    "tvaluelocal": ("账号", "本地时间"),
    "tzone": ("账号", "时区"),
    "tzoffset": ("账号", "时区偏移"),
    "tvaluelocal_next_monday": ("账号", "下周一本地时间"),
    "unit_list": ("魔灵", "背包里现存的魔灵，不是完整召唤流水"),
    "unit_collection": ("魔灵", "图鉴"),
    "unit_storage_normal_list": ("魔灵", "普通仓库"),
    "unit_storage_normal_slots": ("魔灵", "普通仓库格子"),
    "unit_depository_slots": ("魔灵", "保管所格子"),
    "unit_marker_list": ("魔灵", "魔灵标记"),
    "unit_state": ("魔灵", "魔灵状态"),
    "favorite_unit_list": ("魔灵", "收藏"),
    "lobby_proud_unit_id_list": ("魔灵", "大厅展示"),
    "wish_list": ("魔灵", "心愿单"),
    "draft_unit_list": ("魔灵", "征召池"),
    "worldboss_used_unit": ("魔灵", "世界首领已用魔灵"),
    "runes": ("符文", "符文"),
    "rune_lock_list": ("符文", "锁定的符文"),
    "rune_craft_item_list": ("符文", "符文精工石、宝石"),
    "artifacts": ("符文", "神器"),
    "artifact_crafts": ("符文", "神器制作材料"),
    "relics": ("符文", "遗物"),
    "trans_item_list": ("符文", "附着的转换道具"),
    "equip_info_list": ("符文", "装备"),
    "world_arena_rune_equip_list": ("符文", "世界竞技场符文预设"),
    "world_arena_artifact_equip_list": ("符文", "世界竞技场神器预设"),
    "world_arena_rune_equip_sync": ("符文", "符文预设是否已同步"),
    "world_arena_artifact_equip_sync": ("符文", "神器预设是否已同步"),
    "inventory_info": ("背包", "卷轴、精髓等道具"),
    "inventory_open_info": ("背包", "已开格子"),
    "inventory_mail_info": ("背包", "邮箱附件"),
    "inventory_item_expire_list": ("背包", "限时道具"),
    "period_item_list": ("背包", "限时物品"),
    "shop_info": ("背包", "商店及购买冷却"),
    "shop_daily_bonus_list": ("背包", "每日商店奖励"),
    "shop_bonus_event": ("背包", "商店活动"),
    "costume_ticket_purchased_list": ("背包", "已买时装券"),
    "summon_special_info": ("召唤", "当前特殊召唤卡池，不是抽卡历史"),
    "summon_choices": ("召唤", "自选召唤 / 祝福二选一"),
    "summon_custom_pool_info": ("召唤", "自定义卡池"),
    "summon_beginner_pickup_info": ("召唤", "新手 Pickup"),
    "summon_pass_info": ("召唤", "召唤通行证"),
    "summon_pass_reward_list": ("召唤", "召唤通行证奖励"),
    "beginner_summon_free": ("召唤", "新手免费召唤"),
    "island_info": ("建筑", "天空之岛"),
    "building_list": ("建筑", "建筑"),
    "deco_list": ("建筑", "装饰"),
    "obstacle_list": ("建筑", "岛上障碍"),
    "object_state": ("建筑", "岛上物件状态"),
    "object_storage_list": ("建筑", "物件仓库"),
    "object_storage_slots": ("建筑", "物件仓库格子"),
    "markers": ("建筑", "地图标记"),
    "mob_list": ("建筑", "岛上生物"),
    "mob_costume_equip_list": ("建筑", "魔灵时装"),
    "mob_costume_part_list": ("建筑", "时装部件"),
    "homunculus_skill_list": ("建筑", "人造魔灵技能"),
    "deck_list": ("编队", "保存的队伍"),
    "deck_recent_list": ("编队", "最近使用的队伍"),
    "defense_deck_info": ("编队", "竞技场防守"),
    "temporary_defense_deck": ("编队", "临时防守"),
    "raid_deck": ("编队", "团本队伍"),
    "battle_option_list": ("编队", "战斗选项"),
    "pvp_info": ("竞技场", "普通竞技场"),
    "arena_shutdown_info": ("竞技场", "竞技场维护"),
    "server_arena_defense_deck_info": ("竞技场", "服务器竞技场防守"),
    "server_arena_schedule_info": ("竞技场", "服务器竞技场赛程"),
    "rtpvp_info": ("竞技场", "世界竞技场"),
    "rtpvp_season_info": ("竞技场", "世界竞技场赛季"),
    "rtpvp_team_season_info": ("竞技场", "组队赛季"),
    "rtpvp_draft_season_info": ("竞技场", "征召赛季"),
    "rtpvp_contest_info": ("竞技场", "对抗赛"),
    "guild": ("公会", "公会信息"),
    "guild_join_timer": ("公会", "入会冷却"),
    "guild_attend_info": ("公会", "公会签到"),
    "guildsiege_defense_deck_equip_list": ("公会", "公会战防守装备"),
    "guildsiege_defense_deck_unit_list": ("公会", "公会战防守魔灵"),
    "scenario_list": ("副本", "剧情进度"),
    "quest_active": ("副本", "进行中的任务"),
    "quest_rewarded": ("副本", "已领任务"),
    "event_id_list": ("副本", "当前活动"),
    "dimension_hole_info": ("副本", "次元洞"),
    "raid_info_list": ("副本", "团本"),
    "raid_best_clear_info_list": ("副本", "团本最佳通关"),
    "worldboss_status": ("副本", "世界首领状态"),
    "my_worldboss_ranking": ("副本", "世界首领排名"),
    "scout_info": ("副本", "探索进行中的一场"),
    "daily_reward_info": ("奖励", "每日签到"),
    "daily_reward_list": ("奖励", "每日签到列表"),
    "friend_list": ("社交", "好友"),
    "mentoring_info": ("社交", "师徒"),
    "notice_info": ("通知", "公告"),
    "push_noti_status_list": ("通知", "推送开关"),
}

GROUP_ORDER = ["账号", "魔灵", "符文", "背包", "召唤", "建筑", "编队", "竞技场", "公会", "副本", "奖励", "社交", "通知", "其他"]
NAME_BLOCK = re.compile(r"names:\s*\{([\s\S]*?)\n\s*\},")


def cached_swex_names() -> dict[int, str]:
    path = PYSCRIPT / ".cache" / "mapping.js"
    if not path.is_file():
        return {}
    block = NAME_BLOCK.search(path.read_text(encoding="utf-8"))
    if not block:
        return {}
    return {int(mid): name for mid, name in re.findall(r"(\d+):\s*'([^']*)'", block.group(1))}


SWEX_NAMES = cached_swex_names()


def load_natural_stars() -> dict[int, int]:
    table = {
        int(mid): int(star)
        for mid, star in NATURAL_STARS_BY_MASTER_ID.items()
        if star in (1, 2, 3, 4, 5)
    }
    path = PYSCRIPT / ".cache" / "natural_stars.json"
    if not path.is_file():
        return table
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        return table
    for mid, star in raw.items():
        try:
            mid_i = int(mid)
            star_i = int(star)
        except (TypeError, ValueError):
            continue
        if star_i in (1, 2, 3, 4, 5):
            table[mid_i] = star_i
    return table


NATURAL_STARS = load_natural_stars()


class Store:
    def __init__(self) -> None:
        self.lock = threading.Lock()
        self.filename = ""
        self.data: dict | None = None
        self.units: list[dict] = []
        self.runes: list = []
        self.warnings: list[str] = []
        self.rta: list[dict] = []


STORE = Store()


def describe(value) -> tuple[str, int | None]:
    if isinstance(value, dict):
        return "object", len(value)
    if isinstance(value, list):
        return "array", len(value)
    if isinstance(value, str):
        return "string", len(value)
    if isinstance(value, bool):
        return "bool", None
    if isinstance(value, (int, float)):
        return "number", None
    if value is None:
        return "null", None
    return type(value).__name__, None


def preview(value, depth: int = 0):
    if isinstance(value, str) and len(value) > 160:
        return value[:160] + "…"
    if depth >= 3:
        kind, count = describe(value)
        if count is None:
            return value if not isinstance(value, (dict, list)) else f"<{kind}>"
        return f"<{kind} {count}>"
    if isinstance(value, dict):
        out = {}
        items = list(value.items())
        for key, item in items[:24]:
            name = str(key)
            if name in REDACT:
                out[name] = "已隐藏"
            else:
                out[name] = preview(item, depth + 1)
        if len(items) > 24:
            out["…"] = f"另有 {len(items) - 24} 个字段"
        return out
    if isinstance(value, list):
        return {
            "length": len(value),
            "sample": [preview(item, depth + 1) for item in value[:2]],
        }
    return value


def catalog(data: dict) -> list[dict]:
    buckets: dict[str, list[dict]] = {name: [] for name in GROUP_ORDER}
    for key, value in data.items():
        kind, count = describe(value)
        group, note = KEY_INFO.get(str(key), ("其他", ""))
        buckets.setdefault(group, []).append(
            {"name": str(key), "type": kind, "count": count, "note": note}
        )
    groups = []
    for name in GROUP_ORDER:
        rows = buckets.get(name) or []
        if name == "其他":
            rows.sort(key=lambda row: row["name"])
        if rows:
            groups.append({"name": name, "keys": rows})
    return groups


def usable_units(units) -> tuple[list[dict], int]:
    ok: list[dict] = []
    bad = 0
    if not isinstance(units, list):
        return ok, 0
    needed = ("unit_master_id", "attribute", "create_time", "class", "unit_level", "source", "unit_id")
    for unit in units:
        if not isinstance(unit, dict) or any(key not in unit for key in needed):
            bad += 1
            continue
        try:
            datetime.strptime(str(unit["create_time"]), TIME_FMT)
        except (TypeError, ValueError):
            bad += 1
            continue
        ok.append(unit)
    return ok, bad


# 魔灵仓库的 building_master_id。放在这座建筑里的魔灵，身上的符文算仓库符文。
STORAGE_BUILDING = 25


def storage_building_ids(data: dict) -> set[int]:
    found: set[int] = set()
    for building in data.get("building_list") or []:
        if not isinstance(building, dict):
            continue
        try:
            if int(building.get("building_master_id") or 0) != STORAGE_BUILDING:
                continue
            found.add(int(building["building_id"]))
        except (TypeError, ValueError, KeyError):
            continue
    return found


def append_equipped_runes(data: dict, runes: list, bad_runes: int) -> tuple[list, int, int, int]:
    """库存之外，并进魔灵身上的符文。仓库里的和岛上正在穿的都算。"""
    storage_ids = storage_building_ids(data)
    seen = {rune.rune_id for rune in runes}
    stored = 0
    island = 0
    for unit in data.get("unit_list") or []:
        if not isinstance(unit, dict):
            continue
        try:
            in_storage = int(unit.get("building_id") or 0) in storage_ids
        except (TypeError, ValueError):
            in_storage = False
        for raw in unit.get("runes") or []:
            if not isinstance(raw, dict):
                continue
            try:
                rune = parse_rune(raw)
            except (TypeError, ValueError, KeyError):
                bad_runes += 1
                continue
            if rune.slot not in range(1, 7):
                bad_runes += 1
                continue
            if rune.rune_id in seen:
                continue
            seen.add(rune.rune_id)
            runes.append(rune)
            if in_storage:
                stored += 1
            else:
                island += 1
    return runes, bad_runes, stored, island


def load_packet(data: dict, filename: str) -> dict:
    warnings: list[str] = []
    command = data.get("command")
    if command and command != "HubUserLogin":
        warnings.append(f"command 是 {command}，不是 HubUserLogin")
    info = data.get("wizard_info") if isinstance(data.get("wizard_info"), dict) else {}
    units, bad_units = usable_units(data.get("unit_list"))
    if "unit_list" not in data:
        warnings.append("没有 unit_list，召唤记录页是空的")
    elif bad_units:
        warnings.append(f"跳过 {bad_units} 条无法读取的魔灵")
    runes = []
    raw_runes = data.get("runes")
    if not isinstance(raw_runes, list):
        warnings.append("没有 runes，符文配置页是空的")
        raw_runes = []
    bad_runes = 0
    for raw in raw_runes:
        try:
            rune = parse_rune(raw)
        except (TypeError, ValueError, KeyError):
            bad_runes += 1
            continue
        if rune.slot not in range(1, 7):
            bad_runes += 1
            continue
        runes.append(rune)
    runes, bad_runes, stored, island = append_equipped_runes(data, runes, bad_runes)
    if stored:
        warnings.append(f"魔灵仓库里还有 {stored} 颗符文，已并进配置")
    if island:
        warnings.append(f"岛上正在穿的还有 {island} 颗符文，已并进配置")
    if bad_runes:
        warnings.append(f"跳过 {bad_runes} 颗无法读取的符文")
    presets, skipped = rta_presets(data, runes, units)
    if presets:
        warnings.append(f"世界竞技场有 {len(presets)} 套，可一键导入")
    if skipped:
        warnings.append(f"世界竞技场有 {skipped} 套对不上四件套加两件套或散件，一键导入时会跳过")
    artifacts = data.get("artifacts")
    artifact_count = len(artifacts) if isinstance(artifacts, list) else 0
    overview = {
        "loaded": True,
        "filename": filename,
        "wizard": {
            "name": info.get("wizard_name") or "未命名",
            "id": info.get("wizard_id") or data.get("wizard_id") or "",
            "level": info.get("wizard_level"),
            "mana": info.get("wizard_mana"),
            "crystal": info.get("wizard_crystal"),
            "last_login": info.get("wizard_last_login") or "",
        },
        "counts": {
            "keys": len(data),
            "units": len(units),
            "runes": len(runes),
            "artifacts": artifact_count,
        },
        "warnings": warnings,
        "keys": catalog(data),
        "rta": presets,
    }
    with STORE.lock:
        STORE.filename = filename
        STORE.data = data
        STORE.units = units
        STORE.runes = runes
        STORE.warnings = warnings
        STORE.rta = presets
    return overview


MAX_SETS = 60
TWO_IDS = frozenset(TWO_OPTIONS)


def classify_equipped(runes: list) -> tuple[str, int, int | None] | None:
    """六颗符文收成四件套+两件套，或四件套+散件。无形可以补进其中一套。"""
    if len(runes) != 6 or len({rune.slot for rune in runes}) != 6:
        return None
    counts: dict[int, int] = {}
    for rune in runes:
        counts[rune.set_id] = counts.get(rune.set_id, 0) + 1
    intangible = counts.pop(INTANGIBLE, 0)
    chosen: tuple[tuple[int, int], int, int] | None = None
    for order, sid in enumerate(FOUR_OPTIONS):
        raw = counts.get(sid, 0)
        if raw <= 0 or max(0, 4 - raw) > intangible:
            continue
        rank = (min(raw, 4), -order)
        if chosen is None or rank > chosen[0]:
            chosen = (rank, sid, max(0, 4 - raw))
    if chosen is None:
        return None
    _, four, used_intangible = chosen
    left_intangible = intangible - used_intangible
    rest = dict(counts)
    leftover = rest.get(four, 0) - min(rest.get(four, 0), 4)
    if leftover > 0:
        rest[four] = leftover
    else:
        rest.pop(four, None)
    if sum(rest.values()) + left_intangible != 2:
        return None
    for sid, count in rest.items():
        need = 2 - count
        others = sum(value for other, value in rest.items() if other != sid)
        if sid in TWO_IDS and need >= 0 and need == left_intangible and others == 0:
            return "pair", four, sid
    return "broken", four, None


def current_mins(runes: list, mode: str, four: int, two: int | None, unit: dict) -> dict[str, int]:
    total = add_vec(sum_stats(tuple(runes)), bonus_vector(four, two if mode == "pair" else None))
    mins = {
        key: total[index]
        for index, key in enumerate(STAT_KEYS)
        if key not in PANEL_KEYS and total[index] > 0
    }
    if any(key not in unit for key in ("con", "atk", "def", "spd", "attribute")):
        return mins
    base = monster_base(unit)
    flats = [0, 0, 0]
    for rune in runes:
        for index, value in enumerate(rune.flats):
            flats[index] += value
    art = artifact_flats(unit)
    # 一键导入的绿字不含竞技场建筑，和默认展示一致。
    extra_pct = (0, 0, 0)
    extra_flat = (art["hp"], art["atk"], art["def"])
    stat_index = {key: index for index, key in enumerate(STAT_KEYS)}
    for index, key in enumerate(PANEL_KEYS):
        green = panel_value(
            base[key],
            total[stat_index[key]],
            flats[index],
            extra_pct[index],
            extra_flat[index],
        )
        if green > 0:
            mins[key] = green
    return mins


def rta_presets(data: dict, runes: list, units: list[dict]) -> tuple[list[dict], int]:
    links = data.get("world_arena_rune_equip_list")
    if not isinstance(links, list):
        return [], 0
    by_id = {rune.rune_id: rune for rune in runes}
    unit_by = {
        int(unit["unit_id"]): unit
        for unit in units
        if isinstance(unit, dict) and unit.get("unit_id")
    }
    grouped: dict[int, list[int]] = {}
    order: list[int] = []
    for link in links:
        if not isinstance(link, dict):
            continue
        try:
            unit_id = int(link.get("occupied_id") or 0)
            rune_id = int(link.get("rune_id") or 0)
        except (TypeError, ValueError):
            continue
        if not unit_id or not rune_id:
            continue
        if unit_id not in grouped:
            order.append(unit_id)
            grouped[unit_id] = []
        if rune_id not in grouped[unit_id]:
            grouped[unit_id].append(rune_id)
    presets: list[dict] = []
    skipped = 0
    for unit_id in order:
        if len(presets) >= MAX_SETS:
            break
        found = [by_id[rune_id] for rune_id in grouped[unit_id] if rune_id in by_id]
        if len(found) != 6:
            continue
        classified = classify_equipped(found)
        if classified is None:
            skipped += 1
            continue
        unit = unit_by.get(unit_id)
        if unit is None:
            continue
        mode, four, two = classified
        presets.append(
            {
                "unit_id": unit_id,
                "mode": mode,
                "four": four,
                "two": two,
                "mins": current_mins(found, mode, four, two, unit),
            }
        )
    return presets, skipped


def stat_list(values: tuple[int, ...]) -> list[dict]:
    return [
        {"key": key, "label": STAT_LABEL[key], "value": values[index]}
        for index, key in enumerate(STAT_KEYS)
    ]


def outcome_payload(outcome) -> dict:
    req = outcome.request
    payload = {
        "index": outcome.index,
        "title": f"{SET_NAME.get(req.four_set, req.four_set)} + "
        + ("散件" if req.mode == "broken" else SET_NAME.get(req.two_set or 0, "")),
        "mins": {key: req.mins[key] for key in STAT_KEYS if key in req.mins},
        "pool": outcome.pool,
        "excluded": outcome.excluded,
        "ok": outcome.build is not None,
        "message": outcome.message,
        "truncated": outcome.truncated,
        "notes": [],
        "runes": [],
        "spd": None,
        "four_slots": [],
        "other_slots": [],
        "other_label": "散件" if req.mode == "broken" else SET_NAME.get(req.two_set or 0, "两件套"),
        "rune_stats": [],
        "bonus": [],
        "total": [],
    }
    build = outcome.build
    if build is None or outcome.total is None or outcome.rune_stats is None or outcome.bonus is None:
        return payload
    notes: list[str] = []
    if outcome.fastest_spd is not None and build.spd < outcome.fastest_spd:
        notes.append(f"只看速度时可以到 {outcome.fastest_spd}，为满足下限用了 {build.spd}")
    elif "spd" not in req.mins and req.mins:
        notes.append("这是满足其他下限后的最快速度")
    elif "spd" not in req.mins:
        notes.append("未填速度下限，这是最快速度")
    if req.four_set == 3:
        notes.append("迅速的 +25% 速度按基础速度结算，没有加进上面的速度")
    four_name = SET_NAME.get(req.four_set, "")
    two_name = SET_NAME.get(req.two_set or 0, "")
    runes = []
    for rune in build.runes:
        if rune.set_id == INTANGIBLE:
            if rune.slot in build.four_slots:
                notes.append(f"槽{rune.slot} 无形计入{four_name}")
            elif req.mode == "pair":
                notes.append(f"槽{rune.slot} 无形计入{two_name}")
            else:
                notes.append(f"槽{rune.slot} 无形作为散件")
        runes.append(
            {
                "id": rune.rune_id,
                "slot": rune.slot,
                "set": SET_NAME.get(rune.set_id, str(rune.set_id)),
                "kind": rune_kind(rune),
                "level": rune.level,
                "main": fmt_eff(rune.main_id, rune.main_val),
                "innate": fmt_eff(rune.innate_id, rune.innate_val) if rune.innate_id else "",
                "subs": [text for text in (fmt_sub(sub) for sub in rune.subs) if text],
                "spd": rune.spd,
            }
        )
    if outcome.truncated:
        notes.append("搜索达到节点上限，这是已找到的最快可行组合，不保证还有更快的")
    payload.update(
        {
            "notes": notes,
            "runes": runes,
            "spd": build.spd,
            "four_slots": list(build.four_slots),
            "other_slots": list(build.other_slots),
            "rune_stats": stat_list(outcome.rune_stats),
            "bonus": [
                {"key": key, "label": STAT_LABEL[key], "value": outcome.bonus[index]}
                for index, key in enumerate(STAT_KEYS)
                if outcome.bonus[index]
            ],
            "total": stat_list(outcome.total),
        }
    )
    return payload


def rune_flats(rune) -> tuple[int, int, int]:
    return rune.flats


def glory_levels(deco_list: list) -> dict:
    found = {"hp": 0, "atk": 0, "def": 0, "spd": 0, "cd": 0}
    sanctuary = {1: 0, 2: 0, 3: 0, 4: 0, 5: 0}
    for deco in deco_list:
        if not isinstance(deco, dict):
            continue
        master = int(deco.get("master_id") or 0)
        level = int(deco.get("level") or 0)
        if level <= 0:
            continue
        spec = GLORY_PERCENT.get(master)
        if spec is not None:
            key, table = spec
            found[key] = table[min(level, len(table)) - 1]
            continue
        attr = SANCTUARY.get(master)
        if attr is not None:
            sanctuary[attr] = SANCTUARY_ATK[min(level, len(SANCTUARY_ATK)) - 1]
    found["sanctuary"] = sanctuary
    return found


def artifact_flats(unit: dict) -> dict[str, int]:
    flat = {"hp": 0, "atk": 0, "def": 0}
    for artifact in unit.get("artifacts") or []:
        if not isinstance(artifact, dict):
            continue
        pri = artifact.get("pri_effect") or []
        if len(pri) < 2:
            continue
        key = ARTIFACT_FLAT.get(int(pri[0]))
        if key:
            flat[key] += int(pri[1])
    return flat


def monster_base(unit: dict) -> dict[str, int]:
    return {
        "hp": int(unit["con"]) * HP_FACTOR,
        "atk": int(unit["atk"]),
        "def": int(unit["def"]),
        "spd": int(unit["spd"]),
        "cr": int(unit.get("critical_rate") or 0),
        "cd": int(unit.get("critical_damage") or 0),
        "acc": int(unit.get("accuracy") or 0),
        "res": int(unit.get("resist") or 0),
    }


def monster_rows() -> list[dict]:
    with STORE.lock:
        units = list(STORE.units)
        loaded = STORE.data is not None
        deco = list((STORE.data or {}).get("deco_list") or [])
    if not loaded:
        raise ValueError("先导入 JSON")
    glory = glory_levels(deco)
    rows = []
    for unit in units:
        if any(key not in unit for key in ("con", "atk", "def", "spd", "unit_id")):
            continue
        named = to_row(unit, SWEX_NAMES)
        stars = NATURAL_STARS.get(int(unit["unit_master_id"]))
        if stars:
            named["natural_stars"] = stars
        base = monster_base(unit)
        attr = int(named["attribute_id"] or 0)
        flat = artifact_flats(unit)
        rows.append(
            {
                "unit_id": unit["unit_id"],
                "name": named["name"],
                "attribute": named["attribute"],
                "attribute_id": named["attribute_id"],
                "level": unit["unit_level"],
                "stars": unit["class"],
                "natural_stars": named["natural_stars"],
                "avatar": named["avatar"],
                "base": base,
                "account": {
                    "hp": glory["hp"],
                    "atk": glory["atk"] + glory["sanctuary"].get(attr, 0),
                    "def": glory["def"],
                    "spd": glory["spd"],
                    "cd": glory["cd"],
                    "flat": flat,
                },
            }
        )
    rows.sort(key=lambda row: (row["name"], -row["level"], row["unit_id"]))
    return rows


def monsters_for(rows: list) -> list[dict | None]:
    wanted: list[int | None] = []
    for index, row in enumerate(rows, 1):
        if not isinstance(row, dict):
            raise ValueError(f"第 {index} 套格式不对")
        raw = row.get("unit_id")
        if raw in (None, "", 0):
            wanted.append(None)
            continue
        try:
            wanted.append(int(raw))
        except (TypeError, ValueError) as exc:
            raise ValueError(f"第 {index} 套的魔灵无效") from exc
    if not any(item is not None for item in wanted):
        return [None] * len(wanted)
    catalog = {int(item["unit_id"]): item for item in monster_rows()}
    found: list[dict | None] = []
    for index, unit_id in enumerate(wanted, 1):
        if unit_id is None:
            found.append(None)
            continue
        monster = catalog.get(unit_id)
        if monster is None:
            raise ValueError(f"第 {index} 套没有这只魔灵")
        found.append(monster)
    return found


def bind_panel_base(requests: list[SetRequest], monsters: list[dict | None]) -> list[SetRequest]:
    bound: list[SetRequest] = []
    for index, (req, monster) in enumerate(zip(requests, monsters), 1):
        filled = [key for key in PANEL_KEYS if key in req.mins]
        if monster is None:
            if filled:
                names = "、".join(PANEL_INPUT[key] for key in filled)
                raise ValueError(f"第 {index} 套的{names}填绿字，要先选魔灵")
            bound.append(req)
            continue
        base = (monster["base"]["hp"], monster["base"]["atk"], monster["base"]["def"])
        account = monster.get("account") or {}
        flat = account.get("flat") or {}
        bound.append(
            SetRequest(
                req.mode,
                req.four_set,
                req.two_set,
                req.mins,
                base,
                (account.get("hp", 0), account.get("atk", 0), account.get("def", 0)),
                (flat.get("hp", 0), flat.get("atk", 0), flat.get("def", 0)),
            )
        )
    return bound


def panel_for(monster: dict, outcome) -> dict:
    base = monster["base"]
    account = monster.get("account") or {}
    art = account.get("flat") or {}
    percent = {key: outcome.total[index] for index, key in enumerate(STAT_KEYS)}
    flat_hp, flat_atk, flat_def = 0, 0, 0
    for rune in outcome.build.runes:
        hp, atk, defense = rune_flats(rune)
        flat_hp += hp
        flat_atk += atk
        flat_def += defense
    swift = 25 if outcome.request.four_set == 3 else 0
    # 这里的绿字只含符文、套装和神器。竞技场建筑和队长技能由页面按勾选加上。
    swift_spd = percent_ceil(base["spd"], swift)
    building = {
        "hp": int(account.get("hp") or 0),
        "atk": int(account.get("atk") or 0),
        "def": int(account.get("def") or 0),
        "spd": int(account.get("spd") or 0) / 10,
        "cd": int(account.get("cd") or 0),
    }
    artifact = {
        "hp": int(art.get("hp") or 0),
        "atk": int(art.get("atk") or 0),
        "def": int(art.get("def") or 0),
    }
    green = {
        "hp": base["hp"] * percent["hp"] // 100 + flat_hp + artifact["hp"],
        "atk": base["atk"] * percent["atk"] // 100 + flat_atk + artifact["atk"],
        "def": base["def"] * percent["def"] // 100 + flat_def + artifact["def"],
        "spd": outcome.build.spd + swift_spd,
        "cr": percent["cr"],
        "cd": percent["cd"],
        "acc": percent["acc"],
        "res": percent["res"],
    }
    lines = []
    for key in STAT_KEYS:
        lines.append(
            {
                "key": key,
                "label": PANEL_LABEL[key],
                "white": base[key],
                "green": green[key],
                "total": base[key] + green[key],
            }
        )
    return {
        "unit_id": monster["unit_id"],
        "name": monster["name"],
        "attribute": monster["attribute"],
        "avatar": monster.get("avatar") or "",
        "level": monster["level"],
        "stars": monster["stars"],
        "swift": swift,
        "swift_spd": swift_spd,
        "rune_spd": outcome.build.spd,
        "spd_tenths": int(account.get("spd") or 0),
        "flat": {"hp": flat_hp, "atk": flat_atk, "def": flat_def},
        "percent": {key: percent[key] for key in STAT_KEYS if key != "spd"},
        "building": building,
        "artifact": artifact,
        "lines": lines,
    }


def parse_requests(payload: dict) -> tuple[list[SetRequest], set[int]]:
    rows = payload.get("sets")
    if not isinstance(rows, list) or not rows:
        raise ValueError("至少添加一套")
    if len(rows) > MAX_SETS:
        raise ValueError(f"最多 {MAX_SETS} 套")
    allow: set[int] = set()
    for raw in payload.get("allow") or []:
        sid = int(raw)
        if sid not in PREMIUM_IDS:
            raise ValueError("散件开关只能是暴走、绝望、意志")
        allow.add(sid)
    requests: list[SetRequest] = []
    for index, row in enumerate(rows, 1):
        if not isinstance(row, dict):
            raise ValueError(f"第 {index} 套格式不对")
        mode = row.get("mode")
        if mode not in {"pair", "broken"}:
            raise ValueError(f"第 {index} 套模式不对")
        four = int(row.get("four"))
        if four not in FOUR_OPTIONS:
            raise ValueError(f"第 {index} 套的四件套不在可选范围内")
        two = None
        if mode == "pair":
            two = int(row.get("two"))
            if two not in TWO_OPTIONS:
                raise ValueError(f"第 {index} 套的两件套不在可选范围内")
        mins: dict[str, int] = {}
        raw_mins = row.get("mins") or {}
        if not isinstance(raw_mins, dict):
            raise ValueError(f"第 {index} 套的下限格式不对")
        for key, value in raw_mins.items():
            if key not in STAT_KEYS:
                raise ValueError(f"第 {index} 套有未知属性 {key}")
            if value is None or value == "":
                continue
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise ValueError(f"第 {index} 套的{STAT_LABEL[key]}要填非负整数")
            mins[key] = value
        requests.append(SetRequest(mode=mode, four_set=four, two_set=two, mins=mins))
    return requests, allow


def meta_payload() -> dict:
    return {
        "attrs": [{"id": key, "name": name} for key, name in ATTR_CN.items()],
        "sources": [
            {"id": "summon", "name": "常规召唤"},
            {"id": "all", "name": "全部来源"},
            *[{"id": str(key), "name": f"{label} ({key})"} for key, label in SOURCE.items()],
        ],
        "stars": [1, 2, 3, 4, 5],
        "four": [{"id": sid, "name": SET_NAME[sid]} for sid in FOUR_OPTIONS],
        "two": [{"id": sid, "name": SET_NAME[sid]} for sid in TWO_OPTIONS],
        "stats": [
            {"key": key, "label": PANEL_INPUT.get(key, STAT_LABEL[key]), "hint": STAT_HINT[key]}
            for key in STAT_KEYS
        ],
        "premium": [{"id": sid, "name": name} for sid, name in PREMIUM],
        "leaders": [{"id": f"{stat}:{percent}", "name": name} for stat, percent, name in LEADER_OPTIONS],
    }


def summon_filter(payload: dict) -> dict:
    with STORE.lock:
        units = STORE.units
        loaded = STORE.data is not None
    if not loaded:
        raise ValueError("先导入 JSON")
    attrs_raw = payload.get("attrs")
    stars_raw = payload.get("stars")
    attrs = None
    if attrs_raw:
        attrs = {int(item) for item in attrs_raw}
        if not attrs <= set(ATTR_CN):
            raise ValueError("属性只能是水火风光暗")
    stars = None
    if stars_raw:
        stars = {int(item) for item in stars_raw}
        if not stars <= {1, 2, 3, 4, 5}:
            raise ValueError("初始星只能是 1 到 5")
    source_raw = payload.get("source") or "summon"
    if source_raw in {"summon", "all"}:
        source: str | set[int] = source_raw
    else:
        source = {int(part) for part in str(source_raw).replace("，", ",").split(",") if part.strip()}
    rows = filter_rows(units, attrs, stars, source, False, SWEX_NAMES)
    query = str(payload.get("q") or "").strip().lower()
    if query:
        rows = [
            row
            for row in rows
            if query in row["name"].lower() or query in str(row["unit_master_id"])
        ]
    return {"count": len(rows), "rows": rows}


class Handler(BaseHTTPRequestHandler):
    server_version = "sw-json/1.0"

    def log_message(self, fmt: str, *args) -> None:
        print(f"{self.address_string()} {fmt % args}")

    def do_GET(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        if parsed.path == "/favicon.ico":
            self._empty(204)
            return
        if parsed.path == "/api/meta":
            self._json(200, meta_payload())
            return
        if parsed.path == "/api/state":
            self._json(200, self._state())
            return
        if parsed.path == "/api/parse":
            self._parse(parse_qs(parsed.query))
            return
        if parsed.path == "/api/monsters":
            try:
                self._json(200, {"monsters": monster_rows()})
            except ValueError as exc:
                self._json(400, {"error": str(exc)})
            return
        if parsed.path in {"/", "/index.html"}:
            self._file(STATIC / "index.html")
            return
        rel = unquote(parsed.path.lstrip("/"))
        target = (STATIC / rel).resolve()
        if STATIC.resolve() not in target.parents and target != STATIC.resolve():
            self._json(404, {"error": "没有这个页面"})
            return
        self._file(target)

    def do_POST(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        try:
            payload = self._body_json() if parsed.path != "/api/import" else None
        except ValueError as exc:
            self._json(400, {"error": str(exc)})
            return
        try:
            if parsed.path == "/api/import":
                self._import()
                return
            if parsed.path == "/api/summons":
                self._json(200, summon_filter(payload or {}))
                return
            if parsed.path == "/api/runes/solve":
                self._solve(payload or {})
                return
        except ValueError as exc:
            self._json(400, {"error": str(exc)})
            return
        except Exception as exc:
            self._json(500, {"error": f"处理失败：{exc}"})
            return
        self._json(404, {"error": "没有这个接口"})

    def _state(self) -> dict:
        with STORE.lock:
            if STORE.data is None:
                return {"loaded": False}
            data = STORE.data
            filename = STORE.filename
        return load_view(data, filename)

    def _import(self) -> None:
        length = int(self.headers.get("Content-Length") or "0")
        if length <= 0:
            self._json(400, {"error": "没有收到文件内容"})
            return
        if length > MAX_BODY:
            self._json(413, {"error": "文件超过 200MB"})
            return
        body = self.rfile.read(length)
        if body.startswith(b"\xef\xbb\xbf"):
            body = body[3:]
        try:
            data = json.loads(body.decode("utf-8"))
        except UnicodeDecodeError:
            self._json(400, {"error": "文件不是 UTF-8"})
            return
        except json.JSONDecodeError as exc:
            self._json(400, {"error": f"不是合法 JSON：{exc.msg}（第 {exc.lineno} 行）"})
            return
        if not isinstance(data, dict):
            self._json(400, {"error": "根节点需要是对象。请导入完整登录包，而不是单个数组"})
            return
        filename = unquote(self.headers.get("X-Filename") or "login.json")
        self._json(200, load_packet(data, filename))

    def _parse(self, query: dict[str, list[str]]) -> None:
        with STORE.lock:
            data = STORE.data
        if data is None:
            self._json(400, {"error": "先导入 JSON"})
            return
        key = (query.get("key") or [""])[0]
        if not key:
            self._json(200, {"groups": catalog(data)})
            return
        if key not in data:
            self._json(404, {"error": f"没有字段 {key}"})
            return
        value = "已隐藏" if key in REDACT else data[key]
        kind, count = describe(data[key])
        group, note = KEY_INFO.get(key, ("其他", ""))
        text = json.dumps(preview(value), ensure_ascii=False, indent=2)
        if len(text) > 80000:
            text = text[:80000] + "\n…（预览已截断）"
        self._json(
            200,
            {"name": key, "type": kind, "count": count, "group": group, "note": note, "text": text},
        )

    def _solve(self, payload: dict) -> None:
        requests, allow = parse_requests(payload)
        with STORE.lock:
            runes = list(STORE.runes)
            loaded = STORE.data is not None
        if not loaded:
            raise ValueError("先导入 JSON")
        if len(runes) < 6:
            raise ValueError(f"可用符文只有 {len(runes)} 颗，凑不齐一套")
        monsters = monsters_for(payload.get("sets") or [])
        requests = bind_panel_base(requests, monsters)
        started = time.perf_counter()
        outcomes = solve_sequence(runes, requests, allow)
        sets = []
        for item, monster in zip(outcomes, monsters):
            body = outcome_payload(item)
            if monster is not None and item.build is not None and item.total is not None:
                body["panel"] = panel_for(monster, item)
            sets.append(body)
        self._json(
            200,
            {
                "elapsed": round(time.perf_counter() - started, 2),
                "rule": broken_rule_text(allow),
                "sets": sets,
            },
        )

    def _body_json(self) -> dict:
        length = int(self.headers.get("Content-Length") or "0")
        if length <= 0:
            return {}
        if length > MAX_BODY:
            raise ValueError("请求超过 200MB")
        body = self.rfile.read(length)
        try:
            data = json.loads(body.decode("utf-8") or "{}")
        except json.JSONDecodeError as exc:
            raise ValueError(f"请求不是合法 JSON：{exc.msg}") from exc
        if not isinstance(data, dict):
            raise ValueError("请求体需要是对象")
        return data

    def _file(self, path: Path) -> None:
        if not path.is_file():
            self._json(404, {"error": "没有这个文件"})
            return
        kind = {
            ".html": "text/html; charset=utf-8",
            ".css": "text/css; charset=utf-8",
            ".js": "text/javascript; charset=utf-8",
        }.get(path.suffix.lower(), "application/octet-stream")
        data = path.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", kind)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()
        self.wfile.write(data)

    def _json(self, status: int, payload: dict) -> None:
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def _empty(self, status: int) -> None:
        self.send_response(status)
        self.end_headers()


def load_view(data: dict, filename: str) -> dict:
    """已导入状态下刷新页面时重建概览，不再解析符文。"""
    info = data.get("wizard_info") if isinstance(data.get("wizard_info"), dict) else {}
    artifacts = data.get("artifacts")
    with STORE.lock:
        units = len(STORE.units)
        runes = len(STORE.runes)
        warnings = list(STORE.warnings)
        rta = list(STORE.rta)
    return {
        "loaded": True,
        "filename": filename,
        "wizard": {
            "name": info.get("wizard_name") or "未命名",
            "id": info.get("wizard_id") or data.get("wizard_id") or "",
            "level": info.get("wizard_level"),
            "mana": info.get("wizard_mana"),
            "crystal": info.get("wizard_crystal"),
            "last_login": info.get("wizard_last_login") or "",
        },
        "counts": {
            "keys": len(data),
            "units": units,
            "runes": runes,
            "artifacts": len(artifacts) if isinstance(artifacts, list) else 0,
        },
        "warnings": warnings,
        "keys": catalog(data),
        "rta": rta,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="本地查看登录包、召唤记录和符文配置")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--open", action="store_true", help="启动后打开浏览器")
    args = parser.parse_args()
    server = ThreadingHTTPServer(("127.0.0.1", args.port), Handler)
    server.daemon_threads = True
    url = f"http://127.0.0.1:{args.port}/"
    print(f"魔灵 JSON 网页已启动：{url}", flush=True)
    if args.open:
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n已停止")


if __name__ == "__main__":
    main()
