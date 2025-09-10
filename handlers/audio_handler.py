"""
音频处理模块
"""
import logging
import base64
from collections import deque
from typing import Optional, List
import numpy as np
import torch
import torchaudio
from io import BytesIO
import tempfile
import os
import time
import gc

from config.settings import get_settings

# 添加pydub支持
try:
    from pydub import AudioSegment
    PYDUB_AVAILABLE = True
except ImportError:
    PYDUB_AVAILABLE = False
    logging.warning("pydub not available, fallback to basic audio processing")

logger = logging.getLogger(__name__)


class AudioBuffer:
    """音频缓冲区管理类 - 支持VAD驱动的音频消费"""

    def __init__(self, max_duration: Optional[float] = None, sample_rate: Optional[int] = None):
        settings = get_settings()
        self.max_duration = max_duration or settings.audio_buffer_duration
        self.sample_rate = sample_rate or settings.target_sample_rate
        self.max_samples = int(self.max_duration * self.sample_rate)
        self.buffer = deque(maxlen=self.max_samples)
        self.processed_offset = 0  # 已处理的音频样本数

        # VAD相关状态
        self.total_samples_added = 0  # 总共添加的样本数（用于计算全局时间）
        self.vad_processed_offset = 0  # 已VAD检测的样本数
        self.speech_segments: List = []  # 检测到的语音片段列表
        self.processed_segments: List = []  # 已ASR处理的语音片段列表

    def add_audio(self, audio_data: np.ndarray):
        """添加音频数据到缓冲区"""
        if len(audio_data.shape) > 1:
            # 转换为单声道
            audio_data = audio_data.mean(axis=1)

        for sample in audio_data:
            self.buffer.append(sample)

        # 更新总样本计数
        self.total_samples_added += len(audio_data)

    def get_audio_chunk(self, duration: float) -> np.ndarray:
        """获取指定时长的音频块（保持向后兼容）"""
        chunk_samples = int(duration * self.sample_rate)
        if len(self.buffer) < chunk_samples:
            return np.array(list(self.buffer))

        # 获取最新的音频数据
        chunk = np.array(list(self.buffer)[-chunk_samples:])
        return chunk

    def get_unprocessed_audio(self) -> np.ndarray:
        """获取未处理的音频数据（用于VAD驱动处理）"""
        buffer_array = np.array(list(self.buffer))
        total_samples = len(buffer_array)

        # 如果processed_offset超出了当前缓冲区大小，重置为0
        if self.processed_offset >= total_samples:
            self.processed_offset = 0
            return buffer_array

        # 返回未处理的部分
        unprocessed = buffer_array[self.processed_offset:]
        return unprocessed

    def get_all_audio_for_vad(self) -> np.ndarray:
        """获取所有音频数据用于VAD处理（包括已处理的上下文）"""
        return np.array(list(self.buffer))

    def mark_processed(self, processed_samples: int):
        """标记已处理的音频样本数"""
        self.processed_offset += processed_samples
        # 确保不超过当前缓冲区大小
        total_samples = len(self.buffer)
        if self.processed_offset > total_samples:
            self.processed_offset = total_samples

    def get_all_audio(self) -> np.ndarray:
        """获取缓冲区中的所有音频数据"""
        return np.array(list(self.buffer))

    def clear(self):
        """清空缓冲区"""
        self.buffer.clear()
        self.processed_offset = 0
        # 清空VAD相关状态
        self.total_samples_added = 0
        self.vad_processed_offset = 0
        self.speech_segments.clear()
        self.processed_segments.clear()

    def get_duration(self) -> float:
        """获取当前缓冲区的音频时长（秒）"""
        return len(self.buffer) / self.sample_rate

    def get_unprocessed_duration(self) -> float:
        """获取未处理音频的时长（秒）"""
        unprocessed_samples = len(self.buffer) - self.processed_offset
        return max(0, unprocessed_samples) / self.sample_rate

    def has_enough_audio(self, required_duration: float) -> bool:
        """检查是否有足够的音频数据"""
        return self.get_duration() >= required_duration

    def has_unprocessed_audio(self, min_duration: float = 0.1) -> bool:
        """检查是否有足够的未处理音频数据"""
        return self.get_unprocessed_duration() >= min_duration

    # VAD相关方法
    def get_audio_for_vad(self) -> tuple[np.ndarray, float]:
        """获取需要VAD检测的音频数据和起始时间"""
        buffer_array = np.array(list(self.buffer))
        total_samples = len(buffer_array)

        # 计算当前缓冲区的起始时间（相对于全局时间轴）
        buffer_start_time = max(0, (self.total_samples_added - total_samples) / self.sample_rate)

        # 计算需要VAD检测的部分
        vad_start_sample = max(0, self.vad_processed_offset - (self.total_samples_added - total_samples))

        if vad_start_sample >= total_samples:
            return np.array([]), buffer_start_time

        # 返回未VAD检测的音频和其在全局时间轴上的起始时间
        unprocessed_audio = buffer_array[vad_start_sample:]
        audio_start_time = buffer_start_time + (vad_start_sample / self.sample_rate)

        # 调试日志
        logger.debug(f"VAD音频获取: 总样本={self.total_samples_added}, 缓冲区样本={total_samples}, "
                    f"缓冲区起始时间={buffer_start_time:.2f}s, VAD已处理偏移={self.vad_processed_offset}, "
                    f"VAD起始样本={vad_start_sample}, 音频起始时间={audio_start_time:.2f}s, "
                    f"未处理音频长度={len(unprocessed_audio)}")

        return unprocessed_audio, audio_start_time

    def get_all_audio(self) -> np.ndarray:
        """获取整个缓冲区的音频数据"""
        return np.array(list(self.buffer))

    def consume_audio(self, samples_to_consume: int):
        """消费指定数量的音频样本

        Args:
            samples_to_consume: 要消费的样本数
        """
        if samples_to_consume <= 0:
            return

        # 从缓冲区左侧移除指定数量的样本
        for _ in range(min(samples_to_consume, len(self.buffer))):
            self.buffer.popleft()

        # 清理相关状态
        self.speech_segments.clear()
        self.processed_segments.clear()
        self.vad_processed_offset = 0

        logger.debug(f"消费了 {samples_to_consume} 个样本，缓冲区剩余: {len(self.buffer)} 样本")

    def add_speech_segments(self, segments: List):
        """添加VAD检测到的语音片段"""
        for segment in segments:
            # 检查是否已存在（避免重复）
            exists = any(
                abs(existing.start_time - segment.start_time) < 0.1 and
                abs(existing.end_time - segment.end_time) < 0.1
                for existing in self.speech_segments
            )
            if not exists:
                self.speech_segments.append(segment)

        # 按时间排序
        self.speech_segments.sort(key=lambda x: x.start_time)

    def mark_vad_processed(self, processed_samples: int):
        """标记已VAD检测的样本数"""
        self.vad_processed_offset += processed_samples

    def get_unprocessed_speech_segments(self):
        """获取未ASR处理的语音片段"""
        unprocessed = []
        for segment in self.speech_segments:
            if not segment.processed:
                unprocessed.append(segment)
        return unprocessed

    def get_speech_segment_audio(self, segment, context_ms: int = 100) -> Optional[np.ndarray]:
        """获取指定语音片段的音频数据（带上下文）"""
        buffer_array = np.array(list(self.buffer))
        total_samples = len(buffer_array)

        # 计算当前缓冲区的起始时间
        buffer_start_time = max(0, (self.total_samples_added - total_samples) / self.sample_rate)
        buffer_end_time = self.total_samples_added / self.sample_rate

        # 检查语音片段是否在当前缓冲区范围内
        if segment.end_time < buffer_start_time or segment.start_time > buffer_end_time:
            return None

        # 添加上下文
        context_seconds = context_ms / 1000.0
        start_time_with_context = max(buffer_start_time, segment.start_time - context_seconds)
        end_time_with_context = min(buffer_end_time, segment.end_time + context_seconds)

        # 转换为样本索引
        start_sample = int((start_time_with_context - buffer_start_time) * self.sample_rate)
        end_sample = int((end_time_with_context - buffer_start_time) * self.sample_rate)

        # 确保索引在有效范围内
        start_sample = max(0, min(start_sample, total_samples))
        end_sample = max(start_sample, min(end_sample, total_samples))

        return buffer_array[start_sample:end_sample]

    def mark_segment_processed(self, segment):
        """标记语音片段为已处理"""
        segment.processed = True
        if segment not in self.processed_segments:
            self.processed_segments.append(segment)


class AudioProcessor:
    """音频处理器"""
    
    def __init__(self):
        self.settings = get_settings()
    
    def decode_audio_data(self, audio_data: str, encoding: str = "base64") -> Optional[np.ndarray]:
        """解码Opus音频数据"""
        try:
            if encoding == "base64":
                # 解码base64音频数据
                audio_bytes = base64.b64decode(audio_data)
                logger.info(f"接收到Opus音频数据，长度: {len(audio_bytes)} bytes")
                
                # 使用pydub解码Opus格式
                if PYDUB_AVAILABLE:
                    audio_array = self._decode_opus_with_pydub(audio_bytes)
                else:
                    # 降级到基础处理（假设为WAV格式）
                    logger.warning("pydub不可用，尝试直接解码为WAV")
                    audio_array = self._decode_as_wav(audio_bytes)
                
                if audio_array is None:
                    return None
                
                logger.info(f"Opus音频解码成功，样本数: {len(audio_array)}")
                return audio_array
            else:
                logger.error(f"不支持的音频编码格式: {encoding}")
                return None
                
        except Exception as e:
            logger.error(f"Opus音频解码失败: {e}")
            return None
    
    def _decode_opus_with_pydub(self, audio_bytes: bytes) -> Optional[np.ndarray]:
        """使用pydub解码Opus音频"""
        try:
            # 首先尝试内存处理方式（避免临时文件）
            try:
                audio_io = BytesIO(audio_bytes)
                audio_segment = AudioSegment.from_file(audio_io, format="webm")

                # 转换为目标采样率和单声道
                audio_segment = audio_segment.set_frame_rate(self.settings.target_sample_rate)
                audio_segment = audio_segment.set_channels(1)

                # 转换为numpy数组
                audio_array = np.array(audio_segment.get_array_of_samples(), dtype=np.float32)

                # 归一化到[-1, 1]
                audio_array = audio_array / 32768.0

                # 显式删除audio_segment以释放资源
                del audio_segment

                logger.debug("使用内存方式成功解码Opus音频")
                return audio_array

            except Exception as memory_error:
                logger.debug(f"内存解码失败，回退到临时文件方式: {memory_error}")
                # 回退到临时文件方式
                return self._decode_opus_with_temp_file(audio_bytes)

        except Exception as e:
            logger.error(f"pydub Opus解码失败: {e}")
            return None

    def _decode_opus_with_temp_file(self, audio_bytes: bytes) -> Optional[np.ndarray]:
        """使用临时文件解码Opus音频（回退方案）"""
        temp_file_path = None
        try:
            # 创建临时文件
            with tempfile.NamedTemporaryFile(suffix='.webm', delete=False) as temp_file:
                temp_file_path = temp_file.name
                temp_file.write(audio_bytes)
                temp_file.flush()

            # 文件句柄已关闭，现在可以安全地被其他程序访问
            try:
                # 使用pydub加载WebM/Opus文件
                audio_segment = AudioSegment.from_file(temp_file_path, format="webm")

                # 转换为目标采样率和单声道
                audio_segment = audio_segment.set_frame_rate(self.settings.target_sample_rate)
                audio_segment = audio_segment.set_channels(1)

                # 转换为numpy数组
                audio_array = np.array(audio_segment.get_array_of_samples(), dtype=np.float32)

                # 归一化到[-1, 1]
                audio_array = audio_array / 32768.0

                # 显式删除audio_segment以释放资源
                del audio_segment

                return audio_array

            finally:
                # 安全删除临时文件，使用重试机制
                self._safe_delete_temp_file(temp_file_path)

        except Exception as e:
            logger.error(f"临时文件Opus解码失败: {e}")
            # 确保临时文件被清理
            if temp_file_path:
                self._safe_delete_temp_file(temp_file_path)
            return None

    def _safe_delete_temp_file(self, file_path: str, max_retries: int = 3, delay: float = 0.1):
        """安全删除临时文件，使用重试机制处理Windows文件锁定问题"""
        if not file_path or not os.path.exists(file_path):
            return

        for attempt in range(max_retries):
            try:
                # 强制垃圾回收以释放可能的文件句柄
                gc.collect()

                # 尝试删除文件
                os.unlink(file_path)
                logger.debug(f"临时文件删除成功: {file_path}")
                return

            except (OSError, PermissionError) as e:
                if attempt < max_retries - 1:
                    logger.debug(f"删除临时文件失败 (尝试 {attempt + 1}/{max_retries}): {e}")
                    time.sleep(delay)
                    delay *= 2  # 指数退避
                else:
                    logger.warning(f"无法删除临时文件 {file_path}: {e}")
                    # 不抛出异常，避免影响主流程

    def _decode_as_wav(self, audio_bytes: bytes) -> Optional[np.ndarray]:
        """降级方案：尝试直接解码为WAV"""
        try:
            audio_io = BytesIO(audio_bytes)
            waveform, sample_rate = torchaudio.load(audio_io)
            
            # 重采样到目标采样率
            if sample_rate != self.settings.target_sample_rate:
                resampler = torchaudio.transforms.Resample(
                    orig_freq=sample_rate, 
                    new_freq=self.settings.target_sample_rate
                )
                waveform = resampler(waveform)
            
            # 转换为numpy数组并确保是单声道
            audio_array = waveform.numpy()
            if len(audio_array.shape) > 1:
                audio_array = audio_array.mean(axis=0)
            
            return audio_array
            
        except Exception as e:
            logger.error(f"WAV降级解码失败: {e}")
            return None
    
    def preprocess_audio(self, audio_data: np.ndarray) -> torch.Tensor:
        """预处理音频数据"""
        try:
            # 确保是单声道
            if len(audio_data.shape) > 1:
                audio_data = audio_data.mean(axis=1)
            
            # 转换为torch tensor
            audio_tensor = torch.from_numpy(audio_data).float()
            
            return audio_tensor
            
        except Exception as e:
            logger.error(f"音频预处理失败: {e}")
            return torch.empty(0)
    
    def validate_audio_format(self, audio_data: np.ndarray, min_duration: float = 0.5) -> bool:
        """验证音频格式和质量"""
        try:
            if len(audio_data) == 0:
                return False
            
            duration = len(audio_data) / self.settings.target_sample_rate
            if duration < min_duration:
                logger.debug(f"音频时长过短: {duration:.2f}s")
                return False
            
            # 检查音频是否为静音（提高阈值）
            max_amplitude = np.max(np.abs(audio_data))
            if max_amplitude < 0.01:  # 提高静音检测阈值
                logger.debug("检测到静音音频")
                return False
            
            # 检查音频能量是否足够
            rms_energy = np.sqrt(np.mean(audio_data ** 2))
            if rms_energy < 0.005:  # 添加能量阈值
                logger.debug(f"音频能量过低: {rms_energy:.6f}")
                return False
            
            return True
            
        except Exception as e:
            logger.error(f"音频格式验证失败: {e}")
            return False
