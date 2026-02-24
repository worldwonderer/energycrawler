const state = {
  apiBase: "",
  jobs: [],
};

function normalizeApiBase(value) {
  const raw = (value || "").trim();
  if (!raw) return "";
  return raw.replace(/\/+$/, "");
}

function buildUrl(path, params = {}) {
  const base = state.apiBase;
  const finalPath = path.startsWith("/") ? path : `/${path}`;
  const url = new URL(base ? `${base}${finalPath}` : finalPath, window.location.origin);
  Object.entries(params).forEach(([key, value]) => {
    if (value === undefined || value === null || value === "") return;
    url.searchParams.set(key, String(value));
  });
  return url.toString();
}

async function apiRequest(path, { method = "GET", body = null, params = null } = {}) {
  const url = buildUrl(path, params || {});
  const options = {
    method,
    headers: {
      Accept: "application/json",
    },
  };
  if (body !== null) {
    options.headers["Content-Type"] = "application/json";
    options.body = JSON.stringify(body);
  }
  const response = await fetch(url, options);
  const payload = await response.json().catch(() => null);
  if (!response.ok || !payload || payload.success === false) {
    const message =
      payload?.error?.message || payload?.message || `${response.status} ${response.statusText}`;
    throw new Error(message);
  }
  return payload;
}

function showToast(message, isError = false) {
  const toast = document.getElementById("toast");
  toast.textContent = message;
  toast.classList.remove("hidden");
  toast.style.borderColor = isError ? "var(--error)" : "var(--border)";
  setTimeout(() => toast.classList.add("hidden"), 3200);
}

function formatTime(value) {
  if (!value) return "-";
  try {
    const date = new Date(value);
    if (Number.isNaN(date.getTime())) return String(value);
    return date.toLocaleString();
  } catch {
    return String(value);
  }
}

async function refreshJobs() {
  try {
    const payload = await apiRequest("/api/scheduler/jobs");
    state.jobs = payload.data?.jobs || [];
    renderJobs();
  } catch (error) {
    showToast(`加载任务失败: ${error.message}`, true);
  }
}

async function refreshRuns() {
  try {
    const payload = await apiRequest("/api/scheduler/runs", { params: { limit: 50 } });
    renderRuns(payload.data?.runs || []);
  } catch (error) {
    showToast(`加载运行记录失败: ${error.message}`, true);
  }
}

function renderJobs() {
  const tbody = document.getElementById("jobsTbody");
  tbody.innerHTML = "";
  state.jobs.forEach((job) => {
    const tr = document.createElement("tr");
    tr.innerHTML = `
      <td>${job.job_id}</td>
      <td>${job.name || "-"}</td>
      <td>${job.job_type}</td>
      <td>${job.platform}</td>
      <td>${job.interval_minutes}</td>
      <td>${job.enabled ? "是" : "否"}</td>
      <td>${formatTime(job.next_run_at)}</td>
      <td class="ops"></td>
    `;
    const opsCell = tr.querySelector(".ops");

    const toggleBtn = document.createElement("button");
    toggleBtn.type = "button";
    toggleBtn.className = "secondary";
    toggleBtn.textContent = job.enabled ? "停用" : "启用";
    toggleBtn.onclick = () => toggleJob(job);

    const runNowBtn = document.createElement("button");
    runNowBtn.type = "button";
    runNowBtn.className = "secondary";
    runNowBtn.textContent = "立即执行";
    runNowBtn.onclick = () => runNow(job.job_id);

    const deleteBtn = document.createElement("button");
    deleteBtn.type = "button";
    deleteBtn.className = "danger";
    deleteBtn.textContent = "删除";
    deleteBtn.onclick = () => deleteJob(job.job_id);

    opsCell.append(toggleBtn, runNowBtn, deleteBtn);
    tbody.appendChild(tr);
  });
  if (state.jobs.length === 0) {
    const tr = document.createElement("tr");
    tr.innerHTML = `<td colspan="8" class="muted">暂无调度任务</td>`;
    tbody.appendChild(tr);
  }
}

function renderRuns(runs) {
  const tbody = document.getElementById("runsTbody");
  tbody.innerHTML = "";
  runs.forEach((run) => {
    const tr = document.createElement("tr");
    tr.innerHTML = `
      <td>${run.run_id}</td>
      <td>${run.job_id}</td>
      <td>${run.status}</td>
      <td>${run.task_id || "-"}</td>
      <td>${formatTime(run.triggered_at)}</td>
      <td>${run.message || "-"}</td>
    `;
    tbody.appendChild(tr);
  });
  if (runs.length === 0) {
    const tr = document.createElement("tr");
    tr.innerHTML = `<td colspan="6" class="muted">暂无运行记录</td>`;
    tbody.appendChild(tr);
  }
}

async function toggleJob(job) {
  try {
    await apiRequest(`/api/scheduler/jobs/${job.job_id}`, {
      method: "PATCH",
      body: { enabled: !job.enabled },
    });
    showToast(`任务 ${job.name} 已${job.enabled ? "停用" : "启用"}`);
    await refreshJobs();
  } catch (error) {
    showToast(`更新任务失败: ${error.message}`, true);
  }
}

async function runNow(jobId) {
  try {
    const payload = await apiRequest(`/api/scheduler/jobs/${jobId}/run-now`, { method: "POST", body: {} });
    showToast(
      `触发完成: ${payload.data?.accepted ? "accepted" : "rejected"} (${payload.data?.message || "-"})`
    );
    await refreshRuns();
    await refreshJobs();
  } catch (error) {
    showToast(`立即执行失败: ${error.message}`, true);
  }
}

async function deleteJob(jobId) {
  if (!window.confirm(`确认删除任务 ${jobId} ?`)) return;
  try {
    await apiRequest(`/api/scheduler/jobs/${jobId}`, { method: "DELETE" });
    showToast(`已删除任务 ${jobId}`);
    await refreshJobs();
    await refreshRuns();
  } catch (error) {
    showToast(`删除失败: ${error.message}`, true);
  }
}

function collectFormValues(form) {
  const formData = new FormData(form);
  return Object.fromEntries(formData.entries());
}

async function submitKeywordJob(event) {
  event.preventDefault();
  const values = collectFormValues(event.target);
  try {
    await apiRequest("/api/scheduler/jobs", {
      method: "POST",
      body: {
        name: values.name,
        job_type: "keyword",
        platform: values.platform,
        interval_minutes: Number(values.interval_minutes),
        enabled: true,
        payload: {
          keywords: values.keywords,
          save_option: values.save_option,
          safety_profile: values.safety_profile,
          headless: values.headless === "on",
        },
      },
    });
    showToast("关键词任务创建成功");
    event.target.reset();
    await refreshJobs();
  } catch (error) {
    showToast(`创建关键词任务失败: ${error.message}`, true);
  }
}

async function submitKolJob(event) {
  event.preventDefault();
  const values = collectFormValues(event.target);
  try {
    await apiRequest("/api/scheduler/jobs", {
      method: "POST",
      body: {
        name: values.name,
        job_type: "kol",
        platform: values.platform,
        interval_minutes: Number(values.interval_minutes),
        enabled: true,
        payload: {
          creator_ids: values.creator_ids,
          save_option: values.save_option,
          safety_profile: values.safety_profile,
          headless: values.headless === "on",
        },
      },
    });
    showToast("KOL 任务创建成功");
    event.target.reset();
    await refreshJobs();
  } catch (error) {
    showToast(`创建 KOL 任务失败: ${error.message}`, true);
  }
}

function renderPreview(records) {
  const head = document.getElementById("previewHead");
  const body = document.getElementById("previewBody");
  head.innerHTML = "";
  body.innerHTML = "";
  if (!Array.isArray(records) || records.length === 0) {
    head.innerHTML = "<tr><th>提示</th></tr>";
    body.innerHTML = "<tr><td class='muted'>暂无数据</td></tr>";
    return;
  }

  const columns = Array.from(
    records.reduce((set, row) => {
      Object.keys(row || {}).forEach((key) => set.add(key));
      return set;
    }, new Set())
  );
  const headRow = document.createElement("tr");
  columns.forEach((column) => {
    const th = document.createElement("th");
    th.textContent = column;
    headRow.appendChild(th);
  });
  head.appendChild(headRow);

  records.forEach((record) => {
    const tr = document.createElement("tr");
    columns.forEach((column) => {
      const td = document.createElement("td");
      const raw = record?.[column];
      td.textContent = raw === null || raw === undefined ? "" : String(raw);
      tr.appendChild(td);
    });
    body.appendChild(tr);
  });
}

async function submitPreview(event) {
  event.preventDefault();
  const values = collectFormValues(event.target);
  try {
    const payload = await apiRequest("/api/data/latest", {
      params: {
        platform: values.platform || undefined,
        file_type: values.file_type || undefined,
        preview: true,
        limit: Number(values.limit || 20),
      },
    });

    const data = payload.data || {};
    const file = data.file || {};
    const records = data.data || [];
    const total = data.total ?? records.length;
    document.getElementById("previewMeta").textContent = JSON.stringify(
      {
        file,
        total,
        shown: Array.isArray(records) ? records.length : 0,
      },
      null,
      2
    );
    renderPreview(Array.isArray(records) ? records : [records]);
  } catch (error) {
    showToast(`预览失败: ${error.message}`, true);
  }
}

function bindApiBase() {
  const input = document.getElementById("apiBase");
  const saved = localStorage.getItem("energycrawler_api_base") || "";
  input.value = saved;
  state.apiBase = normalizeApiBase(saved);

  document.getElementById("saveApiBaseBtn").addEventListener("click", async () => {
    state.apiBase = normalizeApiBase(input.value);
    localStorage.setItem("energycrawler_api_base", state.apiBase);
    showToast("API Base 已保存");
    await Promise.all([refreshJobs(), refreshRuns()]);
  });
}

async function init() {
  bindApiBase();
  document.getElementById("keywordJobForm").addEventListener("submit", submitKeywordJob);
  document.getElementById("kolJobForm").addEventListener("submit", submitKolJob);
  document.getElementById("previewForm").addEventListener("submit", submitPreview);
  document.getElementById("refreshJobsBtn").addEventListener("click", refreshJobs);
  document.getElementById("refreshRunsBtn").addEventListener("click", refreshRuns);
  await Promise.all([refreshJobs(), refreshRuns()]);
}

init().catch((error) => showToast(`初始化失败: ${error.message}`, true));
