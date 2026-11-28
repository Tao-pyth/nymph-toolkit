"use strict";
const byId = (name) => document.getElementById(name);
const groups = {};
let since = null;
let latest = null;
let querySignature = "";
const stateNames = {new:"開始前", starting:"開始中", running:"稼働中", ready:"準備済み",
  checking:"確認中", invalid:"失効", failed:"異常終了", stopped:"停止済み", stopping:"停止中"};
const stateName = (value) => stateNames[value] ?? value ?? "未報告";

function add(parent, tag, value, className) {
  const element = document.createElement(tag);
  if (value !== undefined) element.textContent = value;
  if (className) element.className = className;
  parent.append(element);
  return element;
}
function timeText(time) {
  return time ? new Date(time).toLocaleString() : "—";
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
  panel.replaceChildren();
  const rows = Object.entries(groups.activities ?? {}).slice(-12).reverse();
  if (!rows.length) add(panel, "p", "活動情報は未報告");
  for (const [id, value] of rows) {
    const card = add(panel, "article", undefined, "card");
    add(card, "strong", id + " · " + stateName(value.state));
    add(card, "span", "予定 " + timeText(value.planned_start_at) + " – " + timeText(value.planned_end_at));
    add(card, "span", "実績 " + timeText(value.started_at) + " – " + timeText(value.ended_at));
    if (value.planned_end_notified) add(card, "small", "予定到達を通知済み");
    const duration = Date.parse(value.planned_end_at) - Date.parse(value.planned_start_at);
    if (duration > 0 && value.started_at) {
      const elapsed = (value.ended_at ? Date.parse(value.ended_at) : Date.now()) - Date.parse(value.started_at);
      const bar = add(card, "progress");
      bar.max = duration;
      bar.value = Math.min(duration, Math.max(0, elapsed));
      bar.setAttribute("aria-label", "予定時間に対する実績の割合");
    }
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
  for (const output of report.outputs) {
    const card = add(target, "article", undefined, "card");
    add(card, "strong", output.label);
    if (output.source) add(card, "small", output.source + " · " + timeText(output.observed_at));
    if (output.expires_at && Date.now() >= Date.parse(output.expires_at)) {
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
  target.replaceChildren();
  const filter = byId("event-filter").value;
  for (const entry of [...latest.events].reverse().filter((event) => event.kind.includes(filter))) {
    add(target, "li", timeText(entry.at) + " · " + entry.kind + " · " + entry.subject);
  }
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
byId("adapter").addEventListener("change", renderReports);
byId("event-filter").addEventListener("change", () => { if (latest) renderEvents(); });
async function tick() {
  try {
    const response = await fetch("/api/snapshot" + (since === null ? "" : "?since=" + since),
                                 {signal:AbortSignal.timeout(2000)});
    const update = await response.json();
    const changed = since !== update.revision || update.reset;
    latest = update;
    merge(update);
    since = update.revision;
    const state = update.stalled ? "観測更新停止" : stateName(update.state);
    if (byId("runtime").textContent !== state) byId("runtime").textContent = state;
    if (changed) { renderModules(); renderEvents(); }
    renderActivities(); renderReports(); renderQueries(update.queries);
  } catch {
    if (latest?.state !== "failed" && latest?.state !== "stopped") byId("runtime").textContent = "観測更新停止";
  } finally {
    setTimeout(tick, 1000);
  }
}
tick();
