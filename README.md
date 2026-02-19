# EnergyCrawler (xhs + x)

一个面向自用场景的精简版 EnergyCrawler，仅保留两个站点：
- `xhs` (小红书)
- `x` (X / Twitter)

当前分支已经移除 `douyin / kuaishou / bilibili / weibo / tieba / zhihu` 相关爬虫与存储实现，不再做向后兼容。

## 当前定位

- 目标：稳定抓取 `xhs` 与 `x`，减少维护面
- 签名方案：`xhs` 签名通过 Energy 获取（不再使用 `playwright_sign` 兜底）
- 运行方式：CLI + WebUI
- 存储方式：`csv / json / db / sqlite / mongodb / excel / postgres`

## 关键变化

- 平台枚举已收敛为：`xhs | x`
- 主入口 `CrawlerFactory` 仅保留 `xhs` 与 `x`（兼容 `twitter` 别名）
- 已删除非目标平台目录：
  - `media_platform/{douyin,kuaishou,bilibili,weibo,tieba,zhihu}`
  - `store/{douyin,kuaishou,bilibili,weibo,tieba,zhihu}`
  - `config/{dy_config,ks_config,bilibili_config,weibo_config,tieba_config,zhihu_config}.py`
- API 平台配置接口仅返回 `xhs` 与 `x`

## 环境要求

- Python `3.11`
- `uv`（依赖安装与运行）
- Energy 服务（默认地址：`localhost:50051`）

可选：
- Node.js（只在你需要前端开发/重建 WebUI 时使用）

## 快速开始

### 1. 安装依赖

```bash
uv sync
```

### 2. 启动 Energy 服务

默认配置在 `config/base_config.py`：
- `ENABLE_ENERGY_BROWSER = True`
- `ENERGY_SERVICE_ADDRESS = "localhost:50051"`

macOS 可直接使用：

```bash
bash energy-service/start-macos.sh
```

### 3. 配置账号与抓取参数

编辑 `config/base_config.py`（和必要的环境变量）例如：
- 平台：`PLATFORM = "xhs"` 或 `PLATFORM = "x"`
- 抓取模式：`CRAWLER_TYPE = "search" | "detail" | "creator"`
- 登录方式：`LOGIN_TYPE = "qrcode" | "cookie" | "phone"`
- X 站点常用：`TWITTER_AUTH_TOKEN`、`TWITTER_CT0`

### 4. 运行 CLI

小红书关键词抓取：

```bash
uv run main.py --platform xhs --lt qrcode --type search --keywords 编程副业,独立开发
```

小红书详情抓取：

```bash
uv run main.py --platform xhs --lt qrcode --type detail --specified_id "https://www.xiaohongshu.com/explore/xxxx?xsec_token=xxxx"
```

X 关键词抓取：

```bash
uv run main.py --platform x --lt cookie --type search --keywords "open source"
```

X 指定推文抓取：

```bash
uv run main.py --platform x --lt cookie --type detail --specified_id "1890000000000000000"
```

X 创作者抓取：

```bash
uv run main.py --platform x --lt cookie --type creator --creator_id "elonmusk"
```

查看全部参数：

```bash
uv run main.py --help
```

## WebUI

启动 API + WebUI：

```bash
uv run uvicorn api.main:app --port 8080 --reload
```

打开：`http://localhost:8080`

## 常见问题

1. `xhs` 接口签名失败
- 确认 Energy 服务已启动并监听 `50051`
- 确认 `ENABLE_ENERGY_BROWSER=True`
- 确认 `XHS_ENABLE_ENERGY=True`

2. X 抓取返回鉴权错误
- 检查 `TWITTER_AUTH_TOKEN` 是否有效
- 必要时补充 `TWITTER_CT0`
- 先在浏览器确认账号可正常访问目标内容

3. `--platform` 报错
- 当前仅支持 `xhs` 与 `x`（`twitter` 作为代码别名，不建议 CLI 使用）

## 测试

```bash
uv run pytest -q tests
```

当前基线：`37 passed, 55 skipped`（本地环境）。

## 免责声明

本项目仅用于个人学习与技术研究，请遵守目标平台服务条款和相关法律法规。禁止用于商业化和非法用途。
