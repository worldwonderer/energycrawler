# EnergyCrawler 使用方法（xhs + x）

当前仓库仅保留两个平台：`xhs`（小红书）、`x`（X / Twitter）。
签名与浏览器自动化统一依赖 Energy 服务。

## 10 分钟 Quickstart（首选）

```bash
# 1) 安装核心依赖
uv sync

# 2) 一键上手（推荐）
uv run energycrawler quickstart
```

> 若当前分支尚未包含 `quickstart` 子命令，请改用下方“兼容路径（旧命令）”。

## 依赖安装：core 与 optional

核心能力（xhs/x 基础抓取）：

```bash
uv sync
# 或
uv pip install -r requirements-core.txt
```

可选能力按需追加：

```bash
# Excel 导出
uv sync --extra excel

# PostgreSQL 存储
uv sync --extra postgres

# 开发/测试
uv sync --extra dev

# 兼容旧方式：安装全量依赖
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

### C) 远程 Energy 服务路径

```bash
export ENERGY_SERVICE_ADDRESS="<remote-host>:50051"
uv sync
uv run energycrawler doctor --skip-login-check
uv run energycrawler run --platform x --keywords "open source"
```

## 兼容路径（旧命令）

```bash
uv run energycrawler init --template .env.quickstart.example --check
uv run energycrawler energy ensure
uv run energycrawler auth xhs-open-login --api-base http://localhost:8080
uv run energycrawler config env --mode core
uv run energycrawler doctor
```

## 常用运行命令

```bash
# 简化模式（推荐）
uv run energycrawler run --platform xhs --keywords 编程副业,独立开发

# 兼容旧命令（保留）
uv run energycrawler crawl -- --platform xhs --lt cookie --type search --keywords 编程副业,独立开发

# 查看运行态与导出数据
uv run energycrawler status
uv run energycrawler data list --platform xhs --limit 20
uv run energycrawler data latest --download
```

## API 服务

```bash
uv run uvicorn api.main:app --port 8080 --reload
```

访问接口文档：`http://localhost:8080/docs`。  
访问 Web UI 控制台：`http://localhost:8080/ui`。

> 说明：CLI 运行时会为每次任务自动生成独立 `ENERGYCRAWLER_BROWSER_ID`，默认隔离 xhs/x 浏览器会话。

### API 食谱（复制即用）

查看运行态健康快照（Energy / 登录态 / 队列）：

```bash
uv run energycrawler status --json
curl -s http://localhost:8080/api/health/runtime | jq .
```

下载“最新导出文件”：

```bash
LATEST_FILE=$(curl -s http://localhost:8080/api/data/files | jq -r '.data.files[0].path')
curl -s "http://localhost:8080/api/data/files/${LATEST_FILE}?preview=true&limit=20" | jq .
curl -L "http://localhost:8080/api/data/download/${LATEST_FILE}" -o "./latest-$(basename "$LATEST_FILE")"
```

直接调用 latest 接口：

```bash
curl -s "http://localhost:8080/api/data/latest?platform=xhs&preview=true&limit=20" | jq .
curl -L "http://localhost:8080/api/data/latest/download?platform=xhs" -o ./latest-xhs.dat
```

带 safety_profile 的启动示例：

```bash
curl -s -X POST http://localhost:8080/api/crawler/start \
  -H "Content-Type: application/json" \
  -d '{
    "platform":"xhs",
    "crawler_type":"search",
    "login_type":"cookie",
    "keywords":"新能源",
    "save_option":"json",
    "safety_profile":"balanced"
  }' | jq .
```

WebSocket 实时日志/状态订阅（浏览器控制台）：

```javascript
const logsWs = new WebSocket("ws://localhost:8080/api/ws/logs");
logsWs.onmessage = (ev) => console.log("[logs]", ev.data);
logsWs.onopen = () => logsWs.send("ping");

const statusWs = new WebSocket("ws://localhost:8080/api/ws/status");
statusWs.onmessage = (ev) => console.log("[status]", JSON.parse(ev.data));
```

## 数据保存

支持：`csv / json / excel / sqlite / db(mysql) / postgres / mongodb`

参考：
- [数据保存指南](data_storage_guide.md)
- [Excel 导出指南](excel_export_guide.md)
- [xhs/x 字段对照清单（creator）](field_mapping_xhs_x.md)

## 进阶文档

- [项目代码结构](项目代码结构.md)
- [项目架构文档](项目架构文档.md)

## 免责声明

仅供学习和研究使用，请遵守目标平台服务条款与法律法规。禁止用于商业化和非法用途。
