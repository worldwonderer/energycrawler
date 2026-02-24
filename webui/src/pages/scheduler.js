import { api } from "../lib/api.js";

const STYLE_LINK_ID = "energycrawler-ui2-scheduler-runs-style";

const FALLBACK_OPTIONS = {
  save_options: [
    { value: "json", label: "JSON File" },
    { value: "csv", label: "CSV File" },
    { value: "excel", label: "Excel File" },
  ],
  safety_profiles: [
    { value: "safe", label: "Safe" },
    { value: "balanced", label: "Balanced" },
    { value: "aggressive", label: "Aggressive" },
  ],
};

const TEMPLATE_STORAGE_KEY = "energycrawler.ui.scheduler.templates.v1";
const TEMPLATE_JOB_TYPES = ["keyword", "kol"];
const TEMPLATE_MAX_PER_JOB_TYPE = 20;
const TEMPLATE_SENSITIVE_KEY_PATTERNS = [
  /(^|[_-])cookie(s)?($|[_-])/i,
  /token/i,
  /authorization/i,
  /password/i,
  /secret/i,
  /credential/i,
  /session/i,
];

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

function parseOptionalNumber(rawValue, fieldName) {
  const text = String(rawValue ?? "").trim();
  if (!text) return null;
  const parsed = Number(text);
  if (!Number.isFinite(parsed)) {
    throw new Error(`${fieldName} 必须是数字`);
  }
  return parsed;
}

function buildPayloadFromForm(formData, jobType) {
  const normalizedJobType = String(jobType || "keyword");
  const basePayload = {
    login_type: "cookie",
    save_option: String(formData.get("save_option") || "json"),
    headless: formData.get("headless") === "on",
    start_page: Number(formData.get("start_page") || 1),
    enable_comments: formData.get("enable_comments") === "on",
    enable_sub_comments: formData.get("enable_sub_comments") === "on",
    cookies: String(formData.get("cookies") || "").trim(),
    safety_profile: String(formData.get("safety_profile") || "").trim() || null,
    max_notes_count: parseOptionalNumber(formData.get("max_notes_count"), "max_notes_count"),
    crawl_sleep_sec: parseOptionalNumber(formData.get("crawl_sleep_sec"), "crawl_sleep_sec"),
  };

  if (!Number.isInteger(basePayload.start_page) || basePayload.start_page < 1) {
    throw new Error("start_page 需为大于等于 1 的整数");
  }

  if (normalizedJobType === "kol") {
    const creatorIds = String(formData.get("creator_ids") || "").trim();
    if (!creatorIds) {
      throw new Error("KOL 任务必须填写 creator_ids");
    }
    return {
      ...basePayload,
      creator_ids: creatorIds,
    };
  }

  const keywords = String(formData.get("keywords") || "").trim();
  if (!keywords) {
    throw new Error("关键词任务必须填写 keywords");
  }
  return {
    ...basePayload,
    keywords,
  };
}

function normalizeJobs(payload) {
  const jobs = payload?.data?.jobs;
  return Array.isArray(jobs) ? jobs : [];
}

function uniqueJobIds(ids) {
  const seen = new Set();
  const output = [];
  ids.forEach((item) => {
    const value = String(item || "").trim();
    if (!value || seen.has(value)) return;
    seen.add(value);
    output.push(value);
  });
  return output;
}

function normalizeTemplateJobType(rawValue) {
  const value = String(rawValue || "keyword")
    .trim()
    .toLowerCase();
  return TEMPLATE_JOB_TYPES.includes(value) ? value : "keyword";
}

function buildTemplateId() {
  return `tpl-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
}

function normalizeTemplateRecord(rawTemplate) {
  if (!rawTemplate || typeof rawTemplate !== "object") return null;

  const jobType = normalizeTemplateJobType(rawTemplate.job_type);
  const name = String(rawTemplate.name || "").trim().slice(0, 80);
  if (!name) return null;

  const nowIso = new Date().toISOString();
  return {
    id: String(rawTemplate.id || buildTemplateId()),
    name,
    job_type: jobType,
    snapshot: sanitizeTemplateSnapshot(
      rawTemplate.snapshot && typeof rawTemplate.snapshot === "object" ? rawTemplate.snapshot : {}
    ),
    created_at: String(rawTemplate.created_at || nowIso),
    updated_at: String(rawTemplate.updated_at || rawTemplate.created_at || nowIso),
  };
}

function isSensitiveTemplateKey(key) {
  const normalized = String(key || "").trim().toLowerCase();
  if (!normalized) return false;
  return TEMPLATE_SENSITIVE_KEY_PATTERNS.some((pattern) => pattern.test(normalized));
}

function sanitizeTemplateSnapshot(input) {
  if (Array.isArray(input)) {
    return input.map((item) => sanitizeTemplateSnapshot(item));
  }
  if (!input || typeof input !== "object") {
    return input;
  }

  const sanitized = {};
  Object.entries(input).forEach(([key, value]) => {
    if (isSensitiveTemplateKey(key)) return;
    sanitized[key] = sanitizeTemplateSnapshot(value);
  });
  return sanitized;
}

function sortTemplatesByUpdatedDesc(templates) {
  return [...templates].sort(
    (left, right) => Date.parse(right.updated_at || "") - Date.parse(left.updated_at || "")
  );
}

function pruneTemplatesByTypeLimit(templates) {
  const sorted = sortTemplatesByUpdatedDesc(templates);
  const counters = {};
  const kept = [];

  sorted.forEach((template) => {
    const jobType = normalizeTemplateJobType(template.job_type);
    const nextCount = (counters[jobType] || 0) + 1;
    if (nextCount > TEMPLATE_MAX_PER_JOB_TYPE) return;
    counters[jobType] = nextCount;
    kept.push(template);
  });

  return kept;
}

function readSchedulerTemplatesFromStorage() {
  if (typeof window === "undefined" || !window.localStorage) return [];
  try {
    const raw = window.localStorage.getItem(TEMPLATE_STORAGE_KEY);
    if (!raw) return [];

    const parsed = JSON.parse(raw);
    const list = Array.isArray(parsed)
      ? parsed
      : Array.isArray(parsed?.templates)
        ? parsed.templates
        : [];

    return pruneTemplatesByTypeLimit(
      list.map((template) => normalizeTemplateRecord(template)).filter(Boolean)
    );
  } catch {
    return [];
  }
}

function writeSchedulerTemplatesToStorage(templates) {
  if (typeof window === "undefined" || !window.localStorage) return false;
  try {
    window.localStorage.setItem(
      TEMPLATE_STORAGE_KEY,
      JSON.stringify({
        version: 1,
        templates: pruneTemplatesByTypeLimit(templates),
      })
    );
    return true;
  } catch {
    return false;
  }
}

function parseCommaSeparatedItems(text) {
  return String(text || "")
    .split(",")
    .map((item) => item.trim())
    .filter(Boolean);
}

function runSubmitPrecheck(formData, jobType) {
  const name = String(formData.get("name") || "").trim();
  if (!name) return "任务名称不能为空";

  const intervalMinutes = Number(formData.get("interval_minutes"));
  if (!Number.isInteger(intervalMinutes) || intervalMinutes < 5 || intervalMinutes > 10080) {
    return "interval_minutes 需为 5-10080 的整数";
  }

  const startPage = Number(formData.get("start_page") || 1);
  if (!Number.isInteger(startPage) || startPage < 1) {
    return "start_page 需为大于等于 1 的整数";
  }

  const normalizedJobType = normalizeTemplateJobType(jobType);
  const keywords = parseCommaSeparatedItems(formData.get("keywords"));
  const creatorIds = parseCommaSeparatedItems(formData.get("creator_ids"));
  if (normalizedJobType === "keyword" && keywords.length === 0) {
    return "关键词任务至少需要 1 个 keyword";
  }
  if (normalizedJobType === "kol" && creatorIds.length === 0) {
    return "KOL 任务至少需要 1 个 creator_id";
  }

  const maxNotesCount = parseOptionalNumber(formData.get("max_notes_count"), "max_notes_count");
  if (maxNotesCount !== null && (!Number.isInteger(maxNotesCount) || maxNotesCount < 1)) {
    return "max_notes_count 必须是大于等于 1 的整数";
  }

  const crawlSleepSec = parseOptionalNumber(formData.get("crawl_sleep_sec"), "crawl_sleep_sec");
  if (crawlSleepSec !== null && crawlSleepSec <= 0) {
    return "crawl_sleep_sec 必须大于 0";
  }

  const enableComments = formData.get("enable_comments") === "on";
  const enableSubComments = formData.get("enable_sub_comments") === "on";
  if (enableSubComments && !enableComments) {
    return "启用 enable_sub_comments 前请先启用 enable_comments";
  }

  return "";
}

export default async function renderSchedulerPage(mountEl, ctx = {}) {
  ensurePageStyle();

  const state = {
    jobs: [],
    selectedJobIds: new Set(),
    options: FALLBACK_OPTIONS,
    templates: [],
    loading: false,
    editingJobId: "",
  };

  mountEl.innerHTML = `
    <section class="sr-page sr-scheduler-page">
      <header class="sr-header">
        <div>
          <h2>Scheduler Studio</h2>
          <p class="sr-muted">任务筛选、创建/编辑、clone、批量启停与 run-now。</p>
        </div>
        <div class="sr-actions">
          <button type="button" class="secondary" data-action="refresh-jobs">刷新任务</button>
        </div>
      </header>

      <section class="sr-card">
        <h3 class="sr-card-title">任务列表</h3>
        <div class="sr-controls sr-controls--jobs">
          <label class="sr-control">
            <span>关键字筛选</span>
            <input type="text" data-role="filter-query" placeholder="job_id / name / payload" />
          </label>
          <label class="sr-control">
            <span>任务类型</span>
            <select data-role="filter-job-type">
              <option value="">全部</option>
              <option value="keyword">keyword</option>
              <option value="kol">kol</option>
            </select>
          </label>
          <label class="sr-control">
            <span>平台</span>
            <select data-role="filter-platform">
              <option value="">全部</option>
              <option value="xhs">xhs</option>
              <option value="x">x</option>
            </select>
          </label>
          <label class="sr-control">
            <span>启用状态</span>
            <select data-role="filter-enabled">
              <option value="all">全部</option>
              <option value="enabled">启用</option>
              <option value="disabled">停用</option>
            </select>
          </label>
          <div class="sr-actions sr-controls-actions">
            <button type="button" class="secondary" data-action="clear-filters">清空筛选</button>
            <button type="button" class="secondary" data-action="batch-enable">批量启用</button>
            <button type="button" class="secondary" data-action="batch-disable">批量停用</button>
          </div>
        </div>

        <div class="sr-table-wrap">
          <table class="sr-table sr-table--jobs">
            <thead>
              <tr>
                <th class="sr-col-select"><input type="checkbox" data-role="select-all" aria-label="选择全部" /></th>
                <th class="sr-col-id">Job ID</th>
                <th class="sr-col-name">Name</th>
                <th class="sr-col-type">Type</th>
                <th class="sr-col-platform">Platform</th>
                <th class="sr-col-interval">Interval(min)</th>
                <th class="sr-col-enabled">Enabled</th>
                <th class="sr-col-time">Next Run</th>
                <th class="sr-col-time">Last Run</th>
                <th>操作</th>
              </tr>
            </thead>
            <tbody data-role="jobs-body"></tbody>
          </table>
        </div>
        <p class="sr-muted" data-role="jobs-meta">-</p>
      </section>

      <section class="sr-card">
        <div class="sr-card-headline">
          <h3 class="sr-card-title" data-role="form-title">创建任务</h3>
          <button type="button" class="secondary" data-action="reset-form">重置</button>
        </div>

        <section class="sr-template-panel">
          <div class="sr-template-headline">
            <h4>任务模板（按 job_type 分组）</h4>
            <p class="sr-muted" data-role="template-meta">-</p>
          </div>
          <p class="sr-muted">
            安全提示：模板不会保存 cookies / token 等敏感字段，应用模板时会保留当前 cookies。
          </p>
          <div class="sr-template-save-row">
            <label class="sr-control">
              <span>模板名称</span>
              <input
                type="text"
                data-role="template-name"
                maxlength="80"
                placeholder="例如：keyword-品牌词高频"
              />
            </label>
            <div class="sr-actions">
              <button type="button" data-action="save-template">从当前表单保存模板</button>
            </div>
          </div>
          <div class="sr-template-groups" data-role="template-groups"></div>
        </section>

        <form data-role="job-form" class="sr-form-grid">
          <label class="sr-control">
            <span>名称</span>
            <input type="text" name="name" required maxlength="120" placeholder="任务名称" />
          </label>
          <label class="sr-control">
            <span>任务类型</span>
            <select name="job_type" data-role="job-type" required>
              <option value="keyword">keyword</option>
              <option value="kol">kol</option>
            </select>
          </label>
          <label class="sr-control">
            <span>平台</span>
            <select name="platform" data-role="platform" required>
              <option value="xhs">xhs</option>
              <option value="x">x</option>
            </select>
          </label>
          <label class="sr-control">
            <span>间隔分钟</span>
            <input type="number" name="interval_minutes" min="5" max="10080" value="60" required />
          </label>

          <label class="sr-control sr-field-keywords" data-role="field-keywords">
            <span>keywords</span>
            <input type="text" name="keywords" placeholder="关键词，逗号分隔" />
          </label>
          <label class="sr-control sr-field-creator-ids sr-hidden" data-role="field-creator-ids">
            <span>creator_ids</span>
            <input type="text" name="creator_ids" placeholder="KOL ID，逗号分隔" />
          </label>

          <label class="sr-control">
            <span>save_option</span>
            <select name="save_option" data-role="save-option"></select>
          </label>
          <label class="sr-control">
            <span>safety_profile</span>
            <select name="safety_profile" data-role="safety-profile">
              <option value="">(空)</option>
            </select>
          </label>
          <label class="sr-control">
            <span>start_page</span>
            <input type="number" name="start_page" min="1" value="1" />
          </label>
          <label class="sr-control">
            <span>max_notes_count</span>
            <input type="number" name="max_notes_count" min="1" max="200" placeholder="可选" />
          </label>
          <label class="sr-control">
            <span>crawl_sleep_sec</span>
            <input type="number" name="crawl_sleep_sec" min="0.1" max="120" step="0.1" placeholder="可选" />
          </label>

          <label class="sr-control sr-control--full">
            <span>cookies（可选）</span>
            <textarea name="cookies" rows="2" placeholder="可留空"></textarea>
          </label>

          <div class="sr-switches sr-control--full">
            <label><input type="checkbox" name="enabled" checked /> enabled</label>
            <label><input type="checkbox" name="enable_comments" checked /> enable_comments</label>
            <label><input type="checkbox" name="enable_sub_comments" /> enable_sub_comments</label>
            <label><input type="checkbox" name="headless" /> headless</label>
          </div>

          <div class="sr-actions sr-control--full">
            <button type="submit" data-role="submit-btn">创建任务</button>
            <button type="button" class="secondary" data-action="cancel-edit" data-role="cancel-edit" hidden>
              取消编辑
            </button>
          </div>
        </form>
      </section>
    </section>
  `;

  const refs = {
    jobsBody: mountEl.querySelector('[data-role="jobs-body"]'),
    jobsMeta: mountEl.querySelector('[data-role="jobs-meta"]'),
    selectAll: mountEl.querySelector('[data-role="select-all"]'),
    filterQuery: mountEl.querySelector('[data-role="filter-query"]'),
    filterJobType: mountEl.querySelector('[data-role="filter-job-type"]'),
    filterPlatform: mountEl.querySelector('[data-role="filter-platform"]'),
    filterEnabled: mountEl.querySelector('[data-role="filter-enabled"]'),
    formTitle: mountEl.querySelector('[data-role="form-title"]'),
    jobForm: mountEl.querySelector('[data-role="job-form"]'),
    jobTypeSelect: mountEl.querySelector('[data-role="job-type"]'),
    platformSelect: mountEl.querySelector('[data-role="platform"]'),
    fieldKeywords: mountEl.querySelector('[data-role="field-keywords"]'),
    fieldCreatorIds: mountEl.querySelector('[data-role="field-creator-ids"]'),
    saveOption: mountEl.querySelector('[data-role="save-option"]'),
    safetyProfile: mountEl.querySelector('[data-role="safety-profile"]'),
    templateMeta: mountEl.querySelector('[data-role="template-meta"]'),
    templateName: mountEl.querySelector('[data-role="template-name"]'),
    templateGroups: mountEl.querySelector('[data-role="template-groups"]'),
    submitBtn: mountEl.querySelector('[data-role="submit-btn"]'),
    cancelEditBtn: mountEl.querySelector('[data-role="cancel-edit"]'),
    refreshBtn: mountEl.querySelector('[data-action="refresh-jobs"]'),
  };

  function toast(message, options = {}) {
    if (ctx && typeof ctx.showToast === "function") {
      ctx.showToast(message, options);
      return;
    }
    // eslint-disable-next-line no-console
    console.log(`[scheduler] ${message}`);
  }

  function setLoading(isLoading) {
    state.loading = isLoading;
    if (refs.refreshBtn) refs.refreshBtn.disabled = isLoading;
    if (refs.submitBtn) refs.submitBtn.disabled = isLoading;
  }

  function getFilteredJobs() {
    const query = String(refs.filterQuery?.value || "").trim().toLowerCase();
    const jobType = String(refs.filterJobType?.value || "").trim();
    const platform = String(refs.filterPlatform?.value || "").trim();
    const enabledFilter = String(refs.filterEnabled?.value || "all");

    return state.jobs.filter((job) => {
      if (jobType && job.job_type !== jobType) return false;
      if (platform && job.platform !== platform) return false;
      if (enabledFilter === "enabled" && !job.enabled) return false;
      if (enabledFilter === "disabled" && job.enabled) return false;

      if (!query) return true;
      const payload = job?.payload || {};
      const haystack = [
        job.job_id,
        job.name,
        job.job_type,
        job.platform,
        payload.keywords,
        payload.creator_ids,
      ]
        .filter(Boolean)
        .join(" ")
        .toLowerCase();
      return haystack.includes(query);
    });
  }

  function updateJobTypeVisibility() {
    const isKol = String(refs.jobTypeSelect?.value || "") === "kol";
    refs.fieldKeywords?.classList.toggle("sr-hidden", isKol);
    refs.fieldCreatorIds?.classList.toggle("sr-hidden", !isKol);
  }

  function readCurrentFormSnapshot() {
    const { elements } = refs.jobForm;
    return {
      name: String(elements.name?.value || "").trim(),
      job_type: normalizeTemplateJobType(elements.job_type?.value || "keyword"),
      platform: String(elements.platform?.value || "xhs").trim() || "xhs",
      interval_minutes: String(elements.interval_minutes?.value || "60").trim() || "60",
      keywords: String(elements.keywords?.value || "").trim(),
      creator_ids: String(elements.creator_ids?.value || "").trim(),
      save_option: String(elements.save_option?.value || "json").trim() || "json",
      safety_profile: String(elements.safety_profile?.value || "").trim(),
      start_page: String(elements.start_page?.value || "1").trim() || "1",
      max_notes_count: String(elements.max_notes_count?.value || "").trim(),
      crawl_sleep_sec: String(elements.crawl_sleep_sec?.value || "").trim(),
      cookies: String(elements.cookies?.value || ""),
      enabled: Boolean(elements.enabled?.checked),
      enable_comments: Boolean(elements.enable_comments?.checked),
      enable_sub_comments: Boolean(elements.enable_sub_comments?.checked),
      headless: Boolean(elements.headless?.checked),
    };
  }

  function applyFormSnapshot(snapshot, jobTypeHint) {
    const { elements } = refs.jobForm;
    const preservedCookies = String(elements.cookies?.value || "");
    const normalizedHint = normalizeTemplateJobType(jobTypeHint);
    const snapshotJobType = normalizeTemplateJobType(snapshot?.job_type || normalizedHint);
    const nextJobType = state.editingJobId ? normalizedHint : snapshotJobType;

    if (!state.editingJobId) {
      elements.job_type.value = nextJobType;
    }

    elements.name.value = String(snapshot?.name || "");
    elements.platform.value = String(snapshot?.platform || elements.platform.value || "xhs");
    elements.interval_minutes.value = String(snapshot?.interval_minutes || "60");
    elements.keywords.value = String(snapshot?.keywords || "");
    elements.creator_ids.value = String(snapshot?.creator_ids || "");
    elements.save_option.value = String(snapshot?.save_option || "json");
    elements.safety_profile.value = String(snapshot?.safety_profile || "");
    elements.start_page.value = String(snapshot?.start_page || "1");
    elements.max_notes_count.value = String(snapshot?.max_notes_count || "");
    elements.crawl_sleep_sec.value = String(snapshot?.crawl_sleep_sec || "");
    elements.cookies.value = preservedCookies;

    elements.enabled.checked =
      snapshot?.enabled === undefined ? Boolean(elements.enabled?.checked) : Boolean(snapshot.enabled);
    elements.enable_comments.checked =
      snapshot?.enable_comments === undefined
        ? Boolean(elements.enable_comments?.checked)
        : Boolean(snapshot.enable_comments);
    elements.enable_sub_comments.checked = Boolean(snapshot?.enable_sub_comments);
    elements.headless.checked = Boolean(snapshot?.headless);

    updateJobTypeVisibility();
  }

  function getTemplateGroups() {
    const groups = { keyword: [], kol: [] };
    state.templates.forEach((template) => {
      const jobType = normalizeTemplateJobType(template.job_type);
      groups[jobType].push(template);
    });
    return groups;
  }

  function updateTemplatesState(nextTemplates, { persist = true } = {}) {
    state.templates = pruneTemplatesByTypeLimit(
      nextTemplates.map((template) => normalizeTemplateRecord(template)).filter(Boolean)
    );
    if (persist) {
      const ok = writeSchedulerTemplatesToStorage(state.templates);
      if (!ok) {
        toast("模板已更新，但写入 localStorage 失败（可能是浏览器隐私限制）", {
          tone: "warning",
          title: "模板",
        });
      }
    }
  }

  function renderTemplateGroups() {
    if (!refs.templateGroups) return;
    refs.templateGroups.innerHTML = "";

    const grouped = getTemplateGroups();
    const activeJobType = normalizeTemplateJobType(refs.jobTypeSelect?.value || "keyword");
    TEMPLATE_JOB_TYPES.forEach((jobType) => {
      const templates = grouped[jobType];

      const section = createElement("section", "sr-template-group");
      const title = createElement(
        "h5",
        "sr-template-group-title",
        `${jobType.toUpperCase()} 模板 (${templates.length})`
      );
      section.appendChild(title);

      if (templates.length === 0) {
        section.appendChild(createElement("p", "sr-template-empty", "暂无模板"));
      } else {
        const list = createElement("ul", "sr-template-list");

        templates.forEach((template) => {
          const item = createElement("li", "sr-template-item");
          if (template.job_type === activeJobType) item.classList.add("is-active");

          const info = createElement("div", "sr-template-item-info");
          info.appendChild(createElement("p", "sr-template-name", template.name));
          info.appendChild(
            createElement(
              "p",
              "sr-template-item-meta",
              `更新：${safeFormatDateTime(ctx, template.updated_at)}`
            )
          );
          item.appendChild(info);

          const actions = createElement("div", "sr-row-actions");

          const applyBtn = createElement("button", "secondary sr-btn-sm", "应用");
          applyBtn.type = "button";
          applyBtn.dataset.action = "apply-template";
          applyBtn.dataset.templateId = template.id;
          if (state.editingJobId && template.job_type !== activeJobType) {
            applyBtn.disabled = true;
            applyBtn.title = "编辑模式仅允许应用同 job_type 模板";
          }
          actions.appendChild(applyBtn);

          const deleteBtn = createElement("button", "secondary sr-btn-sm", "删除");
          deleteBtn.type = "button";
          deleteBtn.dataset.action = "delete-template";
          deleteBtn.dataset.templateId = template.id;
          actions.appendChild(deleteBtn);

          item.appendChild(actions);
          list.appendChild(item);
        });

        section.appendChild(list);
      }

      refs.templateGroups.appendChild(section);
    });

    const groupedCount = getTemplateGroups();
    if (refs.templateMeta) {
      refs.templateMeta.textContent = `共 ${state.templates.length} 个模板（keyword ${groupedCount.keyword.length} / kol ${groupedCount.kol.length}）`;
    }
  }

  function loadTemplatesFromStorage() {
    updateTemplatesState(readSchedulerTemplatesFromStorage(), { persist: false });
    renderTemplateGroups();
  }

  function saveCurrentFormAsTemplate() {
    const snapshot = sanitizeTemplateSnapshot(readCurrentFormSnapshot());
    const jobType = normalizeTemplateJobType(snapshot.job_type);
    const customName = String(refs.templateName?.value || "").trim();
    const defaultName = `${jobType}-${new Date().toLocaleString()}`;
    const templateName = (customName || defaultName).slice(0, 80);

    const nowIso = new Date().toISOString();
    const existingIndex = state.templates.findIndex(
      (template) =>
        normalizeTemplateJobType(template.job_type) === jobType &&
        String(template.name || "").toLowerCase() === templateName.toLowerCase()
    );

    let nextTemplates = [...state.templates];
    if (existingIndex >= 0) {
      const existing = nextTemplates[existingIndex];
      nextTemplates[existingIndex] = {
        ...existing,
        name: templateName,
        job_type: jobType,
        snapshot,
        updated_at: nowIso,
      };
      updateTemplatesState(nextTemplates);
      renderTemplateGroups();
      toast(`模板已更新：${templateName}`, { tone: "success", title: "模板" });
    } else {
      nextTemplates = [
        {
          id: buildTemplateId(),
          name: templateName,
          job_type: jobType,
          snapshot,
          created_at: nowIso,
          updated_at: nowIso,
        },
        ...nextTemplates,
      ];
      updateTemplatesState(nextTemplates);
      renderTemplateGroups();
      toast(`模板已保存：${templateName}`, { tone: "success", title: "模板" });
    }
  }

  function applyTemplate(templateId) {
    const template = state.templates.find((item) => item.id === templateId);
    if (!template) {
      toast("模板不存在，可能已被删除", { tone: "warning", title: "模板" });
      return;
    }

    const currentJobType = normalizeTemplateJobType(refs.jobTypeSelect?.value || "keyword");
    if (state.editingJobId && normalizeTemplateJobType(template.job_type) !== currentJobType) {
      toast("编辑模式仅允许应用同 job_type 模板", { tone: "warning", title: "模板" });
      return;
    }

    applyFormSnapshot(sanitizeTemplateSnapshot(template.snapshot || {}), template.job_type);
    if (refs.templateName) refs.templateName.value = template.name;
    renderTemplateGroups();
    toast(`已应用模板：${template.name}`, { tone: "success", title: "模板" });
  }

  function deleteTemplate(templateId) {
    const template = state.templates.find((item) => item.id === templateId);
    if (!template) return;

    const shouldDelete = window.confirm(`确认删除模板「${template.name}」？`);
    if (!shouldDelete) return;

    updateTemplatesState(state.templates.filter((item) => item.id !== templateId));
    renderTemplateGroups();
    toast(`模板已删除：${template.name}`, { tone: "success", title: "模板" });
  }

  function renderSelectAllCheckbox(filteredJobs) {
    const visibleIds = filteredJobs.map((job) => job.job_id);
    const selectedVisibleCount = visibleIds.filter((jobId) => state.selectedJobIds.has(jobId)).length;

    refs.selectAll.checked = visibleIds.length > 0 && selectedVisibleCount === visibleIds.length;
    refs.selectAll.indeterminate =
      selectedVisibleCount > 0 && selectedVisibleCount < visibleIds.length;
  }

  function createStatusBadge(enabled) {
    const badge = createElement(
      "span",
      `sr-status ${enabled ? "sr-status--success" : "sr-status--danger"}`,
      enabled ? "enabled" : "disabled"
    );
    return badge;
  }

  function renderJobsTable() {
    const filteredJobs = getFilteredJobs();
    refs.jobsBody.innerHTML = "";

    if (filteredJobs.length === 0) {
      const tr = createElement("tr");
      const td = createElement("td", "sr-table-empty", "暂无匹配任务");
      td.colSpan = 10;
      tr.appendChild(td);
      refs.jobsBody.appendChild(tr);
    } else {
      filteredJobs.forEach((job) => {
        const tr = createElement("tr", "sr-row");
        if (!job.enabled) tr.classList.add("is-disabled");

        const selectTd = createElement("td");
        const checkbox = createElement("input");
        checkbox.type = "checkbox";
        checkbox.checked = state.selectedJobIds.has(job.job_id);
        checkbox.dataset.role = "row-select";
        checkbox.dataset.jobId = job.job_id;
        selectTd.appendChild(checkbox);
        tr.appendChild(selectTd);

        tr.appendChild(createDataCell(job.job_id || "-", "sr-cell-id"));
        tr.appendChild(createDataCell(job.name || "-", "sr-cell-primary"));

        const typeTd = createElement("td");
        typeTd.appendChild(createPill(job.job_type || "-", "info"));
        tr.appendChild(typeTd);

        const platformTd = createElement("td");
        platformTd.appendChild(createPill(job.platform || "-", "neutral"));
        tr.appendChild(platformTd);

        tr.appendChild(createDataCell(String(job.interval_minutes ?? "-"), "sr-cell-num"));

        const statusTd = createElement("td");
        statusTd.appendChild(createStatusBadge(Boolean(job.enabled)));
        tr.appendChild(statusTd);

        tr.appendChild(createDataCell(safeFormatDateTime(ctx, job.next_run_at), "sr-cell-date"));
        tr.appendChild(createDataCell(safeFormatDateTime(ctx, job.last_run_at), "sr-cell-date"));

        const opsTd = createElement("td");
        const ops = createElement("div", "sr-row-actions");

        const actions = [
          { key: "run-now", label: "run-now" },
          { key: "edit", label: "编辑" },
          { key: "clone", label: "clone" },
          { key: "toggle", label: job.enabled ? "停用" : "启用" },
        ];

        actions.forEach((action) => {
          const button = createElement("button", "secondary sr-btn-sm", action.label);
          button.type = "button";
          button.dataset.action = action.key;
          button.dataset.jobId = job.job_id;
          ops.appendChild(button);
        });

        opsTd.appendChild(ops);
        tr.appendChild(opsTd);

        refs.jobsBody.appendChild(tr);
      });
    }

    renderSelectAllCheckbox(filteredJobs);

    const selectedCount = state.selectedJobIds.size;
    refs.jobsMeta.textContent = `共 ${state.jobs.length} 个任务，筛选后 ${filteredJobs.length} 个，已选 ${selectedCount} 个`;
  }

  function setEditingJob(job) {
    if (!job) {
      state.editingJobId = "";
      refs.formTitle.textContent = "创建任务";
      refs.submitBtn.textContent = "创建任务";
      refs.cancelEditBtn.hidden = true;
      refs.jobTypeSelect.disabled = false;
      refs.platformSelect.disabled = false;
      refs.jobForm.reset();
      refs.jobForm.elements.interval_minutes.value = "60";
      refs.jobForm.elements.start_page.value = "1";
      refs.jobForm.elements.enabled.checked = true;
      refs.jobForm.elements.enable_comments.checked = true;
      refs.jobForm.elements.enable_sub_comments.checked = false;
      refs.jobForm.elements.headless.checked = false;
      refs.jobForm.elements.save_option.value = refs.jobForm.elements.save_option.value || "json";
      refs.jobForm.elements.safety_profile.value = "";
      if (refs.templateName) refs.templateName.value = "";
      updateJobTypeVisibility();
      renderTemplateGroups();
      return;
    }

    state.editingJobId = String(job.job_id || "");
    const payload = job.payload || {};

    refs.formTitle.textContent = `编辑任务：${job.job_id}`;
    refs.submitBtn.textContent = "保存修改";
    refs.cancelEditBtn.hidden = false;

    refs.jobForm.elements.name.value = job.name || "";
    refs.jobForm.elements.job_type.value = job.job_type || "keyword";
    refs.jobForm.elements.platform.value = job.platform || "xhs";
    refs.jobForm.elements.interval_minutes.value = String(job.interval_minutes || 60);
    refs.jobForm.elements.enabled.checked = Boolean(job.enabled);

    refs.jobForm.elements.keywords.value = payload.keywords || "";
    refs.jobForm.elements.creator_ids.value = payload.creator_ids || "";
    refs.jobForm.elements.save_option.value = payload.save_option || "json";
    refs.jobForm.elements.safety_profile.value = payload.safety_profile || "";
    refs.jobForm.elements.start_page.value = String(payload.start_page || 1);
    refs.jobForm.elements.max_notes_count.value =
      payload.max_notes_count === null || payload.max_notes_count === undefined
        ? ""
        : String(payload.max_notes_count);
    refs.jobForm.elements.crawl_sleep_sec.value =
      payload.crawl_sleep_sec === null || payload.crawl_sleep_sec === undefined
        ? ""
        : String(payload.crawl_sleep_sec);
    refs.jobForm.elements.cookies.value = payload.cookies || "";
    refs.jobForm.elements.enable_comments.checked = payload.enable_comments !== false;
    refs.jobForm.elements.enable_sub_comments.checked = Boolean(payload.enable_sub_comments);
    refs.jobForm.elements.headless.checked = Boolean(payload.headless);

    refs.jobTypeSelect.disabled = true;
    refs.platformSelect.disabled = true;
    updateJobTypeVisibility();
    renderTemplateGroups();
  }

  async function loadConfigOptions() {
    try {
      const payload = await api.get("/api/config/options", { suppressErrorToast: true });
      const data = payload?.data || payload || {};
      const saveOptions = Array.isArray(data.save_options) ? data.save_options : FALLBACK_OPTIONS.save_options;
      const safetyProfiles = Array.isArray(data.safety_profiles)
        ? data.safety_profiles
        : FALLBACK_OPTIONS.safety_profiles;
      state.options = {
        save_options: saveOptions,
        safety_profiles: safetyProfiles,
      };
    } catch {
      state.options = FALLBACK_OPTIONS;
    }

    refs.saveOption.innerHTML = "";
    state.options.save_options.forEach((option) => {
      const opt = createElement("option");
      opt.value = option.value;
      opt.textContent = option.label || option.value;
      refs.saveOption.appendChild(opt);
    });

    refs.safetyProfile.innerHTML = '<option value="">(空)</option>';
    state.options.safety_profiles.forEach((option) => {
      const opt = createElement("option");
      opt.value = option.value;
      opt.textContent = option.label || option.value;
      refs.safetyProfile.appendChild(opt);
    });
  }

  async function loadJobs() {
    setLoading(true);
    try {
      const payload = await api.get("/api/scheduler/jobs");
      state.jobs = normalizeJobs(payload);

      const existingIds = new Set(state.jobs.map((job) => job.job_id));
      state.selectedJobIds.forEach((jobId) => {
        if (!existingIds.has(jobId)) {
          state.selectedJobIds.delete(jobId);
        }
      });

      renderJobsTable();
    } catch (error) {
      toast(`加载任务失败：${error?.message || "unknown"}`, {
        tone: "error",
        title: "Scheduler",
      });
    } finally {
      setLoading(false);
    }
  }

  async function triggerRunNow(jobId) {
    await api.post(`/api/scheduler/jobs/${encodeURIComponent(jobId)}/run-now`, {});
    toast(`已触发 run-now：${jobId}`, { tone: "success", title: "Scheduler" });
  }

  async function toggleJobEnabled(job) {
    await api.patch(`/api/scheduler/jobs/${encodeURIComponent(job.job_id)}`, {
      enabled: !job.enabled,
    });
    toast(`任务 ${job.job_id} 已${job.enabled ? "停用" : "启用"}`, {
      tone: "success",
      title: "Scheduler",
    });
  }

  async function cloneJob(job) {
    const suggested = `${job.name || job.job_id} (copy)`;
    const input = window.prompt("请输入克隆任务名称（可留空使用默认）", suggested);
    if (input === null) return;

    const trimmed = input.trim();
    const body = trimmed ? { name: trimmed } : {};
    const payload = await api.post(`/api/scheduler/jobs/${encodeURIComponent(job.job_id)}/clone`, body);
    const cloneId = payload?.data?.job_id || "(new job)";
    toast(`clone 成功：${cloneId}`, { tone: "success", title: "Scheduler" });
  }

  async function batchSetEnabled(enabled) {
    const jobIds = uniqueJobIds(Array.from(state.selectedJobIds));
    if (jobIds.length === 0) {
      toast("请先选择至少一个任务", { tone: "warning", title: "批量操作" });
      return;
    }

    await api.post("/api/scheduler/jobs/batch-enable", {
      job_ids: jobIds,
      enabled,
    });

    toast(`批量${enabled ? "启用" : "停用"}完成：${jobIds.length} 个任务`, {
      tone: "success",
      title: "批量操作",
    });
  }

  async function submitJobForm(event) {
    event.preventDefault();

    const formData = new FormData(refs.jobForm);
    const jobType = state.editingJobId
      ? state.jobs.find((item) => item.job_id === state.editingJobId)?.job_type || "keyword"
      : String(formData.get("job_type") || "keyword");

    let precheckError = "";
    try {
      precheckError = runSubmitPrecheck(formData, jobType);
    } catch (error) {
      precheckError = error?.message || "表单字段格式不正确";
    }
    if (precheckError) {
      toast(`提交前校验失败：${precheckError}`, {
        tone: "error",
        title: "Scheduler 预检",
      });
      return;
    }

    try {
      setLoading(true);
      const payload = buildPayloadFromForm(formData, jobType);
      const requestBody = {
        name: String(formData.get("name") || "").trim(),
        interval_minutes: Number(formData.get("interval_minutes") || 60),
        enabled: formData.get("enabled") === "on",
        payload,
      };

      if (!requestBody.name) {
        throw new Error("任务名称不能为空");
      }

      if (!Number.isInteger(requestBody.interval_minutes) || requestBody.interval_minutes < 5) {
        throw new Error("interval_minutes 需为 >= 5 的整数");
      }

      if (!state.editingJobId) {
        await api.post("/api/scheduler/jobs", {
          ...requestBody,
          job_type: String(formData.get("job_type") || "keyword"),
          platform: String(formData.get("platform") || "xhs"),
        });
        toast("任务创建成功", { tone: "success", title: "Scheduler" });
      } else {
        await api.patch(`/api/scheduler/jobs/${encodeURIComponent(state.editingJobId)}`, requestBody);
        toast(`任务 ${state.editingJobId} 更新成功`, { tone: "success", title: "Scheduler" });
      }

      setEditingJob(null);
      await loadJobs();
    } catch (error) {
      toast(`提交失败：${error?.message || "unknown"}`, {
        tone: "error",
        title: "Scheduler",
      });
    } finally {
      setLoading(false);
    }
  }

  mountEl.addEventListener("click", async (event) => {
    const trigger = event.target.closest("button[data-action]");
    if (!trigger) return;

    const action = trigger.dataset.action;

    try {
      if (action === "refresh-jobs") {
        await loadJobs();
        return;
      }

      if (action === "clear-filters") {
        refs.filterQuery.value = "";
        refs.filterJobType.value = "";
        refs.filterPlatform.value = "";
        refs.filterEnabled.value = "all";
        renderJobsTable();
        return;
      }

      if (action === "reset-form") {
        setEditingJob(null);
        return;
      }

      if (action === "cancel-edit") {
        setEditingJob(null);
        return;
      }

      if (action === "batch-enable" || action === "batch-disable") {
        await batchSetEnabled(action === "batch-enable");
        await loadJobs();
        return;
      }

      if (action === "save-template") {
        saveCurrentFormAsTemplate();
        return;
      }

      if (action === "apply-template") {
        const templateId = String(trigger.dataset.templateId || "");
        if (!templateId) return;
        applyTemplate(templateId);
        return;
      }

      if (action === "delete-template") {
        const templateId = String(trigger.dataset.templateId || "");
        if (!templateId) return;
        deleteTemplate(templateId);
        return;
      }

      const jobId = trigger.dataset.jobId;
      if (!jobId) return;

      const job = state.jobs.find((item) => item.job_id === jobId);
      if (!job) return;

      if (action === "run-now") {
        await triggerRunNow(jobId);
        return;
      }

      if (action === "edit") {
        setEditingJob(job);
        return;
      }

      if (action === "clone") {
        await cloneJob(job);
        await loadJobs();
        return;
      }

      if (action === "toggle") {
        await toggleJobEnabled(job);
        await loadJobs();
      }
    } catch (error) {
      toast(`操作失败：${error?.message || "unknown"}`, {
        tone: "error",
        title: "Scheduler",
      });
    }
  });

  mountEl.addEventListener("change", (event) => {
    const target = event.target;
    if (!(target instanceof HTMLElement)) return;

    if (target.matches('[data-role="job-type"]')) {
      updateJobTypeVisibility();
      renderTemplateGroups();
      return;
    }

    if (target.matches('[data-role="row-select"]')) {
      const jobId = target.dataset.jobId;
      if (!jobId) return;
      if (target.checked) state.selectedJobIds.add(jobId);
      else state.selectedJobIds.delete(jobId);
      renderJobsTable();
      return;
    }

    if (target.matches('[data-role="select-all"]')) {
      const filteredJobs = getFilteredJobs();
      filteredJobs.forEach((job) => {
        if (target.checked) state.selectedJobIds.add(job.job_id);
        else state.selectedJobIds.delete(job.job_id);
      });
      renderJobsTable();
      return;
    }

    if (
      target.matches('[data-role="filter-query"]') ||
      target.matches('[data-role="filter-job-type"]') ||
      target.matches('[data-role="filter-platform"]') ||
      target.matches('[data-role="filter-enabled"]')
    ) {
      renderJobsTable();
    }
  });

  refs.jobForm.addEventListener("submit", submitJobForm);

  await loadConfigOptions();
  setEditingJob(null);
  loadTemplatesFromStorage();
  await loadJobs();
}

export const render = renderSchedulerPage;
