# EnergyCrawler

面向 `xhs` 与 `x` 的 Energy-only 抓取工程。

## 项目定位

- 平台范围：`xhs`（小红书）、`x`（X / Twitter）
- 浏览器能力：统一通过 Energy 服务提供（gRPC）
- 运行入口：CLI + API
- 存储方式：`csv / json / db / sqlite / mongodb / excel / postgres`

## 架构

- 抓取执行：`main.py`
- API 服务：`api.main:app`
- 任务调度：`api/services/crawler_manager.py`
- 并发模型：队列 + worker 池

并发 worker 数由环境变量控制：

```bash
CRAWLER_MAX_WORKERS=2
CRAWLER_MAX_QUEUE_SIZE=100
CRAWLER_WORKER_SPAWN_MAX_RETRIES=2
CRAWLER_DISPATCH_RETRY_DELAY_SEC=2
```

集群模式下每个任务会自动分配独立 `ENERGYCRAWLER_BROWSER_ID`，确保并发抓取时浏览器会话隔离。

## 环境要求

- Python `3.11`
- `uv`
- Energy 服务（默认：`localhost:50051`）

## 快速开始

### 1. 安装依赖

```bash
uv sync
```

可选：先复制最小可用配置模板。

```bash
uv run energycrawler init
```

### 2. 启动 Energy 服务（推荐自动保活）

```bash
uv run energycrawler energy ensure
```

统一入口（等价命令）：

```bash
uv run energycrawler energy ensure
```

手动健康检查：

```bash
uv run python scripts/energy_service_healthcheck.py --host localhost --port 50051
```

XHS 签名运行时探针（检查 `window.mnsv2` 可用性）：

```bash
uv run python scripts/check_xhs_signature_runtime.py --host localhost --port 50051 --json
```

统一入口（等价命令）：

```bash
uv run energycrawler energy check --host localhost --port 50051
```

### 3. 配置参数

配置文件：`config/base_config.py`
环境变量文件：项目根目录 `.env`（会自动加载）

常用项：

- `PLATFORM = "xhs" | "x"`
- `CRAWLER_TYPE = "search" | "detail" | "creator"`
- `LOGIN_TYPE = "cookie"`（当前仅保留 Cookie 注入登录态）
- `ENERGY_SERVICE_ADDRESS = "localhost:50051"`
- X 平台鉴权：`TWITTER_AUTH_TOKEN`、`TWITTER_CT0`（也支持 `TWITTER_COOKIE` 自动提取并透传全量 Cookie）
- CookieCloud 自动同步：`COOKIECLOUD_ENABLED`、`COOKIECLOUD_SERVER`、`COOKIECLOUD_UUID`、`COOKIECLOUD_PASSWORD`
- Auth Watchdog：`AUTH_WATCHDOG_ENABLED`、`AUTH_WATCHDOG_MAX_RETRIES`（鉴权失败自动重试/刷新）
- 安全上限：`CRAWLER_HARD_MAX_NOTES_COUNT`、`CRAWLER_HARD_MAX_CONCURRENCY`、`CRAWLER_MIN_SLEEP_SEC`

登录后可把浏览器 Cookie 持久化到 `.env`：

```bash
uv run energycrawler auth export --platform all --xhs-browser-id manual_login_xhs --x-browser-id manual_login_x
```

统一入口（等价命令）：

```bash
uv run energycrawler auth export --platform all --xhs-browser-id manual_login_xhs --x-browser-id manual_login_x
```

登录态快速检查：

```bash
uv run energycrawler auth status --host localhost --port 50051
```

如需用 CookieCloud 持续维护登录态（支持 `xhs` / `x`）：

```bash
# .env 示例
COOKIECLOUD_ENABLED=true
COOKIECLOUD_SERVER=http://127.0.0.1:8088
COOKIECLOUD_UUID=你的UUID
COOKIECLOUD_PASSWORD=你的PASSWORD

# 可选：本地已有 COOKIES/TWITTER_COOKIE 时是否强制覆盖
COOKIECLOUD_FORCE_SYNC=false
```

开启后，CLI 与 API 任务在启动前都会自动尝试同步对应平台 Cookie；默认不覆盖本地已有登录态（除非 `COOKIECLOUD_FORCE_SYNC=true`）。

可选开启 Auth Watchdog（建议开启，默认开启）：

```bash
AUTH_WATCHDOG_ENABLED=true
AUTH_WATCHDOG_MAX_RETRIES=1
AUTH_WATCHDOG_RETRY_INTERVAL_SEC=2
AUTH_WATCHDOG_FORCE_COOKIECLOUD_SYNC=true
AUTH_WATCHDOG_MAX_RUNTIME_RECOVERIES=1
```

当运行中鉴权检查失败时，Watchdog 会自动触发 CookieCloud 刷新并重建客户端，再重试登录态验证。

统一入口（等价命令）：

```bash
uv run energycrawler auth status --host localhost --port 50051
```

推荐登录流（直接打开小红书登录页，在 Energy 内完成扫码/确认，再自动同步）：

```bash
uv run energycrawler auth xhs-open-login --api-base http://localhost:8080 --browser-id manual_login_xhs
```

如果你已经在 Energy 浏览器里登录了 XHS，也可直接同步该会话（无需再打开登录页）：

```bash
curl -s -X POST http://localhost:8080/api/auth/xhs/energy/sync \
  -H 'Content-Type: application/json' \
  -d '{"browser_id":"manual_login_xhs","verify_login":true}'
```

统一入口（等价命令）：

```bash
uv run energycrawler auth xhs-sync --api-base http://localhost:8080 --browser-id manual_login_xhs
```

XHS QR API 登录（备用方案）：

```bash
# 1) 创建登录会话
curl -s -X POST http://localhost:8080/api/auth/xhs/qr/session/start

# 2) 创建二维码（替换 session_id）
curl -s -X POST http://localhost:8080/api/auth/xhs/qr/session/<session_id>/qrcode

# 3) 扫码后轮询状态
curl -s http://localhost:8080/api/auth/xhs/qr/session/<session_id>/status

# 4) 如需手动结束会话
curl -s -X POST http://localhost:8080/api/auth/xhs/qr/session/<session_id>/cancel
```

也可以直接跑完整联调脚本（自动创建会话、生成二维码、轮询状态）：

```bash
uv run python scripts/xhs_qr_login_flow.py --api-base http://localhost:8080
```

统一入口（等价命令）：

```bash
uv run energycrawler auth xhs-qr-login --api-base http://localhost:8080
```

该脚本默认会把二维码页自动打开到对应 Energy 浏览器窗口，并提示扫码确认。
如不需要自动打开，可加 `--no-open-in-energy`。

服务拉起相关环境变量：

- `ENERGY_ENSURE_RETRIES`：最大重试次数（默认 `3`）
- `ENERGY_ENSURE_SLEEP_SEC`：重试间隔秒数（默认 `2`）
- `ENERGY_HEALTHCHECK_TIMEOUT`：单次检查超时（默认 `8` 秒）

签名运行时相关环境变量：

- `XHS_SIGNATURE_CANARY_ENABLED`：是否启用签名 runtime canary（默认 `false`）
- `XHS_SIGNATURE_CANARY_TIMEOUT_SEC`：canary 超时秒数（默认 `8`）
- `XHS_SIGNATURE_CANARY_BASELINE_PATH`：可选 baseline 路径（默认使用 `data/xhs/signature_runtime_baseline.json`）
- `XHS_SIGNATURE_SESSION_TTL_SEC`：签名会话状态 TTL（默认 `1800`）
- `XHS_SIGNATURE_FAILURE_THRESHOLD`：连续失败告警阈值（默认 `3`）

当 `XHS_SIGNATURE_CANARY_ENABLED=true` 时，API 入队 preflight 与 CLI 启动前检查都会执行签名 runtime canary。

### 4. setup / config show / doctor（建议先执行）

一键初始化（setup 向导，当前命令名为 `init`）：

```bash
# 首次使用推荐：
uv run energycrawler init --template .env.quickstart.example --check

# 已有 .env 且希望覆盖：
uv run energycrawler init --force --check
```

查看当前可选配置（当前版本暂未提供 `energycrawler config show` 子命令，可通过 API 查看）：

```bash
curl -s http://localhost:8080/api/config/platforms | jq .
curl -s http://localhost:8080/api/config/options | jq .
```

环境体检（doctor）：

```bash
# 全量检查：Energy 连通 + 登录态就绪
uv run energycrawler doctor

# 仅检查 Energy 连通（排查服务问题时更快）
uv run energycrawler doctor --skip-login-check --json
```

常见故障排查提示：

- `doctor` 报 `uv command not found`：先安装并配置 [uv](https://docs.astral.sh/uv/getting-started/installation/)
- `doctor` 报 Energy 健康检查失败：先执行 `uv run energycrawler energy ensure`
- `doctor` 报登录态失败：先执行 `uv run energycrawler auth status --json`，确认 Cookie/Token 有效

### 5. 运行 CLI

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
- `GET /api/data/files/{file_path}?preview=true&limit=20`：预览导出文件前 N 条
- `GET /api/data/download/{file_path}`：下载指定导出文件
- `GET /api/ws/logs`：实时日志 WebSocket（`ws://localhost:8080/api/ws/logs`）
- `GET /api/ws/status`：实时状态 WebSocket（`ws://localhost:8080/api/ws/status`）

`POST /api/crawler/start` 支持额外安全参数：

- `max_notes_count`：单任务最大抓取数量
- `crawl_sleep_sec`：请求间隔秒数

任务入队前会执行预检：

- Energy 服务连通性检查
- `x` 平台鉴权材料检查（`auth_token` + `ct0`）

### API 操作食谱（可直接复制）

查看 config（等价 `config show`）：

```bash
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

WebSocket 订阅实时日志/状态（浏览器控制台可直接运行）：

```javascript
const logsWs = new WebSocket("ws://localhost:8080/api/ws/logs");
logsWs.onmessage = (ev) => console.log("[logs]", ev.data);
logsWs.onopen = () => logsWs.send("ping");

const statusWs = new WebSocket("ws://localhost:8080/api/ws/status");
statusWs.onmessage = (ev) => console.log("[status]", JSON.parse(ev.data));
```

## 测试

```bash
uv run pytest -q tests
```

## 免责声明

本项目仅用于学习与研究，请遵守目标平台服务条款和适用法律法规。
