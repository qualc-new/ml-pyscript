const ATTR_CLASS = { 水: "water", 火: "fire", 风: "wind", 光: "light", 暗: "dark" };

const state = {
  overview: null,
  meta: null,
  summons: [],
  summonsLoaded: false,
  monsters: [],
  monstersLoaded: false,
  monsterId: null,
  pickRow: null,
  monsterAttr: 3,
  monsterStar: 5,
  attrs: new Set([4, 5]),
  stars: new Set(),
  selectedKey: "",
  dragRow: null,
};

const MAX_SETS = 60;
const CONFIG_PREFIX = "sw-rune-config:";

const $ = (id) => document.getElementById(id);

function esc(value) {
  return String(value ?? "").replace(/[&<>"']/g, (ch) => ({
    "&": "&amp;",
    "<": "&lt;",
    ">": "&gt;",
    '"': "&quot;",
    "'": "&#39;",
  }[ch]));
}

function num(value) {
  if (value === null || value === undefined || value === "") return "—";
  return Number(value).toLocaleString("zh-CN");
}

async function api(path, options) {
  const response = await fetch(path, options);
  const data = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(data.error || `请求失败 ${response.status}`);
  return data;
}

function showTab(name) {
  document.querySelectorAll("nav button").forEach((button) => {
    button.classList.toggle("active", button.dataset.tab === name);
  });
  document.querySelectorAll("main > section").forEach((section) => {
    section.hidden = section.id !== `tab-${name}`;
  });
  if (name === "parse") renderKeys();
  if (name === "summon" && state.overview && !state.summonsLoaded) loadSummons();
  if (name === "rune" && state.overview && !state.monstersLoaded) loadMonsters();
}

function setAccount(overview) {
  const box = $("account");
  if (!overview?.loaded) {
    box.textContent = "未导入";
    return;
  }
  const wizard = overview.wizard;
  box.textContent = `${wizard.name} · Lv${wizard.level ?? "—"}`;
}

function renderSummary(overview) {
  const box = $("summary");
  const wizard = overview.wizard;
  const counts = overview.counts;
  const warnings = (overview.warnings || []).map((item) => `<li>${esc(item)}</li>`).join("");
  box.hidden = false;
  box.innerHTML = `
    <article class="card who">
      <strong>${esc(wizard.name)}</strong>
      <span>ID ${esc(wizard.id)} · Lv${esc(wizard.level)} · 水晶 ${num(wizard.crystal)} · 魔力 ${num(wizard.mana)}</span>
      <span>上次登录 ${esc(wizard.last_login || "—")}</span>
      <span>${esc(overview.filename)}</span>
    </article>
    <article class="card"><span>字段</span><b>${num(counts.keys)}</b></article>
    <article class="card"><span>魔灵</span><b>${num(counts.units)}</b></article>
    <article class="card"><span>符文</span><b>${num(counts.runes)}</b></article>
    <article class="card"><span>神器</span><b>${num(counts.artifacts)}</b></article>
    ${warnings ? `<ul class="warn">${warnings}</ul>` : ""}
  `;
}

function accountId() {
  const id = state.overview?.wizard?.id;
  if (id === undefined || id === null || id === "") return "";
  return String(id);
}

function readConfig(id) {
  if (!id) return null;
  try {
    const data = JSON.parse(localStorage.getItem(CONFIG_PREFIX + id) || "");
    if (!data || !Array.isArray(data.sets)) return null;
    return data;
  } catch (_error) {
    return null;
  }
}

function snapshotSets() {
  return [...$("rune-rows").children].map((row) => {
    const mode = row.querySelector("[data-mode]").value;
    const mins = {};
    for (const input of row.querySelectorAll("[data-stat]")) {
      const text = input.value.trim();
      if (/^\d+$/.test(text)) mins[input.dataset.stat] = Number(text);
    }
    return {
      mode,
      four: Number(row.querySelector("[data-four]").value),
      two: mode === "pair" ? Number(row.querySelector("[data-two]").value) : null,
      mins,
      unit_id: row.dataset.unitId ? Number(row.dataset.unitId) : null,
    };
  });
}

function saveConfig() {
  const id = accountId();
  if (!id || state.suspendConfig) return;
  const allow = [...document.querySelectorAll("[data-premium]:checked")].map((input) => Number(input.value));
  localStorage.setItem(CONFIG_PREFIX + id, JSON.stringify({ allow, sets: snapshotSets() }));
}

function applyAllow(allow) {
  const chosen = new Set(allow || []);
  for (const input of document.querySelectorAll("[data-premium]")) {
    input.checked = chosen.has(Number(input.value));
  }
}

function applyOverview(overview) {
  state.overview = overview;
  setAccount(overview);
  renderSummary(overview);
  renderKeys();
  if (!state.meta) return;
  const cached = readConfig(accountId());
  state.suspendConfig = true;
  if (cached) {
    applyAllow(cached.allow);
    fillRtaRows(cached.sets.length ? cached.sets : []);
  } else {
    applyAllow([]);
    fillRtaRows([]);
  }
  state.suspendConfig = false;
}

async function upload(file) {
  const status = $("import-status");
  status.className = "status";
  status.textContent = `正在解析 ${file.name}（${num(file.size)} 字节）…`;
  try {
    const text = await file.text();
    const overview = await api("/api/import", {
      method: "POST",
      headers: {
        "Content-Type": "application/json; charset=utf-8",
        "X-Filename": encodeURIComponent(file.name),
      },
      body: text,
    });
    state.summons = [];
    state.summonsLoaded = false;
    state.monsters = [];
    state.monstersLoaded = false;
    state.monsterId = null;
    state.pickRow = null;
    state.selectedKey = "";
    applyOverview(overview);
    status.textContent = "导入完成。可以去解析字段、看召唤记录，或配置符文。";
  } catch (error) {
    status.className = "status bad";
    status.textContent = error.message;
  }
}

function renderKeys() {
  const list = $("key-list");
  const overview = state.overview;
  if (!overview?.loaded) {
    list.innerHTML = `<p class="muted">先在「导入」页放入完整 JSON。</p>`;
    return;
  }
  const query = $("key-search").value.trim().toLowerCase();
  const parts = [];
  for (const group of overview.keys) {
    const keys = group.keys.filter((item) => {
      if (!query) return true;
      return item.name.toLowerCase().includes(query) || (item.note || "").toLowerCase().includes(query);
    });
    if (!keys.length) continue;
    parts.push(`<div class="group-name">${esc(group.name)}</div>`);
    for (const item of keys) {
      const count = item.count === null || item.count === undefined ? item.type : `${item.type} · ${item.count}`;
      parts.push(
        `<button type="button" class="key-btn${item.name === state.selectedKey ? " on" : ""}" data-key="${esc(item.name)}">`
        + `${esc(item.name)}<small>${esc(count)}${item.note ? " · " + esc(item.note) : ""}</small></button>`
      );
    }
  }
  list.innerHTML = parts.join("") || `<p class="muted">没有匹配的字段。</p>`;
}

async function openKey(name) {
  state.selectedKey = name;
  renderKeys();
  const preview = $("preview");
  preview.innerHTML = `<p class="muted">正在读取 ${esc(name)} …</p>`;
  try {
    const data = await api(`/api/parse?key=${encodeURIComponent(name)}`);
    const count = data.count === null || data.count === undefined ? "" : ` · ${data.count}`;
    preview.innerHTML = `
      <h2>${esc(data.name)}</h2>
      <p class="muted">${esc(data.group)} · ${esc(data.type)}${esc(count)}${data.note ? " · " + esc(data.note) : ""}</p>
      <pre></pre>
    `;
    preview.querySelector("pre").textContent = data.text;
  } catch (error) {
    preview.innerHTML = `<p class="status bad">${esc(error.message)}</p>`;
  }
}

function chip(label, on, dataset) {
  const button = document.createElement("button");
  button.type = "button";
  button.className = `chip${on ? " on" : ""}`;
  button.textContent = label;
  Object.assign(button.dataset, dataset);
  return button;
}

function renderFilters() {
  const meta = state.meta;
  if (!meta) return;
  const attrs = $("attr-filters");
  attrs.replaceChildren();
  for (const item of meta.attrs) {
    attrs.append(chip(item.name, state.attrs.has(item.id), { kind: "attr", id: item.id }));
  }
  const stars = $("star-filters");
  stars.replaceChildren();
  for (const star of meta.stars) {
    stars.append(chip(`${star}★`, state.stars.has(star), { kind: "star", id: star }));
  }
  const source = $("source");
  source.replaceChildren();
  for (const item of meta.sources) {
    const option = document.createElement("option");
    option.value = item.id;
    option.textContent = item.name;
    source.append(option);
  }
  source.value = "summon";
  const premium = $("premium");
  premium.replaceChildren();
  const label = document.createElement("span");
  label.className = "muted";
  label.textContent = "散件可用";
  premium.append(label);
  for (const item of meta.premium) {
    const wrap = document.createElement("label");
    wrap.style.display = "flex";
    wrap.style.alignItems = "center";
    wrap.style.gap = "6px";
    const input = document.createElement("input");
    input.type = "checkbox";
    input.value = item.id;
    input.dataset.premium = "1";
    wrap.append(input, document.createTextNode(item.name));
    premium.append(wrap);
  }
  ensureRuneRow();
}

function toggleSet(set, id) {
  if (set.has(id)) set.delete(id);
  else set.add(id);
}

function renderSummons() {
  const list = $("summon-list");
  const meta = $("summon-meta");
  if (!state.overview?.loaded) {
    meta.textContent = "先导入 JSON。";
    list.replaceChildren();
    return;
  }
  meta.textContent = `${state.summons.length} 只，按入手时间从新到旧。不选属性或星级表示全部。勾选星级后，本地常量里没有初始星的魔灵不会列出。unit_list 只有现存魔灵，时间是 create_time（KST）。`;
  list.replaceChildren();
  if (!state.summons.length) {
    const empty = document.createElement("p");
    empty.className = "muted";
    empty.textContent = "没有符合筛选的魔灵。";
    list.append(empty);
    return;
  }
  for (const row of state.summons) {
    const item = document.createElement("article");
    item.className = "summon-row";
    const cls = ATTR_CLASS[row.attribute] || "";
    if (row.avatar && String(row.avatar).startsWith("https://")) {
      const img = document.createElement("img");
      img.alt = "";
      img.src = row.avatar;
      img.addEventListener("error", () => img.replaceWith(fallback(row, cls)));
      item.append(img);
    } else {
      item.append(fallback(row, cls));
    }
    const body = document.createElement("div");
    body.innerHTML = `
      <div class="name ${cls}">${esc(row.name)}</div>
      <div class="meta">${esc(row.attribute)} · ${esc(row.natural_stars || "—")}★ → ${esc(row.current_stars)}★ Lv${esc(row.level)} · ${esc(row.source_label)} · ${esc(row.create_time_kst)}</div>
    `;
    item.append(body);
    list.append(item);
  }
}

function face(monster) {
  const cls = ATTR_CLASS[monster.attribute] || "";
  if (monster.avatar && String(monster.avatar).startsWith("https://")) {
    const img = document.createElement("img");
    img.className = "face";
    img.alt = "";
    img.src = monster.avatar;
    img.addEventListener("error", () => img.replaceWith(fallback(monster, cls)));
    return img;
  }
  return fallback(monster, cls);
}

function fallback(row, cls) {
  const span = document.createElement("span");
  span.className = `avatar-fallback ${cls}`;
  span.textContent = row.attribute || "?";
  return span;
}

async function loadSummons() {
  const meta = $("summon-meta");
  if (!state.overview?.loaded) {
    meta.textContent = "先导入 JSON。";
    return;
  }
  meta.className = "status";
  meta.textContent = "正在筛选…";
  try {
    const data = await api("/api/summons", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        attrs: [...state.attrs],
        stars: [...state.stars],
        source: $("source").value,
        q: $("summon-q").value.trim(),
      }),
    });
    state.summons = data.rows;
    state.summonsLoaded = true;
    renderSummons();
  } catch (error) {
    meta.className = "status bad";
    meta.textContent = error.message;
  }
}

function runeSummary(row) {
  const mode = row.querySelector("[data-mode]").value;
  const fourName = row.querySelector("[data-four]").selectedOptions[0].textContent;
  if (mode === "broken") return `${fourName} + 散件`;
  const twoName = row.querySelector("[data-two]").selectedOptions[0].textContent;
  return `${fourName} + ${twoName}`;
}

function syncRuneBrief(row) {
  const brief = row.querySelector("[data-brief]");
  if (brief) brief.textContent = runeSummary(row);
}

function setRowFolded(row, folded) {
  row.classList.toggle("folded", folded);
  const button = row.querySelector("[data-fold]");
  button.textContent = folded ? "展开" : "折叠";
  button.setAttribute("aria-expanded", folded ? "false" : "true");
  syncRuneBrief(row);
}

function syncConfigFold() {
  const rows = [...$("rune-rows").children];
  const allFolded = rows.length > 0 && rows.every((row) => row.classList.contains("folded"));
  $("rune-panel").classList.toggle("folded", allFolded);
  const button = $("fold-config");
  button.textContent = allFolded ? "展开配置" : "折叠配置";
  button.setAttribute("aria-expanded", allFolded ? "false" : "true");
}

function fillRtaRows(presets) {
  const host = $("rune-rows");
  if (!host || !state.meta) return;
  host.replaceChildren();
  const source = presets.length ? presets : [null];
  for (const preset of source) host.append(runeRow(host.children.length + 1, preset));
  refreshRemove();
  syncConfigFold();
  if (presets.length) loadMonsters();
}

function runeRow(index, preset) {
  const meta = state.meta;
  const box = document.createElement("article");
  box.className = "rune-row";
  box.dataset.index = String(index);
  const four = meta.four.map((item) => `<option value="${item.id}"${item.id === 3 ? " selected" : ""}>${esc(item.name)}</option>`).join("");
  const two = meta.two.map((item) => `<option value="${item.id}"${item.id === 15 ? " selected" : ""}>${esc(item.name)}</option>`).join("");
  const mins = meta.stats.map((item) => `
    <label>${esc(item.label)}
      <input data-stat="${esc(item.key)}" inputmode="numeric" placeholder="${esc(item.hint || "")}" />
    </label>
  `).join("");
  box.innerHTML = `
    <div class="row-head">
      <button type="button" class="drag" data-drag draggable="true" aria-label="拖拽排序" title="拖拽排序">↕</button>
      <h3>第 ${index} 套</h3>
      <span class="rune-brief" data-brief></span>
      <button type="button" data-fold aria-expanded="true">折叠</button>
      <button type="button" data-remove>删除</button>
    </div>
    <div class="monster-slot">
      <button type="button" data-pick>选择魔灵</button>
      <span class="monster-chip muted" data-chip>未选魔灵，本套只显示符文百分比</span>
      <button type="button" data-clear hidden>清除</button>
    </div>
    <div class="row-detail">
      <div class="filter-row">
        <label>模式
          <select data-mode>
            <option value="pair">四件套 + 两件套</option>
            <option value="broken">四件套 + 散件</option>
          </select>
        </label>
        <label>四件套 <select data-four>${four}</select></label>
        <label>两件套 <select data-two>${two}</select></label>
      </div>
      <div class="mins">${mins}</div>
    </div>
  `;
  if (preset) {
    box.querySelector("[data-mode]").value = preset.mode === "broken" ? "broken" : "pair";
    if (preset.four) box.querySelector("[data-four]").value = String(preset.four);
    if (preset.two) box.querySelector("[data-two]").value = String(preset.two);
    box.querySelector("[data-two]").disabled = preset.mode === "broken";
    if (preset.unit_id) box.dataset.unitId = String(preset.unit_id);
    for (const [key, value] of Object.entries(preset.mins || {})) {
      const input = box.querySelector(`[data-stat="${key}"]`);
      if (input && value) input.value = String(value);
    }
  }
  syncRuneBrief(box);
  return box;
}

function ensureRuneRow() {
  const host = $("rune-rows");
  if (!state.meta || host.children.length) return;
  host.append(runeRow(1));
  refreshRemove();
}

function refreshRemove() {
  const rows = [...$("rune-rows").children];
  rows.forEach((row, index) => {
    row.querySelector("h3").textContent = `第 ${index + 1} 套`;
    row.querySelector("[data-remove]").disabled = rows.length === 1;
  });
}

function collectSets() {
  return [...$("rune-rows").children].map((row, index) => {
    const mode = row.querySelector("[data-mode]").value;
    const mins = {};
    for (const input of row.querySelectorAll("[data-stat]")) {
      const text = input.value.trim();
      if (!text) continue;
      const label = input.closest("label").childNodes[0].textContent.trim();
      if (!/^\d+$/.test(text)) {
        throw new Error(`第 ${index + 1} 套的${label}要填非负整数，或留空`);
      }
      mins[input.dataset.stat] = Number(text);
    }
    return {
      mode,
      four: Number(row.querySelector("[data-four]").value),
      two: mode === "pair" ? Number(row.querySelector("[data-two]").value) : null,
      mins,
      unit_id: row.dataset.unitId ? Number(row.dataset.unitId) : null,
    };
  });
}

function monsterLabel(monster) {
  const stars = monster.natural_stars ? `${monster.natural_stars}★` : `${monster.stars}★`;
  return `${monster.attribute} ${monster.name} ${stars} Lv${monster.level} 速${monster.base.spd}`;
}

async function loadMonsters() {
  if (!state.overview?.loaded) return;
  try {
    const data = await api("/api/monsters");
    state.monsters = data.monsters;
    state.monstersLoaded = true;
    if ($("monster-dialog").open) {
      renderMonsterTabs();
      renderMonsterList();
    }
    for (const row of $("rune-rows").children) renderRowMonster(row);
  } catch (error) {
    const status = $("rune-status");
    status.className = "status bad";
    status.textContent = error.message;
  }
}

function renderMonsterTabs() {
  for (const button of $("monster-attrs").querySelectorAll("[data-mattr]")) {
    const id = Number(button.dataset.mattr);
    const on = id === state.monsterAttr;
    button.className = on ? `on ${ATTR_CLASS[button.textContent.trim()] || ""}` : "";
  }
  for (const button of $("monster-stars").querySelectorAll("[data-mstar]")) {
    button.className = Number(button.dataset.mstar) === state.monsterStar ? "on" : "";
  }
}

function renderMonsterList() {
  const host = $("monster-list");
  const count = $("monster-count");
  if (!host) return;
  host.replaceChildren();
  const matches = state.monsters.filter(
    (monster) => monster.attribute_id === state.monsterAttr && monster.natural_stars === state.monsterStar,
  );
  if (count) count.textContent = state.monstersLoaded ? `${matches.length} 只` : "";
  if (!matches.length) {
    const empty = document.createElement("p");
    empty.className = "muted";
    empty.textContent = state.monstersLoaded ? "这一页没有魔灵" : "正在读取魔灵…";
    host.append(empty);
    return;
  }
  for (const monster of matches) {
    const button = document.createElement("button");
    button.type = "button";
    if (monster.unit_id === state.monsterId) button.className = "on";
    const name = document.createElement("b");
    name.className = ATTR_CLASS[monster.attribute] || "";
    name.textContent = monster.name;
    const meta = document.createElement("span");
    meta.className = "meta";
    meta.textContent = `${monster.stars}★ Lv${monster.level} · 速${monster.base.spd}`;
    const text = document.createElement("span");
    text.append(name, meta);
    button.append(face(monster), text);
    button.addEventListener("click", () => {
      const row = state.pickRow;
      if (!row) return;
      state.monsterId = monster.unit_id;
      row.dataset.unitId = String(monster.unit_id);
      renderRowMonster(row);
      $("monster-dialog").close();
      saveConfig();
    });
    host.append(button);
  }
}

function renderRowMonster(row) {
  const chip = row.querySelector("[data-chip]");
  const clear = row.querySelector("[data-clear]");
  if (!chip || !clear) return;
  const id = row.dataset.unitId ? Number(row.dataset.unitId) : null;
  const monster = state.monsters.find((item) => item.unit_id === id);
  chip.replaceChildren();
  if (!monster) {
    chip.classList.add("muted");
    chip.textContent = "未选魔灵，本套只显示符文百分比";
    clear.hidden = true;
    return;
  }
  chip.classList.remove("muted");
  chip.append(face(monster));
  const label = document.createElement("span");
  label.textContent = monsterLabel(monster);
  chip.append(label);
  clear.hidden = false;
}

async function openMonsterDialog(row) {
  const status = $("rune-status");
  if (!state.overview?.loaded) {
    status.className = "status bad";
    status.textContent = "先导入 JSON。";
    return;
  }
  state.pickRow = row;
  state.monsterId = row.dataset.unitId ? Number(row.dataset.unitId) : null;
  if (!state.monstersLoaded) await loadMonsters();
  const selected = state.monsters.find((item) => item.unit_id === state.monsterId);
  if (selected?.attribute_id) state.monsterAttr = selected.attribute_id;
  if (selected?.natural_stars >= 1 && selected.natural_stars <= 5) state.monsterStar = selected.natural_stars;
  renderMonsterTabs();
  renderMonsterList();
  const dialog = $("monster-dialog");
  if (!dialog.open) dialog.showModal();
}

function panelHtml(panel) {
  const row = (title, field, klass, lineClass) => {
    const bits = panel.lines.map((line) => `<span class="${klass}">${esc(line.label)} ${line[field] >= 0 && field === "green" ? "+" : ""}${num(line[field])}</span>`).join("");
    return `<div class="panel-line${lineClass ? ` ${lineClass}` : ""}"><b>${title}</b>${bits}</div>`;
  };
  const flat = panel.flat;
  const pct = panel.percent;
  const building = panel.building || { hp: 0, atk: 0, def: 0, spd: 0, cd: 0 };
  const artifact = panel.artifact || { hp: 0, atk: 0, def: 0 };
  const speedBits = [`符文 ${panel.rune_spd}`];
  if (panel.swift) speedBits.push(`迅速 ${panel.swift_spd}（白字 × 25%，向上取整）`);
  const flatBit = (runeFlat, artFlat) =>
    artFlat ? `符文平值 ${num(runeFlat)} + 神器 ${num(artFlat)}` : `平值 ${num(runeFlat)}`;
  return `
    <div class="panel-block">
      <div class="sheet-extra">
        ${row("白字", "white", "num-white")}
        ${row("绿字", "green", "num-green")}
        <p class="formula">生命 = 白字 × ${pct.hp + building.hp}%（符文 ${pct.hp}% + 建筑 ${building.hp}%）+ ${flatBit(flat.hp, artifact.hp)}；攻击 = 白字 × ${pct.atk + building.atk}% + ${flatBit(flat.atk, artifact.atk)}；防御 = 白字 × ${pct.def + building.def}% + ${flatBit(flat.def, artifact.def)}。速度 = ${speedBits.join(" + ")}。爆伤另加建筑 ${building.cd}%。速度图腾、召唤师技能和公会旗子没有算进面板。</p>
      </div>
      ${row("合计", "total", "", "sheet-total")}
    </div>
  `;
}

function setSheetFolded(sheet, folded) {
  sheet.classList.toggle("folded", folded);
  const button = sheet.querySelector("[data-fold-sheet]");
  if (!button) return;
  button.textContent = folded ? "展开" : "折叠";
  button.setAttribute("aria-expanded", folded ? "false" : "true");
}

function renderRuneResult(data) {
  const host = $("rune-result");
  host.replaceChildren();
  const bar = document.createElement("div");
  bar.className = "row-head";
  const rule = document.createElement("p");
  rule.className = "muted";
  rule.textContent = `${data.rule} · 用时 ${data.elapsed} 秒`;
  const foldAll = document.createElement("button");
  foldAll.type = "button";
  foldAll.textContent = "折叠计算";
  foldAll.setAttribute("aria-expanded", "true");
  foldAll.addEventListener("click", () => {
    const sheets = [...host.querySelectorAll(".sheet")];
    const fold = sheets.some((sheet) => !sheet.classList.contains("folded"));
    for (const sheet of sheets) setSheetFolded(sheet, fold);
    foldAll.textContent = fold ? "展开计算" : "折叠计算";
    foldAll.setAttribute("aria-expanded", fold ? "false" : "true");
  });
  bar.append(rule, foldAll);
  host.append(bar);
  for (const item of data.sets) {
    const sheet = document.createElement("article");
    sheet.className = "sheet";
    const fold = `<button type="button" data-fold-sheet aria-expanded="true">折叠</button>`;
    if (!item.ok) {
      sheet.innerHTML = `
        <div class="sheet-bar"><h2>第 ${item.index} 套 · ${esc(item.title)}</h2>${fold}</div>
        <p class="fail">${esc(item.message)}</p>
        <p class="muted sheet-extra">候选 ${item.pool} 颗，已排除 ${item.excluded} 颗</p>
      `;
      host.append(sheet);
      continue;
    }
    const stats = item.total.map((stat) => `<span>${esc(stat.label)} ${stat.value}</span>`).join("");
    const bonus = item.bonus.length
      ? item.bonus.map((stat) => `${esc(stat.label)}+${stat.value}`).join("、")
      : "无百分比加成";
    const notes = item.notes
      .filter((note) => !(item.panel && note.includes("没有加进")))
      .map((note) => `<p class="muted">${esc(note)}</p>`).join("");
    const lines = item.runes.map((rune) => `
      <div class="rune-line">
        <b>槽${rune.slot} ${esc(rune.set)}</b>
        ${esc(rune.kind)} +${rune.level} · 主 ${esc(rune.main)}
        ${rune.innate ? ` · 先天 ${esc(rune.innate)}` : ""}
        · 副 ${esc(rune.subs.join("，") || "无")}
        · 速度 ${rune.spd}
      </div>
    `).join("");
    const speed = item.panel
      ? `${item.panel.lines.find((line) => line.key === "spd").total}<small>面板速度</small>`
      : `${item.spd}<small>符文速度</small>`;
    const who = item.panel ? ` · ${esc(item.panel.attribute)} ${esc(item.panel.name)}` : "";
    const faceHtml = item.panel?.avatar && String(item.panel.avatar).startsWith("https://")
      ? `<img class="face" alt="" src="${esc(item.panel.avatar)}" />`
      : "";
    const totals = item.panel ? "" : `<div class="stats sheet-total">${stats}</div>`;
    sheet.innerHTML = `
      <div class="sheet-bar"><h2>${faceHtml}第 ${item.index} 套${who} · ${esc(item.title)}</h2>${fold}</div>
      <div class="sheet-extra">
        <div class="speed">${speed}</div>
        <p class="muted">四件套槽 ${item.four_slots.join("、")}；${esc(item.other_label)}槽 ${item.other_slots.join("、")} · 候选 ${item.pool} 颗，已排除 ${item.excluded} 颗</p>
        ${notes}
      </div>
      ${item.panel ? panelHtml(item.panel) : totals}
      <div class="sheet-extra">
        <p class="muted">套装 ${esc(bonus)}。括号内是精炼，* 表示附魔。</p>
        ${lines}
      </div>
    `;
    host.append(sheet);
  }
}

async function solve() {
  const status = $("rune-status");
  const button = $("solve");
  if (!state.overview?.loaded) {
    status.className = "status bad";
    status.textContent = "先导入 JSON。";
    return;
  }
  let sets;
  try {
    sets = collectSets();
  } catch (error) {
    status.className = "status bad";
    status.textContent = error.message;
    return;
  }
  const allow = [...document.querySelectorAll("[data-premium]:checked")].map((input) => Number(input.value));
  button.disabled = true;
  status.className = "status";
  status.textContent = "正在配置…";
  try {
    const data = await api("/api/runes/solve", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ allow, sets }),
    });
    renderRuneResult(data);
    saveConfig();
    status.textContent = "配置完成，已按账号写入本地缓存。";
  } catch (error) {
    status.className = "status bad";
    status.textContent = error.message;
  } finally {
    button.disabled = false;
  }
}

function bind() {
  document.querySelectorAll("nav button").forEach((button) => {
    button.addEventListener("click", () => showTab(button.dataset.tab));
  });
  const file = $("file");
  $("pick").addEventListener("click", () => file.click());
  $("drop").addEventListener("click", (event) => {
    if (event.target.id !== "pick") file.click();
  });
  $("drop").addEventListener("keydown", (event) => {
    if (event.key === "Enter" || event.key === " ") file.click();
  });
  file.addEventListener("change", () => {
    if (file.files[0]) upload(file.files[0]);
  });
  const drop = $("drop");
  drop.addEventListener("dragover", (event) => {
    event.preventDefault();
    drop.classList.add("hot");
  });
  drop.addEventListener("dragleave", () => drop.classList.remove("hot"));
  drop.addEventListener("drop", (event) => {
    event.preventDefault();
    drop.classList.remove("hot");
    const picked = event.dataTransfer.files[0];
    if (picked) upload(picked);
  });
  window.addEventListener("dragover", (event) => event.preventDefault());
  window.addEventListener("drop", (event) => event.preventDefault());
  $("key-search").addEventListener("input", renderKeys);
  $("key-list").addEventListener("click", (event) => {
    const button = event.target.closest("[data-key]");
    if (button) openKey(button.dataset.key);
  });
  document.body.addEventListener("click", (event) => {
    const button = event.target.closest(".chip");
    if (!button) return;
    const id = Number(button.dataset.id);
    const set = button.dataset.kind === "attr" ? state.attrs : state.stars;
    toggleSet(set, id);
    button.classList.toggle("on", set.has(id));
  });
  $("summon-go").addEventListener("click", loadSummons);
  $("summon-q").addEventListener("keydown", (event) => {
    if (event.key === "Enter") loadSummons();
  });
  $("add-set").addEventListener("click", () => {
    const host = $("rune-rows");
    if (host.children.length >= MAX_SETS) {
      const status = $("rune-status");
      status.className = "status bad";
      status.textContent = `最多 ${MAX_SETS} 套`;
      return;
    }
    host.append(runeRow(host.children.length + 1));
    refreshRemove();
    syncConfigFold();
    saveConfig();
  });
  $("import-rta").addEventListener("click", () => {
    const status = $("rune-status");
    if (!state.overview?.loaded) {
      status.className = "status bad";
      status.textContent = "先导入 JSON。";
      return;
    }
    const presets = state.overview.rta || [];
    if (!presets.length) {
      status.className = "status bad";
      status.textContent = "这个账号没有可导入的世界竞技场配置。";
      return;
    }
    $("rune-result").replaceChildren();
    fillRtaRows(presets);
    saveConfig();
    status.className = "status";
    status.textContent = `已清空并导入 ${presets.length} 套世界竞技场配置。`;
  });
  $("fold-config").addEventListener("click", () => {
    const rows = [...$("rune-rows").children];
    const fold = rows.some((row) => !row.classList.contains("folded"));
    for (const row of rows) setRowFolded(row, fold);
    syncConfigFold();
  });
  $("rune-rows").addEventListener("dragstart", (event) => {
    const handle = event.target.closest("[data-drag]");
    const row = handle && handle.closest(".rune-row");
    if (!row) return;
    state.dragRow = row;
    row.classList.add("dragging");
    event.dataTransfer.effectAllowed = "move";
    event.dataTransfer.setData("text/plain", row.dataset.index || "set");
  });
  $("rune-rows").addEventListener("dragover", (event) => {
    if (!state.dragRow) return;
    event.preventDefault();
    const row = event.target.closest(".rune-row");
    if (!row || row === state.dragRow) return;
    const box = row.getBoundingClientRect();
    const after = event.clientY > box.top + box.height / 2;
    row.parentNode.insertBefore(state.dragRow, after ? row.nextSibling : row);
    refreshRemove();
  });
  $("rune-rows").addEventListener("drop", (event) => {
    if (!state.dragRow) return;
    event.preventDefault();
  });
  $("rune-rows").addEventListener("dragend", () => {
    if (state.dragRow) state.dragRow.classList.remove("dragging");
    state.dragRow = null;
    refreshRemove();
    saveConfig();
  });
  $("rune-rows").addEventListener("click", (event) => {
    const row = event.target.closest(".rune-row");
    if (!row) return;
    if (event.target.closest("[data-fold]")) {
      setRowFolded(row, !row.classList.contains("folded"));
      syncConfigFold();
      return;
    }
    if (event.target.matches("[data-remove]")) {
      if (state.pickRow === row) state.pickRow = null;
      row.remove();
      refreshRemove();
      syncConfigFold();
      saveConfig();
      return;
    }
    if (event.target.closest("[data-pick]")) {
      openMonsterDialog(row).catch((error) => {
        const status = $("rune-status");
        status.className = "status bad";
        status.textContent = error.message;
      });
      return;
    }
    if (event.target.closest("[data-clear]")) {
      delete row.dataset.unitId;
      if (state.pickRow === row) state.monsterId = null;
      renderRowMonster(row);
      if ($("monster-dialog").open) renderMonsterList();
      saveConfig();
    }
  });
  $("rune-rows").addEventListener("input", (event) => {
    if (event.target.matches("[data-stat]")) saveConfig();
  });
  $("rune-rows").addEventListener("change", (event) => {
    const row = event.target.closest(".rune-row");
    if (!row) return;
    if (event.target.matches("[data-mode]")) {
      row.querySelector("[data-two]").disabled = event.target.value === "broken";
    }
    if (event.target.matches("[data-mode], [data-four], [data-two]")) {
      syncRuneBrief(row);
      saveConfig();
    }
  });
  $("premium").addEventListener("change", (event) => {
    if (event.target.matches("[data-premium]")) saveConfig();
  });
  $("rune-result").addEventListener("click", (event) => {
    const button = event.target.closest("[data-fold-sheet]");
    if (!button) return;
    const sheet = button.closest(".sheet");
    setSheetFolded(sheet, !sheet.classList.contains("folded"));
    const foldAll = $("rune-result").querySelector(".row-head button");
    if (!foldAll) return;
    const sheets = [...$("rune-result").querySelectorAll(".sheet")];
    const allFolded = sheets.length > 0 && sheets.every((item) => item.classList.contains("folded"));
    foldAll.textContent = allFolded ? "展开计算" : "折叠计算";
    foldAll.setAttribute("aria-expanded", allFolded ? "false" : "true");
  });
  $("solve").addEventListener("click", solve);
  $("monster-close").addEventListener("click", () => $("monster-dialog").close());
  $("monster-dialog").addEventListener("click", (event) => {
    if (event.target === $("monster-dialog")) $("monster-dialog").close();
  });
  $("monster-attrs").addEventListener("click", (event) => {
    const button = event.target.closest("[data-mattr]");
    if (!button) return;
    state.monsterAttr = Number(button.dataset.mattr);
    renderMonsterTabs();
    renderMonsterList();
  });
  $("monster-stars").addEventListener("click", (event) => {
    const button = event.target.closest("[data-mstar]");
    if (!button) return;
    state.monsterStar = Number(button.dataset.mstar);
    renderMonsterTabs();
    renderMonsterList();
  });
}

async function boot() {
  bind();
  try {
    state.meta = await api("/api/meta");
    renderFilters();
  } catch (error) {
    $("import-status").textContent = error.message;
  }
  try {
    const overview = await api("/api/state");
    if (overview.loaded) applyOverview(overview);
  } catch (_error) {
    /* 还没有导入 */
  }
}

boot();
