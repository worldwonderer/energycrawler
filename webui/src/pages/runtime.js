const SETTINGS_STORAGE_KEYS = {
  apiBase: "energycrawler_api_base",
  autoRefreshEnabled: "energycrawler_ui_auto_refresh_enabled",
  autoRefreshIntervalSec: "energycrawler_ui_auto_refresh_interval_sec",
};

const STYLE_LINK_ID = "energycrawler-ui2-runtime-settings-style";
const SETTINGS_UPDATED_EVENT = "energycrawler:settings-updated";
const DEFAULT_AUTO_REFRESH_INTERVAL_SEC = 15;
const MIN_AUTO_REFRESH_INTERVAL_SEC = 5;
const MAX_AUTO_REFRESH_INTERVAL_SEC = 300;

function ensurePageStyle() {
  if (typeof document === "undefined") return;
  if (document.getElementById(STYLE_LINK_ID)) return;

  const link = document.createElement("link");
  link.id = STYLE_LINK_ID;
  link.rel = "stylesheet";
  link.href = new URL("../styles/runtime-settings.css", import.meta.url).href;
  document.head.appendChild(link);
}

function safeReadStorage(storage, key, fallback = "") {
  try {
    if (!storage || typeof storage.getItem !== "function") return fallback;
    const value = storage.getItem(key);
    return value === null ? fallback : value;
  } catch {
    return fallback;
  }
}

function safeWriteStorage(storage, key, value) {
  try {
    if (!storage || typeof storage.setItem !== "function") return;
    storage.setItem(key, value);
  } catch {
    // ignore storage write failure (private mode / quota)
  }
}

function normalizeApiBase(value) {
  const raw = String(value || "").trim();
  if (!raw) return "";
  return raw.replace(/\/+$/, "");
}

function normalizeIntervalSec(value) {
  const parsed = Number(value);
  if (!Number.isFinite(parsed)) return DEFAULT_AUTO_REFRESH_INTERVAL_SEC;
  return Math.min(MAX_AUTO_REFRESH_INTERVAL_SEC, Math.max(MIN_AUTO_REFRESH_INTERVAL_SEC, Math.round(parsed)));
}

function normalizeBoolean(value, fallback = true) {
  if (typeof value === "boolean") return value;
  if (typeof value === "string") {
    if (value === "true") return true;
    if (value === "false") return false;
  }
  return fallback;
}

function formatTime(value) {
  if (!value) return "-";
  try {
    const date = value instanceof Date ? value : new Date(value);
    if (Number.isNaN(date.getTime())) return String(value);
    return date.toLocaleString();
  } catch {
    return String(value);
  }
}

function maskValue(value) {
  const raw = String(value || "").trim();
  if (!raw) return "未配置";
  if (raw.length <= 6) return `${raw.slice(0, 1)}***`;
  return `${raw.slice(0, 3)}***${raw.slice(-2)}`;
}

function toTone(okValue) {
  if (okValue === true) return "success";
  if (okValue === false) return "danger";
  return "neutral";
}

function asArray(value) {
  return Array.isArray(value) ? value : [];
}

export function readUiPreferences(storage = globalThis?.localStorage) {
  return {
    apiBase: normalizeApiBase(safeReadStorage(storage, SETTINGS_STORAGE_KEYS.apiBase, "")),
    autoRefreshEnabled: normalizeBoolean(
      safeReadStorage(storage, SETTINGS_STORAGE_KEYS.autoRefreshEnabled, "true"),
      true
    ),
    autoRefreshIntervalSec: normalizeIntervalSec(
      safeReadStorage(storage, SETTINGS_STORAGE_KEYS.autoRefreshIntervalSec, String(DEFAULT_AUTO_REFRESH_INTERVAL_SEC))
    ),
  };
}

export function persistUiPreferences(nextPreferences, storage = globalThis?.localStorage) {
  const current = readUiPreferences(storage);
  const merged = {
    ...current,
    ...(nextPreferences || {}),
  };
  const normalized = {
    apiBase: normalizeApiBase(merged.apiBase),
    autoRefreshEnabled: normalizeBoolean(merged.autoRefreshEnabled, true),
    autoRefreshIntervalSec: normalizeIntervalSec(merged.autoRefreshIntervalSec),
  };

  safeWriteStorage(storage, SETTINGS_STORAGE_KEYS.apiBase, normalized.apiBase);
  safeWriteStorage(storage, SETTINGS_STORAGE_KEYS.autoRefreshEnabled, String(normalized.autoRefreshEnabled));
  safeWriteStorage(
    storage,
    SETTINGS_STORAGE_KEYS.autoRefreshIntervalSec,
    String(normalized.autoRefreshIntervalSec)
  );

  return normalized;
}

function buildUrl(path, apiBase) {
  const finalPath = path.startsWith("/") ? path : `/${path}`;
  const normalizedBase = normalizeApiBase(apiBase);
  const base = normalizedBase ? `${normalizedBase}${finalPath}` : finalPath;
  return new URL(base, globalThis?.window?.location?.origin || "http://127.0.0.1").toString();
}

async function requestJson(path, { apiBase = "", signal, method = "GET", body } = {}) {
  const options = {
    method,
    headers: {
      Accept: "application/json",
    },
    signal,
  };

  if (body !== undefined) {
    options.headers["Content-Type"] = "application/json";
    options.body = JSON.stringify(body);
  }

  const response = await fetch(buildUrl(path, apiBase), options);

  const payload = await response.json().catch(() => null);
  if (!response.ok || !payload || payload.success === false) {
    const message =
      payload?.error?.message ||
      payload?.message ||
      `${response.status || "NETWORK"} ${response.statusText || "Request failed"}`;
    throw new Error(message);
  }

  return payload.data ?? payload;
}

function normalizeSmokeSnapshot(payload) {
  const currentRun = payload?.current_run;
  const latest = payload?.latest;
  return {
    running: Boolean(payload?.running),
    currentRun: currentRun && typeof currentRun === "object" ? currentRun : null,
    latest: latest && typeof latest === "object" ? latest : null,
  };
}

function formatSmokeMetric(value) {
  if (value === null || value === undefined || value === "") return "-";
  if (typeof value === "boolean") return value ? "true" : "false";
  if (typeof value === "number") return String(value);
  if (typeof value === "string") return value;
  try {
    return JSON.stringify(value);
  } catch {
    return String(value);
  }
}

function escapeHtml(value) {
  return String(value)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/\"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

function createSmokeSummary(snapshot) {
  const rows = [];
  const latest = snapshot?.latest;
  const payload = latest?.payload;
  const runs = asArray(payload?.runs);
  const changedFiles = asArray(payload?.data_changes?.new_or_updated_files);

  rows.push(["running", snapshot?.running ? "true" : "false"]);
  rows.push(["current_run_id", snapshot?.currentRun?.run_id ?? "-"]);

  if (!latest) {
    rows.push(["latest", "未执行"]);
    return rows;
  }

  rows.push(["latest_run_id", latest?.run_id ?? "-"]);
  rows.push(["ok", latest?.ok ?? "-"]);
  rows.push(["exit_code", latest?.exit_code ?? "-"]);
  rows.push(["started_at", formatTime(latest?.started_at)]);
  rows.push(["finished_at", formatTime(latest?.finished_at)]);
  rows.push(["runs", runs.length]);
  rows.push(["data_changes", changedFiles.length]);

  const previewFile = payload?.latest_preview?.file;
  if (previewFile && typeof previewFile === "object") {
    rows.push(["latest_file", previewFile.path || previewFile.name || "-"]);
  }

  if (latest?.error) {
    rows.push(["error", latest.error]);
  }

  return rows;
}

function createRuntimeCards(runtime) {
  const queue = runtime?.crawler_queue || {};
  const login = runtime?.login || {};

  return [
    {
      title: "Overall",
      value: runtime?.overall_status || "unknown",
      tone: toTone(runtime?.overall_healthy),
      meta: [`checked_at: ${formatTime(runtime?.checked_at)}`],
    },
    {
      title: "Energy Service",
      value: runtime?.energy?.ok ? "reachable" : "unreachable",
      tone: toTone(runtime?.energy?.ok),
      meta: [runtime?.energy?.message || "-"],
    },
    {
      title: "Login (xhs)",
      value: login?.xhs?.ok ? "ready" : "missing",
      tone: toTone(login?.xhs?.ok),
      meta: [login?.xhs?.message || "-"],
    },
    {
      title: "Login (x)",
      value: login?.x?.ok ? "ready" : "missing",
      tone: toTone(login?.x?.ok),
      meta: [login?.x?.message || "-"],
    },
    {
      title: "Crawler Queue",
      value: queue?.status || "unknown",
      tone: toTone(queue?.healthy),
      meta: [
        `workers ${queue?.running_workers ?? 0}/${queue?.total_workers ?? 0}`,
        `queued ${queue?.queued_tasks ?? 0}/${queue?.max_queue_size ?? 0}`,
      ],
    },
    {
      title: "Active Task IDs",
      value: String(asArray(queue?.active_task_ids).length),
      tone: "neutral",
      meta: [asArray(queue?.active_task_ids).join(", ") || "(none)"],
    },
  ];
}

function createConfigSummary(config) {
  const runtime = config?.runtime || {};
  const energy = config?.energy || {};
  const auth = config?.auth || {};
  const cookiecloud = auth?.cookiecloud || {};
  const storage = config?.storage || {};

  return [
    ["platform", runtime.platform || "-"],
    ["crawler_type", runtime.crawler_type || "-"],
    ["login_type", runtime.login_type || "-"],
    ["headless", String(runtime.headless)],
    ["energy_enabled", String(energy.enabled)],
    ["energy_service", energy.service_address || "-"],
    ["cookiecloud_enabled", String(cookiecloud.enabled)],
    ["cookiecloud_server", cookiecloud.server || "-"],
    ["cookiecloud_uuid", cookiecloud?.uuid?.masked || "-"],
    ["save_data_option", storage.save_data_option || "-"],
    ["save_data_path", storage.save_data_path || "-"],
  ];
}

function createDiagnostics(runtime, config) {
  const diagnostics = [];
  const cookiecloud = config?.auth?.cookiecloud || {};
  const login = runtime?.login || {};
  const queue = runtime?.crawler_queue || {};

  if (!runtime?.energy?.ok) {
    diagnostics.push({
      tone: "danger",
      title: "Energy 服务不可达",
      detail: runtime?.energy?.message || "无法连接 energy service",
      action: "检查 ENERGY_SERVICE_ADDRESS / energy-service 进程后重试。",
    });
  }

  if (cookiecloud.enabled) {
    if (!cookiecloud.server) {
      diagnostics.push({
        tone: "danger",
        title: "CookieCloud Server 未配置",
        detail: "COOKIECLOUD_ENABLED=true 但缺少 COOKIECLOUD_SERVER。",
        action: "补全 CookieCloud 地址，例如 http://127.0.0.1:8088。",
      });
    }

    if (!cookiecloud?.uuid?.configured) {
      diagnostics.push({
        tone: "danger",
        title: "CookieCloud UUID 未配置",
        detail: "常见导致 CookieCloud 404 或同步不到数据。",
        action: "检查 COOKIECLOUD_UUID 是否和插件配置一致。",
      });
    }

    if (!cookiecloud?.password?.configured) {
      diagnostics.push({
        tone: "warning",
        title: "CookieCloud Password 未配置",
        detail: "可能导致同步鉴权失败。",
        action: "补全 COOKIECLOUD_PASSWORD 后重新同步并重试 run-now。",
      });
    }

    if (cookiecloud.server && cookiecloud?.uuid?.configured && cookiecloud?.password?.configured) {
      diagnostics.push({
        tone: "info",
        title: "CookieCloud 基础配置完整",
        detail: `server=${cookiecloud.server}, uuid=${maskValue(cookiecloud?.uuid?.masked)}`,
        action: "若仍报错，请核对 CookieCloud 服务可达性与最近同步日志。",
      });
    }
  } else {
    diagnostics.push({
      tone: "info",
      title: "CookieCloud 未启用",
      detail: "当前系统不会自动同步浏览器登录态。",
      action: "需要自动恢复登录态时可启用 COOKIECLOUD_ENABLED。",
    });
  }

  if (!login?.xhs?.ok) {
    diagnostics.push({
      tone: "warning",
      title: "xhs 登录态无效",
      detail: login?.xhs?.message || "env COOKIES 缺少 a1。",
      action: "执行登录同步后，再次触发 run-now 验证。",
    });
  }

  if (!login?.x?.ok) {
    diagnostics.push({
      tone: "warning",
      title: "x 登录态无效",
      detail: login?.x?.message || "缺少 auth_token 或 ct0。",
      action: "更新 TWITTER_AUTH_TOKEN / TWITTER_CT0，或同步 twitter cookie。",
    });
  }

  if (Number(queue?.max_queue_size) > 0 && Number(queue?.queued_tasks) >= Number(queue?.max_queue_size)) {
    diagnostics.push({
      tone: "warning",
      title: "队列已接近/达到上限",
      detail: `queued=${queue?.queued_tasks}, max=${queue?.max_queue_size}`,
      action: "降低触发频率或扩容 worker 数量，避免 run 被拒绝。",
    });
  }

  if (diagnostics.length === 0) {
    diagnostics.push({
      tone: "success",
      title: "未发现高优先级问题",
      detail: "Runtime/Auth 关键项状态良好。",
      action: "保持当前配置，按需观察运行中心日志。",
    });
  }

  return diagnostics;
}

function resolveContainer(target) {
  if (target && typeof target === "object" && "nodeType" in target) return target;
  if (typeof target === "string") return document.querySelector(target);
  return null;
}

function renderEmptyState(message) {
  return `<div class="rs-inline-note rs-empty-state" data-tone="warning">${escapeHtml(
    formatSmokeMetric(message)
  )}</div>`;
}

export function mountRuntimePage(target, options = {}) {
  const container = resolveContainer(target);
  if (!container) {
    throw new Error("Runtime page mount target not found");
  }
  ensurePageStyle();

  const storage = options.storage || globalThis?.localStorage;
  const initialPreferences = {
    ...readUiPreferences(storage),
    ...(options.preferences || {}),
  };

  const state = {
    apiBase: normalizeApiBase(initialPreferences.apiBase),
    autoRefreshEnabled: normalizeBoolean(initialPreferences.autoRefreshEnabled, true),
    autoRefreshIntervalSec: normalizeIntervalSec(initialPreferences.autoRefreshIntervalSec),
    loading: false,
    smokeStarting: false,
    lastUpdatedAt: null,
    runtime: null,
    config: null,
    smoke: normalizeSmokeSnapshot({}),
    timerId: null,
    inflightController: null,
  };

  container.innerHTML = `
    <section class="runtime-settings-page runtime-page">
      <header class="rs-header">
        <div class="rs-header-copy">
          <h2>Runtime & Auth</h2>
          <p>查看运行时健康状态、登录态和 CookieCloud 诊断建议。</p>
        </div>
        <div class="rs-header-actions">
          <label class="rs-toggle">
            <input type="checkbox" data-role="auto-refresh-toggle" />
            <span>自动刷新</span>
          </label>
          <span class="rs-inline-note" data-role="refresh-hint"></span>
          <button type="button" class="secondary" data-role="refresh-btn">立即刷新</button>
        </div>
      </header>

      <section class="rs-inline-note" data-tone="info">
        新部署实例可先完成 <a href="#/welcome">Welcome 引导</a>，按步骤检查环境 / 鉴权 / Demo / 数据视图。
      </section>

      <section class="rs-inline-note rs-status-banner" data-role="status-banner" data-tone="info" aria-live="polite">
        等待加载运行时快照...
      </section>

      <section class="rs-grid rs-grid-cards rs-runtime-cards" data-role="runtime-cards">
        ${renderEmptyState("尚未获取到运行时数据")}
      </section>

      <section class="rs-panel rs-panel--diagnostics">
        <h3>CookieCloud 诊断提示</h3>
        <ul class="rs-diagnostics" data-role="diagnostics-list">
          <li class="rs-diagnostic-item" data-tone="neutral">等待数据...</li>
        </ul>
      </section>

      <section class="rs-panel rs-panel--summary">
        <h3>/api/config 摘要</h3>
        <div class="rs-summary-grid" data-role="config-summary">
          ${renderEmptyState("尚未加载配置摘要")}
        </div>
      </section>

      <section class="rs-panel rs-smoke-panel">
        <div class="rs-panel-headline">
          <div>
            <h3>一键自检（Smoke E2E）</h3>
            <p class="rs-panel-subtitle">后台执行 \`energycrawler scheduler smoke-e2e --json\` 并缓存最近结果。</p>
          </div>
          <div class="rs-actions">
            <button type="button" class="secondary" data-role="smoke-refresh-btn">刷新报告</button>
            <button type="button" data-role="smoke-start-btn">运行自检</button>
          </div>
        </div>
        <div class="rs-inline-note" data-role="smoke-status" data-tone="warning">尚未获取自检状态</div>
        <div class="rs-summary-grid rs-smoke-summary" data-role="smoke-summary">
          ${renderEmptyState("尚未生成自检报告")}
        </div>
        <details class="rs-json-panel">
          <summary>最新自检报告（JSON）</summary>
          <pre data-role="smoke-raw">{}</pre>
        </details>
      </section>

      <details class="rs-panel rs-json-panel rs-panel--debug">
        <summary>原始快照（调试）</summary>
        <div class="rs-json-grid">
          <div>
            <h4>/api/health/runtime</h4>
            <pre data-role="runtime-raw"></pre>
          </div>
          <div>
            <h4>/api/config</h4>
            <pre data-role="config-raw"></pre>
          </div>
        </div>
      </details>
    </section>
  `;

  const refs = {
    statusBanner: container.querySelector('[data-role="status-banner"]'),
    autoRefreshToggle: container.querySelector('[data-role="auto-refresh-toggle"]'),
    refreshHint: container.querySelector('[data-role="refresh-hint"]'),
    refreshBtn: container.querySelector('[data-role="refresh-btn"]'),
    runtimeCards: container.querySelector('[data-role="runtime-cards"]'),
    diagnosticsList: container.querySelector('[data-role="diagnostics-list"]'),
    configSummary: container.querySelector('[data-role="config-summary"]'),
    smokeStartBtn: container.querySelector('[data-role="smoke-start-btn"]'),
    smokeRefreshBtn: container.querySelector('[data-role="smoke-refresh-btn"]'),
    smokeStatus: container.querySelector('[data-role="smoke-status"]'),
    smokeSummary: container.querySelector('[data-role="smoke-summary"]'),
    smokeRaw: container.querySelector('[data-role="smoke-raw"]'),
    runtimeRaw: container.querySelector('[data-role="runtime-raw"]'),
    configRaw: container.querySelector('[data-role="config-raw"]'),
  };

  function setBanner(tone, text) {
    refs.statusBanner.dataset.tone = tone;
    refs.statusBanner.textContent = text;
  }

  function renderAutoRefreshHint() {
    const enabled = state.autoRefreshEnabled;
    refs.autoRefreshToggle.checked = enabled;
    refs.refreshHint.textContent = enabled
      ? `${state.autoRefreshIntervalSec}s 自动刷新`
      : "自动刷新已关闭";
  }

  function renderRuntimeCards() {
    if (!state.runtime) {
      refs.runtimeCards.innerHTML = renderEmptyState("暂无运行时数据");
      return;
    }

    const cards = createRuntimeCards(state.runtime);
    refs.runtimeCards.innerHTML = cards
      .map((card) => {
        const meta = asArray(card.meta)
          .map((line) => `<li>${escapeHtml(formatSmokeMetric(line))}</li>`)
          .join("");
        return `
          <article class="rs-card" data-tone="${card.tone}">
            <p class="rs-card-title">${escapeHtml(formatSmokeMetric(card.title))}</p>
            <p class="rs-card-value">${escapeHtml(formatSmokeMetric(card.value))}</p>
            <ul class="rs-card-meta">${meta}</ul>
          </article>
        `;
      })
      .join("");
  }

  function renderDiagnostics() {
    const diagnostics = createDiagnostics(state.runtime || {}, state.config || {});
    refs.diagnosticsList.innerHTML = diagnostics
      .map(
        (item) => `
          <li class="rs-diagnostic-item" data-tone="${item.tone}">
            <p class="rs-diagnostic-title">${escapeHtml(formatSmokeMetric(item.title))}</p>
            <p class="rs-diagnostic-detail">${escapeHtml(formatSmokeMetric(item.detail))}</p>
            <p class="rs-diagnostic-action">建议：${escapeHtml(formatSmokeMetric(item.action))}</p>
          </li>
        `
      )
      .join("");
  }

  function renderConfigSummary() {
    if (!state.config) {
      refs.configSummary.innerHTML = renderEmptyState("暂无配置摘要");
      return;
    }

    const rows = createConfigSummary(state.config)
      .map(
        ([key, value]) => `
          <article class="rs-summary-item">
            <p class="rs-summary-key">${escapeHtml(formatSmokeMetric(key))}</p>
            <p class="rs-summary-value">${escapeHtml(formatSmokeMetric(value))}</p>
          </article>
        `
      )
      .join("");

    refs.configSummary.innerHTML = rows;
  }

  function renderSmokeSection() {
    const smoke = state.smoke || normalizeSmokeSnapshot({});
    const latest = smoke.latest;
    const running = smoke.running;

    let tone = "warning";
    let statusText = "尚未执行自检，点击“运行自检”触发。";

    if (running) {
      tone = "info";
      statusText = `自检执行中（run #${smoke.currentRun?.run_id ?? "-"}, started ${formatTime(smoke.currentRun?.started_at)}）`;
    } else if (latest) {
      tone = latest.ok ? "success" : "danger";
      statusText = latest.ok
        ? `最近一次自检成功（${formatTime(latest.finished_at)}）`
        : `最近一次自检失败（${formatTime(latest.finished_at)}）：${latest.error || "未知错误"}`;
    }

    refs.smokeStatus.dataset.tone = tone;
    refs.smokeStatus.textContent = statusText;

    const summaryRows = createSmokeSummary(smoke);
    refs.smokeSummary.innerHTML = summaryRows
      .map(
        ([key, value]) => `
          <article class="rs-summary-item">
            <p class="rs-summary-key">${escapeHtml(key)}</p>
            <p class="rs-summary-value">${escapeHtml(formatSmokeMetric(value))}</p>
          </article>
        `
      )
      .join("");

    const rawReport = latest?.payload ?? latest ?? {};
    refs.smokeRaw.textContent = JSON.stringify(rawReport, null, 2);

    refs.smokeStartBtn.disabled = state.smokeStarting || running;
    refs.smokeRefreshBtn.disabled = state.loading;
  }

  function renderRawPayloads() {
    refs.runtimeRaw.textContent = state.runtime ? JSON.stringify(state.runtime, null, 2) : "{}";
    refs.configRaw.textContent = state.config ? JSON.stringify(state.config, null, 2) : "{}";
  }

  function renderAll() {
    renderAutoRefreshHint();
    renderRuntimeCards();
    renderDiagnostics();
    renderConfigSummary();
    renderSmokeSection();
    renderRawPayloads();
  }

  function clearInflightRequest() {
    if (state.inflightController) {
      state.inflightController.abort();
      state.inflightController = null;
    }
  }

  function stopAutoRefreshTimer() {
    if (state.timerId) {
      globalThis.clearInterval(state.timerId);
      state.timerId = null;
    }
  }

  function startAutoRefreshTimer() {
    stopAutoRefreshTimer();
    if (!state.autoRefreshEnabled) return;
    state.timerId = globalThis.setInterval(() => {
      refreshSnapshot();
    }, state.autoRefreshIntervalSec * 1000);
  }

  function persistPreferences(nextPartial) {
    const next = persistUiPreferences(
      {
        apiBase: state.apiBase,
        autoRefreshEnabled: state.autoRefreshEnabled,
        autoRefreshIntervalSec: state.autoRefreshIntervalSec,
        ...(nextPartial || {}),
      },
      storage
    );

    state.apiBase = next.apiBase;
    state.autoRefreshEnabled = next.autoRefreshEnabled;
    state.autoRefreshIntervalSec = next.autoRefreshIntervalSec;

    globalThis.dispatchEvent(
      new CustomEvent(SETTINGS_UPDATED_EVENT, {
        detail: next,
      })
    );
  }

  async function refreshSnapshot() {
    if (state.loading) return;
    state.loading = true;
    refs.refreshBtn.disabled = true;

    clearInflightRequest();
    state.inflightController = new AbortController();

    setBanner("info", "正在加载 /api/health/runtime、/api/config 与自检状态...");

    try {
      const [runtimeData, configData, smokeData] = await Promise.all([
        requestJson("/api/health/runtime", {
          apiBase: state.apiBase,
          signal: state.inflightController.signal,
        }),
        requestJson("/api/config", {
          apiBase: state.apiBase,
          signal: state.inflightController.signal,
        }),
        requestJson("/api/diagnostics/smoke-e2e/latest", {
          apiBase: state.apiBase,
          signal: state.inflightController.signal,
        }),
      ]);

      state.runtime = runtimeData || {};
      state.config = configData || {};
      state.smoke = normalizeSmokeSnapshot(smokeData || {});
      state.lastUpdatedAt = new Date();
      setBanner("success", `快照已更新：${formatTime(state.lastUpdatedAt)}`);
    } catch (error) {
      if (error?.name === "AbortError") return;
      setBanner("danger", `加载失败：${error?.message || "未知错误"}`);
    } finally {
      state.loading = false;
      refs.refreshBtn.disabled = false;
      renderAll();
    }
  }

  async function refreshSmokeStatus() {
    if (state.loading) return;

    refs.smokeRefreshBtn.disabled = true;
    try {
      const smokeData = await requestJson("/api/diagnostics/smoke-e2e/latest", {
        apiBase: state.apiBase,
      });
      state.smoke = normalizeSmokeSnapshot(smokeData || {});
      renderSmokeSection();
    } catch (error) {
      refs.smokeStatus.dataset.tone = "danger";
      refs.smokeStatus.textContent = `自检状态刷新失败：${error?.message || "未知错误"}`;
    } finally {
      refs.smokeRefreshBtn.disabled = state.loading;
    }
  }

  async function startSmokeCheck() {
    if (state.smokeStarting || state.smoke?.running) return;

    state.smokeStarting = true;
    renderSmokeSection();

    try {
      const payload = await requestJson("/api/diagnostics/smoke-e2e/start", {
        apiBase: state.apiBase,
        method: "POST",
        body: {},
      });
      state.smoke = normalizeSmokeSnapshot(payload || {});

      if (payload?.accepted) {
        setBanner("info", "已触发一键自检，后台执行中。");
      } else {
        setBanner("warning", "自检任务已在执行，稍后查看最新结果。");
      }
    } catch (error) {
      refs.smokeStatus.dataset.tone = "danger";
      refs.smokeStatus.textContent = `启动自检失败：${error?.message || "未知错误"}`;
    } finally {
      state.smokeStarting = false;
      renderSmokeSection();
    }
  }

  function onAutoRefreshChange(event) {
    state.autoRefreshEnabled = event?.target?.checked ?? false;
    persistPreferences({ autoRefreshEnabled: state.autoRefreshEnabled });
    renderAutoRefreshHint();
    startAutoRefreshTimer();
  }

  function onSettingsUpdated(event) {
    const detail = event?.detail || {};
    const nextApiBase = normalizeApiBase(detail.apiBase);
    const nextAutoRefresh = normalizeBoolean(detail.autoRefreshEnabled, state.autoRefreshEnabled);
    const nextInterval = normalizeIntervalSec(detail.autoRefreshIntervalSec ?? state.autoRefreshIntervalSec);

    const changed =
      state.apiBase !== nextApiBase ||
      state.autoRefreshEnabled !== nextAutoRefresh ||
      state.autoRefreshIntervalSec !== nextInterval;

    state.apiBase = nextApiBase;
    state.autoRefreshEnabled = nextAutoRefresh;
    state.autoRefreshIntervalSec = nextInterval;
    renderAutoRefreshHint();
    startAutoRefreshTimer();

    if (changed) {
      refreshSnapshot();
    }
  }

  refs.autoRefreshToggle.addEventListener("change", onAutoRefreshChange);
  refs.refreshBtn.addEventListener("click", refreshSnapshot);
  refs.smokeStartBtn.addEventListener("click", startSmokeCheck);
  refs.smokeRefreshBtn.addEventListener("click", refreshSmokeStatus);
  globalThis.addEventListener(SETTINGS_UPDATED_EVENT, onSettingsUpdated);

  renderAll();
  startAutoRefreshTimer();
  refreshSnapshot();

  return {
    id: "runtime-auth",
    refresh: refreshSnapshot,
    destroy() {
      stopAutoRefreshTimer();
      clearInflightRequest();
      refs.autoRefreshToggle.removeEventListener("change", onAutoRefreshChange);
      refs.refreshBtn.removeEventListener("click", refreshSnapshot);
      refs.smokeStartBtn.removeEventListener("click", startSmokeCheck);
      refs.smokeRefreshBtn.removeEventListener("click", refreshSmokeStatus);
      globalThis.removeEventListener(SETTINGS_UPDATED_EVENT, onSettingsUpdated);
    },
  };
}

const runtimePage = {
  id: "runtime-auth",
  title: "Runtime & Auth",
  mount: mountRuntimePage,
};

export default runtimePage;
