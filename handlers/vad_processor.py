"""
独立VAD处理器模块
使用ModelScope的VAD模型进行语音活动检测
"""
import logging
import numpy as np
from typing import List, Tuple, Optional, Dict, Any
import torch

from funasr import AutoModel
from config.settings import get_settings

logger = logging.getLogger(__name__)


class SpeechSegment:
    """语音片段类"""
    
    def __init__(self, start_time: float, end_time: float, start_sample: int, end_sample: int):
        self.start_time = start_time
        self.end_time = end_time
        self.start_sample = start_sample
        self.end_sample = end_sample
        self.processed = False  # 是否已经ASR处理过
    
    def __repr__(self):
        return f"SpeechSegment({self.start_time:.2f}s-{self.end_time:.2f}s, processed={self.processed})"
    
    def duration(self) -> float:
        return self.end_time - self.start_time
    
    def sample_count(self) -> int:
        return self.end_sample - self.start_sample


class VADProcessor:
    """独立VAD处理器"""
    
    def __init__(self):
        self.settings = get_settings()
        self.vad_model: Optional[AutoModel] = None
        self._initialized = False
        
        # VAD参数
        self.min_speech_duration = 0.25  # 最小语音长度（秒）
        self.max_silence_duration = 0.8  # 最大静音长度（秒）
        self.speech_pad_ms = 30  # 语音前后填充（毫秒）
        
    def initialize(self) -> bool:
        """初始化VAD模型"""
        try:
            logger.info("正在加载独立VAD模型...")
            self.vad_model = AutoModel(
                model="iic/speech_fsmn_vad_zh-cn-16k-common-pytorch",
                trust_remote_code=True,
                device=self.settings.device,
                disable_update=True
            )
            self._initialized = True
            logger.info("独立VAD模型加载成功")
            return True
            
        except Exception as e:
            logger.error(f"VAD模型加载失败: {e}")
            self._initialized = False
            return False
    
    def is_initialized(self) -> bool:
        """检查VAD模型是否已初始化"""
        return self._initialized and self.vad_model is not None
    
    def detect_speech_segments(self, audio_data: np.ndarray, sample_rate: int = 16000) -> List[SpeechSegment]:
        """
        检测音频中的语音片段边界

        Args:
            audio_data: 音频数据
            sample_rate: 采样率

        Returns:
            语音片段列表（只包含时间边界信息）
        """
        if not self.is_initialized():
            logger.warning("VAD模型未初始化，返回空结果")
            return []

        if len(audio_data) == 0:
            return []

        try:
            # 确保音频数据格式正确
            if len(audio_data.shape) > 1:
                audio_data = audio_data.mean(axis=1)

            # 使用VAD模型检测语音边界
            vad_result = self.vad_model.generate(
                input=audio_data,
                cache={},
                is_final=True,  # 设置为True以获得完整结果
            )

            logger.debug(f"VAD原始结果: {vad_result}")

            segments = []

            if vad_result and len(vad_result) > 0:
                # 解析VAD结果
                vad_data = vad_result[0] if isinstance(vad_result, list) else vad_result
                logger.info(f"VAD数据类型: {type(vad_data)}")
                logger.debug(f"VAD数据内容: {vad_data}")

                # VAD结果通常包含语音片段的时间边界
                if isinstance(vad_data, dict):
                    logger.debug(f"VAD数据键: {list(vad_data.keys())}")

                    # 检查不同可能的结果格式
                    speech_timestamps = None
                    if 'value' in vad_data:
                        speech_timestamps = vad_data['value']
                        logger.debug(f"找到'value'字段: {speech_timestamps}")
                    elif 'speech_timestamps' in vad_data:
                        speech_timestamps = vad_data['speech_timestamps']
                        logger.info(f"找到'speech_timestamps'字段: {speech_timestamps}")
                    elif 'text' in vad_data:
                        speech_timestamps = vad_data['text']
                        logger.info(f"找到'text'字段: {speech_timestamps}")
                    elif 'segments' in vad_data:
                        speech_timestamps = vad_data['segments']
                        logger.info(f"找到'segments'字段: {speech_timestamps}")
                    else:
                        # 尝试直接使用整个数据
                        logger.info("未找到已知字段，尝试直接解析数据")
                        speech_timestamps = vad_data

                    if speech_timestamps:
                        logger.info(f"语音时间戳数据: {speech_timestamps}")
                        logger.info(f"语音时间戳类型: {type(speech_timestamps)}")

                        # 如果是列表，处理每个片段
                        if isinstance(speech_timestamps, list):
                            for i, segment in enumerate(speech_timestamps):
                                logger.info(f"处理片段 {i}: {segment} (类型: {type(segment)})")

                                if isinstance(segment, (list, tuple)) and len(segment) >= 2:
                                    start_ms, end_ms = segment[0], segment[1]
                                    start_time = start_ms / 1000.0
                                    end_time = end_ms / 1000.0

                                    logger.info(f"片段时间: {start_time:.2f}s - {end_time:.2f}s")

                                    # 过滤太短的语音片段
                                    if end_time - start_time >= self.min_speech_duration:
                                        start_sample = int(start_time * sample_rate)
                                        end_sample = int(end_time * sample_rate)

                                        # 确保样本索引在有效范围内
                                        start_sample = max(0, min(start_sample, len(audio_data)))
                                        end_sample = max(start_sample, min(end_sample, len(audio_data)))

                                        speech_segment = SpeechSegment(
                                            start_time=start_time,
                                            end_time=end_time,
                                            start_sample=start_sample,
                                            end_sample=end_sample
                                        )
                                        segments.append(speech_segment)
                                        logger.info(f"添加语音片段: {speech_segment}")
                                    else:
                                        logger.info(f"片段太短，跳过: {end_time - start_time:.2f}s < {self.min_speech_duration}s")
                        else:
                            logger.warning(f"语音时间戳不是列表格式: {type(speech_timestamps)}")
                    else:
                        logger.warning("未找到语音时间戳数据")
                else:
                    logger.warning(f"VAD数据不是字典格式: {type(vad_data)}")
            else:
                logger.warning("VAD结果为空或无效")

            logger.debug(f"VAD检测到 {len(segments)} 个语音片段")
            return segments

        except Exception as e:
            logger.error(f"VAD检测失败: {e}")
            return []
    
    def detect_speech_in_window(self, audio_data: np.ndarray, window_start_time: float,
                               sample_rate: int = 16000) -> List[SpeechSegment]:
        """
        在指定时间窗口内检测语音片段

        Args:
            audio_data: 音频数据
            window_start_time: 窗口开始时间（秒）
            sample_rate: 采样率

        Returns:
            语音片段列表（时间相对于全局时间轴）
        """
        logger.debug(f"VAD窗口检测: 窗口起始时间={window_start_time:.2f}s, 音频长度={len(audio_data)/sample_rate:.2f}s")

        segments = self.detect_speech_segments(audio_data, sample_rate)

        logger.debug(f"原始VAD片段数: {len(segments)}")
        for i, seg in enumerate(segments):
            logger.debug(f"  原始片段{i+1}: {seg.start_time:.2f}s-{seg.end_time:.2f}s")

        # 调整时间偏移
        adjusted_segments = []
        for segment in segments:
            adjusted_segment = SpeechSegment(
                start_time=segment.start_time + window_start_time,
                end_time=segment.end_time + window_start_time,
                start_sample=segment.start_sample,
                end_sample=segment.end_sample
            )
            adjusted_segments.append(adjusted_segment)
            logger.debug(f"调整后片段: {segment.start_time:.2f}s+{window_start_time:.2f}s = {adjusted_segment.start_time:.2f}s-{adjusted_segment.end_time:.2f}s")

        return adjusted_segments


# 全局VAD处理器实例
vad_processor = VADProcessor()
