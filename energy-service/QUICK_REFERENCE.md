# Energy + EnergyCrawler 快速参考

## 一、启动 Energy 服务

```bash
cd /Users/pite/EnergyCrawler/energy-service && bash start-macos.sh
```

验证：`lsof -i :50051`

## 二、完整测试脚本

```python
#!/usr/bin/env python3
import grpc, sys, time, json, hashlib, base64, urllib.request
sys.path.insert(0, '/Users/pite/EnergyCrawler')
from energy_client import browser_pb2, browser_pb2_grpc

# 连接
channel = grpc.insecure_channel('localhost:50051')
stub = browser_pb2_grpc.BrowserServiceStub(channel)
BROWSER_ID = "xhs_test"

# 创建浏览器
stub.CreateBrowser(browser_pb2.CreateBrowserRequest(browser_id=BROWSER_ID, headless=False), timeout=30)

# 导航
stub.Navigate(browser_pb2.NavigateRequest(browser_id=BROWSER_ID, url="https://www.xiaohongshu.com", timeout_ms=30000), timeout=35)
time.sleep(3)

# 获取 Cookie
resp = stub.GetCookies(browser_pb2.GetCookiesRequest(browser_id=BROWSER_ID, url="https://www.xiaohongshu.com"), timeout=10)
cookies = {c.name: c.value for c in resp.cookies}
cookie_str = "; ".join([f"{k}={v}" for k, v in cookies.items()])
a1 = cookies.get('a1', '')

# 获取 b1
resp = stub.ExecuteJS(browser_pb2.ExecuteJSRequest(browser_id=BROWSER_ID, script="window.localStorage.getItem('b1')"), timeout=10)
b1 = resp.result.strip('"') if resp.success else ""

# 构建签名
def b64(s): return base64.b64encode(s.encode() if isinstance(s, str) else s).decode()
def mrc(s): return hashlib.sha256(s.encode()).hexdigest()[:16]

uri = "/api/sns/web/v1/search/notes"
data = {"keyword": "美食", "page": 1, "page_size": 20, "search_id": str(int(time.time()*1000)), "sort": "general", "note_type": 0}
sign_str = uri + json.dumps(data, separators=(",", ":"), ensure_ascii=False)
md5_str = hashlib.md5(sign_str.encode()).hexdigest()

# 调用 mnsv2
escaped = sign_str.replace("\\", "\\\\").replace("'", "\\'")
resp = stub.ExecuteJS(browser_pb2.ExecuteJSRequest(browser_id=BROWSER_ID, script=f"window.mnsv2('{escaped}', '{md5_str}')"), timeout=10)
x3 = resp.result.strip('"') if resp.success else ""

x_s = "XYS_" + b64(json.dumps({"x0":"4.2.1","x1":"xhs-pc-web","x2":"Mac OS","x3":x3,"x4":"object"}, separators=(",", ":")))
x_t = str(int(time.time() * 1000))
x_s_common = b64(json.dumps({"s0":3,"s1":"","x0":"1","x1":"4.2.2","x2":"Mac OS","x3":"xhs-pc-web","x4":"4.74.0","x5":a1,"x6":x_t,"x7":x_s,"x8":b1,"x9":mrc(x_t+x_s+b1),"x10":154,"x11":"normal"}, separators=(",", ":")))

# 发送请求
headers = {
    "accept": "application/json, text/plain, */*",
    "content-type": "application/json;charset=UTF-8",
    "origin": "https://www.xiaohongshu.com",
    "referer": "https://www.xiaohongshu.com/",
    "user-agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
    "Cookie": cookie_str,
    "X-s": x_s, "X-t": x_t, "x-S-Common": x_s_common, "X-B3-Traceid": "".join(__import__('random').choices('0123456789abcdef', k=32))
}
body = json.dumps(data, separators=(",", ":"), ensure_ascii=False).encode()
req = urllib.request.Request(f"https://edith.xiaohongshu.com{uri}", data=body, headers=headers, method='POST')
resp = urllib.request.urlopen(req, timeout=15)
result = json.loads(resp.read().decode())

# 输出结果
if result.get('success'):
    notes = [i for i in result.get('data', {}).get('items', []) if i.get('note_card')]
    print(f"成功! 找到 {len(notes)} 条笔记")
else:
    print(f"失败: code={result.get('code')}, msg={result.get('msg')}")
```

## 三、关键点

1. **启动方式**: 必须用 `bash start-macos.sh`
2. **签名流程**: uri + JSON → MD5 → mnsv2 → base64
3. **必须先导航**: mnsv2 在小红书页面 JS 中定义
4. **请求头**: 需要 X-s, X-t, x-S-Common, X-B3-Traceid
5. **b1 值**: 从 localStorage 获取，用于 x-s-common

## 四、常见错误

| 错误 | 原因 | 解决 |
|------|------|------|
| SIGSEGV | 直接运行二进制 | 用 start-macos.sh |
| gRPC 超时 | 浏览器未创建 | 先 CreateBrowser |
| code=300011 | 签名/请求格式问题 | 检查签名构建 |
| mnsv2 返回空 | 未导航到小红书 | 先 Navigate |
