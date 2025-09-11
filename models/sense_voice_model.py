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
    
    def initialize(self) -> bool:
        """初始化模型"""
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
            
            # 初始化AutoModel（用于流式处理）
            try:
                logger.info("正在加载流式模型...")
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
                logger.warning(f"流式模型加载失败，将仅使用基础模型: {e}")
                self.streaming_model = None
            
            self._initialized = True
            return True

        except Exception as e:
            logger.error(f"模型初始化失败: {e}")
            return False

    def _setup_memory_management(self):
        """设置显存管理"""
        try:
            if self.settings.device.startswith("cuda"):
                # 设置具体的GPU设备
                if ":" in self.settings.device:
                    device_id = int(self.settings.device.split(":")[1])
                    torch.cuda.set_device(device_id)
                    logger.info(f"设置当前CUDA设备为: {self.settings.device}")

                # 清理显存缓存
                torch.cuda.empty_cache()

                # 设置显存分配策略
                # 使用更保守的显存分配策略
                torch.cuda.memory.set_per_process_memory_fraction(0.8)  # 限制使用80%显存

                # 启用显存回收
                import gc
                gc.collect()

                logger.info("显存管理设置完成")

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
    
    def get_streaming_model(self) -> Optional[AutoModel]:
        """获取流式模型"""
        if not self._initialized:
            raise RuntimeError("模型未初始化，请先调用initialize()")
        return self.streaming_model
    
    def has_streaming_model(self) -> bool:
        """检查是否有可用的流式模型"""
        return self._initialized and self.streaming_model is not None


# 全局模型管理器实例
model_manager = SenseVoiceModelManager()
