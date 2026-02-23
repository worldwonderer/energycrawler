# EnergyCrawler 使用方法（xhs + x）

当前仓库是精简版，只保留两个平台：

- `xhs`（小红书）
- `x`（X / Twitter）

签名与浏览器自动化基于 Energy 服务，不再提供旧平台兼容路径。

## 快速开始

### 1. 前置依赖

- Python `3.11`
- [uv](https://docs.astral.sh/uv/getting-started/installation)
- Energy 服务（默认 `localhost:50051`）

### 2. 安装依赖

```bash
cd EnergyCrawler
uv sync
uv run energycrawler init
```

### 3. 启动 Energy 服务

```bash
uv run energycrawler energy ensure
```

### 4. setup / config show / doctor（先做环境可用性确认）

```bash
# setup（一键向导）
uv run energycrawler setup

# config show（核心配置）
uv run energycrawler config show --simple

# doctor（全量体检）
uv run energycrawler doctor
```

### 4.1 极简 3 步（推荐）

```bash
uv run energycrawler setup
uv run energycrawler run --platform xhs --keywords 新能源
uv run energycrawler data latest --download
```

### 5. 运行爬虫

```bash
# xhs 关键词搜索
uv run energycrawler crawl -- --platform xhs --lt cookie --type search --keywords 编程副业,独立开发

# 简化模式（推荐）
uv run energycrawler run --platform xhs --keywords 编程副业,独立开发

# x 指定推文详情
uv run energycrawler crawl -- --platform x --lt cookie --type detail --specified_id 1890000000000000000

# 查看全部参数
uv run energycrawler crawl -- --help

# 一键环境体检
uv run energycrawler doctor

# 通过 API 快速预览/下载最新导出数据
uv run energycrawler data latest --platform xhs
uv run energycrawler data latest --download --platform x --output ./downloads/

# 严格清理报告（含旧命令/绝对路径/尾随空格）
uv run energycrawler cleanup-report --json
```

## API 服务

```bash
uv run uvicorn api.main:app --port 8080 --reload
```

访问接口文档：`http://localhost:8080/docs`。

### API 食谱（复制即用）

查看运行态健康快照（Energy / 登录态 / 队列）：

```bash
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
