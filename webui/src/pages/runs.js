import { api, buildApiUrl } from "../lib/api.js";

const STYLE_LINK_ID = "energycrawler-ui2-scheduler-runs-style";
const LIVE_LOG_MAX = 300;
const WS_RECONNECT_DELAY_MS = 3000;
const FALLBACK_POLL_INTERVAL_MS = 5000;

function ensurePageStyle() {
  if (document.getElementById(STYLE_LINK_ID)) return;
  const link = document.createElement("link");
  link.id = STYLE_LINK_ID;
  link.rel = "stylesheet";
  link.href = new URL("../styles/scheduler-runs.css", import.meta.url).href;
  document.head.appendChild(link);
}

function safeFormatDateTime(ctx, value) {
  if (!value) return "-";
  if (ctx && typeof ctx.formatDateTime === "function") {
    return ctx.formatDateTime(value);
  }
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return String(value);
  return date.toLocaleString();
}

function createElement(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined) node.textContent = text;
  return node;
}

function createDataCell(text, className = "") {
  return createElement("td", className, text);
}

function createPill(text, tone = "neutral") {
  return createElement("span", `sr-pill sr-pill--${tone}`, String(text || "-"));
}

function normalizeRuns(payload) {
  const runs = payload?.data?.runs;
  return Array.isArray(runs) ? runs : [];
}

function normalizeRun(payload) {
  const run = payload?.data;
  if (run && typeof run === "object") return run;
  return null;
}

function normalizeLogs(payload) {
  const logs = payload?.data?.logs;
  return Array.isArray(logs) ? logs : [];
}

function parsePositiveInteger(value, fallback) {
  const parsed = Number(value);
  if (!Number.isInteger(parsed) || parsed <= 0) return fallback;
  return parsed;
}

function toIsoFromLocalInput(value) {
  const text = String(value || "").trim();
  if (!text) return "";
  const date = new Date(text);
  if (Number.isNaN(date.getTime())) return "";
  return date.toISOString();
}

function toLocalDateTimeInput(value) {
  if (!value) return "";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "";

  const yyyy = String(date.getFullYear()).padStart(4, "0");
  const mm = String(date.getMonth() + 1).padStart(2, "0");
  const dd = String(date.getDate()).padStart(2, "0");
  const hh = String(date.getHours()).padStart(2, "0");
  const min = String(date.getMinutes()).padStart(2, "0");
  return `${yyyy}-${mm}-${dd}T${hh}:${min}`;
}

function parseHashQueryParams() {
  if (typeof window === "undefined") return new URLSearchParams();
  const hash = String(window.location.hash || "");
  const queryIndex = hash.indexOf("?");
  if (queryIndex < 0) return new URLSearchParams();
  return new URLSearchParams(hash.slice(queryIndex + 1));
}

function statusTone(status) {
  const normalized = String(status || "").toLowerCase();
  if (["completed", "success"].includes(normalized)) return "success";
  if (["queued", "pending"].includes(normalized)) return "warning";
  if (["running", "accepted"].includes(normalized)) return "info";
  if (["failed", "rejected", "cancelled", "error"].includes(normalized)) return "danger";
  return "neutral";
}

function createStatusBadge(status) {
  return createElement(
    "span",
    `sr-status sr-status--${statusTone(status)}`,
    String(status || "unknown")
  );
}

function stringifyMessage(value) {
  if (value === null || value === undefined) return "";
  return String(value);
}

function formatDetails(details) {
  try {
    return JSON.stringify(details ?? {}, null, 2);
  } catch {
    return "{}";
  }
}

function buildLogsSocketUrl() {
  const httpUrl = new URL(buildApiUrl("/api/ws/logs"), window.location.origin);
  if (httpUrl.protocol === "https:") httpUrl.protocol = "wss:";
  else if (httpUrl.protocol === "http:") httpUrl.protocol = "ws:";
  return httpUrl.toString();
}

function buildLogKey(log) {
  return [
    log?.id,
    log?.timestamp || log?.time || log?.created_at,
    log?.level,
    log?.task_id,
    log?.run_id,
    log?.message,
  ]
    .map((chunk) => String(chunk ?? ""))
    .join("|");
}

export default async function renderRunsPage(mountEl, ctx = {}) {
  ensurePageStyle();

  const state = {
    runs: [],
    loadingRuns: false,
    loadingDetail: false,
    loadingLogs: false,
    retryingRun: false,
    selectedRunId: null,
    selectedRun: null,
    runLogs: [],
    ws: null,
    wsState: "idle",
    wsReconnectTimer: null,
    fallbackPollTimer: null,
    destroyed: false,
  };
  const cleanups = [];

  mountEl.innerHTML = `
    <section class="sr-page sr-runs-page">
      <header class="sr-header">
        <div>
          <h2>Run Center</h2>
          <p class="sr-muted">按状态/平台/时间过滤 runs，查看详情抽屉与关联 task 日志。</p>
        </div>
        <div class="sr-actions">
          <button type="button" class="secondary" data-action="refresh-runs">刷新 runs</button>
        </div>
      </header>

      <section class="sr-card">
        <h3 class="sr-card-title">Run 过滤</h3>
        <form data-role="runs-filter-form" class="sr-controls sr-controls--runs">
          <label class="sr-control">
            <span>job_id</span>
            <input type="text" name="job_id" placeholder="可选" />
          </label>
          <label class="sr-control">
            <span>status</span>
            <select name="status">
              <option value="">全部</option>
              <option value="queued">queued</option>
              <option value="running">running</option>
              <option value="completed">completed</option>
              <option value="failed">failed</option>
              <option value="cancelled">cancelled</option>
            </select>
          </label>
          <label class="sr-control">
            <span>platform</span>
            <select name="platform">
              <option value="">全部</option>
              <option value="xhs">xhs</option>
              <option value="x">x</option>
            </select>
          </label>
          <label class="sr-control">
            <span>from</span>
            <input type="datetime-local" name="from" />
          </label>
          <label class="sr-control">
            <span>to</span>
            <input type="datetime-local" name="to" />
          </label>
          <label class="sr-control">
            <span>limit</span>
            <input type="number" name="limit" min="1" max="500" value="100" />
          </label>
          <div class="sr-actions sr-controls-actions">
            <button type="submit">应用筛选</button>
            <button type="button" class="secondary" data-action="clear-runs-filters">清空</button>
          </div>
        </form>
      </section>

      <section class="sr-card">
        <h3 class="sr-card-title">Run 列表</h3>
        <div class="sr-table-wrap">
          <table class="sr-table sr-table--runs">
            <thead>
              <tr>
                <th class="sr-col-id">Run ID</th>
                <th class="sr-col-id">Job ID</th>
                <th class="sr-col-status">Status</th>
                <th class="sr-col-platform">Platform</th>
                <th class="sr-col-id">Task ID</th>
                <th class="sr-col-time">Triggered</th>
                <th class="sr-col-time">Started</th>
                <th class="sr-col-time">Finished</th>
                <th class="sr-col-message">Message</th>
                <th>操作</th>
              </tr>
            </thead>
            <tbody data-role="runs-body"></tbody>
          </table>
        </div>
        <p class="sr-muted" data-role="runs-meta">-</p>
      </section>

      <button type="button" class="sr-drawer-backdrop" data-role="drawer-backdrop" hidden></button>
      <aside class="sr-drawer" data-role="run-drawer" aria-hidden="true">
        <div class="sr-drawer-header">
          <div>
            <h3>Run 详情</h3>
            <p class="sr-muted" data-role="run-detail-subtitle">-</p>
          </div>
          <button type="button" class="secondary" data-action="close-drawer">关闭</button>
        </div>

        <div class="sr-drawer-body">
          <section class="sr-panel-flat">
            <h4>基础信息</h4>
            <dl class="sr-detail-grid" data-role="run-detail-grid"></dl>
          </section>

          <section class="sr-panel-flat">
            <div class="sr-card-headline">
              <h4>阶段时间线</h4>
              <button
                type="button"
                class="secondary sr-btn-sm"
                data-action="retry-run-now"
                data-role="retry-run-btn"
              >
                重试本次任务
              </button>
            </div>
            <ol class="sr-run-timeline" data-role="run-timeline"></ol>
            <p class="sr-muted sr-timeline-hint" data-role="retry-run-hint">
              将按 run.job_id 调用 /api/scheduler/jobs/{job_id}/run-now。
            </p>
          </section>

          <section class="sr-panel-flat">
            <h4>details JSON</h4>
            <pre class="sr-json" data-role="run-details-json">{}</pre>
          </section>

          <section class="sr-panel-flat">
            <div class="sr-card-headline">
              <h4>关联 task 日志查询</h4>
              <div class="sr-inline">
                <span class="sr-ws-state sr-ws-state--idle" data-role="ws-state">WS 未连接</span>
                <button type="button" class="secondary" data-action="refresh-logs">刷新日志</button>
              </div>
            </div>
            <p class="sr-muted" data-role="ws-hint">实时日志优先 WebSocket，断线后自动回退轮询。</p>
            <form class="sr-controls sr-controls--log" data-role="log-filter-form">
              <label class="sr-control">
                <span>task_id</span>
                <input type="text" name="task_id" placeholder="task-xxxx" />
              </label>
              <label class="sr-control">
                <span>run_id</span>
                <input type="number" name="run_id" min="1" placeholder="可选" />
              </label>
              <label class="sr-control">
                <span>limit</span>
                <input type="number" name="limit" min="1" max="1000" value="120" />
              </label>
              <div class="sr-actions">
                <button type="submit">查询日志</button>
              </div>
            </form>
            <ul class="sr-log-list" data-role="log-list"></ul>
          </section>
        </div>
      </aside>
    </section>
  `;

  const refs = {
    runsFilterForm: mountEl.querySelector('[data-role="runs-filter-form"]'),
    runsBody: mountEl.querySelector('[data-role="runs-body"]'),
    runsMeta: mountEl.querySelector('[data-role="runs-meta"]'),
    refreshRunsBtn: mountEl.querySelector('[data-action="refresh-runs"]'),

    drawer: mountEl.querySelector('[data-role="run-drawer"]'),
    drawerBackdrop: mountEl.querySelector('[data-role="drawer-backdrop"]'),
    drawerSubtitle: mountEl.querySelector('[data-role="run-detail-subtitle"]'),
    runDetailGrid: mountEl.querySelector('[data-role="run-detail-grid"]'),
    runDetailsJson: mountEl.querySelector('[data-role="run-details-json"]'),
    runTimeline: mountEl.querySelector('[data-role="run-timeline"]'),
    retryRunBtn: mountEl.querySelector('[data-role="retry-run-btn"]'),
    retryRunHint: mountEl.querySelector('[data-role="retry-run-hint"]'),

    logFilterForm: mountEl.querySelector('[data-role="log-filter-form"]'),
    logList: mountEl.querySelector('[data-role="log-list"]'),
    wsState: mountEl.querySelector('[data-role="ws-state"]'),
    wsHint: mountEl.querySelector('[data-role="ws-hint"]'),
  };

  function toast(message, options = {}) {
    if (ctx && typeof ctx.showToast === "function") {
      ctx.showToast(message, options);
      return;
    }
    // eslint-disable-next-line no-console
    console.log(`[runs] ${message}`);
  }

  function setRunsLoading(isLoading) {
    state.loadingRuns = isLoading;
    if (refs.refreshRunsBtn) refs.refreshRunsBtn.disabled = isLoading;
  }

  function setWsState(nextState, detail = "") {
    state.wsState = nextState;
    if (!refs.wsState || !refs.wsHint) return;

    refs.wsState.className = `sr-ws-state sr-ws-state--${nextState}`;
    const textMap = {
      idle: "WS 未连接",
      connecting: "WS 连接中",
      connected: "WS 已连接",
      reconnecting: "WS 重连中",
      fallback: "WS 不可用",
      error: "WS 异常",
    };
    refs.wsState.textContent = textMap[nextState] || "WS 未知";

    const hintMap = {
      idle: "打开 Run 详情后将自动连接实时日志流。",
      connecting: "正在连接 /api/ws/logs ...",
      connected: "实时日志已启用，轮询已暂停。",
      reconnecting: "连接断开，正在尝试重连；期间将使用轮询。",
      fallback: "当前使用轮询兜底（每 5 秒刷新）。",
      error: "连接异常，已切换轮询兜底。",
    };
    refs.wsHint.textContent = detail || hintMap[nextState] || "";
  }

  function appendRealtimeLog(logEntry) {
    const existing = state.runLogs;
    const key = buildLogKey(logEntry);
    if (existing.some((item) => buildLogKey(item) === key)) return;

    const nextLogs = [...existing, logEntry];
    if (nextLogs.length > LIVE_LOG_MAX) {
      nextLogs.splice(0, nextLogs.length - LIVE_LOG_MAX);
    }
    state.runLogs = nextLogs;
    renderLogs();
  }

  function matchesSelectedRun(logEntry) {
    if (!state.selectedRun && !state.selectedRunId) return false;

    const selectedRunId = Number(state.selectedRun?.run_id || state.selectedRunId || 0);
    const selectedTaskId = String(state.selectedRun?.task_id || "").trim();

    const candidateRunId = Number(logEntry?.run_id || 0);
    if (selectedRunId && candidateRunId && candidateRunId === selectedRunId) {
      return true;
    }

    const candidateTaskId = String(logEntry?.task_id || "").trim();
    if (selectedTaskId && candidateTaskId && candidateTaskId === selectedTaskId) {
      return true;
    }

    return false;
  }

  function clearWsReconnectTimer() {
    if (!state.wsReconnectTimer) return;
    window.clearTimeout(state.wsReconnectTimer);
    state.wsReconnectTimer = null;
  }

  function stopFallbackPolling() {
    if (!state.fallbackPollTimer) return;
    window.clearInterval(state.fallbackPollTimer);
    state.fallbackPollTimer = null;
  }

  function startFallbackPolling() {
    if (!state.selectedRunId || state.fallbackPollTimer || state.destroyed) return;
    setWsState("fallback");
    state.fallbackPollTimer = window.setInterval(() => {
      loadLogs({ silent: true }).catch(() => {});
    }, FALLBACK_POLL_INTERVAL_MS);
  }

  function closeWebSocket() {
    if (!state.ws) return;
    try {
      state.ws.onopen = null;
      state.ws.onmessage = null;
      state.ws.onerror = null;
      state.ws.onclose = null;
      state.ws.close();
    } catch {
      // ignore
    }
    state.ws = null;
  }

  function updateRetryRunButton() {
    if (!refs.retryRunBtn || !refs.retryRunHint) return;

    const jobId = String(state.selectedRun?.job_id || "").trim();
    refs.retryRunBtn.dataset.jobId = jobId;
    refs.retryRunBtn.textContent = state.retryingRun ? "重试中..." : "重试本次任务";
    refs.retryRunBtn.disabled = state.retryingRun || !jobId;

    if (!jobId) {
      refs.retryRunHint.textContent = "当前 run 缺少 job_id，无法执行重试。";
      return;
    }

    refs.retryRunHint.textContent = state.retryingRun
      ? `正在触发 /api/scheduler/jobs/${jobId}/run-now ...`
      : `将调用 /api/scheduler/jobs/${jobId}/run-now。`;
  }

  function renderRunTimeline(run) {
    if (!refs.runTimeline) return;
    refs.runTimeline.innerHTML = "";
    if (!run || typeof run !== "object") return;

    const normalizedStatus = String(run.status || "").toLowerCase();
    const terminalStatuses = ["completed", "success", "failed", "cancelled", "error", "rejected"];
    const isTerminal = terminalStatuses.includes(normalizedStatus);

    const stages = [
      {
        key: "triggered",
        label: "Triggered",
        value: run.triggered_at,
        pendingText: "等待触发",
      },
      {
        key: "started",
        label: "Started",
        value: run.started_at,
        pendingText: isTerminal ? "未记录开始时间" : "尚未开始",
      },
      {
        key: "finished",
        label: "Finished",
        value: run.finished_at,
        pendingText: isTerminal ? "未记录结束时间" : "尚未结束",
      },
    ];

    stages.forEach((stage) => {
      const item = createElement("li", "sr-run-timeline-item");
      item.classList.add(stage.value ? "is-done" : "is-pending");

      const main = createElement("div", "sr-run-timeline-main");
      const label = createElement("span", "sr-run-timeline-label", stage.label);
      const value = createElement(
        "span",
        `sr-run-timeline-value${stage.value ? "" : " is-muted"}`,
        stage.value ? safeFormatDateTime(ctx, stage.value) : stage.pendingText
      );
      main.append(label, value);
      item.appendChild(main);
      refs.runTimeline.appendChild(item);
    });

    const statusItem = createElement("li", "sr-run-timeline-item sr-run-timeline-item--status");
    statusItem.classList.add(`is-${statusTone(run.status)}`);

    const statusMain = createElement("div", "sr-run-timeline-main");
    const statusLabel = createElement("span", "sr-run-timeline-label", "Status");
    const statusMeta = createElement("div", "sr-inline");
    statusMeta.appendChild(createStatusBadge(run.status));
    const statusTimeValue = run.finished_at || run.updated_at || run.started_at || run.triggered_at;
    statusMeta.appendChild(
      createElement(
        "span",
        "sr-run-timeline-value",
        statusTimeValue ? safeFormatDateTime(ctx, statusTimeValue) : "-"
      )
    );
    statusMain.append(statusLabel, statusMeta);
    statusItem.appendChild(statusMain);
    if (run.message) {
      statusItem.appendChild(
        createElement("p", "sr-run-timeline-note", stringifyMessage(run.message))
      );
    }
    refs.runTimeline.appendChild(statusItem);
  }

  function stopLiveLogs() {
    clearWsReconnectTimer();
    stopFallbackPolling();
    closeWebSocket();
    setWsState("idle");
  }

  function scheduleWsReconnect() {
    if (state.wsReconnectTimer || !state.selectedRunId || state.destroyed) return;
    setWsState("reconnecting");
    startFallbackPolling();
    state.wsReconnectTimer = window.setTimeout(() => {
      state.wsReconnectTimer = null;
      connectWebSocket();
    }, WS_RECONNECT_DELAY_MS);
  }

  function connectWebSocket() {
    if (!state.selectedRunId || state.destroyed) return;
    if (typeof window === "undefined" || typeof window.WebSocket !== "function") {
      startFallbackPolling();
      return;
    }

    closeWebSocket();
    setWsState("connecting");

    let socketUrl;
    try {
      socketUrl = buildLogsSocketUrl();
    } catch {
      setWsState("error", "无法构建 WS 地址，已降级轮询。");
      startFallbackPolling();
      return;
    }

    const ws = new WebSocket(socketUrl);
    state.ws = ws;

    ws.onopen = () => {
      if (state.ws !== ws || state.destroyed) return;
      clearWsReconnectTimer();
      stopFallbackPolling();
      setWsState("connected");
    };

    ws.onmessage = (event) => {
      if (state.ws !== ws || state.destroyed) return;

      const rawData = event.data;
      if (typeof rawData === "string") {
        if (rawData === "ping") {
          try {
            ws.send("pong");
          } catch {
            // ignore heartbeat send failure
          }
          return;
        }
        if (rawData === "pong") return;
      }

      let payload = null;
      try {
        payload = typeof rawData === "string" ? JSON.parse(rawData) : rawData;
      } catch {
        return;
      }

      if (!payload || typeof payload !== "object") return;
      if (!matchesSelectedRun(payload)) return;
      appendRealtimeLog(payload);
    };

    ws.onerror = () => {
      if (state.ws !== ws || state.destroyed) return;
      setWsState("error", "WS 连接异常，切换到轮询模式。");
      startFallbackPolling();
    };

    ws.onclose = () => {
      if (state.ws !== ws || state.destroyed) return;
      state.ws = null;
      scheduleWsReconnect();
    };
  }

  function setDrawerOpen(open) {
    refs.drawer.classList.toggle("is-open", open);
    refs.drawer.setAttribute("aria-hidden", open ? "false" : "true");
    refs.drawerBackdrop.hidden = !open;
    refs.drawerBackdrop.classList.toggle("is-open", open);

    if (!open) {
      stopLiveLogs();
      state.selectedRunId = null;
      state.selectedRun = null;
      state.retryingRun = false;
      state.runLogs = [];
      refs.drawerSubtitle.textContent = "-";
      refs.runDetailGrid.innerHTML = "";
      refs.runDetailsJson.textContent = "{}";
      if (refs.runTimeline) refs.runTimeline.innerHTML = "";
      refs.logList.innerHTML = "";
      refs.logFilterForm.reset();
      refs.logFilterForm.elements.limit.value = "120";
      updateRetryRunButton();
      renderRunsTable();
    }
  }

  function buildRunsQuery() {
    const formData = new FormData(refs.runsFilterForm);
    const query = {
      job_id: String(formData.get("job_id") || "").trim() || undefined,
      status: String(formData.get("status") || "").trim() || undefined,
      platform: String(formData.get("platform") || "").trim() || undefined,
      from: toIsoFromLocalInput(formData.get("from")) || undefined,
      to: toIsoFromLocalInput(formData.get("to")) || undefined,
      limit: parsePositiveInteger(formData.get("limit"), 100),
    };
    return query;
  }

  function applyFiltersFromHash() {
    const params = parseHashQueryParams();
    if (!params || Array.from(params.keys()).length === 0) return;

    const jobId = String(params.get("job_id") || "").trim();
    const status = String(params.get("status") || "").trim();
    const platform = String(params.get("platform") || "").trim();
    const from = String(params.get("from") || "").trim();
    const to = String(params.get("to") || "").trim();
    const limit = String(params.get("limit") || "").trim();

    if (jobId) refs.runsFilterForm.elements.job_id.value = jobId;
    if (status) refs.runsFilterForm.elements.status.value = status;
    if (platform) refs.runsFilterForm.elements.platform.value = platform;
    if (from) refs.runsFilterForm.elements.from.value = toLocalDateTimeInput(from);
    if (to) refs.runsFilterForm.elements.to.value = toLocalDateTimeInput(to);
    if (limit && Number(limit) > 0) refs.runsFilterForm.elements.limit.value = limit;
  }

  function renderRunsTable() {
    refs.runsBody.innerHTML = "";

    if (state.runs.length === 0) {
      const tr = createElement("tr");
      const td = createElement("td", "sr-table-empty", "暂无 runs 数据");
      td.colSpan = 10;
      tr.appendChild(td);
      refs.runsBody.appendChild(tr);
    } else {
      state.runs.forEach((run) => {
        const tr = createElement("tr", "sr-row sr-row--run");
        tr.classList.add(`sr-row--${statusTone(run.status)}`);
        if (String(run.run_id ?? "") === String(state.selectedRunId ?? "")) {
          tr.classList.add("is-selected");
        }

        tr.appendChild(createDataCell(String(run.run_id ?? "-"), "sr-cell-id"));
        tr.appendChild(createDataCell(String(run.job_id ?? "-"), "sr-cell-id"));

        const statusTd = createElement("td");
        statusTd.appendChild(createStatusBadge(run.status));
        tr.appendChild(statusTd);

        const platformTd = createElement("td");
        platformTd.appendChild(createPill(run.platform || "-", "neutral"));
        tr.appendChild(platformTd);

        tr.appendChild(createDataCell(String(run.task_id || "-"), "sr-cell-id"));
        tr.appendChild(createDataCell(safeFormatDateTime(ctx, run.triggered_at), "sr-cell-date"));
        tr.appendChild(createDataCell(safeFormatDateTime(ctx, run.started_at), "sr-cell-date"));
        tr.appendChild(createDataCell(safeFormatDateTime(ctx, run.finished_at), "sr-cell-date"));

        const messageTd = createElement("td", "sr-message-cell", stringifyMessage(run.message || "-"));
        tr.appendChild(messageTd);

        const opsTd = createElement("td");
        const detailBtn = createElement("button", "secondary sr-btn-sm", "详情");
        detailBtn.type = "button";
        detailBtn.dataset.action = "open-run-detail";
        detailBtn.dataset.runId = String(run.run_id || "");
        opsTd.appendChild(detailBtn);
        tr.appendChild(opsTd);

        refs.runsBody.appendChild(tr);
      });
    }

    refs.runsMeta.textContent = `共 ${state.runs.length} 条运行记录`;
  }

  function renderRunDetail(run) {
    state.selectedRun = run;
    refs.drawerSubtitle.textContent = `run_id=${run.run_id} · job_id=${run.job_id || "-"}`;

    const entries = [
      ["run_id", run.run_id],
      ["job_id", run.job_id],
      ["status", run.status],
      ["platform", run.platform || "-"],
      ["task_id", run.task_id || "-"],
      ["triggered_at", safeFormatDateTime(ctx, run.triggered_at)],
      ["started_at", safeFormatDateTime(ctx, run.started_at)],
      ["finished_at", safeFormatDateTime(ctx, run.finished_at)],
      ["message", run.message || "-"],
      ["updated_at", safeFormatDateTime(ctx, run.updated_at)],
    ];

    refs.runDetailGrid.innerHTML = "";
    entries.forEach(([key, value]) => {
      const dt = createElement("dt", "", key);
      const dd = createElement("dd", "", String(value ?? "-"));
      refs.runDetailGrid.append(dt, dd);
    });

    refs.runDetailsJson.textContent = formatDetails(run.details);
    renderRunTimeline(run);
    updateRetryRunButton();

    refs.logFilterForm.elements.task_id.value = run.task_id || "";
    refs.logFilterForm.elements.run_id.value = run.run_id ? String(run.run_id) : "";
  }

  function renderLogs() {
    refs.logList.innerHTML = "";
    if (state.loadingLogs) {
      refs.logList.innerHTML = '<li class="sr-log-empty">日志加载中...</li>';
      return;
    }

    if (!state.runLogs.length) {
      refs.logList.innerHTML = '<li class="sr-log-empty">暂无日志</li>';
      return;
    }

    state.runLogs.forEach((log) => {
      const li = createElement("li", "sr-log-item");
      const message = stringifyMessage(log.message || "");
      const time = safeFormatDateTime(ctx, log.timestamp || log.time || log.created_at);
      const level = String(log.level || "info").toLowerCase();
      const taskId = String(log.task_id || "-");
      const runId = log.run_id !== undefined && log.run_id !== null ? String(log.run_id) : "-";

      const meta = createElement("p", "sr-log-meta");
      meta.appendChild(createStatusBadge(level));
      meta.appendChild(createElement("span", "", time));
      meta.appendChild(createElement("span", "", `task=${taskId}`));
      meta.appendChild(createElement("span", "", `run=${runId}`));

      const messageNode = createElement("pre", "sr-log-message", message || "(empty)");
      li.append(meta, messageNode);
      refs.logList.appendChild(li);
    });
  }

  async function loadRuns() {
    setRunsLoading(true);
    try {
      const query = buildRunsQuery();
      const payload = await api.get("/api/scheduler/runs", { query });
      state.runs = normalizeRuns(payload);
      renderRunsTable();
    } catch (error) {
      toast(`加载 runs 失败：${error?.message || "unknown"}`, {
        tone: "error",
        title: "Run Center",
      });
    } finally {
      setRunsLoading(false);
    }
  }

  async function loadRunDetail(runId) {
    if (!runId) return;
    state.loadingDetail = true;
    try {
      const payload = await api.get(`/api/scheduler/runs/${encodeURIComponent(runId)}`);
      const run = normalizeRun(payload);
      if (!run) {
        throw new Error("run 详情为空");
      }
      state.selectedRunId = run.run_id;
      renderRunsTable();
      renderRunDetail(run);
      setDrawerOpen(true);
      await loadLogs({ silent: true });
      connectWebSocket();
    } catch (error) {
      toast(`加载 run 详情失败：${error?.message || "unknown"}`, {
        tone: "error",
        title: "Run 详情",
      });
    } finally {
      state.loadingDetail = false;
    }
  }

  async function loadLogs({ silent = false } = {}) {
    if (!state.selectedRunId) return;

    const formData = new FormData(refs.logFilterForm);
    const limit = parsePositiveInteger(formData.get("limit"), 120);
    const taskId = String(formData.get("task_id") || "").trim();
    const runIdRaw = String(formData.get("run_id") || "").trim();

    const query = {
      limit,
      task_id: taskId || undefined,
      run_id: runIdRaw ? parsePositiveInteger(runIdRaw, undefined) : undefined,
    };

    state.loadingLogs = true;
    renderLogs();

    try {
      const payload = await api.get("/api/crawler/logs", { query });
      state.runLogs = normalizeLogs(payload);
      renderLogs();
    } catch (error) {
      state.runLogs = [];
      renderLogs();
      if (!silent) {
        toast(`加载日志失败：${error?.message || "unknown"}`, {
          tone: "error",
          title: "Run 日志",
        });
      }
    } finally {
      state.loadingLogs = false;
      renderLogs();
    }
  }

  async function retrySelectedRunNow() {
    if (state.retryingRun) return;

    const selectedRun = state.selectedRun;
    const jobId = String(selectedRun?.job_id || "").trim();
    if (!jobId) {
      toast("当前 run 缺少 job_id，无法重试。", {
        tone: "warning",
        title: "Run 详情",
      });
      updateRetryRunButton();
      return;
    }

    const currentRunId = selectedRun?.run_id || state.selectedRunId;
    state.retryingRun = true;
    updateRetryRunButton();

    try {
      await api.post(`/api/scheduler/jobs/${encodeURIComponent(jobId)}/run-now`, {});
      toast(`已触发重试：${jobId}`, {
        tone: "success",
        title: "Run 详情",
      });
      await loadRuns();
      if (currentRunId) {
        await loadRunDetail(currentRunId);
      }
    } catch (error) {
      toast(`重试失败：${error?.message || "unknown"}`, {
        tone: "error",
        title: "Run 详情",
      });
    } finally {
      state.retryingRun = false;
      updateRetryRunButton();
    }
  }

  const onRunsFilterSubmit = async (event) => {
    event.preventDefault();
    await loadRuns();
  };
  refs.runsFilterForm.addEventListener("submit", onRunsFilterSubmit);
  cleanups.push(() => refs.runsFilterForm.removeEventListener("submit", onRunsFilterSubmit));

  const onLogFilterSubmit = async (event) => {
    event.preventDefault();
    await loadLogs();
  };
  refs.logFilterForm.addEventListener("submit", onLogFilterSubmit);
  cleanups.push(() => refs.logFilterForm.removeEventListener("submit", onLogFilterSubmit));

  const onClick = async (event) => {
    const trigger = event.target.closest("button[data-action]");
    if (!trigger) return;

    const action = trigger.dataset.action;

    if (action === "refresh-runs") {
      await loadRuns();
      return;
    }

    if (action === "clear-runs-filters") {
      refs.runsFilterForm.reset();
      refs.runsFilterForm.elements.limit.value = "100";
      await loadRuns();
      return;
    }

    if (action === "open-run-detail") {
      await loadRunDetail(trigger.dataset.runId || "");
      return;
    }

    if (action === "close-drawer") {
      setDrawerOpen(false);
      return;
    }

    if (action === "refresh-logs") {
      await loadLogs();
      return;
    }

    if (action === "retry-run-now") {
      await retrySelectedRunNow();
    }
  };
  mountEl.addEventListener("click", onClick);
  cleanups.push(() => mountEl.removeEventListener("click", onClick));

  const onDrawerBackdropClick = () => {
    setDrawerOpen(false);
  };
  refs.drawerBackdrop.addEventListener("click", onDrawerBackdropClick);
  cleanups.push(() => refs.drawerBackdrop.removeEventListener("click", onDrawerBackdropClick));

  applyFiltersFromHash();
  await loadRuns();

  return {
    id: "runs",
    destroy() {
      state.destroyed = true;
      stopLiveLogs();
      cleanups.forEach((cleanup) => cleanup());
      cleanups.length = 0;
    },
  };
}

export const render = renderRunsPage;
