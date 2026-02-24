const DEFAULT_RUN_LIMIT = 200
const DEFAULT_ANOMALY_LIMIT = 20
const DEFAULT_REFRESH_INTERVAL_MS = 30_000
const STYLE_LINK_ID = "energycrawler-ui2-dashboard-data-style"

function ensurePageStyle() {
  if (typeof document === "undefined") return
  if (document.getElementById(STYLE_LINK_ID)) return

  const link = document.createElement("link")
  link.id = STYLE_LINK_ID
  link.rel = "stylesheet"
  link.href = new URL("../styles/dashboard-data.css", import.meta.url).href
  document.head.appendChild(link)
}

function normalizeApiBase(value) {
  const raw = String(value || "").trim()
  if (!raw) return ""
  return raw.replace(/\/+$/, "")
}

function resolveApiBase(options = {}) {
  if (typeof options.getApiBase === "function") {
    return normalizeApiBase(options.getApiBase())
  }

  if (typeof options.apiBase === "string") {
    return normalizeApiBase(options.apiBase)
  }

  if (typeof window !== "undefined") {
    const fromWindow = normalizeApiBase(window.__ENERGYCRAWLER_API_BASE__ || "")
    if (fromWindow) return fromWindow
  }

  try {
    if (typeof localStorage !== "undefined") {
      return normalizeApiBase(localStorage.getItem("energycrawler_api_base") || "")
    }
  } catch {
    return ""
  }

  return ""
}

function buildUrl({ apiBase, path, params = {} }) {
  const finalPath = path.startsWith("/") ? path : `/${path}`
  const origin =
    typeof window !== "undefined" && window.location
      ? window.location.origin
      : "http://localhost"
  const url = new URL(apiBase ? `${apiBase}${finalPath}` : finalPath, origin)

  Object.entries(params || {}).forEach(([key, value]) => {
    if (value === undefined || value === null || value === "") return
    url.searchParams.set(key, String(value))
  })

  return url.toString()
}

async function defaultRequest(options, path, { method = "GET", params, body, signal } = {}) {
  const apiBase = resolveApiBase(options)
  const url = buildUrl({ apiBase, path, params })
  const requestOptions = {
    method,
    headers: {
      Accept: "application/json",
    },
    signal,
  }

  if (body !== undefined && body !== null) {
    requestOptions.headers["Content-Type"] = "application/json"
    requestOptions.body = JSON.stringify(body)
  }

  const response = await fetch(url, requestOptions)
  const payload = await response.json().catch(() => null)
  if (!response.ok || !payload || payload.success === false) {
    const message =
      payload?.error?.message || payload?.message || `${response.status} ${response.statusText}`
    throw new Error(message)
  }
  return payload.data
}

function createRequest(options = {}) {
  if (typeof options.request === "function") {
    return async (path, requestOptions = {}) => {
      const result = await options.request(path, requestOptions)
      if (result && result.success === true && Object.prototype.hasOwnProperty.call(result, "data")) {
        return result.data
      }
      return result
    }
  }

  return (path, requestOptions) => defaultRequest(options, path, requestOptions)
}

function formatNumber(value) {
  if (value === null || value === undefined || Number.isNaN(Number(value))) {
    return "-"
  }
  return Number(value).toLocaleString()
}

function formatDateTime(value) {
  if (!value) return "-"
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return String(value)
  return date.toLocaleString()
}

function summarizeRuns(runs) {
  const summary = {
    total: 0,
    byStatus: {},
    latestTriggeredAt: null,
  }

  if (!Array.isArray(runs)) return summary

  runs.forEach((run) => {
    summary.total += 1
    const status = String(run?.status || "unknown").toLowerCase()
    summary.byStatus[status] = (summary.byStatus[status] || 0) + 1

    const triggeredAt = run?.triggered_at ? new Date(run.triggered_at) : null
    if (triggeredAt && !Number.isNaN(triggeredAt.getTime())) {
      if (!summary.latestTriggeredAt || triggeredAt > summary.latestTriggeredAt) {
        summary.latestTriggeredAt = triggeredAt
      }
    }
  })

  return summary
}

function statusLabel(status) {
  const normalized = String(status || "unknown").toLowerCase()
  const map = {
    healthy: "健康",
    degraded: "降级",
    error: "异常",
    unknown: "未知",
    queued: "排队中",
    running: "运行中",
    completed: "已完成",
    failed: "失败",
    cancelled: "已取消",
    accepted: "已接受",
    rejected: "已拒绝",
  }
  return map[normalized] || normalized
}

function statusTone(status) {
  const normalized = String(status || "").toLowerCase()
  if (["healthy", "completed", "success", "enabled"].includes(normalized)) return "success"
  if (["degraded", "queued", "pending"].includes(normalized)) return "warning"
  if (["running", "active"].includes(normalized)) return "info"
  if (["failed", "error", "rejected", "cancelled", "unhealthy"].includes(normalized)) return "danger"
  return "neutral"
}

function createStatusChip(status, count) {
  const item = document.createElement("li")
  item.className = "ui2-status-list__item"

  const chip = document.createElement("span")
  chip.className = `ui2-chip ui2-chip--${statusTone(status)}`
  chip.textContent = statusLabel(status)

  const value = document.createElement("strong")
  value.className = "ui2-status-list__value"
  value.textContent = formatNumber(count)

  item.append(chip, value)
  return item
}

function setText(root, selector, value) {
  const target = root.querySelector(selector)
  if (!target) return
  target.textContent = value
}

function renderLoginStateList(container, loginState = {}) {
  container.innerHTML = ""

  const entries = Object.entries(loginState || {})
  if (entries.length === 0) {
    const item = document.createElement("li")
    item.className = "ui2-meta-list__item"
    item.textContent = "暂无鉴权状态"
    container.appendChild(item)
    return
  }

  entries.forEach(([platform, snapshot]) => {
    const item = document.createElement("li")
    item.className = "ui2-meta-list__item"

    const label = document.createElement("span")
    label.className = "ui2-meta-list__label"
    label.textContent = platform.toUpperCase()

    const chip = document.createElement("span")
    const status = snapshot?.ok ? "healthy" : "failed"
    chip.className = `ui2-chip ui2-chip--${statusTone(status)}`
    chip.textContent = snapshot?.ok ? "已登录" : "未登录"

    item.append(label, chip)
    container.appendChild(item)
  })
}

function renderTaskIdList(container, ids = []) {
  container.innerHTML = ""
  if (!Array.isArray(ids) || ids.length === 0) {
    const empty = document.createElement("span")
    empty.className = "ui2-muted"
    empty.textContent = "无"
    container.appendChild(empty)
    return
  }

  ids.forEach((taskId) => {
    const tag = document.createElement("span")
    tag.className = "ui2-tag"
    tag.textContent = String(taskId)
    container.appendChild(tag)
  })
}

function renderAnomalyList(container, anomalies = []) {
  container.innerHTML = ""

  if (!Array.isArray(anomalies) || anomalies.length === 0) {
    const empty = document.createElement("li")
    empty.className = "ui2-anomaly-list__item ui2-muted"
    empty.textContent = "暂无 warning / error 日志"
    container.appendChild(empty)
    return
  }

  anomalies.forEach((entry) => {
    const item = document.createElement("li")
    item.className = "ui2-anomaly-list__item"

    const meta = document.createElement("p")
    meta.className = "ui2-anomaly-list__meta"

    const levelChip = document.createElement("span")
    levelChip.className = `ui2-chip ui2-chip--${statusTone(entry?.level || "warning")}`
    levelChip.textContent = String(entry?.level || "unknown")
    meta.appendChild(levelChip)

    const timeNode = document.createElement("span")
    timeNode.textContent = formatDateTime(entry?.timestamp || entry?.time || entry?.created_at)
    meta.appendChild(timeNode)

    if (entry?.task_id) {
      const taskNode = document.createElement("span")
      taskNode.textContent = `task=${entry.task_id}`
      meta.appendChild(taskNode)
    }
    if (entry?.run_id !== undefined && entry?.run_id !== null) {
      const runNode = document.createElement("span")
      runNode.textContent = `run=${entry.run_id}`
      meta.appendChild(runNode)
    }

    const messageNode = document.createElement("p")
    messageNode.className = "ui2-anomaly-list__message"
    messageNode.textContent = String(entry?.message || "(empty)")

    item.append(meta, messageNode)
    container.appendChild(item)
  })
}

function buildRunsJumpHash(runs = []) {
  const params = new URLSearchParams()
  params.set("status", "failed")
  params.set("limit", String(DEFAULT_RUN_LIMIT))

  if (!Array.isArray(runs) || runs.length === 0) {
    return `#/runs?${params.toString()}`
  }

  const failedRuns = runs.filter((run) => String(run?.status || "").toLowerCase() === "failed")
  if (failedRuns.length === 0) {
    return `#/runs?${params.toString()}`
  }

  const latestFailedRun = failedRuns.reduce((latest, current) => {
    const latestAt = Date.parse(String(latest?.triggered_at || ""))
    const currentAt = Date.parse(String(current?.triggered_at || ""))

    if (Number.isFinite(currentAt) && (!Number.isFinite(latestAt) || currentAt > latestAt)) {
      return current
    }

    if (!Number.isFinite(latestAt) && !Number.isFinite(currentAt)) {
      const latestRunId = Number(latest?.run_id || 0)
      const currentRunId = Number(current?.run_id || 0)
      if (currentRunId > latestRunId) {
        return current
      }
    }

    return latest
  }, failedRuns[0])

  const platform = String(latestFailedRun?.platform || "").trim().toLowerCase()
  if (platform) {
    params.set("platform", platform)
  }

  const triggeredAt = Date.parse(String(latestFailedRun?.triggered_at || ""))
  if (Number.isFinite(triggeredAt)) {
    const to = new Date(triggeredAt)
    const from = new Date(triggeredAt - 24 * 60 * 60 * 1000)
    params.set("from", from.toISOString())
    params.set("to", to.toISOString())
  }

  return `#/runs?${params.toString()}`
}

export function createDashboardPage(options = {}) {
  ensurePageStyle()
  const request = createRequest(options)
  const state = {
    loading: false,
    jobs: [],
    runs: [],
    anomalies: [],
    runtime: null,
    error: "",
    refreshTimer: null,
    lastUpdatedAt: "",
  }

  const root = document.createElement("section")
  root.className = "ui2-page ui2-dashboard"
  root.innerHTML = `
    <header class="ui2-page__header">
      <div class="ui2-page__header-main">
        <p class="ui2-page__eyebrow">System Overview</p>
        <h2>Dashboard</h2>
        <p class="ui2-page__description ui2-muted">任务、运行队列与健康状态总览</p>
      </div>
      <div class="ui2-page__header-actions">
        <button type="button" class="ui2-btn" data-action="refresh">刷新</button>
      </div>
    </header>

    <p class="ui2-page__hint ui2-page__hint--pill" data-role="updated-at">最近更新：-</p>
    <p class="ui2-page__error" data-role="error" hidden></p>

    <div class="ui2-card-grid ui2-card-grid--4">
      <article class="ui2-card ui2-card--metric">
        <h3 class="ui2-card__title">任务数</h3>
        <p class="ui2-card__value" data-role="jobs-total">-</p>
        <p class="ui2-card__meta" data-role="jobs-meta">-</p>
      </article>

      <article class="ui2-card ui2-card--metric">
        <h3 class="ui2-card__title">运行数</h3>
        <p class="ui2-card__value" data-role="runs-total">-</p>
        <p class="ui2-card__meta" data-role="runs-meta">-</p>
      </article>

      <article class="ui2-card ui2-card--metric">
        <h3 class="ui2-card__title">队列状态</h3>
        <p class="ui2-card__value" data-role="queue-main">-</p>
        <p class="ui2-card__meta" data-role="queue-meta">-</p>
      </article>

      <article class="ui2-card ui2-card--metric">
        <h3 class="ui2-card__title">健康状态</h3>
        <p class="ui2-card__value" data-role="health-main">-</p>
        <p class="ui2-card__meta" data-role="health-meta">-</p>
      </article>
    </div>

    <div class="ui2-panel-grid ui2-panel-grid--2">
      <section class="ui2-panel">
        <div class="ui2-panel__header">
          <h3>运行状态分布（最近 ${DEFAULT_RUN_LIMIT} 条）</h3>
        </div>
        <ul class="ui2-status-list" data-role="runs-status-list"></ul>
      </section>

      <section class="ui2-panel">
        <div class="ui2-panel__header">
          <h3>运行时详情</h3>
        </div>
        <div class="ui2-metric-grid">
          <div class="ui2-metric">
            <span class="ui2-muted">Queue</span>
            <strong data-role="queue-status">-</strong>
          </div>
          <div class="ui2-metric">
            <span class="ui2-muted">Energy</span>
            <strong data-role="energy-status">-</strong>
          </div>
        </div>
        <h4 class="ui2-subtitle">登录态</h4>
        <ul class="ui2-meta-list" data-role="login-list"></ul>
        <h4 class="ui2-subtitle">活跃任务</h4>
        <div class="ui2-tags" data-role="active-task-ids"></div>
      </section>
    </div>

    <section class="ui2-panel">
      <div class="ui2-panel__header">
        <h3>最新异常日志（warning / error）</h3>
        <button type="button" class="ui2-btn ui2-btn--ghost" data-action="jump-runs">前往 Run Center</button>
      </div>
      <ul class="ui2-anomaly-list" data-role="anomaly-list"></ul>
    </section>
  `

  const refreshButton = root.querySelector('[data-action="refresh"]')
  const jumpRunsButton = root.querySelector('[data-action="jump-runs"]')
  const errorNode = root.querySelector('[data-role="error"]')

  const cleanups = []

  function setLoading(isLoading) {
    state.loading = isLoading
    if (refreshButton) {
      refreshButton.disabled = isLoading
      refreshButton.textContent = isLoading ? "刷新中..." : "刷新"
    }
  }

  function setError(message) {
    state.error = message || ""
    if (!errorNode) return
    if (!state.error) {
      errorNode.hidden = true
      errorNode.textContent = ""
      return
    }
    errorNode.hidden = false
    errorNode.textContent = state.error
  }

  function render() {
    const jobs = Array.isArray(state.jobs) ? state.jobs : []
    const enabledJobs = jobs.filter((item) => item?.enabled).length

    setText(root, '[data-role="jobs-total"]', formatNumber(jobs.length))
    setText(root, '[data-role="jobs-meta"]', `启用 ${formatNumber(enabledJobs)} / 停用 ${formatNumber(jobs.length - enabledJobs)}`)

    const runSummary = summarizeRuns(state.runs)
    const completed = runSummary.byStatus.completed || 0
    const failed = runSummary.byStatus.failed || 0

    setText(root, '[data-role="runs-total"]', formatNumber(runSummary.total))
    setText(root, '[data-role="runs-meta"]', `完成 ${formatNumber(completed)} / 失败 ${formatNumber(failed)}`)

    const runtime = state.runtime || {}
    const queue = runtime.crawler_queue || {}
    const runningWorkers = Number(queue.running_workers || 0)
    const totalWorkers = Number(queue.total_workers || 0)
    const queuedTasks = Number(queue.queued_tasks || 0)

    setText(root, '[data-role="queue-main"]', `${formatNumber(runningWorkers)}/${formatNumber(totalWorkers)} workers`)
    setText(root, '[data-role="queue-meta"]', `排队 ${formatNumber(queuedTasks)} · 状态 ${statusLabel(queue.status || "unknown")}`)

    const healthStatus = runtime.overall_status || "unknown"
    setText(root, '[data-role="health-main"]', statusLabel(healthStatus))
    const checkedAt = runtime.checked_at ? formatDateTime(runtime.checked_at) : "-"
    setText(root, '[data-role="health-meta"]', `最近检测：${checkedAt}`)

    setText(root, '[data-role="queue-status"]', statusLabel(queue.status || "unknown"))
    setText(
      root,
      '[data-role="energy-status"]',
      runtime.energy?.ok ? "可达" : runtime.energy?.message || "不可达"
    )

    const runsStatusList = root.querySelector('[data-role="runs-status-list"]')
    if (runsStatusList) {
      runsStatusList.innerHTML = ""
      const entries = Object.entries(runSummary.byStatus)
        .sort((a, b) => b[1] - a[1])
        .slice(0, 8)

      if (entries.length === 0) {
        const empty = document.createElement("li")
        empty.className = "ui2-status-list__item ui2-muted"
        empty.textContent = "暂无运行数据"
        runsStatusList.appendChild(empty)
      } else {
        entries.forEach(([status, count]) => {
          runsStatusList.appendChild(createStatusChip(status, count))
        })
      }
    }

    const loginList = root.querySelector('[data-role="login-list"]')
    if (loginList) {
      renderLoginStateList(loginList, runtime.login)
    }

    const activeTaskIdsNode = root.querySelector('[data-role="active-task-ids"]')
    if (activeTaskIdsNode) {
      renderTaskIdList(activeTaskIdsNode, queue.active_task_ids || [])
    }

    const anomalyListNode = root.querySelector('[data-role="anomaly-list"]')
    if (anomalyListNode) {
      renderAnomalyList(anomalyListNode, state.anomalies)
    }

    setText(
      root,
      '[data-role="updated-at"]',
      `最近更新：${state.lastUpdatedAt ? formatDateTime(state.lastUpdatedAt) : "-"}`
    )
  }

  async function refreshData({ silent = false } = {}) {
    if (!silent) setLoading(true)
    setError("")

    try {
      const [jobsData, runsData, runtimeData, anomalyData] = await Promise.all([
        request("/api/scheduler/jobs"),
        request("/api/scheduler/runs", { params: { limit: DEFAULT_RUN_LIMIT } }),
        request("/api/health/runtime"),
        request("/api/crawler/logs", {
          params: {
            limit: DEFAULT_ANOMALY_LIMIT,
            level: "warning,error",
          },
        }),
      ])

      state.jobs = Array.isArray(jobsData?.jobs) ? jobsData.jobs : []
      state.runs = Array.isArray(runsData?.runs) ? runsData.runs : []
      state.runtime = runtimeData || {}
      state.anomalies = Array.isArray(anomalyData?.logs) ? anomalyData.logs : []
      state.lastUpdatedAt = new Date().toISOString()
      render()
    } catch (error) {
      setError(`Dashboard 加载失败：${error?.message || "unknown error"}`)
    } finally {
      if (!silent) setLoading(false)
    }
  }

  function startAutoRefresh() {
    if (state.refreshTimer) return
    const intervalMs = Number(options.refreshIntervalMs || DEFAULT_REFRESH_INTERVAL_MS)
    if (!Number.isFinite(intervalMs) || intervalMs <= 0) return

    state.refreshTimer = window.setInterval(() => {
      refreshData({ silent: true }).catch(() => {})
    }, intervalMs)
  }

  function stopAutoRefresh() {
    if (!state.refreshTimer) return
    window.clearInterval(state.refreshTimer)
    state.refreshTimer = null
  }

  if (refreshButton) {
    const onRefreshClick = () => {
      refreshData().catch(() => {})
    }
    refreshButton.addEventListener("click", onRefreshClick)
    cleanups.push(() => refreshButton.removeEventListener("click", onRefreshClick))
  }

  if (jumpRunsButton) {
    const onJumpRunsClick = () => {
      if (typeof window !== "undefined") {
        window.location.hash = buildRunsJumpHash(state.runs)
        return
      }
      if (typeof options.navigate === "function") {
        options.navigate("runs")
      }
    }
    jumpRunsButton.addEventListener("click", onJumpRunsClick)
    cleanups.push(() => jumpRunsButton.removeEventListener("click", onJumpRunsClick))
  }

  if (options.autoRefresh !== false && typeof window !== "undefined") {
    startAutoRefresh()
  }

  if (options.autoLoad !== false) {
    refreshData().catch(() => {})
  }

  return {
    id: "dashboard",
    title: "Dashboard",
    root,
    refresh: refreshData,
    destroy() {
      stopAutoRefresh()
      cleanups.forEach((runCleanup) => runCleanup())
      cleanups.length = 0
    },
  }
}

export function mountDashboardPage(container, options = {}) {
  if (!container || typeof container.appendChild !== "function") {
    throw new Error("mountDashboardPage requires a valid container element")
  }

  const page = createDashboardPage(options)
  container.innerHTML = ""
  container.appendChild(page.root)
  return page
}

export default {
  id: "dashboard",
  title: "Dashboard",
  create: createDashboardPage,
  mount: mountDashboardPage,
}
