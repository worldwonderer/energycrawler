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
```

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
python3 scripts/energy_service_cli.py ensure
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
python3 scripts/energy_service_cli.py check --host localhost --port 50051
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
- 安全上限：`CRAWLER_HARD_MAX_NOTES_COUNT`、`CRAWLER_HARD_MAX_CONCURRENCY`、`CRAWLER_MIN_SLEEP_SEC`

登录后可把浏览器 Cookie 持久化到 `.env`：

```bash
uv run energycrawler auth export --platform all --xhs-browser-id manual_login_xhs --x-browser-id manual_login_x
```

统一入口（等价命令）：

```bash
python3 scripts/auth_cli.py export --platform all --xhs-browser-id manual_login_xhs --x-browser-id manual_login_x
```

登录态快速检查：

```bash
uv run energycrawler auth status --host localhost --port 50051
```

统一入口（等价命令）：

```bash
python3 scripts/auth_cli.py status --host localhost --port 50051
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

### 4. 运行 CLI

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

查看参数：

```bash
uv run energycrawler crawl -- --help
```

一键体检（服务连通 + 登录态就绪）：

```bash
uv run energycrawler doctor
```

输出清理候选报告（未引用文档图片/疑似历史汇总文档）：

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

`POST /api/crawler/start` 支持额外安全参数：

- `max_notes_count`：单任务最大抓取数量
- `crawl_sleep_sec`：请求间隔秒数

任务入队前会执行预检：

- Energy 服务连通性检查
- `x` 平台鉴权材料检查（`auth_token` + `ct0`）

## 测试

```bash
uv run pytest -q tests
```

## 免责声明

本项目仅用于学习与研究，请遵守目标平台服务条款和适用法律法规。
