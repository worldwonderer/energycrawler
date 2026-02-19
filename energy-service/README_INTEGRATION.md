# Energy Browser + EnergyCrawler 集成指南

## 概述

Energy 是一个基于 Go + CEF (Chromium Embedded Framework) 的浏览器自动化框架，可用于小红书等平台的签名生成和 Cookie 获取。

## 启动 Energy 服务

### 正确的启动方式

```bash
cd /Users/pite/EnergyCrawler/energy-service
bash start-macos.sh
```

若本机 `8001` 已被 HTTP 代理等程序占用，可显式指定调试端口：

```bash
cd /Users/pite/EnergyCrawler/energy-service
ENERGY_DEBUG_PORT=9222 bash start-macos.sh
```

**重要**: 必须使用 `start-macos.sh` 脚本启动，而不是直接运行二进制文件。该脚本会：
1. 处理 macOS 代码签名问题
2. 使用正确的 CEF 版本 (109)
3. 创建必要的 Helper 应用包

### 验证服务状态

```bash
# 检查进程
ps aux | grep energy-service | grep -v grep

# 检查端口
lsof -i :50051
```

服务启动后会监听 `localhost:50051` 端口。

## 核心功能

### 1. 浏览器创建与导航

```python
import grpc
from energy_client import browser_pb2, browser_pb2_grpc

channel = grpc.insecure_channel('localhost:50051')
stub = browser_pb2_grpc.BrowserServiceStub(channel)

# 创建浏览器
req = browser_pb2.CreateBrowserRequest(
    browser_id="xhs_browser",
    headless=False  # 调试时设为 False
)
resp = stub.CreateBrowser(req, timeout=30)

# 导航到页面
req = browser_pb2.NavigateRequest(
    browser_id="xhs_browser",
    url="https://www.xiaohongshu.com",
    timeout_ms=30000
)
resp = stub.Navigate(req, timeout=35)
```

### 2. 获取 Cookie (包括 HttpOnly)

```python
# 通过 gRPC 获取所有 Cookie（包括 HttpOnly）
req = browser_pb2.GetCookiesRequest(
    browser_id="xhs_browser",
    url="https://www.xiaohongshu.com"
)
resp = stub.GetCookies(req, timeout=10)
cookies = {c.name: c.value for c in resp.cookies}
```

重要 Cookie：
- `a1`: 设备标识，用于签名
- `web_session`: 登录态
- `webId`: 用户标识
- `gid`: 全局标识

### 3. 获取 b1 值 (localStorage)

```python
req = browser_pb2.ExecuteJSRequest(
    browser_id="xhs_browser",
    script="window.localStorage.getItem('b1')"
)
resp = stub.ExecuteJS(req, timeout=10)
b1 = resp.result.strip('"') if resp.success and resp.result else ""
```

### 4. 生成签名 (mnsv2)

```python
import hashlib
import json
import base64

# 1. 构建签名字符串
uri = "/api/sns/web/v1/search/notes"
data = {"keyword": "美食", "page": 1, "page_size": 20, ...}
sign_str = uri + json.dumps(data, separators=(",", ":"), ensure_ascii=False)

# 2. 计算 MD5
md5_str = hashlib.md5(sign_str.encode("utf-8")).hexdigest()

# 3. 调用 mnsv2
sign_str_escaped = sign_str.replace("\\", "\\\\").replace("'", "\\'")
script = f"window.mnsv2('{sign_str_escaped}', '{md5_str}')"
req = browser_pb2.ExecuteJSRequest(browser_id="xhs_browser", script=script)
resp = stub.ExecuteJS(req, timeout=10)
x3_value = resp.result.strip('"') if resp.success else ""
```

### 5. 构建完整的签名头

```python
def b64_encode(data):
    return base64.b64encode(data).decode('utf-8')

def encode_utf8(s):
    return s.encode('utf-8') if isinstance(s, str) else s

# 构建 x-s
x_s = "XYS_" + b64_encode(encode_utf8(json.dumps({
    "x0": "4.2.1",
    "x1": "xhs-pc-web",
    "x2": "Mac OS",
    "x3": x3_value,  # mnsv2 返回值
    "x4": "object"
}, separators=(",", ":"))))

# 构建 x-t (时间戳)
x_t = str(int(time.time() * 1000))

# 构建 x-s-common
x_s_common = b64_encode(encode_utf8(json.dumps({
    "s0": 3,
    "s1": "",
    "x0": "1",
    "x1": "4.2.2",
    "x2": "Mac OS",
    "x3": "xhs-pc-web",
    "x4": "4.74.0",
    "x5": a1,        # cookie 中的 a1
    "x6": x_t,
    "x7": x_s,
    "x8": b1,        # localStorage 中的 b1
    "x9": mrc(x_t + x_s + b1),  # 简单哈希
    "x10": 154,
    "x11": "normal"
}, separators=(",", ":"))))
```

### 6. 发送 API 请求

```python
import urllib.request

cookie_str = "; ".join([f"{k}={v}" for k, v in cookies.items()])

headers = {
    "accept": "application/json, text/plain, */*",
    "accept-language": "zh-CN,zh;q=0.9",
    "content-type": "application/json;charset=UTF-8",
    "origin": "https://www.xiaohongshu.com",
    "referer": "https://www.xiaohongshu.com/",
    "user-agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
    "Cookie": cookie_str,
    "X-s": x_s,
    "X-t": x_t,
    "x-S-Common": x_s_common,
    "X-B3-Traceid": get_trace_id(),
}

api_url = "https://edith.xiaohongshu.com/api/sns/web/v1/search/notes"
body = json.dumps(data, separators=(",", ":"), ensure_ascii=False).encode('utf-8')

req = urllib.request.Request(api_url, data=body, headers=headers, method='POST')
resp = urllib.request.urlopen(req, timeout=15)
result = json.loads(resp.read().decode())
```

## 常见问题

### 1. SIGSEGV 崩溃

**原因**: 直接运行二进制文件时，CEF 子进程没有正确代码签名。

**解决**: 使用 `bash start-macos.sh` 启动。

### 2. gRPC 超时

**原因**: 浏览器实例不存在或已关闭。

**解决**: 确保在发送请求前创建浏览器并导航到小红书页面。

### 3. API 返回 code=300011 (账号风控)

**原因**:
- 可能是请求格式不正确
- 也可能是账号被风控

**排查**:
1. 先确认签名构建是否正确
2. 检查请求头是否完整
3. 尝试在浏览器中手动操作看是否正常

### 4. window.Browser() 返回 nil

**原因**: 在共享窗口模式下，`window.Browser()` 可能返回 nil。

**解决**: 使用 `window.Chromium()` 直接执行 JavaScript。

## 文件结构

```
energy-service/
├── main.go                 # 主程序入口
├── start-macos.sh          # macOS 启动脚本 (重要!)
├── browser/
│   ├── manager.go          # 浏览器管理
│   ├── javascript.go       # JS 执行和签名
│   └── cookie.go           # Cookie 处理
├── proto/
│   └── browser.proto       # gRPC 协议定义
└── server/
    └── browser_server.go   # gRPC 服务实现

energy_client/              # Python 客户端
├── browser_interface.py    # 高层接口
├── browser_pb2.py          # protobuf 生成的代码
└── browser_pb2_grpc.py     # gRPC 客户端代码

media_platform/xhs/
├── energy_client_adapter.py  # Energy 适配器 (与 EnergyCrawler 集成)
└── xhs_sign.py               # 签名工具函数
```

## 配置项

在 `config/base_config.py` 中：

```python
# 启用 Energy 浏览器
ENABLE_ENERGY_BROWSER = True

# Energy 服务地址
ENERGY_SERVICE_ADDRESS = "localhost:50051"

# 浏览器 ID 前缀
ENERGY_BROWSER_ID_PREFIX = "energycrawler"

# 是否无头模式
ENERGY_HEADLESS = False  # 调试时设为 False
```

## 成功验证

成功的 API 响应：

```json
{
  "success": true,
  "data": {
    "items": [
      {
        "note_card": {
          "display_title": "笔记标题...",
          ...
        }
      }
    ]
  }
}
```

## 注意事项

1. **必须先导航到小红书页面** 才能执行签名，因为 mnsv2 函数是在小红书页面 JS 中定义的
2. **b1 值** 需要从 localStorage 获取，用于 x-s-common 签名
3. **请求头大小写** 注意 `X-s` vs `x-s`，保持一致
4. **JSON 序列化** 使用 `separators=(",", ":")` 确保紧凑格式
5. **时间戳** x-t 使用毫秒级时间戳
