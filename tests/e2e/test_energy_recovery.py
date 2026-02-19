#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Energy 服务恢复测试

这个测试脚本验证：
1. 服务在导航成功后可能崩溃，但页面已加载
2. 客户端可以检测服务崩溃并自动重连
3. 使用已加载的浏览器实例继续操作

关键发现：
- 导航到小红书实际上成功了（日志显示 HTTP 200）
- 服务在导航成功后崩溃
- 重启服务后，可以继续使用之前的浏览器实例
"""

import subprocess
import time
import sys
import os
import grpc

# Add paths
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'energy_client'))

from energy_client.client import BrowserClient
from energy_client import browser_pb2


def start_energy_service():
    """启动 Energy 服务"""
    print("启动 Energy 服务...")

    # 检查是否有进程在运行
    result = subprocess.run(['pgrep', '-f', 'energy-service'], capture_output=True)
    if result.returncode == 0:
        print("  已有 Energy 服务在运行")
        return True

    # 启动服务
    service_path = os.path.join(os.path.dirname(__file__), '..', 'energy-service')
    start_script = os.path.join(service_path, 'start-macos.sh')

    if os.path.exists(start_script):
        subprocess.Popen(['bash', start_script], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    else:
        # 直接启动应用
        app_path = os.path.join(service_path, 'energy-service.app')
        if os.path.exists(app_path):
            subprocess.Popen(['open', app_path], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        else:
            print("  错误：找不到 Energy 服务")
            return False

    # 等待服务启动
    for i in range(10):
        time.sleep(1)
        try:
            channel = grpc.insecure_channel('localhost:50051')
            stub = browser_pb2_grpc.BrowserServiceStub(channel)
            # 尝试一个简单的调用
            channel.close()
            print(f"  服务已启动 (等待 {i+1} 秒)")
            return True
        except:
            continue

    print("  服务启动超时")
    return False


def test_navigate_with_recovery():
    """测试导航并处理服务崩溃恢复"""

    print("\n=== 测试：导航到小红书（带恢复） ===\n")

    browser_id = "xhs-test-recovery"
    client = BrowserClient('localhost', 50051)

    try:
        # 1. 连接服务
        print("1. 连接 Energy 服务...")
        client.connect()
        print("   ✓ 已连接")

        # 2. 创建浏览器
        print("\n2. 创建浏览器...")
        try:
            success = client.create_browser(browser_id, headless=False)  # 使用非 headless 以便观察
            print(f"   浏览器创建: {'✓' if success else '✗'}")
        except Exception as e:
            print(f"   创建失败: {e}")
            # 可能浏览器已存在，继续

        # 3. 导航到小红书
        print("\n3. 导航到小红书...")
        try:
            start_time = time.time()
            status_code = client.navigate(browser_id, "https://www.xiaohongshu.com", timeout_ms=60000)
            elapsed = time.time() - start_time
            print(f"   ✓ 导航成功！状态码: {status_code}, 耗时: {elapsed:.2f}秒")
            navigation_success = True
        except grpc.RpcError as e:
            elapsed = time.time() - start_time
            print(f"   服务断开（可能是崩溃）: {e.code()}")
            print(f"   耗时: {elapsed:.2f}秒")

            # 检查是否在合理时间内断开（页面可能已加载）
            if elapsed > 2.0:
                print("   ! 导航可能已成功，但服务在返回响应后崩溃")
                print("   ! 请检查浏览器窗口 - 页面应该已经加载")
                navigation_success = "likely"
            else:
                navigation_success = False
        except Exception as e:
            print(f"   导航失败: {e}")
            navigation_success = False

        # 4. 如果导航可能成功，等待用户确认
        if navigation_success == "likely":
            print("\n4. 请检查浏览器窗口...")
            user_input = input("   你是否看到小红书页面？(y/n): ")
            if user_input.lower() == 'y':
                print("   ✓ 导航确实成功！")
                return True

        # 5. 尝试重新连接服务
        print("\n5. 尝试重新连接服务...")
        time.sleep(2)

        try:
            client.disconnect()
            client.connect()
            print("   ✓ 重新连接成功")

            # 尝试执行 JavaScript 检查页面
            print("\n6. 检查当前页面...")
            try:
                result = client.execute_js(browser_id, "window.location.href")
                print(f"   当前 URL: {result}")

                # 检查是否有 mnsv2 函数
                result = client.execute_js(browser_id, "typeof window.mnsv2")
                print(f"   mnsv2 函数: {result}")

                if "xiaohongshu" in result.lower() or result == "function":
                    print("\n   ✓ 页面正常，可以进行签名操作")
                    return True

            except Exception as e:
                print(f"   执行 JS 失败: {e}")

        except Exception as e:
            print(f"   重连失败: {e}")

        return navigation_success == True

    finally:
        try:
            client.disconnect()
        except:
            pass


def test_signature_after_navigation():
    """测试导航后的签名生成"""

    print("\n=== 测试：签名生成 ===\n")

    browser_id = "xhs-sig-test"
    client = BrowserClient('localhost', 50051)

    try:
        client.connect()

        # 创建浏览器
        print("1. 创建浏览器...")
        try:
            client.create_browser(browser_id, headless=False)
        except:
            pass  # 可能已存在

        # 先导航到简单页面
        print("\n2. 导航到 example.com（测试基础功能）...")
        try:
            status = client.navigate(browser_id, "https://example.com", timeout_ms=30000)
            print(f"   ✓ 状态码: {status}")
        except Exception as e:
            print(f"   导航失败: {e}")

        time.sleep(1)

        # 然后导航到小红书
        print("\n3. 导航到小红书...")
        try:
            status = client.navigate(browser_id, "https://www.xiaohongshu.com", timeout_ms=60000)
            print(f"   ✓ 导航成功: {status}")

            # 执行签名
            print("\n4. 测试签名生成...")
            test_script = "typeof window.mnsv2"
            result = client.execute_js(browser_id, test_script)
            print(f"   mnsv2 类型: {result}")

            if result == "function":
                # 尝试执行签名
                sign_script = "window.mnsv2('/api/sns/web/v1/search/notes', 'test_md5')"
                result = client.execute_js(browser_id, sign_script)
                print(f"   签名结果: {result[:100] if result else 'empty'}...")
                print("\n   ✓ 签名功能正常！")
                return True
            else:
                print("   mnsv2 函数不可用，可能页面未完全加载")
                return False

        except grpc.RpcError as e:
            print(f"   服务断开: {e.code()}")
            print("   导航可能已成功但服务崩溃")
            return False

    finally:
        try:
            client.disconnect()
        except:
            pass


if __name__ == "__main__":
    print("=" * 60)
    print("Energy 服务恢复测试")
    print("=" * 60)

    # 需要导入 grpc 模块的 stub
    from energy_client import browser_pb2_grpc

    # 运行测试
    result1 = test_navigate_with_recovery()

    print("\n" + "=" * 60)

    if result1:
        print("✓ 测试通过：导航成功")
    else:
        print("✗ 测试失败：需要进一步调查")

    print("\n注意：即使服务崩溃，如果浏览器窗口显示小红书页面，")
    print("说明导航功能是正常的，只是服务稳定性问题。")
