#!/usr/bin/env python3
"""
检查SenseVoice服务状态的脚本
"""
import requests
import json
import time

def check_service_status():
    """检查服务状态"""
    try:
        response = requests.get("http://localhost:50000/api/v1/status", timeout=5)
        if response.status_code == 200:
            status = response.json()
            print("✅ 服务状态检查成功:")
            print(json.dumps(status, indent=2, ensure_ascii=False))
            return True
        else:
            print(f"❌ 服务状态检查失败: HTTP {response.status_code}")
            return False
    except requests.exceptions.ConnectionError:
        print("❌ 无法连接到服务 (服务可能未启动)")
        return False
    except requests.exceptions.Timeout:
        print("❌ 请求超时")
        return False
    except Exception as e:
        print(f"❌ 检查服务状态时出错: {e}")
        return False

def check_main_page():
    """检查主页"""
    try:
        response = requests.get("http://localhost:50000/", timeout=5)
        if response.status_code == 200:
            print("✅ 主页访问成功")
            return True
        else:
            print(f"❌ 主页访问失败: HTTP {response.status_code}")
            return False
    except Exception as e:
        print(f"❌ 访问主页时出错: {e}")
        return False

def check_websocket_test_page():
    """检查WebSocket测试页面"""
    try:
        response = requests.get("http://localhost:50000/ws-test", timeout=5)
        if response.status_code == 200:
            print("✅ WebSocket测试页面访问成功")
            return True
        else:
            print(f"❌ WebSocket测试页面访问失败: HTTP {response.status_code}")
            return False
    except Exception as e:
        print(f"❌ 访问WebSocket测试页面时出错: {e}")
        return False

def main():
    print("🔍 开始检查SenseVoice服务...")
    print("=" * 50)
    
    # 等待服务启动
    print("⏳ 等待服务启动...")
    max_retries = 30
    for i in range(max_retries):
        if check_service_status():
            break
        if i < max_retries - 1:
            print(f"等待中... ({i+1}/{max_retries})")
            time.sleep(2)
    else:
        print("❌ 服务启动超时")
        return
    
    print("\n" + "=" * 50)
    print("🌐 检查各个端点...")
    
    # 检查主页
    check_main_page()
    
    # 检查WebSocket测试页面
    check_websocket_test_page()
    
    print("\n" + "=" * 50)
    print("📋 服务信息:")
    print("- 主页: http://localhost:50000")
    print("- API文档: http://localhost:50000/docs")
    print("- WebSocket测试: http://localhost:50000/ws-test")
    print("- 服务状态: http://localhost:50000/api/v1/status")
    print("- WebSocket端点: ws://localhost:50000/ws/asr")
    
    print("\n✅ 服务检查完成！")

if __name__ == "__main__":
    main()
