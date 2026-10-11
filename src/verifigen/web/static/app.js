"use strict";
const $ = (id) => document.getElementById(id);
const json = (value) => JSON.stringify(value, null, 2);
const icons = () => window.lucide?.createIcons();
let presets = [],
  evaluations = [],
  currentPreset = null,
  runId = null,
  stream = null,
  record = null,
  candidates = [],
  busy = false,
  score = null;
const reasons = {
  judge_passed: "判定通过且满足发布条件",
  judge_unknown: "业务证据不足或冲突",
  repair_budget: "修复轮次已耗尽",
  model_budget: "模型调用预算已耗尽",
  deadline: "达到执行时限",
  no_progress: "修复重复，未取得进展",
  score_below_threshold: "判定通过，但评分未达到阈值",
  score_plateau: "评分连续未提升",
  token_threshold: "达到已观测 Token 阈值",
  usage_unknown: "提供方未返回 Token 用量",
  judge_error: "Judge 调用或结构化协议失败",
  repair_error: "Repair 调用或结构化协议失败",
  generator_error: "生成调用失败",
  gate_error: "关卡执行失败",
  invalid_schema: "输出 Schema 无效",
  renderer_error: "输出渲染失败",
};
function node(tag, text, className) {
  const el = document.createElement(tag);
  if (text !== undefined) el.textContent = text;
  if (className) el.className = className;
  return el;
}
function notice(message = "") {
  $("notice").textContent = message;
  $("notice").hidden = !message;
}
async function api(path, options = {}) {
  const response = await fetch(path, options);
  if (!response.ok) {
    const value = await response.json().catch(() => ({}));
    throw new Error(
      typeof value.detail === "string"
        ? value.detail
        : `请求失败 (${response.status})：请检查输入字段`,
    );
  }
  return response.json();
}
function view(name) {
  document
    .querySelectorAll(".view")
    .forEach((el) => (el.hidden = el.id !== `${name}-view`));
  document
    .querySelectorAll(".tab")
    .forEach((el) => el.classList.toggle("active", el.dataset.view === name));
}
function setBusy(value) {
  busy = value;
  $("run").disabled = value;
  $("reset").disabled = value;
  $("preset").disabled = value;
  $("stop").hidden = !value;
}
function state(value, text) {
  $("run-state").className = `state ${value}`;
  $("run-state").textContent =
    text ||
    {
      running: "运行中",
      passed: "已发布",
      fallback: "已兜底",
      error: "执行失败",
      cancelled: "已取消",
      idle: "等待运行",
    }[value] ||
    value;
}
function fillPreset(preset) {
  currentPreset = preset;
  $("prompt").value = preset.prompt;
  $("source").value = json(preset.source);
  $("initial").value = json(preset.initial);
  $("criteria").value = json(preset.criteria);
  $("schema").value = json(preset.output_schema);
  $("instructions").value = preset.instructions || "";
  $("fallback-text").value =
    preset.fallback_text || "当前内容未通过校验，请人工核实。";
  $("fallback-reasons").value = json(preset.fallback_by_reason || {});
  $("citation-gate").checked = preset.citation_gate;
  $("dataset-tag").textContent =
    preset.dataset === "RAGTruth" ? "RAGTruth · PUBLIC" : "SYNTHETIC";
  $("case-id").textContent = preset.case_id;
  $("generate").checked = false;
  $("initial").disabled = false;
  notice();
}
function clearRun() {
  if (stream) stream.close();
  record = null;
  runId = null;
  candidates = [];
  score = null;
  $("score").textContent = "—";
  $("call-count").textContent = "0";
  $("repair-count").textContent = "0";
  $("token-count").textContent = "—";
  $("token-count").dataset.total = "0";
  $("elapsed").textContent = "—";
  $("round-count").textContent = "0 轮判定";
  $("round-list").replaceChildren();
  $("event-log").replaceChildren();
  $("comparison").hidden = true;
  $("compare-round").replaceChildren();
  $("reason").hidden = true;
  $("final-output").className = "final-output empty";
  $("final-output").textContent = "尚无发布结果";
  $("export").disabled = true;
  document
    .querySelectorAll("[data-stage]")
    .forEach((el) => (el.className = ""));
  state("idle");
}
function badge(status) {
  return node("span", status, `badge status-${status}`);
}
function addRound(round) {
  const details = node("details", undefined, "round");
  details.open = true;
  const summary = node("summary");
  summary.append(
    node("span", `R${round.round_index}`, "mono"),
    badge(round.effective_verdict.status),
    node("span", round.effective_verdict.summary, "summary-text"),
    node("span", round.verdict.score.toFixed(2), "round-score"),
  );
  const body = node("div", undefined, "round-content");
  if (round.verdict.status !== round.effective_verdict.status)
    body.append(
      node(
        "p",
        `模型判定 ${round.verdict.status}，硬关卡改判 ${round.effective_verdict.status}`,
        "round-summary",
      ),
    );
  body.append(node("p", round.effective_verdict.summary, "round-summary"));
  for (const issue of round.effective_verdict.issues) {
    const block = node("div", undefined, "issue");
    block.append(node("strong", issue.criterion_id), node("p", issue.message));
    if (issue.evidence)
      block.append(node("p", `证据：${issue.evidence}`, "evidence"));
    if (issue.suggestion)
      block.append(node("p", `修复建议：${issue.suggestion}`, "evidence"));
    body.append(block);
  }
  details.append(summary, body);
  $("round-list").append(details);
  $("round-count").textContent = `${$("round-list").children.length} 轮判定`;
}
function event(event) {
  const detail = event.details || {};
  const name = event.event;
  const time = event.elapsed_ms;
  if (time !== undefined)
    $("elapsed").textContent = `${(time / 1000).toFixed(1)} s`;
  if (name === "candidate") {
    candidates[detail.round] = detail.candidate;
    $("comparison").hidden = false;
    const select = $("compare-round");
    if (
      !Array.from(select.options).some((o) => o.value === String(detail.round))
    )
      select.add(new Option(`第 ${detail.round} 轮候选`, String(detail.round)));
    select.value = String(detail.round);
    comparison();
  }
  if (name === "round_complete") {
    addRound(detail);
    score = detail.verdict.score;
    $("score").textContent = score.toFixed(2);
  }
  if (name === "call_started") {
    $("call-count").textContent = detail.model_calls;
    document
      .querySelectorAll("[data-stage]")
      .forEach((el) =>
        el.classList.toggle("active", el.dataset.stage === detail.role),
      );
  }
  if (name === "gate_checked") {
    document
      .querySelectorAll("[data-stage]")
      .forEach((el) =>
        el.classList.toggle("active", el.dataset.stage === "gate"),
      );
  }
  if (name === "repair_committed") $("repair-count").textContent = detail.round;
  if (name === "judged" || name === "call_finished") {
    if (detail.total_tokens != null) {
      const previous = $("token-count").dataset.total || "0";
      const value = Number(previous) + detail.total_tokens;
      $("token-count").dataset.total = value;
      $("token-count").textContent = value.toLocaleString();
    }
  }
  if (name === "complete") {
    setBusy(false);
    state(detail.state);
    if (stream) stream.close();
    if (detail.result) renderResult(detail.result);
    else {
      $("final-output").className = "final-output fallback";
      $("final-output").textContent =
        detail.state === "cancelled"
          ? "运行已取消，候选未发布。"
          : "执行失败，候选未发布。";
    }
    loadRecord();
  }
  if (
    name !== "candidate" &&
    name !== "round_complete" &&
    name !== "complete"
  ) {
    const line = node("li");
    line.append(
      node(
        "span",
        `${time == null ? "—" : (time / 1000).toFixed(2) + "s"}  ${name}`,
      ),
      node("span", detail.role || detail.action || detail.reason || ""),
    );
    $("event-log").append(line);
  }
}
function comparison() {
  const index = Number($("compare-round").value);
  $("before").textContent = json(candidates[0]);
  $("after").textContent = json(candidates[index]);
}
function renderResult(result) {
  state(result.status);
  $("final-output").className =
    `final-output ${result.status === "fallback" ? "fallback" : ""}`;
  $("final-output").textContent = result.text;
  $("reason").hidden = false;
  $("reason").textContent =
    `${reasons[result.reason] || result.reason} · ${result.reason}`;
  $("call-count").textContent = result.model_calls;
  $("repair-count").textContent = result.repair_rounds;
  const known = result.usages.filter(
    (u) => u.input_tokens != null && u.output_tokens != null,
  );
  const total = known.reduce(
    (sum, u) => sum + u.input_tokens + u.output_tokens,
    0,
  );
  $("token-count").textContent =
    `${total.toLocaleString()}${known.length < result.usages.length ? " + ?" : ""}`;
  if (result.trace.length)
    $("elapsed").textContent =
      `${(result.trace.at(-1).elapsed_ms / 1000).toFixed(1)} s`;
  document
    .querySelectorAll("[data-stage]")
    .forEach((el) => el.classList.remove("active"));
}
async function loadRecord() {
  if (!runId) return;
  try {
    record = await api(`/api/runs/${runId}`);
    $("export").disabled = false;
    $("footer-run").textContent = `run ${runId.slice(0, 12)}`;
  } catch (error) {
    notice(error.message);
  }
}
async function start() {
  try {
    notice();
    const source = JSON.parse($("source").value),
      criteria = JSON.parse($("criteria").value),
      schema = JSON.parse($("schema").value);
    const generate = $("generate").checked;
    const initial = generate ? null : JSON.parse($("initial").value);
    const payload = {
      scenario: currentPreset?.scenario || "custom",
      source,
      prompt: $("prompt").value,
      criteria,
      output_schema: schema,
      instructions: $("instructions").value,
      fallback_text: $("fallback-text").value,
      fallback_by_reason: JSON.parse($("fallback-reasons").value),
      initial,
      generate,
      citation_gate: $("citation-gate").checked,
      max_repair_rounds: Number($("rounds").value),
      max_model_calls: Number($("calls").value),
      deadline_seconds: Number($("deadline").value),
      min_pass_score: Number($("threshold").value),
      max_observed_tokens: $("tokens").value ? Number($("tokens").value) : null,
      score_patience: $("patience").value ? Number($("patience").value) : null,
    };
    clearRun();
    $("token-count").dataset.total = "0";
    setBusy(true);
    state("running");
    const response = await api("/api/runs", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    runId = response.id;
    stream = new EventSource(response.events_url);
    stream.onmessage = (message) => {
      try {
        event(JSON.parse(message.data));
      } catch (error) {
        notice(`事件解析失败：${error.message}`);
      }
    };
    stream.onerror = () => {
      notice("事件连接暂时中断，正在重连。运行可在历史记录中查询。");
    };
  } catch (error) {
    setBusy(false);
    state("error");
    notice(
      error instanceof SyntaxError
        ? "输入不是有效 JSON，请检查业务证据、候选、规则和 Schema。"
        : error.message,
    );
  }
}
async function history() {
  try {
    const rows = await api("/api/history");
    $("history-rows").replaceChildren();
    for (const item of rows) {
      const tr = node("tr");
      for (const value of [
        new Date(item.created_at).toLocaleString(),
        item.scenario,
        item.model,
        item.state,
        item.model_calls ?? "—",
        item.reason || "—",
      ])
        tr.append(node("td", String(value)));
      const td = node("td"),
        button = node("button", "查看", "row-button");
      button.addEventListener("click", () => openRun(item.id));
      td.append(button);
      tr.append(td);
      $("history-rows").append(tr);
    }
    if (!rows.length) {
      const td = node("td", "暂无运行记录");
      td.colSpan = 7;
      const tr = node("tr");
      tr.append(td);
      $("history-rows").append(tr);
    }
  } catch (error) {
    notice(error.message);
  }
}
async function openRun(id) {
  if (busy) {
    notice("请先等待或停止当前运行。");
    return;
  }
  try {
    const stored = await api(`/api/runs/${id}`);
    clearRun();
    fillPreset({ ...stored.input, dataset: "stored", case_id: id });
    for (const [control, field] of Object.entries({
      rounds: "max_repair_rounds",
      calls: "max_model_calls",
      deadline: "deadline_seconds",
      threshold: "min_pass_score",
      tokens: "max_observed_tokens",
      patience: "score_patience",
    })) {
      $(control).value = stored.input[field] ?? "";
    }
    $("generate").checked = stored.input.generate;
    $("initial").disabled = stored.input.generate;
    runId = id;
    record = stored;
    view("run");
    for (const e of stored.events) if (e.event !== "complete") event(e);
    if (stored.result) renderResult(stored.result);
    state(stored.state);
    $("export").disabled = false;
    $("footer-run").textContent = `run ${id.slice(0, 12)}`;
    if (stored.state === "running") {
      setBusy(true);
      stream = new EventSource(
        `/api/runs/${id}/events?after=${stored.events.length - 1}`,
      );
      stream.onmessage = (message) => event(JSON.parse(message.data));
    }
  } catch (error) {
    notice(error.message);
  }
}
function evaluation() {
  const value = evaluations.find((e) => e.id === $("evaluation-select").value);
  if (!value) return;
  const summary = value.summary,
    overall = summary.overall;
  $("evaluation-note").textContent =
    value.dataset === "RAGTruth"
      ? `RAGTruth · ${overall.cases} 条 · ${summary.model} · 原始人工标签评价首轮幻觉检出；修复稿的独立评审尚未完成。`
      : `合成集 · ${summary.cases} 条 · ${summary.model} · 首轮准确率已按 pass/fail 严格口径重算，调用失败计为错误；修复结果由独立场景规则评分。`;
  $("evaluation-metrics").replaceChildren();
  const metrics = [
    ["首轮准确率", overall.judge_detection_accuracy],
    [
      "错误初稿修复率",
      overall.bad_case_repair_success ?? summary.repair_success_rate,
    ],
    ["兜底率", overall.fallback_rate ?? summary.fallback_rate],
    ["模型调用", overall.model_calls ?? summary.model_calls],
  ];
  if (value.dataset === "RAGTruth") {
    metrics.splice(
      1,
      0,
      ["幻觉检出召回率", overall.error_detection_recall],
      ["正常回答误杀率", overall.false_alarm_rate],
      ["检出 F1", overall.detection_f1],
    );
  }
  for (const [label, value] of metrics) {
    const block = node("div");
    block.append(
      node("span", label),
      node(
        "strong",
        value == null
          ? "待评审"
          : label === "模型调用"
            ? value.toLocaleString()
            : `${(value * 100).toFixed(2)}%`,
      ),
    );
    $("evaluation-metrics").append(block);
  }
  $("evaluation-rows").replaceChildren();
  const filter = $("evaluation-filter").value;
  for (const r of value.records.filter(
    (r) =>
      filter === "all" ||
      (filter === "wrong" && !r.detection_correct) ||
      (filter === "release" &&
        r.status === "passed" &&
        r.final_correct === false) ||
      (filter === "fallback" && r.status === "fallback"),
  )) {
    const tr = node("tr");
    for (const v of [
      r.id,
      r.task_type || r.scenario,
      r.initial_should_pass ? "正常" : "有错",
      r.first_judge_status,
      r.status,
      r.model_calls,
    ])
      tr.append(node("td", String(v)));
    const td = node("td"),
      button = node("button", "记录", "row-button");
    button.addEventListener("click", () => {
      $("record-content").textContent = json(r);
      $("record-dialog").showModal();
    });
    td.append(button);
    tr.append(td);
    $("evaluation-rows").append(tr);
  }
  if (!$("evaluation-rows").children.length) {
    const row = node("tr"),
      cell = node(
        "td",
        value.dataset === "RAGTruth" && filter === "release"
          ? "修复后独立评审尚未完成，不能据此筛选错误放行。"
          : "当前筛选条件下暂无记录。",
      );
    cell.colSpan = 7;
    row.append(cell);
    $("evaluation-rows").append(row);
  }
}
$("run").addEventListener("click", start);
$("stop").addEventListener("click", async () => {
  try {
    if (runId) await api(`/api/runs/${runId}/cancel`, { method: "POST" });
  } catch (error) {
    notice(error.message);
  }
});
$("preset").addEventListener("change", () => {
  if (!busy) fillPreset(presets.find((p) => p.id === $("preset").value));
});
$("reset").addEventListener("click", () => {
  fillPreset(currentPreset);
  clearRun();
});
$("generate").addEventListener("change", () => {
  $("initial").disabled = $("generate").checked;
});
$("compare-round").addEventListener("change", comparison);
$("refresh-history").addEventListener("click", history);
$("evaluation-select").addEventListener("change", evaluation);
$("evaluation-filter").addEventListener("change", evaluation);
$("close-dialog").addEventListener("click", () => $("record-dialog").close());
$("export").addEventListener("click", () => {
  if (!record) return;
  const url = URL.createObjectURL(
    new Blob([json(record)], { type: "application/json" }),
  );
  const link = node("a");
  link.href = url;
  link.download = `verifigen-${record.id}.json`;
  link.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
});
document.querySelectorAll(".tab").forEach((button) =>
  button.addEventListener("click", () => {
    view(button.dataset.view);
    if (button.dataset.view === "history") history();
    if (button.dataset.view === "evaluation") evaluation();
  }),
);
async function boot() {
  try {
    const [config, p, e] = await Promise.all([
      api("/api/config"),
      api("/api/presets"),
      api("/api/evaluations"),
    ]);
    presets = p;
    evaluations = e;
    $("model-label").textContent = config.model;
    $("connection-dot").classList.toggle("ready", config.configured);
    if (!config.configured)
      notice("未配置 DASHSCOPE_API_KEY，暂时不能发起真实运行。");
    for (const preset of presets)
      $("preset").add(new Option(preset.label, preset.id));
    for (const evaluation of evaluations)
      $("evaluation-select").add(new Option(evaluation.label, evaluation.id));
    fillPreset(presets[0]);
    if (!config.configured) {
      notice("未配置 DASHSCOPE_API_KEY，暂时不能发起真实运行。");
      $("run").disabled = true;
    }
    icons();
  } catch (error) {
    notice(error.message);
    $("run").disabled = true;
  }
}
icons();
boot();
