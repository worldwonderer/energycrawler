# EnergyCrawler

面向 `xhs` 与 `x` 的 Energy-only 抓取工程。

## 10 分钟 Quickstart（首选）

```bash
# 1) 安装核心依赖
uv sync

# 2) 一键上手（环境检查 + 最小配置 + Energy 检查 + 引导流程）
uv run energycrawler quickstart
```

> 若当前分支尚未包含 `quickstart` 子命令，请先使用下方“兼容路径（旧命令）”。

## 安装路径（core / optional）

默认安装核心能力（可完成 xhs/x 基础抓取）：

```bash
uv sync
# 或
uv pip install -r requirements-core.txt
```

按能力追加可选依赖：

```bash
# Excel 导出
uv sync --extra excel

# PostgreSQL 存储
uv sync --extra postgres

# 开发/测试工具
uv sync --extra dev

# 兼容旧方式：一次装全
uv pip install -r requirements.txt
```

## 三种官方路径（按场景三选一）

### A) 本地最简（推荐）

```bash
uv sync
uv run energycrawler quickstart
uv run energycrawler status
uv run energycrawler run --platform xhs --keywords 新能源
```

### B) Docker 路径（无本地 Python 环境）

```bash
docker run --rm -it \
  -p 8080:8080 \
  -v "$PWD":/workspace \
  -w /workspace \
  python:3.11-slim bash -lc '
    pip install -U pip uv &&
    uv sync &&
    uv run uvicorn api.main:app --host 0.0.0.0 --port 8080
  '
```

启动后可在宿主机访问：`http://localhost:8080/ui`。

### C) 远程 Energy 服务路径

```bash
# 指向远程 Energy
export ENERGY_SERVICE_ADDRESS="<remote-host>:50051"

uv sync
uv run energycrawler doctor --skip-login-check
uv run energycrawler status
uv run energycrawler run --platform x --keywords "open source"
```

## 兼容路径（旧命令保留）

如果你更熟悉旧流程，仍可按以下方式执行（与 quickstart 并存）：

```bash
uv run energycrawler init --template .env.quickstart.example --check
uv run energycrawler energy ensure
uv run energycrawler auth xhs-open-login --api-base http://localhost:8080
uv run energycrawler config env --mode core
uv run energycrawler doctor
```

详细环境变量、登录与排障说明见：`docs/index.md`、`docs/常见问题.md`。

## 运行 CLI（进阶）

推荐先用简化命令：

```bash
uv run energycrawler run --platform xhs --keywords 编程副业,独立开发
uv run energycrawler run --platform x --keywords "open source" --safety-profile safe
```

小红书关键词抓取：

```bash
uv run energycrawler crawl -- --platform xhs --lt cookie --type search --keywords 编程副业,独立开发
```

小批量安全测试（限制数量 + 增加间隔）：

```bash
uv run energycrawler crawl -- --platform xhs --lt cookie --type search --keywords 新能源 --max_notes_count 3 --crawl_sleep_sec 12
```

小红书详情抓取：

```bash
uv run energycrawler crawl -- --platform xhs --lt cookie --type detail --specified_id "https://www.xiaohongshu.com/explore/xxxx?xsec_token=xxxx"
```

X 关键词抓取：

```bash
uv run energycrawler crawl -- --platform x --lt cookie --type search --keywords "open source"
```

X 指定推文抓取：

```bash
uv run energycrawler crawl -- --platform x --lt cookie --type detail --specified_id "1890000000000000000"
```

X 创作者抓取：

```bash
uv run energycrawler crawl -- --platform x --lt cookie --type creator --creator_id "elonmusk"
```

增量抓取 / 断点续爬（支持按 checkpoint 抓新增内容）：

```bash
# 开启增量 + 断点续爬（默认 checkpoint: data/checkpoints/crawl_state.json）
uv run energycrawler crawl -- --platform xhs --lt cookie --type creator --creator_id "<creator_url>" --incremental true --resume_checkpoint true

# 指定 checkpoint 文件
uv run energycrawler crawl -- --platform x --lt cookie --type creator --creator_id "elonmusk" --incremental true --checkpoint_path "/tmp/energycrawler_checkpoints/state.json"
```

查看参数：

```bash
uv run energycrawler crawl -- --help
```

快速查看/下载最新导出数据（通过 API）：

```bash
# 先列出可用导出文件（按更新时间倒序）
uv run energycrawler data list --platform xhs --limit 20

# 预览最新文件摘要
uv run energycrawler data latest --platform xhs

# 下载最新文件到指定目录
uv run energycrawler data latest --download --platform x --output ./downloads/
```

一键体检（服务连通 + 登录态就绪）：

```bash
uv run energycrawler doctor
```

输出严格清理报告（未引用文档图片、疑似历史汇总文档、旧命令、绝对路径、尾随空格）：

```bash
uv run energycrawler cleanup-report --json
```

## API

启动 API：

```bash
uv run uvicorn api.main:app --port 8080 --reload
```

启动后可访问：

- OpenAPI 文档：`http://localhost:8080/docs`
- Web UI 控制台：`http://localhost:8080/ui`

常用接口：

- `POST /api/crawler/start`：提交任务
- `POST /api/crawler/stop`：停止全部任务并清空队列
- `GET /api/crawler/status`：获取状态
- `GET /api/crawler/cluster`：查看队列与 worker 快照
- `GET /api/crawler/logs`：查看日志
- `POST /api/auth/xhs/qr/session/start`：启动 XHS QR 登录会话
- `POST /api/auth/xhs/qr/session/{session_id}/qrcode`：生成二维码
- `GET /api/auth/xhs/qr/session/{session_id}/status`：轮询扫码状态
- `POST /api/auth/xhs/qr/session/{session_id}/cancel`：结束登录会话
- `POST /api/auth/xhs/energy/sync`：同步已登录 Energy 会话到 `.env` 的 `COOKIES`
- `GET /api/config/platforms`：查看支持的平台列表（config show）
- `GET /api/config/options`：查看可选登录类型/抓取模式/存储方式（config show）
- `GET /api/data/files`：按更新时间倒序列出导出文件
- `GET /api/data/latest`：获取最新文件（默认预览）
- `GET /api/data/latest/download`：下载最新文件
- `GET /api/data/files/{file_path}?preview=true&limit=20`：预览导出文件前 N 条
- `GET /api/data/download/{file_path}`：下载指定导出文件
- `GET /api/health/runtime`：查看运行态健康快照（Energy / 登录态 / 队列）
- `GET /api/ws/logs`：实时日志 WebSocket（`ws://localhost:8080/api/ws/logs`）
- `GET /api/ws/status`：实时状态 WebSocket（`ws://localhost:8080/api/ws/status`）
- `POST /api/scheduler/jobs`：创建调度任务（`keyword` / `kol`）
- `GET /api/scheduler/jobs`：查看调度任务列表
- `PATCH /api/scheduler/jobs/{job_id}`：更新调度任务（启停/间隔/payload）
- `DELETE /api/scheduler/jobs/{job_id}`：删除调度任务
- `POST /api/scheduler/jobs/{job_id}/run-now`：立即执行一次调度任务
- `GET /api/scheduler/runs`：查看调度执行历史
- `GET /api/scheduler/status`：查看调度器运行状态

`POST /api/crawler/start` 支持额外安全参数：

- `safety_profile`：安全预设（`safe` / `balanced` / `aggressive`）
- `max_notes_count`：单任务最大抓取数量
- `crawl_sleep_sec`：请求间隔秒数

说明：当 `safety_profile` 与 `max_notes_count` / `crawl_sleep_sec` 同时提供时，显式参数优先。

任务入队前会执行预检：

- Energy 服务连通性检查
- `x` 平台鉴权材料检查（`auth_token` + `ct0`）

### API 操作食谱（可直接复制）

查看 config：

```bash
# CLI 核心配置视图（推荐）
uv run energycrawler config show --simple

# API 配置选项
curl -s http://localhost:8080/api/config/platforms | jq .
curl -s http://localhost:8080/api/config/options | jq .
```

下载“最新导出数据”（先取最新文件，再预览，再下载）：

```bash
LATEST_FILE=$(curl -s http://localhost:8080/api/data/files | jq -r '.data.files[0].path')
echo "latest file: $LATEST_FILE"

# 预览前 20 条
curl -s "http://localhost:8080/api/data/files/${LATEST_FILE}?preview=true&limit=20" | jq .

# 下载完整文件到当前目录
curl -L "http://localhost:8080/api/data/download/${LATEST_FILE}" -o "./latest-$(basename "$LATEST_FILE")"
```

直接使用 latest 接口（无需先列出 files）：

```bash
# 预览最新 20 条
curl -s "http://localhost:8080/api/data/latest?platform=xhs&preview=true&limit=20" | jq .

# 下载最新文件
curl -L "http://localhost:8080/api/data/latest/download?platform=xhs" -o "./latest-xhs.dat"
```

查看运行态健康快照：

```bash
# CLI 统一状态快照（推荐）
uv run energycrawler status --json

# 直接调用 API
curl -s http://localhost:8080/api/health/runtime | jq .
```

WebSocket 订阅实时日志/状态（浏览器控制台可直接运行）：

```javascript
const logsWs = new WebSocket("ws://localhost:8080/api/ws/logs");
logsWs.onmessage = (ev) => console.log("[logs]", ev.data);
logsWs.onopen = () => logsWs.send("ping");

const statusWs = new WebSocket("ws://localhost:8080/api/ws/status");
statusWs.onmessage = (ev) => console.log("[status]", JSON.parse(ev.data));
```

关键词/KOL 自动调度（固定间隔）：

```bash
# 可选：调度器运行参数
# SCHEDULER_ENABLED=true
# SCHEDULER_POLL_INTERVAL_SEC=10
# SCHEDULER_DB_PATH=./data/scheduler/scheduler.db

# 创建关键词调度任务（每 30 分钟）
curl -s -X POST http://localhost:8080/api/scheduler/jobs \
  -H "Content-Type: application/json" \
  -d '{
    "name":"xhs-新能源关键词",
    "job_type":"keyword",
    "platform":"xhs",
    "interval_minutes":30,
    "enabled":true,
    "payload":{
      "keywords":"新能源,储能",
      "save_option":"json",
      "safety_profile":"balanced",
      "headless":false
    }
  }' | jq .

# 创建 KOL 调度任务（每 60 分钟）
curl -s -X POST http://localhost:8080/api/scheduler/jobs \
  -H "Content-Type: application/json" \
  -d '{
    "name":"x-kol-creator",
    "job_type":"kol",
    "platform":"x",
    "interval_minutes":60,
    "enabled":true,
    "payload":{
      "creator_ids":"elonmusk",
      "save_option":"json",
      "safety_profile":"safe",
      "headless":false
    }
  }' | jq .

# 查看任务与运行历史
curl -s http://localhost:8080/api/scheduler/jobs | jq .
curl -s http://localhost:8080/api/scheduler/runs?limit=20 | jq .
```

一键跑“关键词 + KOL”调度冒烟（自动创建临时任务、触发 run-now、轮询完成、校验数据变化并默认清理任务）：

```bash
uv run energycrawler scheduler smoke-e2e --platform xhs

# 查看完整 JSON 报告
uv run energycrawler scheduler smoke-e2e --platform xhs --json
```

## 测试

```bash
uv run pytest -q tests
```

## 免责声明

本项目仅用于学习与研究，请遵守目标平台服务条款和适用法律法规。
