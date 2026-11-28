"use strict";
const byId = (name) => document.getElementById(name);
const groups = {};
let since = null;
let latest = null;
let querySignature = "";
let reportExpiry = Infinity;
let launcherBusy = false;
let startAccepted = false;
let polling = false;
let pollTimer;
const dateTime = new Intl.DateTimeFormat(undefined, {
  year:"numeric", month:"numeric", day:"numeric", hour:"numeric", minute:"numeric", second:"numeric"
});
const stateNames = {new:"開始前", starting:"開始中", running:"稼働中", ready:"準備済み",
  checking:"確認中", invalid:"失効", failed:"異常終了", stopped:"停止済み", stopping:"停止中",
  pending:"開始待ち", pausing:"中断処理中", paused:"中断中", resume_pending:"再開待ち",
  finishing:"後処理中", completed:"完了"};
const stateName = (value) => stateNames[value] ?? value ?? "未報告";

function renderLauncher() {
  byId("launcher").hidden = !latest?.launcher;
  byId("start-runtime").disabled = !latest?.launcher || latest.stalled ||
    latest.state !== "new" || startAccepted || launcherBusy;
}

async function launcherCommand(button, operation, args) {
  if (launcherBusy || latest?.stalled) return;
  launcherBusy = true;
  button.disabled = true;
  const result = byId("launcher-result");
  result.textContent = "操作を送信中";
  try {
    const response = await fetch("/api/launcher", {
      method:"POST", signal:AbortSignal.timeout(4000),
      headers:{"Content-Type":"application/json",
        "X-NTK-Launcher":document.querySelector('meta[name="ntk-launcher"]').content},
      body:JSON.stringify({operation, arguments:args})
    });
    if (!response.ok) throw new Error("Launcher response unavailable");
    const {status} = await response.json();
    if (operation === "start_runtime" && status === "accepted") startAccepted = true;
    result.textContent = ({
      accepted:"指示を受け付けました。実行状態は画面で確認できます。",
      applied:"指示を適用しました。", no_change:"活動はすでにその状態です。",
      conflict:"活動の状態が更新されました。表示を確認して操作してください。",
      outcome_unknown:"結果が不明です。画面で状態を確認してください。"
    })[status] ?? "現在の状態では操作を受け付けられません。";
  } catch {
    result.textContent = "結果が不明です。画面で状態を確認してください。";
  } finally {
    launcherBusy = false;
    button.disabled = false;
    renderLauncher();
  }
}

function activityControls(card, value) {
  if (!Number.isSafeInteger(value.launcher_revision)) return;
  if (["finishing", "completed", "failed", "stopped"].includes(value.state)) return;
  const controls = add(card, "div", undefined, "activity-controls");
  const actions = [["finish", "活動を終了"]];
  if (value.state === "running") actions.unshift(["pause", "中断"]);
  if (value.state === "paused") actions.unshift(["resume", "再開"]);
  for (const [operation, label] of actions) {
    const button = add(controls, "button", label);
    button.type = "button";
    button.addEventListener("click", () => launcherCommand(button, operation, {
      activity_id:value.activity_id, expected_revision:value.launcher_revision
    }));
  }
}

function add(parent, tag, value, className) {
  const element = document.createElement(tag);
  if (value !== undefined) element.textContent = value;
  if (className) element.className = className;
  parent.append(element);
  return element;
}
function timeText(time) {
  const milliseconds = Date.parse(time);
  return Number.isFinite(milliseconds) ? dateTime.format(milliseconds) : "—";
}
function orderRows(root, rows) {
  let next = root.firstElementChild;
  for (const row of rows) {
    if (row === next) next = next.nextElementSibling;
    else root.insertBefore(row, next);
  }
  while (next) {
    const stale = next;
    next = next.nextElementSibling;
    stale.remove();
  }
}
function usageText(usage) {
  if (!usage) return "稼働情報は未報告";
  const accepting = usage.accepting ? "受付可" : "受付停止";
  const capacity = usage.capacity == null ? "" : usage.active >= usage.capacity
    ? " · 空き枠なし" : " · 上限 " + usage.capacity;
  return accepting + " · 処理中 " + usage.active + capacity;
}
function renderModules() {
  const root = byId("modules");
  root.replaceChildren();
  for (const [id, value] of Object.entries(groups.modules ?? {})) {
    const card = add(root, "article", undefined, "card");
    add(card, "strong", id);
    add(card, "span", stateName(value.state) + " · " + value.placement);
    add(card, "small", usageText(groups.usage?.[id]));
    const abnormal = latest.terminal[id];
    if (abnormal) add(card, "p", "異常の記録 · " + stateName(abnormal.state)
      + (abnormal.cleanup_confirmed === false ? " · 後処理未確認" : ""));
  }
  if (!root.children.length) add(root, "p", "構成情報は未報告");
  const connections = byId("connections");
  connections.replaceChildren();
  for (const entry of Object.values(groups.connections ?? {})) {
    add(connections, "p", entry.requester_id + " → " + entry.provider_id + " · "
      + entry.contract_id + "/" + entry.version + " · " + stateName(entry.state));
  }
  if (!connections.children.length) add(connections, "p", "確立した接続はありません");
}
function renderActivities() {
  const panel = byId("activities");
  const rows = Object.entries(groups.activities ?? {}).slice(-12).reverse();
  if (!rows.length) {
    if (!panel.querySelector("p")) {
      panel.replaceChildren();
      add(panel, "p", "活動情報は未報告");
    }
    return;
  }
  const previous = new Map(Array.from(panel.children, (card) => [card.dataset.activity, card]));
  const cards = [];
  for (const [id, value] of rows) {
    const signature = JSON.stringify(value);
    let card = previous.get(id);
    if (card?.dataset.signature !== signature) {
      card = document.createElement("article");
      card.className = "card";
      card.dataset.activity = id;
      card.dataset.signature = signature;
      add(card, "strong", (value.label ?? id) + " · " + stateName(value.state));
      add(card, "span", "予定 " + timeText(value.planned_start_at) + " – " + timeText(value.planned_end_at));
      add(card, "span", "実績 " + timeText(value.started_at) + " – " + timeText(value.ended_at));
      if (value.planned_end_notified) add(card, "small", "予定到達を通知済み");
      const duration = Date.parse(value.planned_end_at) - Date.parse(value.planned_start_at);
      if (duration > 0 && value.started_at) {
        const bar = add(card, "progress");
        bar.max = duration;
        bar.setAttribute("aria-label", "予定時間に対する実績の割合");
        if (value.ended_at) {
          bar.value = Date.parse(value.ended_at) - Date.parse(value.started_at);
        } else {
          bar.dataset.started = Date.parse(value.started_at);
        }
      }
      if (latest.launcher) activityControls(card, value);
    }
    cards.push(card);
  }
  orderRows(panel, cards);
  const now = Date.now();
  for (const bar of panel.querySelectorAll("progress[data-started]")) {
    bar.value = now - Number(bar.dataset.started);
  }
}
function drawSeries(card, series) {
  const points = series.points;
  add(card, "p", points.at(-1).value + " " + series.unit + " · " + timeText(points.at(-1).at));
  if (points.length < 2) return;
  const canvas = add(card, "canvas");
  canvas.width = 320; canvas.height = 90;
  canvas.setAttribute("aria-label", "時系列 · " + series.unit);
  const ctx = canvas.getContext("2d");
  const values = points.map((point) => point.value);
  const low = Math.min(...values), range = Math.max(...values) - low || 1;
  const start = Date.parse(points[0].at), period = Date.parse(points.at(-1).at) - start || 1;
  ctx.strokeStyle = "#9ad6d2";
  ctx.lineWidth = 2;
  ctx.beginPath();
  points.forEach((point, index) => {
    const x = 6 + (Date.parse(point.at) - start) / period * 308;
    const y = 82 - (point.value - low) / range * 74;
    index ? ctx.lineTo(x, y) : ctx.moveTo(x, y);
  });
  ctx.stroke();
}
function renderReports() {
  reportExpiry = Infinity;
  const select = byId("adapter");
  const modules = Object.keys(groups.modules ?? {});
  const key = JSON.stringify(modules);
  if (select.dataset.modules !== key) {
    const selected = select.value;
    select.replaceChildren();
    for (const module of modules) add(select, "option", module).value = module;
    if (modules.includes(selected)) select.value = selected;
    select.dataset.modules = key;
  }
  const id = select.value;
  const target = byId("reports");
  target.replaceChildren();
  const report = Object.values(groups.reports ?? {}).find((value) => value.module_id === id);
  add(target, "p", usageText(report?.processing ?? groups.usage?.[id]));
  if (!report) return;
  if (report.condition) add(target, "p", report.condition.level + " · " + report.condition.label);
  for (const resource of report.resources) {
    const card = add(target, "article", undefined, "card");
    const detail = resource.limit == null ? "" : " / " + resource.limit;
    add(card, "strong", resource.label + " · " + resource.kind);
    add(card, "span", resource.used + detail + " " + resource.unit);
    if (resource.limit != null) {
      const meter = add(card, "meter");
      meter.max = resource.limit;
      meter.value = Math.min(resource.limit, resource.used);
      meter.setAttribute("aria-label", resource.label);
      if (resource.used > resource.limit) add(card, "p", "上限を超過");
    }
  }
  const now = Date.now();
  for (const output of report.outputs) {
    const card = add(target, "article", undefined, "card");
    add(card, "strong", output.label);
    if (output.source) add(card, "small", output.source + " · " + timeText(output.observed_at));
    const expiry = output.expires_at ? Date.parse(output.expires_at) : Infinity;
    if (expiry > now) reportExpiry = Math.min(reportExpiry, expiry);
    if (now >= expiry) {
      add(card, "p", "期限切れ");
    } else if (output.kind === "text") {
      add(card, "p", output.content);
    } else if (output.kind === "series") {
      drawSeries(card, output.content);
    } else {
      for (const item of output.content) add(card, "p", item.label + " " + item.value + " " + (item.unit ?? ""));
    }
  }
}
function renderEvents() {
  const target = byId("events");
  const previous = new Map(Array.from(target.children, (row) => [row.dataset.sequence, row]));
  const filter = byId("event-filter").value;
  const rows = [];
  for (const entry of [...latest.events].reverse().filter((event) => event.kind.includes(filter))) {
    const sequence = String(entry.sequence);
    const row = previous.get(sequence) ?? document.createElement("li");
    if (!previous.has(sequence)) {
      row.dataset.sequence = sequence;
      row.textContent = timeText(entry.at) + " · " + entry.kind + " · " + entry.subject;
    }
    rows.push(row);
  }
  orderRows(target, rows);
}
function renderQueries(queries) {
  const signature = JSON.stringify(queries);
  if (signature === querySignature) return;
  querySignature = signature;
  const root = byId("queries");
  root.replaceChildren();
  byId("console").hidden = !Object.keys(queries).length;
  for (const [operation, query] of Object.entries(queries)) {
    const form = add(root, "form");
    const fields = {};
    for (const [name, kind] of query.inputs) {
      const label = add(form, "label", name);
      const input = add(label, "input");
      input.type = {boolean:"checkbox", integer:"number", number:"number", string:"text"}[kind];
      input.step = kind === "integer" ? "1" : "any";
      input.required = kind !== "boolean";
      fields[name] = {kind, input};
    }
    const button = add(form, "button", query.label);
    form.addEventListener("submit", async (event) => {
      event.preventDefault();
      const args = {};
      for (const [name, {kind, input}] of Object.entries(fields)) {
        args[name] = kind === "boolean" ? input.checked : kind === "string" ? input.value : Number(input.value);
      }
      button.disabled = true;
      byId("result").textContent = "要求を送信済み";
      try {
        const response = await fetch("/api/console", {method:"POST", headers:{
          "Content-Type":"application/json", "X-NTK-Console":document.querySelector('meta[name="ntk-console"]').content,
        }, body:JSON.stringify({operation, arguments:args})});
        const result = await response.json();
        byId("result").textContent = JSON.stringify(result, null, 2);
      } catch {
        byId("result").textContent = "結果不明";
      } finally {
        button.disabled = false;
      }
    });
  }
}
function merge(update) {
  if (update.reset) for (const group of Object.keys(groups)) delete groups[group];
  for (const [group, values] of Object.entries(update.changes)) {
    if (group === "activities") { groups[group] = values; continue; }
    const records = groups[group] ??= {};
    for (const [id, value] of Object.entries(values)) {
      Object.defineProperty(records, id, {configurable:true, enumerable:true, writable:true,
        value:group === "reports" ? value : {...(Object.hasOwn(records, id) ? records[id] : {}), ...value}});
    }
  }
}
function renderSnapshot() {
  if (!latest) return;
  renderLauncher();
  renderModules(); renderEvents(); renderActivities(); renderReports(); renderQueries(latest.queries);
}
document.addEventListener("visibilitychange", () => {
  clearTimeout(pollTimer);
  if (!document.hidden) {
    renderSnapshot();
    void tick();
  }
});
byId("adapter").addEventListener("change", renderReports);
byId("event-filter").addEventListener("change", () => { if (latest) renderEvents(); });
byId("start-runtime").addEventListener("click", event => launcherCommand(event.currentTarget, "start_runtime", {}));
async function tick() {
  if (polling || (document.hidden && latest)) return;
  polling = true;
  try {
    const response = await fetch("/api/snapshot" + (since === null ? "" : "?since=" + since),
                                 {signal:AbortSignal.timeout(2000)});
    const update = await response.json();
    const previousEvents = update.reset ? [] : latest?.events ?? [];
    latest = {...update, events:[...previousEvents, ...update.events].slice(-200)};
    merge(update);
    since = update.revision;
    const state = update.stalled ? "観測更新停止" : stateName(update.state);
    if (byId("runtime").textContent !== state) byId("runtime").textContent = state;
    if (!document.hidden) {
      if (update.launcher) renderLauncher();
      if (update.reset || update.changes.modules || update.changes.connections || update.changes.usage) renderModules();
      if (update.reset || update.events.length) renderEvents();
      if (update.reset || update.changes.activities || byId("activities").querySelector("progress[data-started]")) {
        renderActivities();
      }
      if (update.reset || update.changes.reports || update.changes.modules || update.changes.usage
          || Date.now() >= reportExpiry) renderReports();
      renderQueries(update.queries);
    }
  } catch {
    if (latest?.state !== "failed" && latest?.state !== "stopped") byId("runtime").textContent = "観測更新停止";
  } finally {
    polling = false;
    if (!document.hidden || !latest) pollTimer = setTimeout(tick, 1000);
  }
}
tick();
