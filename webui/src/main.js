import { AppShell, DEFAULT_ROUTES } from "./app-shell.js";
import { getApiBase, setApiBase, setApiErrorHandler } from "./lib/api.js";

const navEl = document.getElementById("moduleNav");
const viewEl = document.getElementById("routeView");
const toastViewport = document.getElementById("toastViewport");

if (!navEl || !viewEl || !toastViewport) {
  throw new Error("UI 壳层初始化失败：缺少必要挂载节点。");
}

const shell = new AppShell({
  navEl,
  viewEl,
  toastViewport,
  routes: DEFAULT_ROUTES,
});

function bindApiBaseSettings() {
  const input = document.getElementById("apiBaseInput");
  const saveBtn = document.getElementById("saveApiBaseBtn");
  if (!input || !saveBtn) return;

  input.value = getApiBase();

  const save = () => {
    const value = setApiBase(input.value);
    const target = value || "(同源)";
    shell.showToast(`API Base 已保存：${target}`, {
      tone: "success",
      title: "配置已更新",
    });
  };

  saveBtn.addEventListener("click", save);
  input.addEventListener("keydown", (event) => {
    if (event.key === "Enter") {
      event.preventDefault();
      save();
    }
  });
}

function bindGlobalErrorSurface() {
  setApiErrorHandler((message) => {
    shell.showToast(message, {
      tone: "error",
      title: "API 请求失败",
      timeoutMs: 4500,
    });
  });

  window.addEventListener("error", (event) => {
    const message = event?.error?.message || event.message || "未知错误";
    shell.showToast(message, {
      tone: "error",
      title: "页面异常",
      timeoutMs: 4500,
    });
  });

  window.addEventListener("unhandledrejection", (event) => {
    const reason = event.reason;
    const message = reason instanceof Error ? reason.message : String(reason || "Promise rejected");
    shell.showToast(message, {
      tone: "error",
      title: "异步异常",
      timeoutMs: 4500,
    });
  });
}

bindApiBaseSettings();
bindGlobalErrorSurface();
shell.start();

window.__energycrawler_ui2_shell = shell;
