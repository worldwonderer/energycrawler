import { formatDateTime } from "./lib/time.js";

export const ONBOARDING_COMPLETED_STORAGE_KEY = "energycrawler_ui_onboarding_completed_at";
const FIRST_RUN_ROUTE_ID = "welcome";
const DEFAULT_ROUTE_ID = "welcome";

export const DEFAULT_ROUTES = [
  {
    id: "welcome",
    label: "开始使用",
    hash: "#/welcome",
    title: "开始使用",
    modulePath: "./pages/welcome.js",
    description: "按步骤完成连接检查、登录准备并创建首个任务。",
    navHint: "3 步完成首次上手",
  },
  {
    id: "scheduler",
    label: "创建任务",
    hash: "#/scheduler",
    title: "创建任务",
    modulePath: "./pages/scheduler.js",
    description: "选择任务类型并填写必要参数，快速发起任务。",
    navHint: "填写参数并立即发起",
  },
  {
    id: "runs",
    label: "运行监控",
    hash: "#/runs",
    title: "运行监控",
    modulePath: "./pages/runs.js",
    description: "先看状态结论，再查看日志明细与下一步建议。",
    navHint: "先看结论再查日志",
  },
  {
    id: "data",
    label: "查看结果",
    hash: "#/data",
    title: "查看结果",
    modulePath: "./pages/data.js",
    description: "优先浏览最新结果，再按条件筛选、导出与统计。",
    navHint: "默认先看最新结果",
  },
  {
    id: "settings",
    label: "系统设置",
    hash: "#/settings",
    title: "系统设置",
    modulePath: "./pages/settings.js",
    description: "统一管理连接、鉴权、偏好与环境配置。",
    navHint: "统一管理连接与偏好",
  },
];

function normalizeHash(hash, fallbackHash = "#/welcome") {
  if (!hash || hash === "#") return fallbackHash;
  if (hash.startsWith("#/")) return hash;
  if (hash.startsWith("#")) return `#/${hash.slice(1)}`;
  return `#/${hash}`;
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

function hasCompletedOnboarding(storage = globalThis?.localStorage) {
  const raw = String(safeReadStorage(storage, ONBOARDING_COMPLETED_STORAGE_KEY, "")).trim();
  if (!raw) return false;
  if (raw === "false" || raw === "0") return false;
  return true;
}

function isDomNode(value) {
  return value && typeof value === "object" && typeof value.nodeType === "number";
}

function toDisplayText(value) {
  if (value === null || value === undefined) return "";
  return String(value);
}

export class AppShell {
  constructor({ navEl, viewEl, toastViewport, routes = DEFAULT_ROUTES }) {
    this.navEl = navEl;
    this.viewEl = viewEl;
    this.toastViewport = toastViewport;
    this.routes = routes;
    this.routeMap = new Map(routes.map((route) => [route.id, route]));
    this.moduleCache = new Map();
    this.boundOnHashChange = this.onHashChange.bind(this);
    this.renderToken = 0;
    this.activeRouteCleanup = null;
    this.defaultRouteId = this.resolveDefaultRouteId();
  }

  start() {
    this.renderNav();
    window.addEventListener("hashchange", this.boundOnHashChange);
    if (!window.location.hash) {
      this.navigate(this.defaultRouteId, { replace: true });
    } else {
      this.renderCurrentRoute();
    }
  }

  stop() {
    window.removeEventListener("hashchange", this.boundOnHashChange);
    this.teardownActiveRoute();
  }

  navigate(routeId, options = {}) {
    const route = this.routeMap.get(routeId);
    if (!route) return;

    if (options.replace) {
      const { pathname, search } = window.location;
      history.replaceState(null, "", `${pathname}${search}${route.hash}`);
      this.renderCurrentRoute();
      return;
    }

    if (window.location.hash === route.hash) {
      this.renderCurrentRoute();
      return;
    }

    window.location.hash = route.hash;
  }

  onHashChange() {
    this.renderCurrentRoute();
  }

  teardownActiveRoute() {
    if (typeof this.activeRouteCleanup === "function") {
      try {
        this.activeRouteCleanup();
      } catch (error) {
        // eslint-disable-next-line no-console
        console.warn("[AppShell] Failed to cleanup previous route", error);
      }
    }
    this.activeRouteCleanup = null;
  }

  resolveDefaultRouteId() {
    if (this.routeMap.has(FIRST_RUN_ROUTE_ID) && !hasCompletedOnboarding()) {
      return FIRST_RUN_ROUTE_ID;
    }
    if (this.routeMap.has(DEFAULT_ROUTE_ID)) {
      return DEFAULT_ROUTE_ID;
    }
    return this.routes[0]?.id || DEFAULT_ROUTE_ID;
  }

  resolveCurrentRoute() {
    const defaultHash = this.routeMap.get(this.defaultRouteId)?.hash || "#/welcome";
    const normalized = normalizeHash(window.location.hash, defaultHash);
    const routeId = normalized.replace(/^#\//, "").split("?")[0] || this.defaultRouteId;
    return this.routeMap.get(routeId) || this.routeMap.get(this.defaultRouteId);
  }

  createNavTab(route) {
    const tab = document.createElement("a");
    tab.href = route.hash;
    tab.dataset.routeId = route.id;
    tab.className = "module-tab";
    tab.title = toDisplayText(route.description || route.title || route.label);

    const label = document.createElement("span");
    label.className = "module-tab__label";
    label.textContent = toDisplayText(route.label);

    const desc = document.createElement("span");
    desc.className = "module-tab__desc";
    desc.textContent = toDisplayText(route.navHint || route.title);

    tab.append(label, desc);
    return tab;
  }

  renderNav() {
    this.navEl.innerHTML = "";
    this.routes.filter((route) => route.showInNav !== false).forEach((route) => {
      this.navEl.appendChild(this.createNavTab(route));
    });
    this.highlightRoute(this.resolveCurrentRoute());
  }

  highlightRoute(route) {
    this.navEl.dataset.activeRoute = route.id;
    const tabs = this.navEl.querySelectorAll(".module-tab");
    tabs.forEach((tab) => {
      const isActive = tab.dataset.routeId === route.id;
      tab.classList.toggle("active", isActive);
      if (isActive) {
        tab.setAttribute("aria-current", "page");
      } else {
        tab.removeAttribute("aria-current");
      }
    });
  }

  async renderCurrentRoute() {
    const route = this.resolveCurrentRoute();
    if (!route) return;

    const token = ++this.renderToken;
    this.teardownActiveRoute();
    this.highlightRoute(route);
    this.viewEl.dataset.routeId = route.id;
    document.title = `EnergyCrawler · ${route.title}`;

    this.viewEl.innerHTML = "";
    const loadingSection = document.createElement("section");
    loadingSection.className = "shell-page shell-page--loading";

    const heading = document.createElement("h2");
    heading.textContent = toDisplayText(route.title);

    const description = document.createElement("p");
    description.textContent = toDisplayText(route.description);

    const placeholderCard = document.createElement("article");
    placeholderCard.className = "placeholder-card";
    const loadingMessage = document.createElement("p");
    loadingMessage.textContent = "模块资源加载中，请稍候…";
    placeholderCard.appendChild(loadingMessage);

    loadingSection.append(heading, description, placeholderCard);
    this.viewEl.appendChild(loadingSection);

    const module = await this.loadRouteModule(route);
    if (token !== this.renderToken) return;

    if (!module) {
      this.renderFallbackRoute(route);
      return;
    }

    try {
      await this.renderRouteModule(module, route, token);
    } catch (error) {
      this.showToast(`${route.title} 加载失败：${error?.message || "unknown error"}`, {
        tone: "error",
        title: "页面渲染异常",
      });
      // eslint-disable-next-line no-console
      console.error(`[AppShell] Route render failed: ${route.id}`, error);
      if (token === this.renderToken) {
        this.renderFallbackRoute(route);
      }
    }
  }

  async loadRouteModule(route) {
    if (!route.modulePath) return null;
    if (this.moduleCache.has(route.id)) {
      return this.moduleCache.get(route.id);
    }

    try {
      const loaded = await import(route.modulePath);
      this.moduleCache.set(route.id, loaded);
      return loaded;
    } catch (error) {
      this.moduleCache.set(route.id, null);
      this.showToast(`${route.title} 页面未就绪，已回退到占位视图。`, {
        tone: "warning",
        title: "路由回退",
      });
      // eslint-disable-next-line no-console
      console.warn(`[AppShell] Failed to load ${route.modulePath}`, error);
      return null;
    }
  }

  resolveCleanupHandle(routeResult, registeredCleanups = []) {
    const cleanupFns = [...registeredCleanups];

    if (typeof routeResult === "function") {
      cleanupFns.push(routeResult);
    } else if (routeResult && typeof routeResult === "object") {
      if (typeof routeResult.destroy === "function") cleanupFns.push(() => routeResult.destroy());
      else if (typeof routeResult.unmount === "function") cleanupFns.push(() => routeResult.unmount());
      else if (typeof routeResult.dispose === "function") cleanupFns.push(() => routeResult.dispose());
    }

    if (cleanupFns.length === 0) return null;
    return () => {
      cleanupFns.forEach((fn) => {
        try {
          fn();
        } catch (error) {
          // eslint-disable-next-line no-console
          console.warn("[AppShell] Route cleanup callback failed", error);
        }
      });
    };
  }

  async mountModuleObject(moduleObject, mountEl, context) {
    if (!moduleObject || typeof moduleObject !== "object") {
      return { mounted: false, routeResult: null };
    }

    if (typeof moduleObject.mount === "function") {
      const routeResult = await moduleObject.mount(mountEl, context);
      return { mounted: true, routeResult };
    }

    if (typeof moduleObject.create === "function") {
      const routeResult = await moduleObject.create(context);
      if (routeResult && isDomNode(routeResult.root)) {
        mountEl.innerHTML = "";
        mountEl.appendChild(routeResult.root);
      }
      return { mounted: true, routeResult };
    }

    if (typeof moduleObject.template === "string") {
      mountEl.innerHTML = moduleObject.template;
      return { mounted: true, routeResult: null };
    }

    return { mounted: false, routeResult: null };
  }

  async mountRouteModule(module, mountEl, context) {
    if (typeof module.default === "function") {
      const routeResult = await module.default(mountEl, context);
      return { mounted: true, routeResult };
    }

    if (typeof module.render === "function") {
      const routeResult = await module.render(mountEl, context);
      return { mounted: true, routeResult };
    }

    if (typeof module.template === "string") {
      mountEl.innerHTML = module.template;
      return { mounted: true, routeResult: null };
    }

    const mountedByDefaultObject = await this.mountModuleObject(module.default, mountEl, context);
    if (mountedByDefaultObject.mounted) return mountedByDefaultObject;

    const mountedByModuleObject = await this.mountModuleObject(module, mountEl, context);
    if (mountedByModuleObject.mounted) return mountedByModuleObject;

    return { mounted: false, routeResult: null };
  }

  async renderRouteModule(module, route, token) {
    const registeredCleanups = [];
    const context = {
      route,
      showToast: (message, options) => this.showToast(message, options),
      navigate: (routeId, options) => this.navigate(routeId, options),
      formatDateTime,
      registerCleanup: (cleanupFn) => {
        if (typeof cleanupFn === "function") {
          registeredCleanups.push(cleanupFn);
        }
      },
    };

    this.viewEl.innerHTML = "";
    const mountEl = document.createElement("section");
    mountEl.className = "route-module-root";
    mountEl.dataset.routeId = route.id;
    this.viewEl.appendChild(mountEl);

    const { mounted, routeResult } = await this.mountRouteModule(module, mountEl, context);
    const cleanup = this.resolveCleanupHandle(routeResult, registeredCleanups);

    if (token !== this.renderToken) {
      if (cleanup) cleanup();
      return;
    }

    if (mounted) {
      this.activeRouteCleanup = cleanup;
      return;
    }

    this.activeRouteCleanup = cleanup;
    if (token === this.renderToken) {
      this.renderFallbackRoute(route);
    }
  }

  renderFallbackRoute(route) {
    this.viewEl.innerHTML = "";
    const page = document.createElement("section");
    page.className = "shell-page";

    const heading = document.createElement("h2");
    heading.textContent = toDisplayText(route.title);

    const description = document.createElement("p");
    description.textContent = toDisplayText(route.description);

    const placeholderCard = document.createElement("article");
    placeholderCard.className = "placeholder-card";

    const moduleMessage = document.createElement("p");
    moduleMessage.appendChild(document.createTextNode("页面模块暂未就绪："));
    const moduleCode = document.createElement("code");
    moduleCode.textContent = toDisplayText(route.modulePath || "(none)");
    moduleMessage.appendChild(moduleCode);

    const nowMessage = document.createElement("p");
    nowMessage.textContent = `当前时间：${formatDateTime(new Date())}`;

    placeholderCard.append(moduleMessage, nowMessage);
    page.append(heading, description, placeholderCard);
    this.viewEl.appendChild(page);
  }

  showToast(message, options = {}) {
    if (!this.toastViewport) return;
    const { tone = "info", title = "提示", timeoutMs = 3200 } = options;

    const node = document.createElement("article");
    node.className = "toast";
    node.dataset.tone = tone;

    const titleEl = document.createElement("h4");
    titleEl.className = "toast-title";
    titleEl.textContent = toDisplayText(title);

    const messageEl = document.createElement("p");
    messageEl.className = "toast-message";
    messageEl.textContent = toDisplayText(message);

    node.append(titleEl, messageEl);

    this.toastViewport.appendChild(node);

    window.setTimeout(() => {
      node.remove();
    }, timeoutMs);
  }
}
