# Energy Cluster (Simplified)

当前实现采用精简架构，不再拆分 Master / Watcher 两个独立进程：

1. `HTTP API` (`api/routers/crawler.py`)
2. `CrawlerManager` (`api/services/crawler_manager.py`)
3. `Worker`（每个 worker 是一个 `uv run python main.py ...` 子进程）

## 设计目标

- 先把多任务并发能力落地，再考虑跨机分布式与容器编排。
- 在不破坏现有 API 接口的前提下，支持任务队列与 worker 池。

## 运行机制

- `/api/crawler/start`：接收任务并入队，空闲 worker 会立即拉取执行。
- `/api/crawler/stop`：停止所有运行中的 worker，并清空排队任务。
- `/api/crawler/status`：返回总体状态 + worker/queue 指标。
- `/api/crawler/cluster`：返回详细集群快照（调试用）。

## 配置

- `CRAWLER_MAX_WORKERS`：worker 池大小，默认 `2`，范围 `1~16`。
- `CRAWLER_MAX_QUEUE_SIZE`：队列上限，默认 `100`，超限后 `/start` 会拒绝新任务。

## 浏览器集群接入

- 调度器会为每个任务注入独立环境变量 `ENERGYCRAWLER_BROWSER_ID`。
- 浏览器 ID 规则：`{ENERGY_BROWSER_ID_PREFIX}_{platform}_w{worker_id}_{task_id}`。
- 爬虫进程会优先使用该运行时 ID，确保多 worker 并发时浏览器会话隔离，避免 Cookie/页面状态串扰。
