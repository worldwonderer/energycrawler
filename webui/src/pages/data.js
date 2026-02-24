const DEFAULT_PAGE_SIZE = 20
const DEFAULT_PREVIEW_LIMIT = 30
const DEFAULT_SORT_BY = "modified_at"
const DEFAULT_SORT_ORDER = "desc"
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

function parseHashQueryParams() {
  if (typeof window === "undefined") return new URLSearchParams()
  const hash = String(window.location.hash || "")
  const queryIndex = hash.indexOf("?")
  if (queryIndex < 0) return new URLSearchParams()
  return new URLSearchParams(hash.slice(queryIndex + 1))
}

function parsePositiveInteger(value, fallback) {
  const parsed = Number(value)
  if (!Number.isInteger(parsed) || parsed <= 0) return fallback
  return parsed
}

function normalizeDateInput(value) {
  const raw = String(value || "").trim()
  if (!raw) return ""
  if (/^\d{4}-\d{2}-\d{2}$/.test(raw)) return raw

  const date = new Date(raw)
  if (Number.isNaN(date.getTime())) return ""

  const yyyy = String(date.getFullYear()).padStart(4, "0")
  const mm = String(date.getMonth() + 1).padStart(2, "0")
  const dd = String(date.getDate()).padStart(2, "0")
  return `${yyyy}-${mm}-${dd}`
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
  if (value === null || value === undefined || Number.isNaN(Number(value))) return "-"
  return Number(value).toLocaleString()
}

function formatBytes(value) {
  const size = Number(value)
  if (!Number.isFinite(size) || size < 0) return "-"
  if (size < 1024) return `${size} B`

  const units = ["KB", "MB", "GB", "TB"]
  let current = size / 1024
  let index = 0
  while (current >= 1024 && index < units.length - 1) {
    current /= 1024
    index += 1
  }
  return `${current.toFixed(current >= 100 ? 0 : 1)} ${units[index]}`
}

function formatDateTime(value) {
  if (!value && value !== 0) return "-"
  const date = new Date(Number.isFinite(Number(value)) ? Number(value) * 1000 : value)
  if (Number.isNaN(date.getTime())) return String(value)
  return date.toLocaleString()
}

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;")
}

function normalizeRows(rawData) {
  if (Array.isArray(rawData)) return rawData
  if (rawData && typeof rawData === "object") return [rawData]
  return []
}

function extractColumns(rows, preferredColumns = []) {
  if (Array.isArray(preferredColumns) && preferredColumns.length > 0) {
    return preferredColumns
  }

  const columns = new Set()
  rows.forEach((row) => {
    if (!row || typeof row !== "object") return
    Object.keys(row).forEach((key) => columns.add(key))
  })
  return Array.from(columns)
}

function encodeFilePath(filePath) {
  return String(filePath || "")
    .split("/")
    .map((segment) => encodeURIComponent(segment))
    .join("/")
}

function setNodeText(root, selector, value) {
  const node = root.querySelector(selector)
  if (!node) return
  node.textContent = value
}

function setError(root, selector, message) {
  const node = root.querySelector(selector)
  if (!node) return

  if (!message) {
    node.hidden = true
    node.textContent = ""
    return
  }

  node.hidden = false
  node.textContent = message
}

function setFormControlValue(form, name, value) {
  if (!form || !form.elements) return
  const control = form.elements[name]
  if (!control || value === undefined || value === null) return
  control.value = String(value)
}

function renderSummaryList(container, entries, { keyFormatter, valueFormatter } = {}) {
  container.innerHTML = ""
  if (!entries || entries.length === 0) {
    const row = document.createElement("tr")
    row.innerHTML = `<td colspan="2" class="ui2-muted">暂无数据</td>`
    container.appendChild(row)
    return
  }

  entries.forEach(([key, value]) => {
    const row = document.createElement("tr")

    const keyCell = document.createElement("td")
    keyCell.textContent = keyFormatter ? keyFormatter(key) : String(key)

    const valueCell = document.createElement("td")
    valueCell.textContent = valueFormatter ? valueFormatter(value) : formatNumber(value)

    row.append(keyCell, valueCell)
    container.appendChild(row)
  })
}

export function createDataPage(options = {}) {
  ensurePageStyle()
  const request = createRequest(options)

  const state = {
    filesQuery: {
      platform: "",
      fileType: "",
      page: 1,
      pageSize: DEFAULT_PAGE_SIZE,
      sortBy: DEFAULT_SORT_BY,
      sortOrder: DEFAULT_SORT_ORDER,
    },
    latestQuery: {
      platform: "",
      fileType: "",
      limit: DEFAULT_PREVIEW_LIMIT,
    },
    statsQuery: {
      platform: "",
      from: "",
      to: "",
    },
    filesResult: {
      files: [],
      page: 1,
      pageSize: DEFAULT_PAGE_SIZE,
      total: 0,
      totalPages: 0,
      sortBy: DEFAULT_SORT_BY,
      sortOrder: DEFAULT_SORT_ORDER,
    },
    latestResult: {
      file: null,
      rows: [],
      columns: [],
      total: 0,
    },
    statsResult: {
      total_files: 0,
      total_size: 0,
      by_platform: {},
      by_type: {},
      by_date: {},
    },
    loading: {
      files: false,
      latest: false,
      stats: false,
    },
    lastUpdatedAt: "",
  }

  const root = document.createElement("section")
  root.className = "ui2-page ui2-data"
  root.innerHTML = `
    <header class="ui2-page__header">
      <div class="ui2-page__header-main">
        <p class="ui2-page__eyebrow">Data Hub</p>
        <h2>Data Explorer</h2>
        <p class="ui2-page__description ui2-muted">文件分页排序、Latest 预览与数据统计过滤</p>
      </div>
      <div class="ui2-page__header-actions">
        <button type="button" class="ui2-btn" data-action="refresh-all">刷新全部</button>
      </div>
    </header>

    <p class="ui2-page__hint ui2-page__hint--pill" data-role="updated-at">最近更新：-</p>

    <section class="ui2-panel ui2-data__section">
      <div class="ui2-panel__header">
        <h3>Files（分页 + 排序）</h3>
      </div>
      <form class="ui2-form ui2-form--inline" data-form="files">
        <label>
          Platform
          <select name="platform">
            <option value="">全部</option>
            <option value="x">X</option>
            <option value="xhs">XHS</option>
          </select>
        </label>

        <label>
          Type
          <select name="file_type">
            <option value="">全部</option>
            <option value="json">JSON</option>
            <option value="csv">CSV</option>
            <option value="xlsx">XLSX</option>
            <option value="xls">XLS</option>
          </select>
        </label>

        <label>
          Page Size
          <select name="page_size">
            <option value="10">10</option>
            <option value="20" selected>20</option>
            <option value="50">50</option>
            <option value="100">100</option>
          </select>
        </label>

        <label>
          Sort By
          <select name="sort_by">
            <option value="modified_at" selected>modified_at</option>
            <option value="name">name</option>
            <option value="size">size</option>
            <option value="type">type</option>
            <option value="record_count">record_count</option>
          </select>
        </label>

        <label>
          Order
          <select name="sort_order">
            <option value="desc" selected>DESC</option>
            <option value="asc">ASC</option>
          </select>
        </label>

        <button type="submit" class="ui2-btn">查询</button>
      </form>
      <p class="ui2-page__error" data-role="files-error" hidden></p>

      <div class="ui2-table-wrap">
        <table class="ui2-table ui2-table--files">
          <thead>
            <tr>
              <th>name</th>
              <th>path</th>
              <th>type</th>
              <th>size</th>
              <th>records</th>
              <th>modified_at</th>
              <th>download</th>
            </tr>
          </thead>
          <tbody data-role="files-body"></tbody>
        </table>
      </div>

      <div class="ui2-pagination">
        <button type="button" class="ui2-btn ui2-btn--ghost" data-action="files-prev">上一页</button>
        <span data-role="files-page-meta">第 - / - 页</span>
        <button type="button" class="ui2-btn ui2-btn--ghost" data-action="files-next">下一页</button>
      </div>
    </section>

    <section class="ui2-panel ui2-data__section">
      <div class="ui2-panel__header">
        <h3>Latest 预览</h3>
      </div>
      <form class="ui2-form ui2-form--inline" data-form="latest">
        <label>
          Platform
          <select name="platform">
            <option value="">全部</option>
            <option value="x">X</option>
            <option value="xhs">XHS</option>
          </select>
        </label>

        <label>
          Type
          <select name="file_type">
            <option value="">全部</option>
            <option value="json">JSON</option>
            <option value="csv">CSV</option>
            <option value="xlsx">XLSX</option>
            <option value="xls">XLS</option>
          </select>
        </label>

        <label>
          Limit
          <input type="number" min="1" max="500" name="limit" value="${DEFAULT_PREVIEW_LIMIT}" />
        </label>

        <button type="submit" class="ui2-btn">预览</button>
      </form>
      <p class="ui2-page__error" data-role="latest-error" hidden></p>

      <pre class="ui2-code-block" data-role="latest-meta">{}</pre>

      <div class="ui2-table-wrap">
        <table class="ui2-table ui2-table--compact ui2-table--preview">
          <thead data-role="latest-head"></thead>
          <tbody data-role="latest-body"></tbody>
        </table>
      </div>
    </section>

    <section class="ui2-panel ui2-data__section">
      <div class="ui2-panel__header">
        <h3>Stats（平台 + 日期范围过滤）</h3>
      </div>

      <form class="ui2-form ui2-form--inline" data-form="stats">
        <label>
          Platform
          <select name="platform">
            <option value="">全部</option>
            <option value="x">X</option>
            <option value="xhs">XHS</option>
          </select>
        </label>

        <label>
          From
          <input type="date" name="from" />
        </label>

        <label>
          To
          <input type="date" name="to" />
        </label>

        <button type="submit" class="ui2-btn">统计</button>
        <button type="button" class="ui2-btn ui2-btn--ghost" data-action="stats-reset">重置</button>
      </form>

      <p class="ui2-page__error" data-role="stats-error" hidden></p>

      <div class="ui2-card-grid ui2-card-grid--2">
        <article class="ui2-card ui2-card--metric">
          <h4 class="ui2-card__title">总文件数</h4>
          <p class="ui2-card__value" data-role="stats-total-files">-</p>
        </article>
        <article class="ui2-card ui2-card--metric">
          <h4 class="ui2-card__title">总大小</h4>
          <p class="ui2-card__value" data-role="stats-total-size">-</p>
        </article>
      </div>

      <div class="ui2-panel-grid ui2-panel-grid--3">
        <div class="ui2-mini-panel">
          <h4>by_platform</h4>
          <table class="ui2-table ui2-table--compact">
            <tbody data-role="stats-platform-body"></tbody>
          </table>
        </div>
        <div class="ui2-mini-panel">
          <h4>by_type</h4>
          <table class="ui2-table ui2-table--compact">
            <tbody data-role="stats-type-body"></tbody>
          </table>
        </div>
        <div class="ui2-mini-panel">
          <h4>by_date</h4>
          <table class="ui2-table ui2-table--compact">
            <tbody data-role="stats-date-body"></tbody>
          </table>
        </div>
      </div>
    </section>
  `

  const filesForm = root.querySelector('[data-form="files"]')
  const latestForm = root.querySelector('[data-form="latest"]')
  const statsForm = root.querySelector('[data-form="stats"]')

  const refreshAllButton = root.querySelector('[data-action="refresh-all"]')
  const filesPrevButton = root.querySelector('[data-action="files-prev"]')
  const filesNextButton = root.querySelector('[data-action="files-next"]')
  const statsResetButton = root.querySelector('[data-action="stats-reset"]')

  const cleanups = []

  function applyFiltersFromHash() {
    const params = parseHashQueryParams()
    if (!params || Array.from(params.keys()).length === 0) return

    const platform = String(params.get("platform") || "").trim().toLowerCase()
    const fileType = String(params.get("file_type") || params.get("type") || "")
      .trim()
      .toLowerCase()
    const page = parsePositiveInteger(params.get("page"), state.filesQuery.page)
    const pageSize = parsePositiveInteger(params.get("page_size"), state.filesQuery.pageSize)
    const sortBy = String(params.get("sort_by") || "").trim()
    const sortOrder = String(params.get("sort_order") || "").trim().toLowerCase()
    const latestLimit = parsePositiveInteger(params.get("limit"), state.latestQuery.limit)
    const from = normalizeDateInput(params.get("from"))
    const to = normalizeDateInput(params.get("to"))

    if (platform) {
      state.filesQuery.platform = platform
      state.latestQuery.platform = platform
      state.statsQuery.platform = platform
    }

    if (fileType) {
      state.filesQuery.fileType = fileType
      state.latestQuery.fileType = fileType
    }

    state.filesQuery.page = page
    state.filesQuery.pageSize = pageSize
    if (sortBy) state.filesQuery.sortBy = sortBy
    if (sortOrder === "asc" || sortOrder === "desc") {
      state.filesQuery.sortOrder = sortOrder
    }
    state.latestQuery.limit = Math.min(500, Math.max(1, latestLimit))

    if (from) state.statsQuery.from = from
    if (to) state.statsQuery.to = to

    setFormControlValue(filesForm, "platform", state.filesQuery.platform)
    setFormControlValue(filesForm, "file_type", state.filesQuery.fileType)
    setFormControlValue(filesForm, "page_size", state.filesQuery.pageSize)
    setFormControlValue(filesForm, "sort_by", state.filesQuery.sortBy)
    setFormControlValue(filesForm, "sort_order", state.filesQuery.sortOrder)

    setFormControlValue(latestForm, "platform", state.latestQuery.platform)
    setFormControlValue(latestForm, "file_type", state.latestQuery.fileType)
    setFormControlValue(latestForm, "limit", state.latestQuery.limit)

    setFormControlValue(statsForm, "platform", state.statsQuery.platform)
    setFormControlValue(statsForm, "from", state.statsQuery.from)
    setFormControlValue(statsForm, "to", state.statsQuery.to)
  }

  function setLoading(section, isLoading) {
    state.loading[section] = isLoading
    const anyLoading = Object.values(state.loading).some(Boolean)

    if (refreshAllButton) {
      refreshAllButton.disabled = anyLoading
      refreshAllButton.textContent = anyLoading ? "刷新中..." : "刷新全部"
    }
  }

  function refreshUpdatedAt() {
    setNodeText(
      root,
      '[data-role="updated-at"]',
      `最近更新：${state.lastUpdatedAt ? new Date(state.lastUpdatedAt).toLocaleString() : "-"}`
    )
  }

  function renderFilesTable() {
    const tbody = root.querySelector('[data-role="files-body"]')
    if (!tbody) return

    tbody.innerHTML = ""
    const files = state.filesResult.files || []
    if (files.length === 0) {
      const empty = document.createElement("tr")
      empty.innerHTML = `<td colspan="7" class="ui2-muted">暂无文件</td>`
      tbody.appendChild(empty)
    } else {
      const apiBase = resolveApiBase(options)
      files.forEach((file) => {
        const row = document.createElement("tr")
        const encodedPath = encodeFilePath(file.path)
        const downloadUrl = buildUrl({
          apiBase,
          path: `/api/data/download/${encodedPath}`,
        })

        row.innerHTML = `
          <td>${escapeHtml(file.name)}</td>
          <td class="ui2-table__path">${escapeHtml(file.path)}</td>
          <td>${escapeHtml(file.type || "-")}</td>
          <td>${escapeHtml(formatBytes(file.size))}</td>
          <td>${escapeHtml(formatNumber(file.record_count ?? 0))}</td>
          <td>${escapeHtml(formatDateTime(file.modified_at))}</td>
          <td><a class="ui2-link" href="${downloadUrl}" target="_blank" rel="noopener noreferrer">下载</a></td>
        `
        tbody.appendChild(row)
      })
    }

    const currentPage = Number(state.filesResult.page || 1)
    const totalPages = Number(state.filesResult.totalPages || 0)
    const total = Number(state.filesResult.total || 0)

    setNodeText(
      root,
      '[data-role="files-page-meta"]',
      `第 ${formatNumber(currentPage)} / ${formatNumber(totalPages || 1)} 页 · 共 ${formatNumber(total)} 个文件`
    )

    if (filesPrevButton) filesPrevButton.disabled = currentPage <= 1
    if (filesNextButton) filesNextButton.disabled = totalPages === 0 || currentPage >= totalPages
  }

  function renderLatestPreview() {
    const head = root.querySelector('[data-role="latest-head"]')
    const body = root.querySelector('[data-role="latest-body"]')
    const meta = root.querySelector('[data-role="latest-meta"]')
    if (!head || !body || !meta) return

    head.innerHTML = ""
    body.innerHTML = ""

    const { file, rows, columns, total } = state.latestResult
    meta.textContent = JSON.stringify(
      {
        file,
        total,
        shown: rows.length,
      },
      null,
      2
    )

    if (rows.length === 0 || columns.length === 0) {
      head.innerHTML = "<tr><th>提示</th></tr>"
      body.innerHTML = '<tr><td class="ui2-muted">暂无可预览数据</td></tr>'
      return
    }

    const headRow = document.createElement("tr")
    columns.forEach((column) => {
      const th = document.createElement("th")
      th.textContent = column
      headRow.appendChild(th)
    })
    head.appendChild(headRow)

    rows.forEach((row) => {
      const tr = document.createElement("tr")
      columns.forEach((column) => {
        const td = document.createElement("td")
        const value = row?.[column]
        if (value === null || value === undefined) {
          td.textContent = ""
        } else if (typeof value === "object") {
          td.textContent = JSON.stringify(value)
        } else {
          td.textContent = String(value)
        }
        tr.appendChild(td)
      })
      body.appendChild(tr)
    })
  }

  function renderStats() {
    const stats = state.statsResult

    setNodeText(root, '[data-role="stats-total-files"]', formatNumber(stats.total_files || 0))
    setNodeText(root, '[data-role="stats-total-size"]', formatBytes(stats.total_size || 0))

    const platformBody = root.querySelector('[data-role="stats-platform-body"]')
    const typeBody = root.querySelector('[data-role="stats-type-body"]')
    const dateBody = root.querySelector('[data-role="stats-date-body"]')

    if (platformBody) {
      const platformEntries = Object.entries(stats.by_platform || {}).sort((a, b) =>
        String(a[0]).localeCompare(String(b[0]))
      )
      renderSummaryList(platformBody, platformEntries, {
        keyFormatter: (key) => key.toUpperCase(),
      })
    }

    if (typeBody) {
      const typeEntries = Object.entries(stats.by_type || {}).sort((a, b) =>
        String(a[0]).localeCompare(String(b[0]))
      )
      renderSummaryList(typeBody, typeEntries, {
        keyFormatter: (key) => key.toLowerCase(),
      })
    }

    if (dateBody) {
      const dateEntries = Object.entries(stats.by_date || {}).sort((a, b) =>
        String(b[0]).localeCompare(String(a[0]))
      )
      renderSummaryList(dateBody, dateEntries)
    }
  }

  async function loadFiles() {
    setLoading("files", true)
    setError(root, '[data-role="files-error"]', "")

    try {
      const data = await request("/api/data/files", {
        params: {
          platform: state.filesQuery.platform || undefined,
          file_type: state.filesQuery.fileType || undefined,
          page: state.filesQuery.page,
          page_size: state.filesQuery.pageSize,
          sort_by: state.filesQuery.sortBy,
          sort_order: state.filesQuery.sortOrder,
        },
      })

      state.filesResult = {
        files: Array.isArray(data?.files) ? data.files : [],
        page: Number(data?.page || state.filesQuery.page || 1),
        pageSize: Number(data?.page_size || state.filesQuery.pageSize || DEFAULT_PAGE_SIZE),
        total: Number(data?.total || 0),
        totalPages: Number(data?.total_pages || 0),
        sortBy: data?.sort_by || state.filesQuery.sortBy,
        sortOrder: data?.sort_order || state.filesQuery.sortOrder,
      }

      state.lastUpdatedAt = new Date().toISOString()
      renderFilesTable()
      refreshUpdatedAt()
    } catch (error) {
      setError(root, '[data-role="files-error"]', `Files 查询失败：${error?.message || "unknown error"}`)
    } finally {
      setLoading("files", false)
    }
  }

  async function loadLatest() {
    setLoading("latest", true)
    setError(root, '[data-role="latest-error"]', "")

    try {
      const data = await request("/api/data/latest", {
        params: {
          platform: state.latestQuery.platform || undefined,
          file_type: state.latestQuery.fileType || undefined,
          preview: true,
          limit: state.latestQuery.limit,
        },
      })

      const rows = normalizeRows(data?.data)
      const columns = extractColumns(rows, data?.columns)

      state.latestResult = {
        file: data?.file || null,
        rows,
        columns,
        total: Number(data?.total || rows.length),
      }
      state.lastUpdatedAt = new Date().toISOString()
      renderLatestPreview()
      refreshUpdatedAt()
    } catch (error) {
      setError(root, '[data-role="latest-error"]', `Latest 预览失败：${error?.message || "unknown error"}`)
    } finally {
      setLoading("latest", false)
    }
  }

  async function loadStats() {
    setLoading("stats", true)
    setError(root, '[data-role="stats-error"]', "")

    try {
      const data = await request("/api/data/stats", {
        params: {
          platform: state.statsQuery.platform || undefined,
          from: state.statsQuery.from || undefined,
          to: state.statsQuery.to || undefined,
        },
      })

      state.statsResult = {
        total_files: Number(data?.total_files || 0),
        total_size: Number(data?.total_size || 0),
        by_platform: data?.by_platform || {},
        by_type: data?.by_type || {},
        by_date: data?.by_date || {},
      }
      state.lastUpdatedAt = new Date().toISOString()
      renderStats()
      refreshUpdatedAt()
    } catch (error) {
      setError(root, '[data-role="stats-error"]', `Stats 查询失败：${error?.message || "unknown error"}`)
    } finally {
      setLoading("stats", false)
    }
  }

  async function refreshAll() {
    await Promise.all([loadFiles(), loadLatest(), loadStats()])
  }

  if (filesForm) {
    const onFilesSubmit = (event) => {
      event.preventDefault()
      const formData = new FormData(filesForm)
      state.filesQuery.platform = String(formData.get("platform") || "")
      state.filesQuery.fileType = String(formData.get("file_type") || "")
      state.filesQuery.pageSize = Number(formData.get("page_size") || DEFAULT_PAGE_SIZE)
      state.filesQuery.sortBy = String(formData.get("sort_by") || DEFAULT_SORT_BY)
      state.filesQuery.sortOrder = String(formData.get("sort_order") || DEFAULT_SORT_ORDER)
      state.filesQuery.page = 1
      loadFiles().catch(() => {})
    }
    filesForm.addEventListener("submit", onFilesSubmit)
    cleanups.push(() => filesForm.removeEventListener("submit", onFilesSubmit))
  }

  if (latestForm) {
    const onLatestSubmit = (event) => {
      event.preventDefault()
      const formData = new FormData(latestForm)
      state.latestQuery.platform = String(formData.get("platform") || "")
      state.latestQuery.fileType = String(formData.get("file_type") || "")
      state.latestQuery.limit = Math.max(1, Number(formData.get("limit") || DEFAULT_PREVIEW_LIMIT))
      loadLatest().catch(() => {})
    }
    latestForm.addEventListener("submit", onLatestSubmit)
    cleanups.push(() => latestForm.removeEventListener("submit", onLatestSubmit))
  }

  if (statsForm) {
    const onStatsSubmit = (event) => {
      event.preventDefault()
      const formData = new FormData(statsForm)
      state.statsQuery.platform = String(formData.get("platform") || "")
      state.statsQuery.from = String(formData.get("from") || "")
      state.statsQuery.to = String(formData.get("to") || "")
      loadStats().catch(() => {})
    }
    statsForm.addEventListener("submit", onStatsSubmit)
    cleanups.push(() => statsForm.removeEventListener("submit", onStatsSubmit))
  }

  if (refreshAllButton) {
    const onRefreshAllClick = () => {
      refreshAll().catch(() => {})
    }
    refreshAllButton.addEventListener("click", onRefreshAllClick)
    cleanups.push(() => refreshAllButton.removeEventListener("click", onRefreshAllClick))
  }

  if (filesPrevButton) {
    const onFilesPrevClick = () => {
      if (state.filesQuery.page <= 1) return
      state.filesQuery.page -= 1
      loadFiles().catch(() => {})
    }
    filesPrevButton.addEventListener("click", onFilesPrevClick)
    cleanups.push(() => filesPrevButton.removeEventListener("click", onFilesPrevClick))
  }

  if (filesNextButton) {
    const onFilesNextClick = () => {
      const currentPage = Number(state.filesResult.page || 1)
      const totalPages = Number(state.filesResult.totalPages || 0)
      if (totalPages > 0 && currentPage >= totalPages) return
      state.filesQuery.page = currentPage + 1
      loadFiles().catch(() => {})
    }
    filesNextButton.addEventListener("click", onFilesNextClick)
    cleanups.push(() => filesNextButton.removeEventListener("click", onFilesNextClick))
  }

  if (statsResetButton && statsForm) {
    const onStatsResetClick = () => {
      state.statsQuery = {
        platform: "",
        from: "",
        to: "",
      }
      statsForm.reset()
      loadStats().catch(() => {})
    }
    statsResetButton.addEventListener("click", onStatsResetClick)
    cleanups.push(() => statsResetButton.removeEventListener("click", onStatsResetClick))
  }

  applyFiltersFromHash()

  if (options.autoLoad !== false) {
    refreshAll().catch(() => {})
  }

  return {
    id: "data",
    title: "Data Explorer",
    root,
    refresh: refreshAll,
    destroy() {
      cleanups.forEach((runCleanup) => runCleanup())
      cleanups.length = 0
    },
  }
}

export function mountDataPage(container, options = {}) {
  if (!container || typeof container.appendChild !== "function") {
    throw new Error("mountDataPage requires a valid container element")
  }

  const page = createDataPage(options)
  container.innerHTML = ""
  container.appendChild(page.root)
  return page
}

export default {
  id: "data",
  title: "Data Explorer",
  create: createDataPage,
  mount: mountDataPage,
}
