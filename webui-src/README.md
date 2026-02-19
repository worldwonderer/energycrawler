# WebUI Source

`webui-src` 是 WebUI 前端源码目录（source-of-truth）。

- 开发/构建产物目标：`webui-src/dist`
- API 服务静态目录：`api/webui`
- 同步命令：`bash scripts/sync_webui_assets.sh`

说明：
- 当前仓库已包含一份可运行的 `api/webui` 静态资源。
- 当你更新前端源码后，先构建出 `webui-src/dist`，再用同步脚本覆盖 `api/webui`。
