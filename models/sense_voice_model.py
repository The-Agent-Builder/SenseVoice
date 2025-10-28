"""
SenseVoice模型管理模块
"""
import logging
from typing import Optional, Tuple, Any, Dict
import torch

from funasr import AutoModel
from .model import SenseVoiceSmall
from config.settings import get_settings

logger = logging.getLogger(__name__)


class SenseVoiceModelManager:
    """SenseVoice模型管理器"""
    
    def __init__(self):
        self.settings = get_settings()
        self.sense_voice_model: Optional[SenseVoiceSmall] = None
        self.sense_voice_kwargs: Optional[Dict] = None
        self.streaming_model: Optional[AutoModel] = None
        self._initialized = False
    
    def initialize(self, load_streaming: bool = False) -> bool:
        """初始化模型
        
        Args:
            load_streaming: 是否立即加载流式模型（默认False，延迟加载以节省显存）
        """
        try:
            # 设置显存管理
            self._setup_memory_management()

            # 初始化SenseVoiceSmall模型（用于HTTP接口）
            logger.info(f"正在加载SenseVoice模型: {self.settings.model_dir}")
            self.sense_voice_model, self.sense_voice_kwargs = SenseVoiceSmall.from_pretrained(
                model=self.settings.model_dir,
                device=self.settings.device
            )
            self.sense_voice_model.eval()
            logger.info("SenseVoice模型加载成功")
            
            # 流式模型延迟加载（节省显存）
            if load_streaming:
                self._load_streaming_model()
            else:
                logger.info("流式模型将在首次WebSocket连接时延迟加载（节省显存）")
            
            self._initialized = True
            return True

        except Exception as e:
            logger.error(f"模型初始化失败: {e}")
            return False
    
    def _load_streaming_model(self):
        """加载流式模型"""
        if self.streaming_model is not None:
            logger.info("流式模型已加载，跳过")
            return
            
        try:
            logger.info("正在加载流式模型（WebSocket专用）...")
            self.streaming_model = AutoModel(
                model=self.settings.model_dir,
                trust_remote_code=True,
                vad_model="fsmn-vad",
                vad_kwargs={"max_single_segment_time": 30000},
                device=self.settings.device,
                disable_update=True  # 禁用自动更新检查
            )
            logger.info("流式模型加载成功")
        except Exception as e:
            logger.warning(f"流式模型加载失败，WebSocket功能将不可用: {e}")
            self.streaming_model = None

    def _setup_memory_management(self):
        """设置显存管理"""
        try:
            if self.settings.device.startswith("cuda"):
                # 设置PyTorch CUDA内存分配器，避免碎片化
                import os
                os.environ['PYTORCH_CUDA_ALLOC_CONF'] = 'expandable_segments:True'
                
                # 设置具体的GPU设备
                if ":" in self.settings.device:
                    device_id = int(self.settings.device.split(":")[1])
                    torch.cuda.set_device(device_id)
                    logger.info(f"设置当前CUDA设备为: {self.settings.device}")

                # 清理显存缓存
                torch.cuda.empty_cache()

                # 启用显存回收
                import gc
                gc.collect()
                
                # 注意：不设置 memory_fraction，让PyTorch按需分配显存
                # 如果设置了固定的fraction，会导致PyTorch预留大量显存但不释放
                logger.info("显存管理：使用按需分配策略（不预留固定比例）")

                logger.info("显存管理设置完成（已启用expandable_segments避免碎片化）")

        except Exception as e:
            logger.warning(f"显存管理设置失败: {e}")
    
    def is_initialized(self) -> bool:
        """检查模型是否已初始化"""
        return self._initialized
    
    def get_sense_voice_model(self) -> Tuple[Optional[SenseVoiceSmall], Optional[Dict]]:
        """获取SenseVoice模型和参数"""
        if not self._initialized:
            raise RuntimeError("模型未初始化，请先调用initialize()")
        return self.sense_voice_model, self.sense_voice_kwargs
    
    def get_streaming_model(self, auto_load: bool = True) -> Optional[AutoModel]:
        """获取流式模型
        
        Args:
            auto_load: 如果模型未加载，是否自动加载（默认True）
        """
        if not self._initialized:
            raise RuntimeError("模型未初始化，请先调用initialize()")
        
        # 延迟加载：首次获取时自动加载
        if self.streaming_model is None and auto_load:
            logger.info("首次使用WebSocket，正在加载流式模型...")
            self._load_streaming_model()
        
        return self.streaming_model
    
    def has_streaming_model(self) -> bool:
        """检查是否有可用的流式模型"""
        return self._initialized and self.streaming_model is not None


# 全局模型管理器实例
model_manager = SenseVoiceModelManager()
