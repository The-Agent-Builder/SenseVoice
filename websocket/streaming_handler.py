"""
WebSocket流式处理模块
"""
import json
import logging
import asyncio
from typing import Dict, Any, Optional
from fastapi import WebSocket, WebSocketDisconnect

from websocket.connection_manager import ConnectionManager
from handlers.streaming_asr import StreamingASRHandler
from handlers.audio_handler import AudioProcessor
from config.settings import get_settings

logger = logging.getLogger(__name__)


class WebSocketStreamingHandler:
    """WebSocket流式处理器"""
    
    def __init__(self, connection_manager: ConnectionManager):
        self.connection_manager = connection_manager
        self.asr_handler = StreamingASRHandler()
        self.audio_processor = AudioProcessor()
        self.settings = get_settings()
    
    async def handle_websocket(self, websocket: WebSocket, client_id: Optional[str] = None):
        """处理WebSocket连接"""
        client_id = await self.connection_manager.connect(websocket, client_id)
        
        try:
            while True:
                # 接收消息
                data = await websocket.receive_text()
                await self._process_message(client_id, data)
                
        except WebSocketDisconnect:
            logger.info(f"客户端 {client_id} 主动断开连接")
        except Exception as e:
            logger.error(f"WebSocket处理错误 (客户端 {client_id}): {e}")
            await self._send_error_message(client_id, f"服务器错误: {str(e)}")
        finally:
            self.connection_manager.disconnect(client_id)
    
    async def _process_message(self, client_id: str, message_data: str):
        """处理接收到的消息"""
        try:
            message = json.loads(message_data)
            message_type = message.get("type", "unknown")
            
            self.connection_manager.increment_stat(client_id, "messages_received")
            
            if message_type == "config":
                await self._handle_config_message(client_id, message)
            elif message_type == "audio":
                await self._handle_audio_message(client_id, message)
            elif message_type == "ping":
                await self._handle_ping_message(client_id, message)
            elif message_type == "clear":
                await self._handle_clear_message(client_id, message)
            elif message_type == "end_segment":
                await self._handle_end_segment_message(client_id, message)
            else:
                await self._send_error_message(client_id, f"未知的消息类型: {message_type}")
                
        except json.JSONDecodeError as e:
            logger.error(f"JSON解析错误 (客户端 {client_id}): {e}")
            await self._send_error_message(client_id, "消息格式错误")
            self.connection_manager.increment_stat(client_id, "errors")
        except Exception as e:
            logger.error(f"消息处理错误 (客户端 {client_id}): {e}")
            await self._send_error_message(client_id, f"消息处理失败: {str(e)}")
            self.connection_manager.increment_stat(client_id, "errors")
    
    async def _handle_config_message(self, client_id: str, message: Dict[str, Any]):
        """处理配置消息"""
        config = message.get("config", {})
        
        # 验证配置参数
        valid_languages = ["auto", "zh", "en", "yue", "ja", "ko", "nospeech"]
        if "language" in config and config["language"] not in valid_languages:
            await self._send_error_message(client_id, f"不支持的语言: {config['language']}")
            return
        
        if "chunk_duration" in config:
            try:
                chunk_duration = float(config["chunk_duration"])
                if chunk_duration <= 0 or chunk_duration > 10:
                    await self._send_error_message(client_id, "chunk_duration必须在0-10秒之间")
                    return
            except (ValueError, TypeError):
                await self._send_error_message(client_id, "chunk_duration必须是数字")
                return
        
        # 更新配置
        success = self.connection_manager.update_config(client_id, config)
        if success:
            await self.connection_manager.send_message(client_id, {
                "type": "config_updated",
                "status": "success",
                "config": config,
                "message": "配置已更新"
            })
        else:
            await self._send_error_message(client_id, "配置更新失败")
    
    async def _handle_audio_message(self, client_id: str, message: Dict[str, Any]):
        """处理音频消息"""
        try:
            audio_data = message.get("data", "")
            audio_format = message.get("format", "unknown")
            
            if not audio_data:
                await self._send_error_message(client_id, "音频数据为空")
                return
            
            logger.info(f"客户端 {client_id} 发送音频数据，长度: {len(audio_data)}")
            
            # 获取连接信息
            connection_info = self.connection_manager.get_connection_info(client_id)
            if not connection_info:
                await self._send_error_message(client_id, "连接信息不存在")
                return
            
            config = connection_info["config"]
            audio_buffer = connection_info["audio_buffer"]
            
            # 根据音频格式解码音频数据
            audio_format = message.get("format", "opus")  # 默认为opus
            encoding = config.get("encoding", "base64")

            logger.info(f"音频格式: {audio_format}, 编码: {encoding}")
            logger.info(f"消息内容: {list(message.keys())}")  # 调试信息

            if audio_format == "pcm":
                # 直接解码PCM格式
                logger.info("使用PCM解码器")
                audio_array = self.audio_processor.decode_pcm_data(audio_data, encoding)
                if audio_array is None:
                    await self._send_error_message(client_id, "PCM音频解码失败")
                    return
            else:
                # 解码Opus格式
                logger.info(f"使用Opus解码器 (格式: {audio_format})")
                audio_array = self.audio_processor.decode_audio_data(audio_data, encoding)
                if audio_array is None:
                    await self._send_error_message(client_id, "Opus音频解码失败")
                    return
            
            logger.info(f"音频解码成功，样本数: {len(audio_array)}")
            
            # 添加到缓冲区
            audio_buffer.add_audio(audio_array)
            
            # 验证音频质量
            if not self.audio_processor.validate_audio_format(audio_array, min_duration=0.5):
                logger.debug("音频质量不符合要求，跳过处理")
                return
            
            # 检查是否有足够的音频进行处理
            chunk_duration = config.get("chunk_duration", self.settings.default_chunk_duration)
            if audio_buffer.has_enough_audio(chunk_duration):
                await self._process_audio_chunk(client_id, audio_buffer, config)
            
        except Exception as e:
            logger.error(f"音频消息处理错误 (客户端 {client_id}): {e}")
            await self._send_error_message(client_id, f"音频处理失败: {str(e)}")
            self.connection_manager.increment_stat(client_id, "errors")
    
    async def _process_audio_chunk(self, client_id: str, audio_buffer, config: Dict[str, Any]):
        """处理音频块"""
        try:
            chunk_duration = config.get("chunk_duration", self.settings.default_chunk_duration)
            language = config.get("language", "auto")

            # 获取累积音频用于流式识别（而不是固定时长的音频块）
            audio_chunk = audio_buffer.get_streaming_audio(max_duration=10.0)  # 最多10秒的累积音频

            if len(audio_chunk) == 0:
                return

            # 在实时流式中，大部分时候都是中间结果，只在特定条件下设置is_final
            # 1. 检测到长时间静音
            # 2. 用户主动发送结束信号
            # 3. 连接即将关闭
            is_final = False  # 默认为中间结果

            # 进行ASR处理 - 使用累积音频实现真正的流式识别
            result = await self.asr_handler.process_audio_chunk(
                audio_chunk,
                language=language,
                merge_length_s=chunk_duration,
                is_final=is_final
            )

            # 发送结果（包括空文本的中间结果）
            response = {
                "type": "result",
                "timestamp": asyncio.get_event_loop().time(),
                **result
            }

            await self.connection_manager.send_message(client_id, response)
            self.connection_manager.increment_stat(client_id, "audio_chunks_processed")
            
        except Exception as e:
            logger.error(f"音频块处理错误 (客户端 {client_id}): {e}")
            await self._send_error_message(client_id, f"音频识别失败: {str(e)}")
            self.connection_manager.increment_stat(client_id, "errors")
    
    async def _handle_ping_message(self, client_id: str, message: Dict[str, Any]):
        """处理ping消息"""
        await self.connection_manager.send_message(client_id, {
            "type": "pong",
            "timestamp": asyncio.get_event_loop().time(),
            "message": "pong"
        })
    
    async def _handle_clear_message(self, client_id: str, message: Dict[str, Any]):
        """处理清空缓冲区消息"""
        audio_buffer = self.connection_manager.get_audio_buffer(client_id)
        if audio_buffer:
            audio_buffer.clear()

            # 重置ASR处理器的流式状态
            if hasattr(self.asr_handler, 'reset_streaming_state'):
                self.asr_handler.reset_streaming_state()

            await self.connection_manager.send_message(client_id, {
                "type": "cleared",
                "status": "success",
                "message": "音频缓冲区和流式状态已清空"
            })
        else:
            await self._send_error_message(client_id, "无法清空缓冲区")

    async def _handle_end_segment_message(self, client_id: str, message: Dict[str, Any]):
        """处理结束段落消息 - 强制输出最终结果"""
        audio_buffer = self.connection_manager.get_audio_buffer(client_id)
        if audio_buffer and audio_buffer.get_duration() > 0:
            # 获取配置
            connection_info = self.connection_manager.get_connection_info(client_id)
            config = connection_info["config"] if connection_info else {}

            chunk_duration = config.get("chunk_duration", self.settings.default_chunk_duration)
            language = config.get("language", "auto")

            # 获取剩余的音频
            audio_chunk = audio_buffer.get_all_audio()

            if len(audio_chunk) > 0:
                # 强制设置为最终结果
                result = await self.asr_handler.process_audio_chunk(
                    audio_chunk,
                    language=language,
                    merge_length_s=chunk_duration,
                    is_final=True  # 强制最终结果
                )

                # 发送最终结果
                response = {
                    "type": "result",
                    "timestamp": asyncio.get_event_loop().time(),
                    **result
                }

                await self.connection_manager.send_message(client_id, response)

                # 清空缓冲区，但保持流式状态用于累积识别
                audio_buffer.clear()
                if hasattr(self.asr_handler, 'reset_segment_state'):
                    self.asr_handler.reset_segment_state()  # 使用段落重置而不是完全重置

            await self.connection_manager.send_message(client_id, {
                "type": "segment_ended",
                "status": "success",
                "message": "语音段落已结束"
            })
        else:
            await self._send_error_message(client_id, "没有音频数据需要处理")
    
    async def _send_error_message(self, client_id: str, error_message: str):
        """发送错误消息"""
        await self.connection_manager.send_message(client_id, {
            "type": "error",
            "status": "error",
            "message": error_message,
            "timestamp": asyncio.get_event_loop().time()
        })
