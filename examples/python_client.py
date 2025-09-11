#!/usr/bin/env python3
"""
SenseVoice WebSocket客户端示例

这个示例展示了如何使用Python连接SenseVoice WebSocket服务进行实时语音识别。
"""

import asyncio
import websockets
import json
import base64
import argparse
import logging
from pathlib import Path
from typing import Optional, Dict, Any

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class SenseVoiceClient:
    """SenseVoice WebSocket客户端"""
    
    def __init__(self, ws_url: str = "ws://localhost:50000/ws/asr"):
        self.ws_url = ws_url
        self.websocket: Optional[websockets.WebSocketServerProtocol] = None
        self.client_id: Optional[str] = None
        self.is_connected = False
        
    async def connect(self) -> bool:
        """连接到WebSocket服务器"""
        try:
            logger.info(f"正在连接到 {self.ws_url}")
            self.websocket = await websockets.connect(self.ws_url)
            self.is_connected = True
            logger.info("WebSocket连接成功")
            return True
        except Exception as e:
            logger.error(f"连接失败: {e}")
            return False
    
    async def disconnect(self):
        """断开WebSocket连接"""
        if self.websocket:
            await self.websocket.close()
            self.is_connected = False
            logger.info("WebSocket连接已断开")
    
    async def send_message(self, message: Dict[str, Any]):
        """发送消息到服务器"""
        if not self.is_connected or not self.websocket:
            logger.error("WebSocket未连接")
            return False
        
        try:
            await self.websocket.send(json.dumps(message, ensure_ascii=False))
            logger.debug(f"发送消息: {message['type']}")
            return True
        except Exception as e:
            logger.error(f"发送消息失败: {e}")
            return False
    
    async def send_config(self, language: str = "auto", chunk_duration: float = 3.0, 
                         use_vad: bool = True, encoding: str = "base64"):
        """发送配置消息"""
        config_message = {
            "type": "config",
            "config": {
                "language": language,
                "chunk_duration": chunk_duration,
                "use_vad": use_vad,
                "encoding": encoding
            }
        }
        return await self.send_message(config_message)
    
    async def send_audio_file(self, file_path: str, audio_format: str = "opus"):
        """发送音频文件"""
        try:
            with open(file_path, "rb") as f:
                audio_data = base64.b64encode(f.read()).decode('utf-8')
            
            audio_message = {
                "type": "audio",
                "data": audio_data,
                "format": audio_format
            }
            
            logger.info(f"发送音频文件: {file_path}")
            return await self.send_message(audio_message)
        except Exception as e:
            logger.error(f"发送音频文件失败: {e}")
            return False
    
    async def send_ping(self):
        """发送ping消息"""
        ping_message = {"type": "ping"}
        return await self.send_message(ping_message)
    
    async def clear_buffer(self):
        """清空服务器缓冲区"""
        clear_message = {"type": "clear"}
        return await self.send_message(clear_message)
    
    async def listen_for_messages(self):
        """监听服务器消息"""
        if not self.is_connected or not self.websocket:
            logger.error("WebSocket未连接")
            return
        
        try:
            async for message in self.websocket:
                await self.handle_message(json.loads(message))
        except websockets.exceptions.ConnectionClosed:
            logger.info("服务器关闭了连接")
            self.is_connected = False
        except Exception as e:
            logger.error(f"接收消息时出错: {e}")
    
    async def handle_message(self, message: Dict[str, Any]):
        """处理服务器消息"""
        message_type = message.get("type", "unknown")
        
        if message_type == "connection":
            self.client_id = message.get("client_id")
            logger.info(f"连接确认，客户端ID: {self.client_id}")
            
        elif message_type == "result":
            text = message.get("text", "")
            confidence = message.get("confidence", 0)
            is_final = message.get("is_final", False)
            language = message.get("language", "unknown")
            
            status = "最终结果" if is_final else "中间结果"
            logger.info(f"识别结果 ({status}): {text}")
            logger.info(f"置信度: {confidence:.2%}, 语言: {language}")
            
            # 在这里可以添加自定义的结果处理逻辑
            await self.on_recognition_result(message)
            
        elif message_type == "error":
            error_msg = message.get("message", "未知错误")
            logger.error(f"服务器错误: {error_msg}")
            
        elif message_type == "config_updated":
            logger.info("配置已更新")
            
        elif message_type == "pong":
            logger.debug("收到pong响应")
            
        elif message_type == "cleared":
            logger.info("缓冲区已清空")
            
        else:
            logger.warning(f"未知消息类型: {message_type}")
    
    async def on_recognition_result(self, result: Dict[str, Any]):
        """识别结果回调函数，可以被子类重写"""
        # 这里可以添加自定义的结果处理逻辑
        # 例如：保存到文件、发送到其他服务等
        pass


class FileProcessingClient(SenseVoiceClient):
    """文件处理客户端示例"""
    
    def __init__(self, ws_url: str = "ws://localhost:50000/ws/asr"):
        super().__init__(ws_url)
        self.results = []
    
    async def process_audio_file(self, file_path: str, language: str = "auto"):
        """处理单个音频文件"""
        if not await self.connect():
            return False
        
        # 发送配置
        await self.send_config(language=language, chunk_duration=3.0, use_vad=True)
        
        # 启动消息监听任务
        listen_task = asyncio.create_task(self.listen_for_messages())
        
        # 发送音频文件
        await self.send_audio_file(file_path)
        
        # 等待一段时间接收结果
        await asyncio.sleep(5)
        
        # 停止监听并断开连接
        listen_task.cancel()
        await self.disconnect()
        
        return True
    
    async def on_recognition_result(self, result: Dict[str, Any]):
        """保存识别结果"""
        if result.get("is_final", False):
            self.results.append({
                "text": result.get("text", ""),
                "confidence": result.get("confidence", 0),
                "language": result.get("language", "unknown"),
                "timestamp": result.get("timestamp", 0)
            })


async def main():
    """主函数"""
    parser = argparse.ArgumentParser(description="SenseVoice WebSocket客户端示例")
    parser.add_argument("--url", default="ws://localhost:50000/ws/asr", 
                       help="WebSocket服务器地址")
    parser.add_argument("--file", help="要处理的音频文件路径")
    parser.add_argument("--language", default="auto", 
                       choices=["auto", "zh", "en", "yue", "ja", "ko", "nospeech"],
                       help="识别语言")
    parser.add_argument("--interactive", action="store_true", 
                       help="交互模式")
    
    args = parser.parse_args()
    
    if args.file:
        # 文件处理模式
        if not Path(args.file).exists():
            logger.error(f"文件不存在: {args.file}")
            return
        
        client = FileProcessingClient(args.url)
        await client.process_audio_file(args.file, args.language)
        
        # 输出结果
        if client.results:
            print("\n识别结果:")
            for i, result in enumerate(client.results, 1):
                print(f"{i}. {result['text']} (置信度: {result['confidence']:.2%})")
        else:
            print("没有识别到任何结果")
    
    elif args.interactive:
        # 交互模式
        client = SenseVoiceClient(args.url)
        
        if not await client.connect():
            return
        
        # 发送默认配置
        await client.send_config(language=args.language)
        
        # 启动消息监听任务
        listen_task = asyncio.create_task(client.listen_for_messages())
        
        print("进入交互模式，输入命令:")
        print("  ping - 发送ping消息")
        print("  clear - 清空缓冲区")
        print("  file <path> - 发送音频文件")
        print("  config <lang> - 更新语言配置")
        print("  quit - 退出")
        
        try:
            while True:
                command = input("> ").strip().split()
                if not command:
                    continue
                
                if command[0] == "quit":
                    break
                elif command[0] == "ping":
                    await client.send_ping()
                elif command[0] == "clear":
                    await client.clear_buffer()
                elif command[0] == "file" and len(command) > 1:
                    await client.send_audio_file(command[1])
                elif command[0] == "config" and len(command) > 1:
                    await client.send_config(language=command[1])
                else:
                    print("未知命令")
        
        except KeyboardInterrupt:
            print("\n退出中...")
        finally:
            listen_task.cancel()
            await client.disconnect()
    
    else:
        print("请指定 --file 或 --interactive 模式")
        parser.print_help()


if __name__ == "__main__":
    asyncio.run(main())
