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
    // ignore storage write failures
  }
}

function safeRemoveStorage(storage, key) {
  try {
    if (!storage || typeof storage.removeItem !== "function") return;
    storage.removeItem(key);
  } catch {
    // ignore storage remove failures
  }
}

function buildUrl(path, apiBase) {
  const finalPath = path.startsWith("/") ? path : `/${path}`;
  const normalizedBase = normalizeApiBase(apiBase);
  const base = normalizedBase ? `${normalizedBase}${finalPath}` : finalPath;
  return new URL(base, globalThis?.window?.location?.origin || "http://127.0.0.1").toString();
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

function formatSummaryValue(value) {
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

function readPreferences(storage = globalThis?.localStorage) {
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

function persistPreferences(preferences, storage = globalThis?.localStorage) {
  const normalized = {
    apiBase: normalizeApiBase(preferences?.apiBase),
    autoRefreshEnabled: normalizeBoolean(preferences?.autoRefreshEnabled, true),
    autoRefreshIntervalSec: normalizeIntervalSec(preferences?.autoRefreshIntervalSec),
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

async function requestJson(path, { apiBase = "", signal } = {}) {
  const response = await fetch(buildUrl(path, apiBase), {
    method: "GET",
    headers: {
      Accept: "application/json",
    },
    signal,
  });

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

function resolveContainer(target) {
  if (target && typeof target === "object" && "nodeType" in target) return target;
  if (typeof target === "string") return document.querySelector(target);
  return null;
}

function createConfigSummaryRows(config) {
  const runtime = config?.runtime || {};
  const crawler = config?.crawler || {};
  const energy = config?.energy || {};
  const auth = config?.auth || {};
  const cookiecloud = auth?.cookiecloud || {};
  const watchdog = auth?.auth_watchdog || {};

  return [
    ["platform", runtime.platform || "-"],
    ["crawler_type", runtime.crawler_type || "-"],
    ["login_type", runtime.login_type || "-"],
    ["headless", String(runtime.headless)],
    ["crawler.start_page", String(crawler.start_page ?? "-")],
    ["crawler.max_notes_count", String(crawler.max_notes_count ?? "-")],
    ["energy.enabled", String(energy.enabled)],
    ["energy.service_address", energy.service_address || "-"],
    ["cookiecloud.enabled", String(cookiecloud.enabled)],
    ["cookiecloud.server", cookiecloud.server || "-"],
    ["cookiecloud.uuid", cookiecloud?.uuid?.masked || "-"],
    ["cookiecloud.force_sync", String(cookiecloud.force_sync)],
    ["auth_watchdog.enabled", String(watchdog.enabled)],
    ["auth_watchdog.max_retries", String(watchdog.max_retries ?? "-")],
  ];
}

function normalizeLayerEntries(entries, fallbackLayer = "minimal") {
  if (!Array.isArray(entries)) return [];
  return entries
    .filter((entry) => entry && typeof entry === "object")
    .map((entry) => {
      const key = String(entry.key || entry.label || "").trim();
      return {
        key: key || "-",
        label: String(entry.label || key || "-"),
        description: String(entry.description || ""),
        value: entry.value,
        layer: String(entry.layer || fallbackLayer),
        configured: typeof entry.configured === "boolean" ? entry.configured : true,
        sensitive: typeof entry.sensitive === "boolean" ? entry.sensitive : false,
      };
    });
}

function renderLayerItems(entries, emptyText) {
  if (!entries.length) {
    return `<div class="rs-inline-note rs-empty-state" data-tone="neutral">${escapeHtml(emptyText)}</div>`;
  }

  return `
    <div class="rs-summary-grid">
      ${entries
        .map((entry) => {
          const metaParts = [];
          if (!entry.configured) metaParts.push("未配置");
          if (entry.sensitive) metaParts.push("敏感项（已脱敏）");
          if (entry.description) metaParts.push(entry.description);
          const metaMarkup = metaParts.length
            ? `<p class="rs-summary-meta">${escapeHtml(metaParts.join(" · "))}</p>`
            : "";
          return `
            <article class="rs-summary-item">
              <p class="rs-summary-key">${escapeHtml(formatSummaryValue(entry.label))}</p>
              <p class="rs-summary-value">${escapeHtml(formatSummaryValue(entry.value))}</p>
              ${metaMarkup}
            </article>
          `;
        })
        .join("")}
    </div>
  `;
}

function createGroupedSummaryMarkup(config) {
  const grouped = config?.grouped;
  const layers = grouped?.layers;
  if (!layers || typeof layers !== "object") return "";

  const minimalEntries = normalizeLayerEntries(layers.minimal, "minimal");
  const coreEntries = normalizeLayerEntries(layers.core, "core");
  const advancedEntries = normalizeLayerEntries(layers.advanced, "advanced");
  if (!minimalEntries.length && !coreEntries.length && !advancedEntries.length) return "";

  const defaultLayer = String(grouped?.default_layer || "minimal");
  const defaultLayerLabel = defaultLayer === "minimal" ? "minimal（默认）" : defaultLayer;

  return `
    <section class="rs-layer-block">
      <div class="rs-panel-headline">
        <div>
          <h4>新手配置（${escapeHtml(defaultLayerLabel)}）</h4>
          <p class="rs-panel-subtitle">默认只展示 minimal，先跑通后再调优。</p>
        </div>
      </div>
      ${renderLayerItems(minimalEntries, "暂无 minimal 配置项")}
    </section>

    <details class="rs-layer-details">
      <summary>高级配置（core + advanced）</summary>
      <div class="rs-layer-sections">
        <section class="rs-layer-section">
          <h4>Core（常用运行控制）</h4>
          ${renderLayerItems(coreEntries, "暂无 core 配置项")}
        </section>
        <section class="rs-layer-section">
          <h4>Advanced（诊断/性能）</h4>
          ${renderLayerItems(advancedEntries, "暂无 advanced 配置项")}
        </section>
      </div>
    </details>
  `;
}

function summarizeCookieCloud(config) {
  const cookiecloud = config?.auth?.cookiecloud || {};

  if (!cookiecloud.enabled) {
    return {
      tone: "info",
      title: "CookieCloud 未启用",
      detail: "系统不会自动同步浏览器登录态。",
    };
  }

  if (!cookiecloud.server || !cookiecloud?.uuid?.configured || !cookiecloud?.password?.configured) {
    return {
      tone: "warning",
      title: "CookieCloud 配置不完整",
      detail: "建议补全 server / uuid / password 后再执行调度任务。",
    };
  }

  return {
    tone: "success",
    title: "CookieCloud 配置完整",
    detail: `server=${cookiecloud.server}, uuid=${cookiecloud?.uuid?.masked || "-"}`,
  };
}

export function mountSettingsPage(target, options = {}) {
  const container = resolveContainer(target);
  if (!container) {
    throw new Error("Settings page mount target not found");
  }
  ensurePageStyle();

  const storage = options.storage || globalThis?.localStorage;
  const state = {
    preferences: {
      ...readPreferences(storage),
      ...(options.preferences || {}),
    },
    config: null,
    isLoadingConfig: false,
    inflightController: null,
    lastConfigSyncAt: null,
  };

  container.innerHTML = `
    <section class="runtime-settings-page settings-page">
      <header class="rs-header">
        <div class="rs-header-copy">
          <h2>系统设置（主入口）</h2>
          <p>统一管理连接地址、鉴权相关配置与页面偏好。</p>
        </div>
        <div class="rs-header-actions">
          <button type="button" class="secondary" data-role="reload-config-btn">刷新 /api/config</button>
          <span class="rs-inline-note" data-role="config-updated-at">尚未同步</span>
        </div>
      </header>

      <section class="rs-inline-note" data-tone="info">
        建议在本页完成连接地址、登录配置和自动刷新等核心设置。
      </section>

      <section class="rs-panel rs-panel--preferences">
        <h3>连接与页面偏好</h3>
        <form class="settings-form" data-role="settings-form" autocomplete="off">
          <label class="rs-field">
            <span>API 地址</span>
            <input
              type="text"
              name="apiBase"
              placeholder="留空使用同源（例如 http://127.0.0.1:8080）"
              data-role="api-base-input"
            />
            <small>保存后写入 localStorage key: <code>${SETTINGS_STORAGE_KEYS.apiBase}</code></small>
          </label>

          <label class="rs-field rs-field-inline">
            <input type="checkbox" name="autoRefreshEnabled" data-role="auto-refresh-enabled-input" />
            <span>启用运行页自动刷新</span>
          </label>

          <label class="rs-field">
            <span>自动刷新间隔（秒）</span>
            <input
              type="number"
              min="${MIN_AUTO_REFRESH_INTERVAL_SEC}"
              max="${MAX_AUTO_REFRESH_INTERVAL_SEC}"
              step="1"
              name="autoRefreshIntervalSec"
              data-role="auto-refresh-interval-input"
            />
          </label>

          <div class="rs-actions">
            <button type="submit">保存设置</button>
            <button type="button" class="secondary" data-role="reset-default-btn">恢复默认</button>
            <button type="button" class="secondary" data-role="clear-api-base-btn">清空 API Base</button>
          </div>
        </form>
        <p class="rs-inline-note rs-status-banner" data-role="settings-message" data-tone="neutral" aria-live="polite">
          尚未修改设置
        </p>
      </section>

      <section class="rs-panel rs-panel--diagnostics">
        <h3>登录同步（CookieCloud）摘要</h3>
        <div class="rs-inline-note" data-role="cookiecloud-summary" data-tone="info">等待 /api/config ...</div>
      </section>

      <section class="rs-panel rs-panel--summary">
        <h3>系统配置摘要</h3>
        <div class="rs-config-summary" data-role="config-summary-grid">
          <div class="rs-inline-note rs-empty-state" data-tone="warning">尚未加载配置摘要</div>
        </div>
      </section>

      <details class="rs-panel rs-json-panel rs-panel--debug">
        <summary>/api/config 原始 JSON</summary>
        <pre data-role="config-raw"></pre>
      </details>
    </section>
  `;

  const refs = {
    settingsForm: container.querySelector('[data-role="settings-form"]'),
    apiBaseInput: container.querySelector('[data-role="api-base-input"]'),
    autoRefreshEnabledInput: container.querySelector('[data-role="auto-refresh-enabled-input"]'),
    autoRefreshIntervalInput: container.querySelector('[data-role="auto-refresh-interval-input"]'),
    settingsMessage: container.querySelector('[data-role="settings-message"]'),
    clearApiBaseBtn: container.querySelector('[data-role="clear-api-base-btn"]'),
    resetDefaultBtn: container.querySelector('[data-role="reset-default-btn"]'),
    reloadConfigBtn: container.querySelector('[data-role="reload-config-btn"]'),
    configUpdatedAt: container.querySelector('[data-role="config-updated-at"]'),
    cookiecloudSummary: container.querySelector('[data-role="cookiecloud-summary"]'),
    configSummaryGrid: container.querySelector('[data-role="config-summary-grid"]'),
    configRaw: container.querySelector('[data-role="config-raw"]'),
  };

  function setSettingsMessage(tone, text) {
    refs.settingsMessage.dataset.tone = tone;
    refs.settingsMessage.textContent = text;
  }

  function renderPreferences() {
    refs.apiBaseInput.value = normalizeApiBase(state.preferences.apiBase);
    refs.autoRefreshEnabledInput.checked = normalizeBoolean(state.preferences.autoRefreshEnabled, true);
    refs.autoRefreshIntervalInput.value = String(normalizeIntervalSec(state.preferences.autoRefreshIntervalSec));
  }

  function renderConfigSummary() {
    if (!state.config) {
      refs.configSummaryGrid.innerHTML =
        '<div class="rs-inline-note rs-empty-state" data-tone="warning">尚未加载配置摘要</div>';
      refs.configRaw.textContent = "{}";
      refs.cookiecloudSummary.dataset.tone = "info";
      refs.cookiecloudSummary.textContent = "等待 /api/config ...";
      return;
    }

    const groupedMarkup = createGroupedSummaryMarkup(state.config);
    if (groupedMarkup) {
      refs.configSummaryGrid.innerHTML = groupedMarkup;
    } else {
      const summaryRows = createConfigSummaryRows(state.config);
      refs.configSummaryGrid.innerHTML = `
        <div class="rs-summary-grid">
          ${summaryRows
            .map(
              ([key, value]) => `
                <article class="rs-summary-item">
                  <p class="rs-summary-key">${escapeHtml(formatSummaryValue(key))}</p>
                  <p class="rs-summary-value">${escapeHtml(formatSummaryValue(value))}</p>
                </article>
              `
            )
            .join("")}
        </div>
      `;
    }

    refs.configRaw.textContent = JSON.stringify(state.config, null, 2);

    const cookiecloud = summarizeCookieCloud(state.config);
    refs.cookiecloudSummary.dataset.tone = cookiecloud.tone;
    refs.cookiecloudSummary.textContent = `${cookiecloud.title}：${cookiecloud.detail}`;
  }

  function broadcastSettingsUpdate() {
    globalThis.dispatchEvent(
      new CustomEvent(SETTINGS_UPDATED_EVENT, {
        detail: { ...state.preferences },
      })
    );
  }

  function updatePreferencesAndPersist(nextPreferences, message) {
    state.preferences = persistPreferences(
      {
        ...state.preferences,
        ...(nextPreferences || {}),
      },
      storage
    );
    renderPreferences();
    broadcastSettingsUpdate();
    setSettingsMessage("success", message || "设置已保存");
  }

  function readFormPreferences() {
    return {
      apiBase: normalizeApiBase(refs.apiBaseInput.value),
      autoRefreshEnabled: refs.autoRefreshEnabledInput.checked,
      autoRefreshIntervalSec: normalizeIntervalSec(refs.autoRefreshIntervalInput.value),
    };
  }

  function onSubmitSettings(event) {
    event.preventDefault();
    const next = readFormPreferences();
    updatePreferencesAndPersist(next, "设置已保存并持久化到 localStorage");
  }

  function onResetDefault() {
    updatePreferencesAndPersist(
      {
        apiBase: "",
        autoRefreshEnabled: true,
        autoRefreshIntervalSec: DEFAULT_AUTO_REFRESH_INTERVAL_SEC,
      },
      "已恢复默认设置"
    );
  }

  function onClearApiBase() {
    state.preferences.apiBase = "";
    safeRemoveStorage(storage, SETTINGS_STORAGE_KEYS.apiBase);
    renderPreferences();
    broadcastSettingsUpdate();
    setSettingsMessage("success", "API Base 已清空（将使用同源地址）");
  }

  function clearInflight() {
    if (state.inflightController) {
      state.inflightController.abort();
      state.inflightController = null;
    }
  }

  async function refreshConfig() {
    if (state.isLoadingConfig) return;
    state.isLoadingConfig = true;
    refs.reloadConfigBtn.disabled = true;
    refs.configUpdatedAt.textContent = "正在加载 /api/config ...";

    clearInflight();
    state.inflightController = new AbortController();

    try {
      state.config = await requestJson("/api/config", {
        apiBase: state.preferences.apiBase,
        signal: state.inflightController.signal,
      });
      state.lastConfigSyncAt = new Date();
      refs.configUpdatedAt.textContent = `最近同步：${formatTime(state.lastConfigSyncAt)}`;
      setSettingsMessage("info", "/api/config 摘要已刷新");
    } catch (error) {
      if (error?.name === "AbortError") return;
      refs.configUpdatedAt.textContent = "配置同步失败";
      setSettingsMessage("danger", `加载 /api/config 失败：${error?.message || "未知错误"}`);
    } finally {
      state.isLoadingConfig = false;
      refs.reloadConfigBtn.disabled = false;
      renderConfigSummary();
    }
  }

  function onSettingsUpdated(event) {
    const detail = event?.detail || {};
    state.preferences = {
      apiBase: normalizeApiBase(detail.apiBase ?? state.preferences.apiBase),
      autoRefreshEnabled: normalizeBoolean(
        detail.autoRefreshEnabled ?? state.preferences.autoRefreshEnabled,
        true
      ),
      autoRefreshIntervalSec: normalizeIntervalSec(
        detail.autoRefreshIntervalSec ?? state.preferences.autoRefreshIntervalSec
      ),
    };
    renderPreferences();
  }

  refs.settingsForm.addEventListener("submit", onSubmitSettings);
  refs.resetDefaultBtn.addEventListener("click", onResetDefault);
  refs.clearApiBaseBtn.addEventListener("click", onClearApiBase);
  refs.reloadConfigBtn.addEventListener("click", refreshConfig);
  globalThis.addEventListener(SETTINGS_UPDATED_EVENT, onSettingsUpdated);

  renderPreferences();
  renderConfigSummary();
  refreshConfig();

  return {
    id: "settings",
    refreshConfig,
    destroy() {
      clearInflight();
      refs.settingsForm.removeEventListener("submit", onSubmitSettings);
      refs.resetDefaultBtn.removeEventListener("click", onResetDefault);
      refs.clearApiBaseBtn.removeEventListener("click", onClearApiBase);
      refs.reloadConfigBtn.removeEventListener("click", refreshConfig);
      globalThis.removeEventListener(SETTINGS_UPDATED_EVENT, onSettingsUpdated);
    },
  };
}

const settingsPage = {
  id: "settings",
  title: "系统设置",
  mount: mountSettingsPage,
};

export default settingsPage;
