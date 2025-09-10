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

        # Paraformer流式配置 - 参考FunASR官方文档
        self.chunk_size = [0, 10, 5]  # [0, 10, 5] 600ms, [0, 8, 4] 480ms
        self.encoder_chunk_look_back = 4  # number of chunks to lookback for encoder self-attention
        self.decoder_chunk_look_back = 1  # number of encoder chunks to lookback for decoder cross-attention
        self.chunk_stride = self.chunk_size[1] * 960  # 600ms (10 * 96 = 960 samples per chunk)

        # 获取模型
        self.streaming_model = model_manager.get_streaming_model()
        self.vad_model = model_manager.get_vad_model()

        if not self.streaming_model:
            logger.warning("流式模型不可用，将回退到基础模型")
            self.sense_voice_model, self.sense_voice_kwargs = model_manager.get_sense_voice_model()

        if not self.vad_model:
            logger.warning("VAD模型不可用，将使用简单的静音检测")

        # 流式状态管理
        self.cache = {}  # Paraformer流式缓存
        self.chunk_count = 0  # 当前处理的chunk数量
        self.accumulated_text = ""  # 累积的识别文本
        self.current_segment_texts = []  # 当前语音段落的所有中间结果

        # VAD状态管理
        self.vad_cache = {}  # VAD模型缓存
        self.speech_segments = []  # 检测到的语音段落
        self.last_speech_end = 0  # 最后一次检测到语音结束的时间
        self.vad_chunk_size = 200  # VAD检测的chunk大小（ms）
        self.silence_timeout = 1500  # 静音超时时间（ms）- 增加到1.5秒，让用户有更多时间思考
        
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
                # 流式模型总是返回结果，即使是空文本（这对流式处理很重要）
                return result

            # 回退到基础模型
            return await self._process_with_base_model(audio_tensor, language, **kwargs)
            
        except Exception as e:
            logger.error(f"音频处理错误: {e}")
            return self._create_error_result(str(e))
    
    async def _process_with_streaming_model(self, audio_tensor: torch.Tensor, language: str, **kwargs) -> Dict[str, Any]:
        """使用Paraformer流式模型处理音频"""
        try:
            streaming_model = model_manager.get_streaming_model()
            if streaming_model is None:
                return self._create_empty_result("流式模型不可用")

            # 获取音频数据
            audio_data = audio_tensor.numpy()
            if audio_data.ndim > 1:
                audio_data = audio_data.flatten()

            # 处理变长音频输入 - 支持真正的流式累积识别
            # 不再强制固定长度，让模型处理累积的音频数据
            logger.info(f"处理累积音频: {len(audio_data)} samples, 时长: {len(audio_data)/16000:.2f}s")

            # 检查是否明确要求结束
            explicit_final = kwargs.get("is_final", False)

            # 使用VAD检测端点（如果可用）
            is_final = explicit_final
            if not explicit_final and self.vad_model:
                is_final = self._detect_endpoint_with_vad(audio_data)
                if is_final:
                    logger.info(f"VAD检测到端点，设置为最终结果")

            logger.debug(f"Chunk {self.chunk_count}: is_final={is_final} (explicit={explicit_final}, vad_detected={is_final and not explicit_final})")

            # 使用Paraformer流式推理 - 关键：保持cache状态实现真正的流式累积
            logger.info(f"Chunk {self.chunk_count}: 调用流式模型, is_final={is_final}, cache_keys={list(self.cache.keys())}")

            res = streaming_model.generate(
                input=audio_data,
                cache=self.cache,  # 关键：cache在整个流式过程中保持状态
                is_final=is_final,
                chunk_size=self.chunk_size,
                encoder_chunk_look_back=self.encoder_chunk_look_back,  # 提供历史上下文
                decoder_chunk_look_back=self.decoder_chunk_look_back   # 提供解码上下文
            )

            self.chunk_count += 1

            if res and len(res) > 0:
                # 解析结果
                result_data = res[0] if isinstance(res, list) else res
                text = result_data.get("text", "") if isinstance(result_data, dict) else str(result_data)

                if text and text.strip():
                    logger.info(f"Chunk {self.chunk_count}: 识别结果='{text}', is_final={is_final}")

                    # Paraformer流式模型通过cache实现累积输出
                    result = self._create_success_result(text.strip(), "paraformer-streaming", confidence=0.9, is_final=is_final)

                    # 如果是最终结果，重置端点检测状态，但保持cache用于下一个语音段落
                    if is_final:
                        logger.info(f"Chunk {self.chunk_count}: 最终结果，重置端点检测状态")
                        self._reset_endpoint_detection()
                        # 重要：保持cache状态，这样下一个语音段落可以继续累积

                    return result
                else:
                    # 返回空的中间结果，但保持cache状态
                    return self._create_success_result("", "paraformer-streaming", confidence=0.9, is_final=False)

            return self._create_empty_result()

        except Exception as e:
            logger.warning(f"Paraformer流式模型处理失败: {e}")
            return self._create_empty_result(f"流式模型错误: {str(e)}")
    
    async def _process_with_base_model(self, audio_tensor: torch.Tensor, language: str, **kwargs) -> Dict[str, Any]:
        """使用基础模型处理音频"""
        try:
            sense_voice_model, sense_voice_kwargs = model_manager.get_sense_voice_model()
            if sense_voice_model is None:
                return self._create_error_result("基础模型不可用")
            
            # 使用SenseVoice模型进行识别
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
                    is_final = self._should_be_final(audio_tensor.numpy(), text)
                    return self._create_success_result(text, "base", confidence=0.8, is_final=is_final)
            
            return self._create_empty_result()
            
        except Exception as e:
            logger.error(f"基础模型处理失败: {e}")
            return self._create_error_result(f"基础模型错误: {str(e)}")
    
    def _create_success_result(self, text: str, model_type: str, confidence: float = 0.8, is_final: bool = False) -> Dict[str, Any]:
        """创建成功结果"""
        # 清理和后处理文本
        clean_text = re.sub(self.regex, "", text, 0, re.MULTILINE)
        processed_text = rich_transcription_postprocess(text)

        # Paraformer流式模型本身就支持累积输出，直接使用处理后的文本
        result_text = processed_text.strip()

        return {
            "text": result_text,
            "raw_text": text,
            "clean_text": clean_text,
            "is_final": is_final,
            "confidence": confidence,
            "model_type": model_type,
            "status": "success" if is_final else "partial"
        }

    def _should_be_final(self, audio_chunk: np.ndarray, text: str) -> bool:
        """判断是否应该输出最终结果（简化版本，主要依赖Paraformer的is_final参数）"""
        if not text or not text.strip():
            return False

        # 基于文本特征的简单判断
        text_stripped = text.strip()

        # 如果文本以句号结尾，可能是句子结束
        if text_stripped.endswith(('。', '！', '？', '.', '!', '?')):
            return True

        return False

    def _detect_endpoint_with_vad(self, audio_data: np.ndarray) -> bool:
        """使用VAD模型检测语音端点"""
        try:
            # 将音频数据转换为VAD模型需要的格式
            current_time = self.chunk_count * 600  # 当前时间（ms）

            # 使用VAD模型检测语音活动
            vad_result = self.vad_model.generate(
                input=audio_data,
                cache=self.vad_cache,
                is_final=False,
                chunk_size=self.vad_chunk_size
            )

            # 解析VAD结果
            if vad_result and len(vad_result) > 0 and "value" in vad_result[0]:
                segments = vad_result[0]["value"]

                # 检查是否有语音段落结束
                for segment in segments:
                    if len(segment) == 2 and segment[1] != -1:  # [start, end]
                        # 检测到语音段落结束
                        self.last_speech_end = current_time + segment[1]
                        logger.debug(f"VAD检测到语音结束: {self.last_speech_end}ms")

                # 检查静音超时
                silence_duration = current_time - self.last_speech_end
                if silence_duration > self.silence_timeout:
                    logger.info(f"VAD检测到静音超时 {silence_duration}ms，设置为最终结果")
                    return True

            return False

        except Exception as e:
            logger.warning(f"VAD端点检测失败: {e}")
            # 回退到简单检测
            return self._detect_endpoint_simple(audio_data)

    def _detect_endpoint_simple(self, audio_data: np.ndarray) -> bool:
        """简单的静音检测端点"""
        # 计算音频能量
        audio_energy = np.mean(np.abs(audio_data))
        silence_threshold = 0.01

        if audio_energy < silence_threshold:
            self.silence_count = getattr(self, 'silence_count', 0) + 1
        else:
            self.silence_count = 0

        # 连续5个chunk（3秒）静音则认为结束
        max_silence_chunks = 5
        if self.silence_count >= max_silence_chunks:
            logger.info(f"简单检测到连续静音 {self.silence_count} 个chunk，设置为最终结果")
            return True

        return False

    def _reset_endpoint_detection(self):
        """重置端点检测状态"""
        self.silence_count = 0
        self.last_speech_end = self.chunk_count * 600
        # 注意：不重置vad_cache，保持VAD的连续性

    def reset_streaming_state(self):
        """完全重置流式状态 - 只在用户明确要求时调用"""
        self.cache = {}
        self.vad_cache = {}
        self.chunk_count = 0
        self.silence_count = 0
        self.last_speech_end = 0
        logger.info("完全重置流式状态：清空所有cache和计数器")

    def reset_segment_state(self):
        """重置段落状态 - 保持cache用于累积识别"""
        # 只重置端点检测相关状态，保持模型cache
        self.silence_count = 0
        self.last_speech_end = self.chunk_count * 600
        # 重要：不重置 self.cache 和 self.vad_cache，保持流式连续性
        logger.info("重置段落状态：保持cache，只重置端点检测")

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
