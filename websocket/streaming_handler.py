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
        self.consumer_tasks = {}  # 存储每个客户端的消费任务
    
    async def handle_websocket(self, websocket: WebSocket, client_id: Optional[str] = None):
        """处理WebSocket连接"""
        client_id = await self.connection_manager.connect(websocket, client_id)

        # 启动独立的消费任务
        consumer_task = asyncio.create_task(self._audio_consumer_loop(client_id))
        self.consumer_tasks[client_id] = consumer_task

        try:
            while True:
                # 接收消息（只负责接收，不处理）
                data = await websocket.receive_text()
                await self._process_message(client_id, data)

        except WebSocketDisconnect:
            logger.info(f"客户端 {client_id} 主动断开连接")
        except Exception as e:
            logger.error(f"WebSocket处理错误 (客户端 {client_id}): {e}")
            await self._send_error_message(client_id, f"服务器错误: {str(e)}")
        finally:
            # 停止消费任务
            if client_id in self.consumer_tasks:
                self.consumer_tasks[client_id].cancel()
                del self.consumer_tasks[client_id]
            self.connection_manager.disconnect(client_id)

    async def _audio_consumer_loop(self, client_id: str):
        """独立的音频消费循环

        持续监控客户端的音频缓冲区，当VAD检测到完整语音片段时进行消费
        """
        logger.info(f"启动客户端 {client_id} 的音频消费循环")

        try:
            while True:
                # 获取客户端的音频缓冲区
                audio_buffer = self.connection_manager.get_audio_buffer(client_id)

                if audio_buffer:
                    current_duration = audio_buffer.get_duration()

                    # 5秒窗口策略：等待足够的音频累积
                    if current_duration >= 5.0:  # 至少有5秒音频才考虑处理
                        logger.info(f"客户端 {client_id} 检查5秒窗口: {current_duration:.2f}s")

                        # 尝试消费音频（只有VAD检测到完整片段才会真正消费）
                        result = await self.asr_handler.process_audio_with_independent_vad(
                            audio_buffer,
                            language="auto"
                        )

                        # 如果有识别结果，说明成功消费了
                        if result.get("text") and result["text"].strip():
                            await self._send_recognition_result(client_id, result)
                            logger.info(f"客户端 {client_id} 成功消费，剩余缓冲区: {audio_buffer.get_duration():.2f}s")
                        else:
                            # 没有识别结果，说明VAD没有检测到完整片段，继续等待
                            logger.debug(f"客户端 {client_id} VAD未检测到完整片段，继续累积")

                        # 处理后等待一段时间，避免过度处理
                        await asyncio.sleep(1.0)
                    else:
                        # 缓冲区音频不足5秒，继续等待
                        await asyncio.sleep(0.5)
                else:
                    # 没有音频缓冲区，等待
                    await asyncio.sleep(0.5)

        except asyncio.CancelledError:
            logger.info(f"客户端 {client_id} 的音频消费循环已停止")
        except Exception as e:
            logger.error(f"客户端 {client_id} 音频消费循环错误: {e}")

    async def _send_recognition_result(self, client_id: str, result: Dict[str, Any]):
        """发送识别结果给客户端"""
        try:
            text = result.get("text", "")
            message = {
                "type": "result",  # 前端期望的类型
                "status": "success",
                "text": text,
                "raw_text": text,  # 原始文本
                "clean_text": text,  # 清理后的文本（暂时相同）
                "confidence": 0.95,  # 默认置信度
                "model_type": "SenseVoice",  # 模型类型
                "is_final": True,  # 标记为最终结果
                "language": result.get("language", "auto"),
                "timestamp": result.get("timestamp"),
                "segment_start_time": result.get("segment_start_time"),
                "segment_end_time": result.get("segment_end_time"),
                "segment_duration": result.get("segment_duration")
            }

            await self.connection_manager.send_message(client_id, message)
            self.connection_manager.increment_stat(client_id, "recognitions")

            logger.info(f"客户端 {client_id} 独立VAD识别结果: {result.get('text', '')}")

        except Exception as e:
            logger.error(f"发送识别结果失败 (客户端 {client_id}): {e}")

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
            
            logger.info(f"客户端 {client_id} 发送Opus音频数据，长度: {len(audio_data)}")
            
            # 获取连接信息
            connection_info = self.connection_manager.get_connection_info(client_id)
            if not connection_info:
                await self._send_error_message(client_id, "连接信息不存在")
                return
            
            config = connection_info["config"]
            audio_buffer = connection_info["audio_buffer"]
            
            # 解码音频数据（固定Opus格式）
            encoding = config.get("encoding", "base64")
            audio_array = self.audio_processor.decode_audio_data(audio_data, encoding)
            
            if audio_array is None:
                await self._send_error_message(client_id, "Opus音频解码失败")
                return
            
            logger.info(f"音频解码成功，样本数: {len(audio_array)}")
            
            # 添加到缓冲区（只负责接收，不处理）
            audio_buffer.add_audio(audio_array)

            # 验证音频质量
            if not self.audio_processor.validate_audio_format(audio_array, min_duration=0.5):
                logger.debug("音频质量不符合要求，跳过处理")
                return

            logger.debug(f"音频已添加到缓冲区，当前缓冲区时长: {audio_buffer.get_duration():.2f}s")

            # 注意：不在这里进行VAD处理，处理由独立的消费循环负责
            
        except Exception as e:
            logger.error(f"音频消息处理错误 (客户端 {client_id}): {e}")
            await self._send_error_message(client_id, f"音频处理失败: {str(e)}")
            self.connection_manager.increment_stat(client_id, "errors")
    
    async def _process_audio_chunk(self, client_id: str, audio_buffer, config: Dict[str, Any]):
        """处理音频块"""
        try:
            chunk_duration = config.get("chunk_duration", self.settings.default_chunk_duration)
            language = config.get("language", "auto")
            
            # 获取音频块
            audio_chunk = audio_buffer.get_audio_chunk(chunk_duration)
            
            if len(audio_chunk) == 0:
                return
            
            # 进行ASR处理
            result = await self.asr_handler.process_audio_chunk(
                audio_chunk, 
                language=language,
                merge_length_s=chunk_duration
            )
            
            # 发送结果
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

    async def _process_audio_with_independent_vad(self, client_id: str, audio_buffer, config: Dict[str, Any]):
        """使用独立VAD模型进行音频处理"""
        try:
            language = config.get("language", "auto")

            # 使用独立VAD进行处理
            result = await self.asr_handler.process_audio_with_independent_vad(
                audio_buffer,
                language=language
            )

            # 如果有识别结果，发送给客户端
            if result.get("text") and result["text"].strip():
                response = {
                    "type": "result",
                    "timestamp": asyncio.get_event_loop().time(),
                    **result
                }

                await self.connection_manager.send_message(client_id, response)
                self.connection_manager.increment_stat(client_id, "audio_chunks_processed")

                logger.info(f"客户端 {client_id} 独立VAD识别结果: {result['text']}")

        except Exception as e:
            logger.error(f"独立VAD音频处理错误 (客户端 {client_id}): {e}")
            await self._send_error_message(client_id, f"独立VAD音频识别失败: {str(e)}")
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
            # 同时清空ASR缓存
            self.connection_manager.clear_asr_cache(client_id)
            await self.connection_manager.send_message(client_id, {
                "type": "cleared",
                "status": "success",
                "message": "音频缓冲区和ASR缓存已清空"
            })
        else:
            await self._send_error_message(client_id, "无法清空缓冲区")
    
    async def _send_error_message(self, client_id: str, error_message: str):
        """发送错误消息"""
        await self.connection_manager.send_message(client_id, {
            "type": "error",
            "status": "error",
            "message": error_message,
            "timestamp": asyncio.get_event_loop().time()
        })
