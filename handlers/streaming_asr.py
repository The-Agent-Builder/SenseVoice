"""
流式ASR处理模块
"""
import re
import logging
from typing import Dict, Any, Optional
import numpy as np
import torch

from funasr.utils.postprocess_utils import rich_transcription_postprocess
from models.sense_voice_model import model_manager
from handlers.audio_handler import AudioProcessor
from config.settings import get_settings

logger = logging.getLogger(__name__)


class StreamingASRHandler:
    """流式ASR处理器"""
    
    def __init__(self):
        self.settings = get_settings()
        self.audio_processor = AudioProcessor()
        self.regex = r"<\|.*\|>"
        
    async def process_audio_chunk(self, audio_chunk: np.ndarray, language: str = "auto", **kwargs) -> Dict[str, Any]:
        """处理音频块并返回识别结果"""
        try:
            if len(audio_chunk) == 0:
                return self._create_empty_result()
            
            # 验证音频格式
            if not self.audio_processor.validate_audio_format(audio_chunk):
                return self._create_empty_result("音频格式无效")
            
            # 预处理音频
            audio_tensor = self.audio_processor.preprocess_audio(audio_chunk)
            if len(audio_tensor) == 0:
                return self._create_empty_result("音频预处理失败")
            
            # 尝试使用流式模型
            if model_manager.has_streaming_model():
                result = await self._process_with_streaming_model(audio_tensor, language, **kwargs)
                if result["text"]:
                    return result
            
            # 回退到基础模型
            return await self._process_with_base_model(audio_tensor, language, **kwargs)
            
        except Exception as e:
            logger.error(f"音频处理错误: {e}")
            return self._create_error_result(str(e))
    
    async def _process_with_streaming_model(self, audio_tensor: torch.Tensor, language: str, **kwargs) -> Dict[str, Any]:
        """使用流式模型处理音频"""
        try:
            streaming_model = model_manager.get_streaming_model()
            if streaming_model is None:
                return self._create_empty_result("流式模型不可用")
            
            # 使用AutoModel进行识别
            res = streaming_model.generate(
                input=audio_tensor.numpy(),
                cache={},
                language=language,
                use_itn=True,
                batch_size_s=60,
                merge_vad=True,
                merge_length_s=kwargs.get("merge_length_s", 2),
            )
            
            if res and len(res) > 0:
                text = res[0].get("text", "")
                if text:
                    return self._create_success_result(text, "streaming", confidence=0.9)
            
            return self._create_empty_result()
            
        except Exception as e:
            logger.warning(f"流式模型处理失败: {e}")
            return self._create_empty_result(f"流式模型错误: {str(e)}")
    
    async def _process_with_base_model(self, audio_tensor: torch.Tensor, language: str, **kwargs) -> Dict[str, Any]:
        """使用基础模型处理音频"""
        try:
            sense_voice_model, sense_voice_kwargs = model_manager.get_sense_voice_model()
            if sense_voice_model is None:
                return self._create_error_result("基础模型不可用")
            
            # 使用SenseVoiceSmall进行识别
            res = sense_voice_model.inference(
                data_in=[audio_tensor],
                language=language,
                use_itn=False,
                ban_emo_unk=False,
                key=["streaming_chunk"],
                fs=self.settings.target_sample_rate,
                **sense_voice_kwargs,
            )
            
            if res and len(res) > 0 and len(res[0]) > 0:
                result = res[0][0]
                text = result.get("text", "")
                if text:
                    return self._create_success_result(text, "base", confidence=0.8)
            
            return self._create_empty_result()
            
        except Exception as e:
            logger.error(f"基础模型处理失败: {e}")
            return self._create_error_result(f"基础模型错误: {str(e)}")
    
    def _create_success_result(self, text: str, model_type: str, confidence: float = 0.8) -> Dict[str, Any]:
        """创建成功结果"""
        # 清理和后处理文本
        clean_text = re.sub(self.regex, "", text, 0, re.MULTILINE)
        processed_text = rich_transcription_postprocess(text)
        
        return {
            "text": processed_text,
            "raw_text": text,
            "clean_text": clean_text,
            "is_final": True,
            "confidence": confidence,
            "model_type": model_type,
            "status": "success"
        }
    
    def _create_empty_result(self, message: str = "") -> Dict[str, Any]:
        """创建空结果"""
        return {
            "text": "",
            "raw_text": "",
            "clean_text": "",
            "is_final": False,
            "confidence": 0.0,
            "model_type": "none",
            "status": "empty",
            "message": message
        }
    
    def _create_error_result(self, error_message: str) -> Dict[str, Any]:
        """创建错误结果"""
        return {
            "text": "",
            "raw_text": "",
            "clean_text": "",
            "is_final": False,
            "confidence": 0.0,
            "model_type": "none",
            "status": "error",
            "error": error_message
        }
