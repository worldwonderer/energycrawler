import { api } from "../lib/api.js";

const STYLE_LINK_ID = "energycrawler-ui2-welcome-style";
const ONBOARDING_COMPLETED_STORAGE_KEY = "energycrawler_ui_onboarding_completed_at";

const ONBOARDING_STEPS = [
  {
    id: "connection-check",
    title: "1) 连接检查",
    detail: "先确认服务和调度队列可用，避免任务刚创建就卡住。",
    actions: [
      { label: "查看运行监控健康状态", hash: "#/runs", markComplete: false },
      { label: "打开系统设置检查连接", hash: "#/settings", markComplete: false },
    ],
  },
  {
    id: "login-ready",
    title: "2) 登录就绪",
    detail: "确认 xhs / x 登录状态就绪，任务才能稳定执行。",
    actions: [
      { label: "去系统设置检查登录态", hash: "#/settings", markComplete: false },
      { label: "去系统设置更新登录配置", hash: "#/settings", markComplete: false },
    ],
  },
  {
    id: "create-first-task",
    title: "3) 创建首个任务",
    detail: "使用简化默认参数创建任务，再到运行监控与结果页确认效果。",
    actions: [
      { label: "立即创建任务", hash: "#/scheduler", markComplete: true },
      { label: "查看最近运行", hash: "#/runs", markComplete: true },
      { label: "查看最新结果", hash: "#/data", markComplete: true },
    ],
  },
];

function ensurePageStyle() {
  if (typeof document === "undefined") return;
  if (document.getElementById(STYLE_LINK_ID)) return;

  const link = document.createElement("link");
  link.id = STYLE_LINK_ID;
  link.rel = "stylesheet";
  link.href = new URL("../styles/welcome.css", import.meta.url).href;
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
    // ignore storage write failures
  }
}

function isOnboardingCompleted(storage = globalThis?.localStorage) {
  const raw = String(safeReadStorage(storage, ONBOARDING_COMPLETED_STORAGE_KEY, "")).trim();
  if (!raw) return false;
  if (raw === "0" || raw === "false") return false;
  return true;
}

function markOnboardingCompleted(storage = globalThis?.localStorage) {
  const timestamp = new Date().toISOString();
  safeWriteStorage(storage, ONBOARDING_COMPLETED_STORAGE_KEY, timestamp);
  return timestamp;
}

function safeFormatDateTime(ctx, value) {
  if (!value) return "-";
  if (ctx && typeof ctx.formatDateTime === "function") {
    return ctx.formatDateTime(value);
  }
  try {
    const date = value instanceof Date ? value : new Date(value);
    if (Number.isNaN(date.getTime())) return String(value);
    return date.toLocaleString();
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

function resolveRuntimeData(payload) {
  const data = payload?.data ?? payload;
  return data && typeof data === "object" ? data : null;
}

function resolveLatestRun(payload) {
  const runs = payload?.data?.runs;
  if (!Array.isArray(runs) || runs.length === 0) return null;
  return runs[0] && typeof runs[0] === "object" ? runs[0] : null;
}

function runTone(status) {
  const normalized = String(status || "").toLowerCase();
  if (["completed", "success"].includes(normalized)) return "success";
  if (["queued", "pending"].includes(normalized)) return "warning";
  if (["running", "accepted"].includes(normalized)) return "info";
  if (["failed", "rejected", "cancelled", "error"].includes(normalized)) return "danger";
  return "neutral";
}

function renderActionLink(action, className = "wc-action-link") {
  return `<a
    class="${className}"
    href="${escapeHtml(action.hash)}"
    data-role="welcome-step-link"
    data-progress-link="true"
    data-mark-complete="${action.markComplete ? "true" : "false"}"
  >${escapeHtml(action.label)}</a>`;
}

function renderStepCard(step) {
  const actions = (step.actions || []).map((action) => renderActionLink(action)).join("");
  return `
    <article class="wc-step-card" data-step-id="${escapeHtml(step.id)}">
      <h3>${escapeHtml(step.title)}</h3>
      <p>${escapeHtml(step.detail)}</p>
      <div class="wc-step-actions">${actions}</div>
    </article>
  `;
}

function createAvailabilityRows(runtime) {
  if (!runtime) {
    return [
      { label: "系统状态", value: "等待检测", tone: "neutral", detail: "点击“刷新摘要”后展示实时可用性。" },
    ];
  }

  const login = runtime.login || {};
  const queue = runtime.crawler_queue || {};
  const xhsReady = login?.xhs?.ok === true;
  const xReady = login?.x?.ok === true;

  const loginTone = xhsReady && xReady ? "success" : "warning";
  const loginValue = xhsReady && xReady ? "已就绪" : "待处理";
  const queueStatus = String(queue.status || "unknown");

  return [
    {
      label: "整体可用性",
      value: runtime.overall_healthy ? "可用" : "需处理",
      tone: runtime.overall_healthy ? "success" : "warning",
      detail: `状态：${runtime.overall_status || "unknown"}`,
    },
    {
      label: "服务连接",
      value: runtime?.energy?.ok ? "可达" : "不可达",
      tone: runtime?.energy?.ok ? "success" : "danger",
      detail: runtime?.energy?.message || "未返回连接详情",
    },
    {
      label: "登录就绪",
      value: loginValue,
      tone: loginTone,
      detail: `xhs: ${xhsReady ? "ready" : "missing"} · x: ${xReady ? "ready" : "missing"}`,
    },
    {
      label: "调度队列",
      value: queueStatus,
      tone: queueStatus === "error" ? "danger" : "info",
      detail: `运行中 ${queue.running_workers ?? 0}/${queue.total_workers ?? 0} · 排队 ${queue.queued_tasks ?? 0}`,
    },
  ];
}

function renderAvailabilityRows(rows) {
  return rows
    .map(
      (row) => `
        <li class="wc-status-item" data-tone="${escapeHtml(row.tone)}">
          <div>
            <p class="wc-status-label">${escapeHtml(row.label)}</p>
            <p class="wc-status-detail">${escapeHtml(row.detail)}</p>
          </div>
          <p class="wc-status-value">${escapeHtml(row.value)}</p>
        </li>
      `
    )
    .join("");
}

function renderRecentRun(run, ctx) {
  if (!run) {
    return `
      <div class="wc-empty">
        <p>暂时还没有运行记录。</p>
        ${renderActionLink({ label: "去创建首个任务", hash: "#/scheduler", markComplete: true })}
      </div>
    `;
  }

  const status = String(run.status || "unknown");
  const runTime = safeFormatDateTime(ctx, run.triggered_at || run.started_at || run.finished_at);

  return `
    <article class="wc-recent-run" data-tone="${escapeHtml(runTone(status))}">
      <div class="wc-recent-run-row">
        <p class="wc-recent-label">Run #</p>
        <p class="wc-recent-value">${escapeHtml(run.run_id || "-")}</p>
      </div>
      <div class="wc-recent-run-row">
        <p class="wc-recent-label">状态</p>
        <p class="wc-recent-value">${escapeHtml(status)}</p>
      </div>
      <div class="wc-recent-run-row">
        <p class="wc-recent-label">触发时间</p>
        <p class="wc-recent-value">${escapeHtml(runTime)}</p>
      </div>
      <p class="wc-recent-message">${escapeHtml(run.message || "无额外说明")}</p>
      <div class="wc-step-actions">
        ${renderActionLink({ label: "打开运行监控", hash: "#/runs", markComplete: true })}
        ${renderActionLink({ label: "查看最新结果", hash: "#/data", markComplete: true })}
      </div>
    </article>
  `;
}

export function mountWelcomePage(target, ctx = {}) {
  ensurePageStyle();

  const mountEl = target && typeof target === "object" && "nodeType" in target ? target : null;
  if (!mountEl) {
    throw new Error("Welcome page mount target not found");
  }

  const storage = globalThis?.localStorage;
  const alreadyDone = isOnboardingCompleted(storage);
  const state = {
    loadingSummary: false,
    summaryError: "",
    checkedAt: "",
    runtime: null,
    latestRun: null,
    inflightController: null,
  };

  mountEl.innerHTML = `
    <section class="welcome-page">
      <header class="wc-hero">
        <p class="wc-kicker">开始使用 EnergyCrawler</p>
        <h2>3 步完成首次上手</h2>
        <p class="wc-summary">
          先检查连接和登录，再创建第一个任务。你可以在本页直接跳到下一步。
        </p>
        <div class="wc-hero-actions">
          <button type="button" data-role="complete-onboarding-btn">我已完成 3 步，进入查看结果</button>
          ${renderActionLink(
            { label: "先去运行监控做连接检查", hash: "#/runs", markComplete: false },
            "wc-inline-link secondary"
          )}
        </div>
        <p class="wc-note" data-tone="${alreadyDone ? "success" : "info"}">
          ${
            alreadyDone
              ? "当前实例已记录完成引导，你仍可随时回到本页复查。"
              : "建议按 1→3 顺序完成；完成后系统会记住你的引导状态。"
          }
        </p>
      </header>

      <section class="wc-overview-grid">
        <article class="wc-overview-card">
          <div class="wc-card-headline">
            <div>
              <h3>当前系统可用性</h3>
              <p class="wc-overview-meta" data-role="availability-meta">等待首次检测...</p>
            </div>
            <button type="button" class="secondary" data-role="refresh-summary-btn">刷新摘要</button>
          </div>
          <ul class="wc-status-list" data-role="availability-list"></ul>
        </article>

        <article class="wc-overview-card">
          <div class="wc-card-headline">
            <div>
              <h3>最近运行入口</h3>
              <p class="wc-overview-meta">先看结论，再决定下一步操作</p>
            </div>
          </div>
          <div data-role="recent-run"></div>
        </article>
      </section>

      <section class="wc-steps-grid">
        ${ONBOARDING_STEPS.map((step) => renderStepCard(step)).join("")}
      </section>
    </section>
  `;

  const completeBtn = mountEl.querySelector('[data-role="complete-onboarding-btn"]');
  const refreshSummaryBtn = mountEl.querySelector('[data-role="refresh-summary-btn"]');
  const availabilityMeta = mountEl.querySelector('[data-role="availability-meta"]');
  const availabilityList = mountEl.querySelector('[data-role="availability-list"]');
  const recentRunSlot = mountEl.querySelector('[data-role="recent-run"]');

  const markCompletedOnce = () => {
    const wasCompleted = isOnboardingCompleted(storage);
    markOnboardingCompleted(storage);

    if (!wasCompleted && typeof ctx.showToast === "function") {
      ctx.showToast("已记录上手引导完成状态。", {
        tone: "success",
        title: "Welcome 完成",
      });
    }
  };

  const onCompleteClick = () => {
    markCompletedOnce();
    if (typeof ctx.navigate === "function") {
      ctx.navigate("data");
      return;
    }
    if (typeof window !== "undefined") {
      window.location.hash = "#/data";
    }
  };

  const onMountClick = (event) => {
    const trigger = event?.target?.closest?.('[data-progress-link="true"]');
    if (!trigger) return;

    if (String(trigger.dataset.markComplete || "false") === "true") {
      markCompletedOnce();
    }
  };

  function renderSummary() {
    if (!availabilityMeta || !availabilityList || !recentRunSlot || !refreshSummaryBtn) return;

    if (state.loadingSummary) {
      refreshSummaryBtn.disabled = true;
      refreshSummaryBtn.textContent = "刷新中...";
    } else {
      refreshSummaryBtn.disabled = false;
      refreshSummaryBtn.textContent = "刷新摘要";
    }

    if (state.summaryError) {
      availabilityMeta.textContent = `部分数据获取失败：${state.summaryError}`;
    } else if (state.checkedAt) {
      availabilityMeta.textContent = `最近检测：${safeFormatDateTime(ctx, state.checkedAt)}`;
    } else {
      availabilityMeta.textContent = "等待首次检测...";
    }

    availabilityList.innerHTML = renderAvailabilityRows(createAvailabilityRows(state.runtime));
    recentRunSlot.innerHTML = renderRecentRun(state.latestRun, ctx);
  }

  function clearInflightRequest() {
    if (state.inflightController) {
      state.inflightController.abort();
      state.inflightController = null;
    }
  }

  async function refreshSummary(options = {}) {
    if (state.loadingSummary) return;

    clearInflightRequest();
    state.loadingSummary = true;
    state.summaryError = "";
    state.inflightController = new AbortController();
    renderSummary();

    const controller = state.inflightController;

    try {
      const [runtimeResult, runsResult] = await Promise.allSettled([
        api.get("/api/health/runtime", {
          signal: controller.signal,
          suppressErrorToast: true,
        }),
        api.get("/api/scheduler/runs", {
          signal: controller.signal,
          suppressErrorToast: true,
          query: { limit: 1 },
        }),
      ]);

      if (runtimeResult.status === "fulfilled") {
        state.runtime = resolveRuntimeData(runtimeResult.value);
      }
      if (runsResult.status === "fulfilled") {
        state.latestRun = resolveLatestRun(runsResult.value);
      }

      const errors = [];
      if (runtimeResult.status === "rejected" && runtimeResult.reason?.name !== "AbortError") {
        errors.push("可用性摘要");
      }
      if (runsResult.status === "rejected" && runsResult.reason?.name !== "AbortError") {
        errors.push("最近运行");
      }

      state.summaryError = errors.join(" / ");
      state.checkedAt = new Date().toISOString();

      if (state.summaryError && !options.silent && typeof ctx.showToast === "function") {
        ctx.showToast("部分 Welcome 摘要暂不可用，可稍后重试。", {
          tone: "warning",
          title: "Welcome 摘要",
        });
      }
    } catch (error) {
      if (error?.name !== "AbortError") {
        state.summaryError = error?.message || "未知错误";
      }
    } finally {
      if (state.inflightController === controller) {
        state.inflightController = null;
      }
      state.loadingSummary = false;
      renderSummary();
    }
  }

  const onRefreshSummaryClick = () => {
    refreshSummary({ silent: false });
  };

  completeBtn?.addEventListener("click", onCompleteClick);
  refreshSummaryBtn?.addEventListener("click", onRefreshSummaryClick);
  mountEl.addEventListener("click", onMountClick);

  renderSummary();
  refreshSummary({ silent: true });

  return {
    id: "welcome",
    destroy() {
      clearInflightRequest();
      completeBtn?.removeEventListener("click", onCompleteClick);
      refreshSummaryBtn?.removeEventListener("click", onRefreshSummaryClick);
      mountEl.removeEventListener("click", onMountClick);
    },
  };
}

const welcomePage = {
  id: "welcome",
  title: "Welcome / Onboarding",
  mount: mountWelcomePage,
};

export default welcomePage;
