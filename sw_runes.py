"""符文配置：按套装和属性下限依次配出最快速度。

图形界面::

    python sw_runes.py
    python sw_runes.py ../某账号/runes.json

生命 / 攻击 / 防御按百分比合计，不含平值。速度是六颗符文的速度之和，
不含迅速对基础速度的 +25%。其余百分比含套装加成。
"""

from __future__ import annotations

import json
import sys
import threading
import time
import tkinter as tk
from collections import defaultdict
from dataclasses import dataclass
from itertools import combinations
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from tkinter.scrolledtext import ScrolledText

HERE = Path(__file__).resolve().parent
JSO = HERE.parent

STAT_KEYS = ("hp", "atk", "def", "spd", "cr", "cd", "acc", "res")
STAT_LABEL = {
    "hp": "生命%",
    "atk": "攻击%",
    "def": "防御%",
    "spd": "速度",
    "cr": "暴击%",
    "cd": "爆伤%",
    "acc": "命中%",
    "res": "抵抗%",
}
STAT_CN = {
    1: "生命",
    2: "生命%",
    3: "攻击",
    4: "攻击%",
    5: "防御",
    6: "防御%",
    8: "速度",
    9: "暴击%",
    10: "爆伤%",
    11: "抵抗%",
    12: "命中%",
}
ID_TO_IDX = {2: 0, 4: 1, 6: 2, 8: 3, 9: 4, 10: 5, 12: 6, 11: 7}
KEY_INDEX = {key: index for index, key in enumerate(STAT_KEYS)}

SET_NAME = {
    1: "生命",
    2: "守护",
    3: "迅速",
    4: "刀刃",
    5: "激怒",
    6: "集中",
    7: "忍耐",
    8: "猛攻",
    10: "绝望",
    11: "吸血",
    13: "暴走",
    14: "应报",
    15: "意志",
    16: "保护",
    17: "反击",
    18: "覆灭",
    19: "斗志",
    20: "决心",
    21: "发扬",
    22: "命中",
    23: "韧性",
    24: "封印",
    25: "无形",
}

FOUR_OPTIONS = (3, 13, 10, 8, 5, 11)
TWO_OPTIONS = (15, 4, 1, 2, 6, 7, 14, 17, 16, 18, 19, 20, 21, 22, 23, 24)
TWO_PIECE = frozenset(TWO_OPTIONS)
PREMIUM = ((13, "暴走"), (10, "绝望"), (15, "意志"))
PREMIUM_IDS = frozenset(sid for sid, _ in PREMIUM)
INTANGIBLE = 25
GRADE_CN = {1: "普通", 2: "魔法", 3: "稀有", 4: "英雄", 5: "传说"}

# 套装直接加在百分比上。迅速是基础速度的 25%，不加进符文速度。
SET_BONUS: dict[int, dict[str, int]] = {
    1: {"hp": 15},
    2: {"def": 15},
    4: {"cr": 12},
    5: {"cd": 40},
    6: {"acc": 20},
    7: {"res": 20},
    8: {"atk": 35},
    19: {"atk": 8},
    20: {"def": 8},
    21: {"hp": 8},
    22: {"acc": 10},
    23: {"res": 10},
}

SEARCH_NODE_LIMIT = 4_000_000
FONT = ("Microsoft YaHei UI", 10)


@dataclass(frozen=True, slots=True)
class Rune:
    rune_id: int
    slot: int
    set_id: int
    stars: int
    ancient: bool
    grade: int
    level: int
    main_id: int
    main_val: int
    innate_id: int
    innate_val: int
    subs: tuple[tuple[int, int, int, int], ...]
    stats: tuple[int, int, int, int, int, int, int, int]
    spd: int
    flats: tuple[int, int, int]


@dataclass(frozen=True, slots=True)
class Build:
    runes: tuple[Rune, ...]
    four_slots: tuple[int, ...]

    @property
    def spd(self) -> int:
        return sum(rune.spd for rune in self.runes)

    @property
    def other_slots(self) -> tuple[int, ...]:
        used = set(self.four_slots)
        return tuple(slot for slot in range(1, 7) if slot not in used)


@dataclass(frozen=True)
class SetRequest:
    mode: str
    four_set: int
    two_set: int | None
    mins: dict[str, int]
    # 有白字时，生命 / 攻击 / 防御的下限是绿字固定值；否则这三项仍是百分比。
    base: tuple[int, int, int] | None = None
    # 荣耀建筑百分比，以及神器主属性平值。绿字 = 白字 × (符文% + 建筑%) + 符文平值 + 神器平值。
    extra_pct: tuple[int, int, int] = (0, 0, 0)
    extra_flat: tuple[int, int, int] = (0, 0, 0)


@dataclass
class Outcome:
    index: int
    request: SetRequest
    build: Build | None
    rune_stats: tuple[int, ...] | None
    bonus: tuple[int, ...] | None
    total: tuple[int, ...] | None
    fastest_spd: int | None
    pool: int
    excluded: int
    message: str = ""
    truncated: bool = False
    nodes: int = 0


def rune_key(rune: Rune) -> tuple[int, int, int, int, int]:
    extra = sum(rune.stats) - rune.spd
    return (rune.spd, extra, rune.level, rune.grade, -rune.rune_id)


def build_key(runes: tuple[Rune, ...]) -> tuple[int, int, int]:
    spd = sum(rune.spd for rune in runes)
    extra = sum(sum(rune.stats) for rune in runes) - spd
    level = sum(rune.level for rune in runes)
    return (spd, extra, level)


def bonus_vector(four_set: int, two_set: int | None) -> tuple[int, ...]:
    acc = [0] * 8
    for set_id in (four_set, two_set):
        if set_id is None:
            continue
        for key, value in SET_BONUS.get(set_id, {}).items():
            acc[KEY_INDEX[key]] += value
    return tuple(acc)


def sum_stats(runes: tuple[Rune, ...]) -> tuple[int, ...]:
    acc = [0] * 8
    for rune in runes:
        for index, value in enumerate(rune.stats):
            acc[index] += value
    return tuple(acc)


def add_vec(left: tuple[int, ...], right: tuple[int, ...]) -> tuple[int, ...]:
    return tuple(a + b for a, b in zip(left, right))


def meets(total: tuple[int, ...], mins: dict[str, int]) -> bool:
    return all(total[KEY_INDEX[key]] >= need for key, need in mins.items())


def panel_value(
    white: int,
    rune_pct: int,
    rune_flat: int,
    extra_pct: int,
    extra_flat: int,
) -> int:
    return white * (rune_pct + extra_pct) // 100 + rune_flat + extra_flat


def panel_meets(
    build: Build,
    total: tuple[int, ...],
    base: tuple[int, int, int] | None,
    panel_need: tuple[int, int, int],
    extra_pct: tuple[int, int, int] = (0, 0, 0),
    extra_flat: tuple[int, int, int] = (0, 0, 0),
) -> bool:
    if base is None or not any(panel_need):
        return True
    flats = [0, 0, 0]
    for rune in build.runes:
        for index in range(3):
            flats[index] += rune.flats[index]
    return all(
        not panel_need[index]
        or panel_value(
            base[index], total[index], flats[index], extra_pct[index], extra_flat[index]
        )
        >= panel_need[index]
        for index in range(3)
    )


def forms_two_set(left: Rune, right: Rune) -> bool:
    """两颗散件如果能凑成两件套，就不再算散件。"""
    if left.set_id == INTANGIBLE and right.set_id == INTANGIBLE:
        return True
    if left.set_id == INTANGIBLE:
        return right.set_id in TWO_PIECE
    if right.set_id == INTANGIBLE:
        return left.set_id in TWO_PIECE
    return left.set_id == right.set_id and left.set_id in TWO_PIECE


def dominates(
    better: Rune,
    worse: Rune,
    dims: tuple[int, ...],
    flat_dims: tuple[int, ...] = (),
) -> bool:
    if better.spd < worse.spd:
        return False
    for index in dims:
        if better.stats[index] < worse.stats[index]:
            return False
    for index in flat_dims:
        if better.flats[index] < worse.flats[index]:
            return False
    if better.spd > worse.spd:
        return True
    for index in dims:
        if better.stats[index] > worse.stats[index]:
            return True
    for index in flat_dims:
        if better.flats[index] > worse.flats[index]:
            return True
    return (better.level, better.grade, -better.rune_id) > (
        worse.level,
        worse.grade,
        -worse.rune_id,
    )


def pareto(
    runes: list[Rune],
    dims: tuple[int, ...],
    flat_dims: tuple[int, ...] = (),
) -> list[Rune]:
    kept: list[Rune] = []
    for rune in runes:
        nxt: list[Rune] = []
        dominated = False
        for other in kept:
            if dominates(other, rune, dims, flat_dims):
                dominated = True
                break
            if not dominates(rune, other, dims, flat_dims):
                nxt.append(other)
        if dominated:
            continue
        nxt.append(rune)
        kept = nxt
    return kept


FLAT_ID = {1: 0, 3: 1, 5: 2}


def flat_values(
    main_id: int,
    main_val: int,
    innate_id: int,
    innate_val: int,
    subs: list[tuple[int, int, int, int]] | tuple[tuple[int, int, int, int], ...],
) -> tuple[int, int, int]:
    acc = [0, 0, 0]

    def add(stat_id: int, value: int) -> None:
        index = FLAT_ID.get(stat_id)
        if index is not None and value:
            acc[index] += value

    add(main_id, main_val)
    add(innate_id, innate_val)
    for stat_id, base, _enchanted, grind in subs:
        add(stat_id, base + grind)
    return acc[0], acc[1], acc[2]


def parse_rune(raw: dict) -> Rune:
    try:
        stats = [0] * 8

        def add(stat_id: int, value: int) -> None:
            index = ID_TO_IDX.get(stat_id)
            if index is not None and value:
                stats[index] += value

        pri = raw["pri_eff"]
        pre = raw["prefix_eff"]
        add(int(pri[0]), int(pri[1]))
        add(int(pre[0]), int(pre[1]))
        subs: list[tuple[int, int, int, int]] = []
        for sec in raw.get("sec_eff") or []:
            stat_id = int(sec[0])
            base = int(sec[1]) if len(sec) > 1 else 0
            enchanted = int(sec[2]) if len(sec) > 2 else 0
            grind = int(sec[3]) if len(sec) > 3 else 0
            add(stat_id, base + grind)
            subs.append((stat_id, base, enchanted, grind))
        stats_t = (
            stats[0],
            stats[1],
            stats[2],
            stats[3],
            stats[4],
            stats[5],
            stats[6],
            stats[7],
        )
        rank = int(raw["rank"])
        clazz = int(raw["class"])
        return Rune(
            rune_id=int(raw["rune_id"]),
            slot=int(raw["slot_no"]),
            set_id=int(raw["set_id"]),
            stars=clazz % 10,
            ancient=clazz >= 10 or rank >= 10,
            grade=rank % 10,
            level=int(raw["upgrade_curr"]),
            main_id=int(pri[0]),
            main_val=int(pri[1]),
            innate_id=int(pre[0]),
            innate_val=int(pre[1]),
            subs=tuple(subs),
            stats=stats_t,
            spd=stats_t[3],
            flats=flat_values(int(pri[0]), int(pri[1]), int(pre[0]), int(pre[1]), subs),
        )
    except (KeyError, TypeError, ValueError, IndexError) as exc:
        rid = raw.get("rune_id") if isinstance(raw, dict) else "?"
        raise ValueError(f"符文 {rid} 无法解析：{exc}") from exc


def load_runes(path: Path) -> list[Rune]:
    if not path.is_file():
        raise FileNotFoundError(f"找不到文件：{path}")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"不是合法 JSON：{exc}") from exc
    if isinstance(data, dict):
        if "runes" not in data:
            raise ValueError("这份 JSON 没有 runes 字段")
        data = data["runes"]
    if not isinstance(data, list):
        raise ValueError("符文数据需要是数组，或带 runes 字段的登录包")
    seen: set[int] = set()
    runes: list[Rune] = []
    for raw in data:
        rune = parse_rune(raw)
        if rune.rune_id in seen or rune.slot not in range(1, 7):
            continue
        seen.add(rune.rune_id)
        runes.append(rune)
    return runes


def index_slots(runes: list[Rune]) -> dict[int, list[Rune]]:
    by = {slot: [] for slot in range(1, 7)}
    for rune in runes:
        by[rune.slot].append(rune)
    return by


def slot_group(
    runes: list[Rune],
    slot: int,
    four_slots: set[int],
    req: SetRequest,
    allow: set[int],
) -> list[Rune]:
    if slot in four_slots:
        return [rune for rune in runes if rune.set_id == req.four_set or rune.set_id == INTANGIBLE]
    if req.mode == "pair":
        return [rune for rune in runes if rune.set_id == req.two_set or rune.set_id == INTANGIBLE]
    return [
        rune
        for rune in runes
        if rune.set_id not in PREMIUM_IDS or rune.set_id in allow
    ]


def best_broken_pair(left: list[Rune], right: list[Rune]) -> tuple[Rune, Rune] | None:
    def reps(runes: list[Rune]) -> list[Rune]:
        best: dict[int, Rune] = {}
        for rune in runes:
            old = best.get(rune.set_id)
            if old is None or rune_key(rune) > rune_key(old):
                best[rune.set_id] = rune
        return list(best.values())

    found: tuple[Rune, Rune] | None = None
    found_key: tuple[int, int, int] | None = None
    for a in reps(left):
        for b in reps(right):
            if forms_two_set(a, b):
                continue
            key = (
                a.spd + b.spd,
                (sum(a.stats) + sum(b.stats)) - (a.spd + b.spd),
                a.level + b.level,
            )
            if found_key is None or key > found_key:
                found_key = key
                found = (a, b)
    return found


def assemble_fast(
    by: dict[int, list[Rune]],
    four_slots: set[int],
    req: SetRequest,
    allow: set[int],
) -> Build | None:
    groups = {
        slot: slot_group(by[slot], slot, four_slots, req, allow) for slot in range(1, 7)
    }
    if any(not groups[slot] for slot in range(1, 7)):
        return None
    chosen: dict[int, Rune] = {}
    other = [slot for slot in range(1, 7) if slot not in four_slots]
    if req.mode == "broken":
        for slot in range(1, 7):
            if slot not in other:
                chosen[slot] = max(groups[slot], key=rune_key)
        pair = best_broken_pair(groups[other[0]], groups[other[1]])
        if pair is None:
            return None
        chosen[other[0]], chosen[other[1]] = pair
    else:
        for slot in range(1, 7):
            chosen[slot] = max(groups[slot], key=rune_key)
    return Build(tuple(chosen[slot] for slot in range(1, 7)), tuple(sorted(four_slots)))


def tighten(
    lists: list[list[Rune]],
    need: list[int],
    bonus: tuple[int, ...],
    dims: tuple[int, ...],
    spd_min: int,
    panel_white: tuple[int, int, int] | None = None,
    panel_need: tuple[int, int, int] = (0, 0, 0),
    extra_pct: tuple[int, int, int] = (0, 0, 0),
    extra_flat: tuple[int, int, int] = (0, 0, 0),
) -> list[list[Rune]]:
    current = [list(group) for group in lists]
    for _ in range(6):
        if any(not group for group in current):
            return current
        max_stat = [
            [max(rune.stats[index] for rune in group) for index in range(8)] for group in current
        ]
        max_spd = [max(rune.spd for rune in group) for group in current]
        max_flat = [
            [max(rune.flats[index] for rune in group) for index in range(3)] for group in current
        ]
        changed = False
        nxt: list[list[Rune]] = []
        spd_all = sum(max_spd)
        flat_all = [sum(slot[index] for slot in max_flat) for index in range(3)]
        for index, group in enumerate(current):
            others_spd = spd_all - max_spd[index]
            others = [
                sum(max_stat[slot][stat] for slot in range(6)) + bonus[stat] - max_stat[index][stat]
                for stat in range(8)
            ]
            others_flat = [flat_all[stat] - max_flat[index][stat] for stat in range(3)]
            kept = []
            for rune in group:
                if rune.spd + others_spd < spd_min:
                    continue
                if any(rune.stats[stat] + others[stat] < need[stat] for stat in dims):
                    continue
                if panel_white is not None and any(
                    panel_need[stat]
                    and panel_value(
                        panel_white[stat],
                        rune.stats[stat] + others[stat],
                        rune.flats[stat] + others_flat[stat],
                        extra_pct[stat],
                        extra_flat[stat],
                    )
                    < panel_need[stat]
                    for stat in range(3)
                ):
                    continue
                kept.append(rune)
            if len(kept) != len(group):
                changed = True
            nxt.append(kept)
        current = nxt
        if not changed:
            break
    return current


def search_constrained(
    lists: list[list[Rune]],
    four_slots: tuple[int, ...],
    bonus: tuple[int, ...],
    need: list[int],
    dims: tuple[int, ...],
    holder: list,
    nodes: list[int],
    stop: list[bool],
    check_pair: bool,
    panel_white: tuple[int, int, int] | None = None,
    panel_need: tuple[int, int, int] = (0, 0, 0),
    extra_pct: tuple[int, int, int] = (0, 0, 0),
    extra_flat: tuple[int, int, int] = (0, 0, 0),
) -> None:
    ordered = [
        sorted(group, key=lambda rune: (-rune.spd, -(sum(rune.stats) - rune.spd), -rune.level))
        for group in lists
    ]
    if any(not group for group in ordered):
        return
    order = sorted(range(6), key=lambda index: len(ordered[index]))
    max_spd = [max(rune.spd for rune in ordered[index]) for index in range(6)]
    max_stat = [
        [max(rune.stats[stat] for rune in ordered[index]) for stat in range(8)]
        for index in range(6)
    ]
    max_flat = [
        [max(rune.flats[stat] for rune in ordered[index]) for stat in range(3)]
        for index in range(6)
    ]
    suf_spd = [0] * 7
    suf_stat = [[0] * 8 for _ in range(7)]
    suf_flat = [[0] * 3 for _ in range(7)]
    for depth in range(5, -1, -1):
        index = order[depth]
        suf_spd[depth] = suf_spd[depth + 1] + max_spd[index]
        for stat in range(8):
            suf_stat[depth][stat] = suf_stat[depth + 1][stat] + max_stat[index][stat]
        for stat in range(3):
            suf_flat[depth][stat] = suf_flat[depth + 1][stat] + max_flat[index][stat]

    pick: list[Rune | None] = [None] * 6
    stats = [0] * 8
    flats = [0, 0, 0]
    pair_idx = tuple(slot - 1 for slot in range(1, 7) if slot not in four_slots) if check_pair else ()

    def panel_short(depth: int) -> bool:
        if panel_white is None:
            return False
        for stat in range(3):
            if not panel_need[stat]:
                continue
            upper = panel_value(
                panel_white[stat],
                stats[stat] + suf_stat[depth][stat] + bonus[stat],
                flats[stat] + suf_flat[depth][stat],
                extra_pct[stat],
                extra_flat[stat],
            )
            if upper < panel_need[stat]:
                return True
        return False

    def dfs(depth: int, spd: int) -> None:
        if stop[0]:
            return
        nodes[0] += 1
        if nodes[0] > SEARCH_NODE_LIMIT:
            stop[0] = True
            return
        if spd + suf_spd[depth] <= holder[0]:
            return
        for stat in dims:
            if stats[stat] + suf_stat[depth][stat] + bonus[stat] < need[stat]:
                return
        if panel_short(depth):
            return
        if depth == 6:
            holder[0] = spd
            holder[1] = (tuple(pick), four_slots)
            return
        index = order[depth]
        group = ordered[index]
        for rune in group:
            nspd = spd + rune.spd
            if nspd + suf_spd[depth + 1] <= holder[0]:
                break
            if any(
                stats[stat] + rune.stats[stat] + suf_stat[depth + 1][stat] + bonus[stat] < need[stat]
                for stat in dims
            ):
                continue
            if panel_white is not None and any(
                panel_need[stat]
                and panel_value(
                    panel_white[stat],
                    stats[stat] + rune.stats[stat] + suf_stat[depth + 1][stat] + bonus[stat],
                    flats[stat] + rune.flats[stat] + suf_flat[depth + 1][stat],
                    extra_pct[stat],
                    extra_flat[stat],
                )
                < panel_need[stat]
                for stat in range(3)
            ):
                continue
            if pair_idx and index in pair_idx:
                other_index = pair_idx[1] if index == pair_idx[0] else pair_idx[0]
                other = pick[other_index]
                if other is not None and forms_two_set(rune, other):
                    continue
            pick[index] = rune
            for stat in range(8):
                stats[stat] += rune.stats[stat]
            for stat in range(3):
                flats[stat] += rune.flats[stat]
            dfs(depth + 1, nspd)
            for stat in range(8):
                stats[stat] -= rune.stats[stat]
            for stat in range(3):
                flats[stat] -= rune.flats[stat]
            pick[index] = None
            if stop[0]:
                return

    dfs(0, 0)


def solve_one(
    index: int,
    req: SetRequest,
    runes: list[Rune],
    allow: set[int],
    excluded: int,
) -> Outcome:
    empty = Outcome(
        index=index,
        request=req,
        build=None,
        rune_stats=None,
        bonus=None,
        total=None,
        fastest_spd=None,
        pool=len(runes),
        excluded=excluded,
    )
    if len(runes) < 6:
        empty.message = f"剩余符文只有 {len(runes)} 颗，凑不齐 6 个槽位"
        return empty

    by = index_slots(runes)
    bonus = bonus_vector(req.four_set, req.two_set if req.mode == "pair" else None)
    panel_keys = ("hp", "atk", "def")
    percent_mins = {
        key: value
        for key, value in req.mins.items()
        if req.base is None or key not in panel_keys
    }
    panel_need = tuple(
        req.mins.get(key, 0) if req.base is not None else 0 for key in panel_keys
    )
    spd_min = percent_mins.get("spd", 0)
    other = {key: value for key, value in percent_mins.items() if key != "spd"}
    best_fast: Build | None = None
    best_fast_key: tuple[int, int, int] | None = None
    feasible_slots: list[tuple[int, set[int]]] = []
    for combo in combinations(range(1, 7), 4):
        four_slots = set(combo)
        build = assemble_fast(by, four_slots, req, allow)
        if build is None:
            continue
        key = build_key(build.runes)
        feasible_slots.append((key[0], four_slots))
        if best_fast_key is None or key > best_fast_key:
            best_fast_key = key
            best_fast = build
    if best_fast is None:
        empty.message = "凑不齐 6 个槽位（某个槽没有对应套装，或散件会凑成两件套）"
        return empty

    empty.fastest_spd = best_fast.spd
    fast_total = add_vec(sum_stats(best_fast.runes), bonus)
    if meets(fast_total, percent_mins) and panel_meets(
        best_fast, fast_total, req.base, panel_need, req.extra_pct, req.extra_flat
    ):
        return _ok(empty, best_fast, bonus, fast_total)

    if not other and not any(panel_need):
        empty.message = f"最快速度是 {best_fast.spd}，低于下限 {spd_min}"
        return empty

    need = [0] * 8
    for key, value in other.items():
        need[KEY_INDEX[key]] = value
    dims = tuple(KEY_INDEX[key] for key in STAT_KEYS if key in other)
    flat_dims = tuple(index for index, value in enumerate(panel_need) if value)
    pareto_dims = tuple(dict.fromkeys((*dims, *flat_dims)))
    holder: list = [spd_min - 1, None]
    nodes = [0]
    stop = [False]
    for _, four_slots in sorted(feasible_slots, key=lambda item: item[0], reverse=True):
        raw = [slot_group(by[slot], slot, four_slots, req, allow) for slot in range(1, 7)]
        raw = tighten(
            raw, need, bonus, dims, spd_min, req.base, panel_need, req.extra_pct, req.extra_flat
        )
        if any(not group for group in raw):
            continue
        lists = []
        for slot_index, group in enumerate(raw):
            per_set = req.mode == "broken" and (slot_index + 1) not in four_slots
            if per_set:
                buckets: dict[int, list[Rune]] = defaultdict(list)
                pared: list[Rune] = []
                for rune in group:
                    buckets[rune.set_id].append(rune)
                for bucket in buckets.values():
                    pared.extend(pareto(bucket, pareto_dims, flat_dims))
                lists.append(pared)
            else:
                lists.append(pareto(group, pareto_dims, flat_dims))
        if any(not group for group in lists):
            continue
        search_constrained(
            lists,
            tuple(sorted(four_slots)),
            bonus,
            need,
            dims,
            holder,
            nodes,
            stop,
            req.mode == "broken",
            req.base,
            panel_need,
            req.extra_pct,
            req.extra_flat,
        )
        if stop[0]:
            break

    empty.nodes = nodes[0]
    empty.truncated = stop[0]
    if holder[1] is None:
        if stop[0]:
            empty.message = "搜索量过大，没有在限制内找到满足下限的组合"
        else:
            empty.message = "没有满足全部下限的组合"
        return empty
    picked, four_slots_t = holder[1]
    build = Build(picked, four_slots_t)
    total = add_vec(sum_stats(build.runes), bonus)
    return _ok(empty, build, bonus, total)


def _ok(
    base: Outcome,
    build: Build,
    bonus: tuple[int, ...],
    total: tuple[int, ...],
) -> Outcome:
    base.build = build
    base.rune_stats = sum_stats(build.runes)
    base.bonus = bonus
    base.total = total
    if base.fastest_spd is None:
        base.fastest_spd = build.spd
    return base


def solve_sequence(
    runes: list[Rune],
    requests: list[SetRequest],
    allow: set[int],
) -> list[Outcome]:
    used: set[int] = set()
    outcomes: list[Outcome] = []
    for index, req in enumerate(requests, 1):
        pool = [rune for rune in runes if rune.rune_id not in used]
        outcome = solve_one(index, req, pool, allow, excluded=len(used))
        outcomes.append(outcome)
        if outcome.build is not None:
            used.update(rune.rune_id for rune in outcome.build.runes)
    return outcomes


def set_title(req: SetRequest) -> str:
    four = SET_NAME.get(req.four_set, str(req.four_set))
    if req.mode == "broken":
        return f"{four} + 散件"
    two = SET_NAME.get(req.two_set or 0, str(req.two_set))
    return f"{four} + {two}"


def broken_rule_text(allow: set[int]) -> str:
    on = [name for sid, name in PREMIUM if sid in allow]
    off = [name for sid, name in PREMIUM if sid not in allow]
    parts = []
    if on:
        parts.append("散件可用 " + "、".join(on))
    if off:
        parts.append("、".join(off) + " 不作为散件")
    return "；".join(parts)


def fmt_eff(stat_id: int, value: int) -> str:
    if not stat_id:
        return "无"
    return f"{STAT_CN.get(stat_id, str(stat_id))}+{value}"


def fmt_sub(sub: tuple[int, int, int, int]) -> str:
    stat_id, base, enchanted, grind = sub
    if not stat_id:
        return ""
    name = STAT_CN.get(stat_id, str(stat_id))
    mark = "*" if enchanted else ""
    if grind:
        return f"{name}+{base}(+{grind}){mark}"
    return f"{name}+{base}{mark}"


def fmt_stats(prefix: str, values: tuple[int, ...]) -> str:
    body = "  ".join(f"{STAT_LABEL[key]} {values[index]}" for index, key in enumerate(STAT_KEYS))
    return f"{prefix}  {body}"


def rune_kind(rune: Rune) -> str:
    grade = GRADE_CN.get(rune.grade, "")
    ancient = "远古" if rune.ancient else ""
    return f"{rune.stars}★{ancient}{grade}"


def format_outcome(outcome: Outcome) -> list[str]:
    req = outcome.request
    lines = [
        f"第 {outcome.index} 套  {set_title(req)}",
        _mins_text(req),
        f"候选 {outcome.pool} 颗，已排除 {outcome.excluded} 颗",
    ]
    if outcome.build is None or outcome.total is None or outcome.rune_stats is None or outcome.bonus is None:
        lines.append(outcome.message or "没有配出这一套")
        return lines

    build = outcome.build
    lines.append(f"速度 {build.spd}")
    if outcome.fastest_spd is not None and build.spd < outcome.fastest_spd:
        lines.append(
            f"只看速度时可以到 {outcome.fastest_spd}，为满足下限用了 {build.spd}"
        )
    elif "spd" not in req.mins and req.mins:
        lines.append("这是满足其他下限后的最快速度")
    elif "spd" not in req.mins:
        lines.append("未填速度下限，这是最快速度")
    role = "散件" if req.mode == "broken" else SET_NAME.get(req.two_set or 0, "两件套")
    lines.append(
        f"四件套槽 {'、'.join(str(slot) for slot in build.four_slots)}；"
        f"{role}槽 {'、'.join(str(slot) for slot in build.other_slots)}"
    )
    four_name = SET_NAME.get(req.four_set, "")
    two_name = SET_NAME.get(req.two_set or 0, "")
    for rune in build.runes:
        if rune.set_id != INTANGIBLE:
            continue
        if rune.slot in build.four_slots:
            lines.append(f"槽{rune.slot} 无形计入{four_name}")
        elif req.mode == "pair":
            lines.append(f"槽{rune.slot} 无形计入{two_name}")
        else:
            lines.append(f"槽{rune.slot} 无形作为散件")
    for rune in build.runes:
        innate = fmt_eff(rune.innate_id, rune.innate_val)
        subs = "，".join(text for text in (fmt_sub(sub) for sub in rune.subs) if text) or "无"
        lines.append(
            f"槽{rune.slot}  {SET_NAME.get(rune.set_id, rune.set_id)}  {rune_kind(rune)} +{rune.level}"
            f"  主:{fmt_eff(rune.main_id, rune.main_val)}  先天:{innate}  副:{subs}"
            f"  本符文速度 {rune.spd}  id {rune.rune_id}"
        )
    lines.append(fmt_stats("符文", outcome.rune_stats))
    bonus_parts = [
        f"{STAT_LABEL[key]}+{outcome.bonus[index]}"
        for index, key in enumerate(STAT_KEYS)
        if outcome.bonus[index]
    ]
    lines.append("套装  " + ("、".join(bonus_parts) if bonus_parts else "无百分比加成"))
    if req.four_set == 3:
        lines.append("迅速的 +25% 速度按基础速度结算，没有加进上面的速度")
    lines.append(fmt_stats("合计", outcome.total))
    if outcome.truncated:
        lines.append("搜索达到节点上限，这是已找到的最快可行组合，不保证还有更快的")
    elif outcome.message:
        lines.append(outcome.message)
    return lines


def _mins_text(req: SetRequest) -> str:
    parts = [f"{STAT_LABEL[key]}>={req.mins[key]}" for key in STAT_KEYS if key in req.mins]
    if not parts:
        return "下限 无"
    text = "下限 " + "  ".join(parts)
    if "spd" not in req.mins:
        text += "；速度取满足其他下限后的最快"
    return text


def format_report(
    path: str,
    total_runes: int,
    allow: set[int],
    outcomes: list[Outcome],
) -> str:
    lines = [
        f"符文文件  {path}",
        f"共 {total_runes} 颗。生命 / 攻击 / 防御是百分比合计，不含平值。",
        "速度是 6 颗符文速度之和，不含迅速对基础速度的 +25%。百分比下限含套装加成。",
        broken_rule_text(allow),
        "副属性括号内是精炼值，* 表示该词条已附魔。",
        "",
    ]
    for outcome in outcomes:
        lines.extend(format_outcome(outcome))
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def default_rune_file() -> Path | None:
    found = [path for path in JSO.glob("*/runes.json") if path.is_file()]
    if not found:
        return None
    return max(found, key=lambda path: path.stat().st_mtime)


class SetRow:
    def __init__(self, master: ttk.Frame, on_remove) -> None:
        self.frame = ttk.LabelFrame(master, padding=8)
        self._on_remove = on_remove
        self.mode = tk.StringVar(value="pair")
        top = ttk.Frame(self.frame)
        top.pack(fill="x")
        ttk.Radiobutton(
            top, text="四件套 + 两件套", variable=self.mode, value="pair", command=self._sync
        ).pack(side="left")
        ttk.Radiobutton(
            top, text="四件套 + 散件", variable=self.mode, value="broken", command=self._sync
        ).pack(side="left", padx=(12, 0))
        self.remove_btn = ttk.Button(top, text="删除", command=self._remove)
        self.remove_btn.pack(side="right")

        mid = ttk.Frame(self.frame)
        mid.pack(fill="x", pady=(6, 0))
        ttk.Label(mid, text="四件套").pack(side="left")
        self.four = ttk.Combobox(
            mid,
            values=[SET_NAME[sid] for sid in FOUR_OPTIONS],
            width=8,
            state="readonly",
        )
        self.four.current(0)
        self.four.pack(side="left", padx=(4, 16))
        ttk.Label(mid, text="两件套").pack(side="left")
        self.two = ttk.Combobox(
            mid,
            values=[SET_NAME[sid] for sid in TWO_OPTIONS],
            width=8,
            state="readonly",
        )
        self.two.current(0)
        self.two.pack(side="left", padx=(4, 0))

        stats = ttk.Frame(self.frame)
        stats.pack(fill="x", pady=(6, 0))
        self.stat_vars: dict[str, tk.StringVar] = {}
        for index, key in enumerate(STAT_KEYS):
            cell = ttk.Frame(stats)
            cell.grid(row=index // 4, column=index % 4, sticky="w", padx=(0, 18), pady=2)
            ttk.Label(cell, text=STAT_LABEL[key], width=6).pack(side="left")
            var = tk.StringVar()
            self.stat_vars[key] = var
            ttk.Entry(cell, textvariable=var, width=7).pack(side="left")
        self.frame.pack(fill="x", padx=4, pady=4)

    def _sync(self) -> None:
        self.two.configure(state="disabled" if self.mode.get() == "broken" else "readonly")

    def _remove(self) -> None:
        self._on_remove(self)

    def set_removable(self, yes: bool) -> None:
        self.remove_btn.configure(state="normal" if yes else "disabled")

    def retitle(self, index: int) -> None:
        self.frame.configure(text=f"第 {index} 套")

    def request(self) -> SetRequest:
        mins: dict[str, int] = {}
        for key in STAT_KEYS:
            text = self.stat_vars[key].get().strip()
            if not text:
                continue
            try:
                value = int(text)
            except ValueError:
                value = -1
            if value < 0:
                raise ValueError(f"第 {self.frame.cget('text')} 的{STAT_LABEL[key]}要填非负整数，或留空")
            mins[key] = value
        mode = self.mode.get()
        four = _id_by_name(self.four.get())
        two = None if mode == "broken" else _id_by_name(self.two.get())
        return SetRequest(mode=mode, four_set=four, two_set=two, mins=mins)

    def destroy(self) -> None:
        self.frame.destroy()


def _id_by_name(name: str) -> int:
    for sid, label in SET_NAME.items():
        if label == name:
            return sid
    raise ValueError(f"未知套装：{name}")


class App(tk.Tk):
    def __init__(self, preload: Path | None = None) -> None:
        super().__init__()
        self.title("符文配置")
        self.geometry("1080x860")
        self.minsize(920, 680)
        style = ttk.Style(self)
        style.configure(".", font=FONT)
        style.configure("TLabel", font=FONT)
        style.configure("TButton", font=FONT)
        style.configure("TRadiobutton", font=FONT)
        style.configure("TCheckbutton", font=FONT)
        style.configure("TLabelframe.Label", font=FONT)
        self.runes: list[Rune] = []
        self.rows: list[SetRow] = []
        self.path = tk.StringVar()
        self.status = tk.StringVar(value="还没有加载符文")
        self.allow_vars = {sid: tk.BooleanVar(value=False) for sid, _ in PREMIUM}

        file_bar = ttk.Frame(self, padding=(10, 10, 10, 4))
        file_bar.pack(fill="x")
        ttk.Label(file_bar, text="符文文件").pack(side="left")
        ttk.Entry(file_bar, textvariable=self.path).pack(side="left", fill="x", expand=True, padx=8)
        ttk.Button(file_bar, text="浏览", command=self._browse).pack(side="left")
        ttk.Button(file_bar, text="加载", command=lambda: self._load(True)).pack(side="left", padx=(6, 0))

        rules = ttk.LabelFrame(self, text="散件规则", padding=8)
        rules.pack(fill="x", padx=10, pady=4)
        ttk.Label(rules, text="勾选后，该套装可以拿去当散件").pack(side="left")
        for sid, name in PREMIUM:
            ttk.Checkbutton(rules, text=name, variable=self.allow_vars[sid]).pack(side="left", padx=(12, 0))

        hint = ttk.Label(
            self,
            wraplength=1040,
            text=(
                "每一套可填下限，留空表示不限制。速度留空时，在满足其他下限的组合里取最快速度。"
                "生命 / 攻击 / 防御填百分比，不含平值。后一套会排除前面已经用掉的符文。"
                "两颗相同的两件套（例如两颗意志）不算散件。无形可以补进四件套或两件套。"
            ),
        )
        hint.pack(fill="x", padx=12, pady=(0, 4))

        list_wrap = ttk.Frame(self)
        list_wrap.pack(fill="x", padx=10, pady=4)
        scroll = ttk.Scrollbar(list_wrap, orient="vertical")
        self.canvas = tk.Canvas(list_wrap, height=280, highlightthickness=0, yscrollcommand=scroll.set)
        scroll.configure(command=self.canvas.yview)
        self.canvas.pack(side="left", fill="both", expand=True)
        scroll.pack(side="right", fill="y")
        self.inner = ttk.Frame(self.canvas)
        self.inner.bind("<Configure>", lambda _e: self.canvas.configure(scrollregion=self.canvas.bbox("all")))
        self.win = self.canvas.create_window((0, 0), window=self.inner, anchor="nw")
        self.canvas.bind("<Configure>", lambda e: self.canvas.itemconfigure(self.win, width=e.width))
        bg = style.lookup("TFrame", "background") or self.cget("bg")
        self.canvas.configure(background=bg)
        self.bind_all("<MouseWheel>", self._wheel)

        actions = ttk.Frame(self, padding=(10, 4))
        actions.pack(fill="x")
        self.add_btn = ttk.Button(actions, text="添加一套", command=self._add_row)
        self.add_btn.pack(side="left")
        self.run_btn = ttk.Button(actions, text="开始配置", command=self._run)
        self.run_btn.pack(side="left", padx=(8, 0))
        ttk.Label(actions, textvariable=self.status).pack(side="left", padx=12)

        self.out = ScrolledText(self, wrap="word", font=FONT, height=16)
        self.out.pack(fill="both", expand=True, padx=10, pady=(0, 10))
        self.out.bind("<Key>", self._readonly_key)

        self._add_row()
        target = preload if preload is not None else default_rune_file()
        if target is not None:
            self.path.set(str(target))
            self._load(interactive=False)

    def _wheel(self, event) -> None:
        widget = self.winfo_containing(self.winfo_pointerx(), self.winfo_pointery())
        if widget is not None and _is_descendant(widget, self.out):
            return
        if widget is not None and _is_descendant(widget, self.canvas):
            self.canvas.yview_scroll(int(-event.delta / 120), "units")

    def _readonly_key(self, event) -> str | None:
        if event.keysym in {"Up", "Down", "Left", "Right", "Prior", "Next", "Home", "End", "Tab"}:
            return None
        if (event.state & 0x4) and event.keysym.lower() in {"c", "a"}:
            return None
        return "break"

    def _browse(self) -> None:
        current = self.path.get().strip()
        initial = str(Path(current).parent) if current else str(JSO)
        picked = filedialog.askopenfilename(
            parent=self,
            title="选择符文 JSON",
            initialdir=initial,
            filetypes=[("JSON", "*.json"), ("全部文件", "*.*")],
        )
        if not picked:
            return
        self.path.set(picked)
        self._load(interactive=True)

    def _load(self, interactive: bool) -> None:
        raw = self.path.get().strip()
        if not raw:
            self.runes = []
            self.status.set("先选择符文文件")
            return
        try:
            self.runes = load_runes(Path(raw))
        except (OSError, ValueError) as exc:
            self.runes = []
            self.status.set(str(exc))
            if interactive:
                messagebox.showerror("无法读取符文", str(exc), parent=self)
            return
        folder = Path(raw).parent.name
        self.status.set(f"已加载 {len(self.runes)} 颗（{folder}）")

    def _add_row(self) -> None:
        if len(self.rows) >= 30:
            return
        self.rows.append(SetRow(self.inner, self._remove_row))
        self._reindex()

    def _remove_row(self, row: SetRow) -> None:
        if len(self.rows) <= 1:
            return
        row.destroy()
        self.rows.remove(row)
        self._reindex()

    def _reindex(self) -> None:
        many = len(self.rows) > 1
        for index, row in enumerate(self.rows, 1):
            row.retitle(index)
            row.set_removable(many)
        self.canvas.update_idletasks()
        self.canvas.configure(scrollregion=self.canvas.bbox("all"))

    def _allow(self) -> set[int]:
        return {sid for sid, var in self.allow_vars.items() if var.get()}

    def _run(self) -> None:
        if not self.runes:
            messagebox.showinfo("符文配置", "先加载符文文件", parent=self)
            return
        try:
            requests = [row.request() for row in self.rows]
        except ValueError as exc:
            messagebox.showerror("符文配置", str(exc), parent=self)
            return
        allow = self._allow()
        runes = self.runes
        path = self.path.get().strip()
        self.run_btn.configure(state="disabled")
        self.add_btn.configure(state="disabled")
        self.status.set("正在配置…")
        started = time.perf_counter()

        def work() -> None:
            try:
                outcomes = solve_sequence(runes, requests, allow)
                text = format_report(path, len(runes), allow, outcomes)
                error: Exception | None = None
            except Exception as exc:
                text = ""
                error = exc
            elapsed = time.perf_counter() - started
            try:
                self.after(0, lambda: self._done(text, error, elapsed))
            except tk.TclError:
                return

        threading.Thread(target=work, daemon=True).start()

    def _done(self, text: str, error: Exception | None, elapsed: float) -> None:
        if not self.winfo_exists():
            return
        self.run_btn.configure(state="normal")
        self.add_btn.configure(state="normal")
        if error is not None:
            self.status.set("配置失败")
            messagebox.showerror("符文配置", str(error), parent=self)
            return
        self.out.configure(state="normal")
        self.out.delete("1.0", "end")
        self.out.insert("1.0", text)
        self.status.set(f"配置完成，用时 {elapsed:.2f} 秒")


def _is_descendant(widget, ancestor) -> bool:
    while widget is not None:
        if widget == ancestor:
            return True
        widget = getattr(widget, "master", None)
    return False


def _enable_dpi() -> None:
    try:
        import ctypes

        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except Exception:
        return


def main() -> None:
    _enable_dpi()
    preload = Path(sys.argv[1]) if len(sys.argv) > 1 else None
    app = App(preload=preload)
    app.mainloop()


if __name__ == "__main__":
    main()
