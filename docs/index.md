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
```

### 3. 启动 Energy 服务

```bash
bash energy-service/start-macos.sh
```

### 4. 运行爬虫

```bash
# xhs 关键词搜索
uv run main.py --platform xhs --lt qrcode --type search --keywords 编程副业,独立开发

# x 指定推文详情
uv run main.py --platform x --lt cookie --type detail --specified_id 1890000000000000000

# 查看全部参数
uv run main.py --help
```

## API 服务

```bash
uv run uvicorn api.main:app --port 8080 --reload
```

访问接口文档：`http://localhost:8080/docs`。

## 数据保存

支持：`csv / json / excel / sqlite / db(mysql) / postgres / mongodb`

参考：
- [数据保存指南](data_storage_guide.md)
- [Excel 导出指南](excel_export_guide.md)

## 进阶文档

- [项目代码结构](项目代码结构.md)
- [项目架构文档](项目架构文档.md)

## 免责声明

仅供学习和研究使用，请遵守目标平台服务条款与法律法规。禁止用于商业化和非法用途。
