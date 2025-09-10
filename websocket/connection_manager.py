"""
WebSocket连接管理模块
"""
import json
import logging
import uuid
from typing import Dict, Any, Optional
from fastapi import WebSocket

from handlers.audio_handler import AudioBuffer
from config.settings import get_settings

logger = logging.getLogger(__name__)


class ConnectionManager:
    """WebSocket连接管理器"""
    
    def __init__(self):
        self.settings = get_settings()
        self.active_connections: Dict[str, Dict[str, Any]] = {}
    
    async def connect(self, websocket: WebSocket, client_id: Optional[str] = None) -> str:
        """建立WebSocket连接"""
        if client_id is None:
            client_id = str(uuid.uuid4())
        
        await websocket.accept()
        
        self.active_connections[client_id] = {
            "websocket": websocket,
            "audio_buffer": AudioBuffer(),
            "asr_cache": {},  # 为FunASR模型维护的持久cache
            "config": {
                "language": "auto",
                "chunk_duration": self.settings.default_chunk_duration,
                "use_vad": True,
                "encoding": "base64"
            },
            "stats": {
                "messages_received": 0,
                "audio_chunks_processed": 0,
                "errors": 0,
                "recognitions": 0
            }
        }
        
        logger.info(f"客户端 {client_id} 已连接，当前连接数: {len(self.active_connections)}")
        
        # 发送连接确认消息
        await self.send_message(client_id, {
            "type": "connection",
            "status": "connected",
            "client_id": client_id,
            "message": "WebSocket连接已建立"
        })
        
        return client_id
    
    def disconnect(self, client_id: str):
        """断开WebSocket连接"""
        if client_id in self.active_connections:
            connection_info = self.active_connections[client_id]
            stats = connection_info["stats"]
            
            logger.info(
                f"客户端 {client_id} 已断开连接。"
                f"统计信息: 接收消息 {stats['messages_received']}, "
                f"处理音频块 {stats['audio_chunks_processed']}, "
                f"识别次数 {stats['recognitions']}, "
                f"错误 {stats['errors']}"
            )
            
            del self.active_connections[client_id]
            logger.info(f"当前连接数: {len(self.active_connections)}")
    
    async def send_message(self, client_id: str, message: Dict[str, Any]) -> bool:
        """发送消息给指定客户端"""
        if client_id not in self.active_connections:
            logger.warning(f"尝试向不存在的客户端 {client_id} 发送消息")
            return False
        
        try:
            websocket = self.active_connections[client_id]["websocket"]
            await websocket.send_text(json.dumps(message, ensure_ascii=False))
            return True
        except Exception as e:
            logger.error(f"向客户端 {client_id} 发送消息失败: {e}")
            return False
    
    async def broadcast_message(self, message: Dict[str, Any], exclude_client: Optional[str] = None):
        """广播消息给所有连接的客户端"""
        disconnected_clients = []
        
        for client_id in self.active_connections:
            if exclude_client and client_id == exclude_client:
                continue
            
            success = await self.send_message(client_id, message)
            if not success:
                disconnected_clients.append(client_id)
        
        # 清理断开的连接
        for client_id in disconnected_clients:
            self.disconnect(client_id)
    
    def get_connection_info(self, client_id: str) -> Optional[Dict[str, Any]]:
        """获取连接信息"""
        return self.active_connections.get(client_id)
    
    def update_config(self, client_id: str, config: Dict[str, Any]) -> bool:
        """更新客户端配置"""
        if client_id not in self.active_connections:
            return False
        
        connection_info = self.active_connections[client_id]
        connection_info["config"].update(config)
        
        logger.info(f"客户端 {client_id} 配置已更新: {config}")
        return True
    
    def get_audio_buffer(self, client_id: str) -> Optional[AudioBuffer]:
        """获取客户端的音频缓冲区"""
        connection_info = self.get_connection_info(client_id)
        if connection_info:
            return connection_info["audio_buffer"]
        return None

    def get_asr_cache(self, client_id: str) -> Optional[dict]:
        """获取客户端的ASR缓存"""
        connection_info = self.get_connection_info(client_id)
        if connection_info:
            return connection_info["asr_cache"]
        return None

    def clear_asr_cache(self, client_id: str) -> bool:
        """清空客户端的ASR缓存"""
        connection_info = self.get_connection_info(client_id)
        if connection_info:
            connection_info["asr_cache"].clear()
            return True
        return False
    
    def increment_stat(self, client_id: str, stat_name: str):
        """增加统计计数"""
        if client_id in self.active_connections:
            stats = self.active_connections[client_id]["stats"]
            if stat_name not in stats:
                stats[stat_name] = 0
            stats[stat_name] += 1
    
    def get_connection_count(self) -> int:
        """获取当前连接数"""
        return len(self.active_connections)
    
    def get_connection_stats(self) -> Dict[str, Any]:
        """获取连接统计信息"""
        total_messages = sum(
            conn["stats"]["messages_received"] 
            for conn in self.active_connections.values()
        )
        total_audio_chunks = sum(
            conn["stats"]["audio_chunks_processed"] 
            for conn in self.active_connections.values()
        )
        total_errors = sum(
            conn["stats"]["errors"] 
            for conn in self.active_connections.values()
        )
        
        return {
            "active_connections": len(self.active_connections),
            "total_messages_received": total_messages,
            "total_audio_chunks_processed": total_audio_chunks,
            "total_errors": total_errors
        }
