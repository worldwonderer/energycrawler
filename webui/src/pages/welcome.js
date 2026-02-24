const STYLE_LINK_ID = "energycrawler-ui2-welcome-style";
const ONBOARDING_COMPLETED_STORAGE_KEY = "energycrawler_ui_onboarding_completed_at";

const ONBOARDING_STEPS = [
  {
    id: "env-health",
    title: "1) 环境健康 (Env Health)",
    detail: "先确认 API 可达、Runtime 快照正常，避免后续操作失败。",
    actions: [
      { label: "打开 Runtime 健康页", hash: "#/runtime" },
      { label: "检查 Settings / API Base", hash: "#/settings" },
    ],
  },
  {
    id: "auth-health",
    title: "2) 鉴权健康 (Auth Health)",
    detail: "检查 xhs / x 登录态与 CookieCloud 配置，确认可稳定抓取。",
    actions: [
      { label: "查看登录与 CookieCloud 诊断", hash: "#/runtime" },
      { label: "回到 Settings 校验配置摘要", hash: "#/settings" },
    ],
  },
  {
    id: "demo-run",
    title: "3) Demo Run",
    detail: "触发一次 smoke-e2e 自检，快速验证调度链路是否可用。",
    actions: [
      { label: "进入 Runtime 运行一键自检", hash: "#/runtime" },
      { label: "打开 Runs 观察执行状态", hash: "#/runs" },
    ],
  },
  {
    id: "data-view",
    title: "4) 数据查看 (Data View)",
    detail: "完成 Demo 后前往 Data Explorer 与 Dashboard 查看结果与指标。",
    actions: [
      { label: "打开 Data Explorer", hash: "#/data" },
      { label: "打开 Dashboard 总览", hash: "#/dashboard" },
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

function escapeHtml(value) {
  return String(value)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/\"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

function renderStepCard(step) {
  const actions = (step.actions || [])
    .map(
      (action) =>
        `<a class="wc-action-link" href="${escapeHtml(action.hash)}" data-role="welcome-step-link">${escapeHtml(action.label)}</a>`
    )
    .join("");

  return `
    <article class="wc-step-card" data-step-id="${escapeHtml(step.id)}">
      <h3>${escapeHtml(step.title)}</h3>
      <p>${escapeHtml(step.detail)}</p>
      <div class="wc-step-actions">${actions}</div>
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
  mountEl.innerHTML = `
    <section class="welcome-page">
      <header class="wc-hero">
        <p class="wc-kicker">EnergyCrawler UI 2.0</p>
        <h2>Welcome · 4 步完成首轮上手</h2>
        <p class="wc-summary">
          按顺序完成环境健康、鉴权检查、Demo 运行和数据查看。每一步都提供直接入口。
        </p>
        <div class="wc-hero-actions">
          <button type="button" data-role="complete-onboarding-btn">我已完成引导，进入 Dashboard</button>
          <a href="#/runtime" class="secondary wc-inline-link" data-role="welcome-step-link">先去 Runtime 自检</a>
        </div>
        <p class="wc-note" data-tone="${alreadyDone ? "success" : "info"}">
          ${
            alreadyDone
              ? "当前实例已记录为“完成引导”，你仍可随时返回本页复查。"
              : "首次进入建议先按 1→4 顺序执行，完成后将默认进入 Dashboard。"
          }
        </p>
      </header>

      <section class="wc-steps-grid">
        ${ONBOARDING_STEPS.map((step) => renderStepCard(step)).join("")}
      </section>
    </section>
  `;

  const completeBtn = mountEl.querySelector('[data-role="complete-onboarding-btn"]');
  const stepLinks = mountEl.querySelectorAll('[data-role="welcome-step-link"]');

  const markCompletedOnce = () => {
    const wasCompleted = isOnboardingCompleted(storage);
    const timestamp = markOnboardingCompleted(storage);

    if (!wasCompleted && typeof ctx.showToast === "function") {
      ctx.showToast("已记录 onboarding 完成状态，下次将默认进入 Dashboard。", {
        tone: "success",
        title: "Welcome 完成",
      });
    }
    return timestamp;
  };

  const onCompleteClick = () => {
    markCompletedOnce();
    if (typeof ctx.navigate === "function") {
      ctx.navigate("dashboard");
      return;
    }
    if (typeof window !== "undefined") {
      window.location.hash = "#/dashboard";
    }
  };

  const onStepLinkClick = () => {
    markCompletedOnce();
  };

  completeBtn?.addEventListener("click", onCompleteClick);
  stepLinks.forEach((node) => node.addEventListener("click", onStepLinkClick));

  return {
    id: "welcome",
    destroy() {
      completeBtn?.removeEventListener("click", onCompleteClick);
      stepLinks.forEach((node) => node.removeEventListener("click", onStepLinkClick));
    },
  };
}

const welcomePage = {
  id: "welcome",
  title: "Welcome / Onboarding",
  mount: mountWelcomePage,
};

export default welcomePage;
