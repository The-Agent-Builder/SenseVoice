"""
音频处理工具函数
"""
import numpy as np
import torch
import torchaudio
from typing import Tuple, Optional
import logging

logger = logging.getLogger(__name__)


def resample_audio(audio: torch.Tensor, orig_freq: int, target_freq: int) -> torch.Tensor:
    """重采样音频"""
    if orig_freq == target_freq:
        return audio
    
    resampler = torchaudio.transforms.Resample(orig_freq=orig_freq, new_freq=target_freq)
    return resampler(audio)


def convert_to_mono(audio: torch.Tensor) -> torch.Tensor:
    """转换为单声道"""
    if len(audio.shape) > 1 and audio.shape[0] > 1:
        return audio.mean(dim=0, keepdim=True)
    return audio


def normalize_audio(audio: torch.Tensor, target_level: float = -20.0) -> torch.Tensor:
    """音频归一化"""
    # 计算RMS
    rms = torch.sqrt(torch.mean(audio ** 2))
    if rms > 0:
        # 转换为dB
        current_db = 20 * torch.log10(rms)
        # 计算增益
        gain_db = target_level - current_db
        gain_linear = 10 ** (gain_db / 20)
        return audio * gain_linear
    return audio


def detect_silence(audio: np.ndarray, threshold: float = 0.01, min_duration: float = 0.5, 
                  sample_rate: int = 16000) -> bool:
    """检测音频是否为静音"""
    if len(audio) == 0:
        return True
    
    # 计算RMS
    rms = np.sqrt(np.mean(audio ** 2))
    
    # 检查是否低于阈值
    if rms < threshold:
        duration = len(audio) / sample_rate
        return duration >= min_duration
    
    return False


def split_audio_by_silence(audio: np.ndarray, sample_rate: int = 16000, 
                          silence_threshold: float = 0.01, min_silence_duration: float = 0.5,
                          min_segment_duration: float = 1.0) -> list:
    """根据静音分割音频"""
    if len(audio) == 0:
        return []
    
    # 计算窗口大小
    window_size = int(sample_rate * 0.1)  # 100ms窗口
    silence_samples = int(sample_rate * min_silence_duration)
    min_segment_samples = int(sample_rate * min_segment_duration)
    
    segments = []
    current_segment_start = 0
    silence_start = None
    
    for i in range(0, len(audio) - window_size, window_size):
        window = audio[i:i + window_size]
        rms = np.sqrt(np.mean(window ** 2))
        
        if rms < silence_threshold:
            if silence_start is None:
                silence_start = i
        else:
            if silence_start is not None:
                silence_duration = i - silence_start
                if silence_duration >= silence_samples:
                    # 找到足够长的静音，分割音频
                    segment_end = silence_start
                    if segment_end - current_segment_start >= min_segment_samples:
                        segments.append(audio[current_segment_start:segment_end])
                    current_segment_start = i
                silence_start = None
    
    # 添加最后一个片段
    if len(audio) - current_segment_start >= min_segment_samples:
        segments.append(audio[current_segment_start:])
    
    return segments


def calculate_audio_features(audio: np.ndarray, sample_rate: int = 16000) -> dict:
    """计算音频特征"""
    if len(audio) == 0:
        return {
            "duration": 0.0,
            "rms": 0.0,
            "max_amplitude": 0.0,
            "zero_crossing_rate": 0.0,
            "spectral_centroid": 0.0
        }
    
    duration = len(audio) / sample_rate
    rms = np.sqrt(np.mean(audio ** 2))
    max_amplitude = np.max(np.abs(audio))
    
    # 零交叉率
    zero_crossings = np.sum(np.diff(np.sign(audio)) != 0)
    zero_crossing_rate = zero_crossings / len(audio)
    
    # 频谱质心（简化计算）
    fft = np.fft.fft(audio)
    magnitude = np.abs(fft[:len(fft)//2])
    freqs = np.fft.fftfreq(len(fft), 1/sample_rate)[:len(fft)//2]
    
    if np.sum(magnitude) > 0:
        spectral_centroid = np.sum(freqs * magnitude) / np.sum(magnitude)
    else:
        spectral_centroid = 0.0
    
    return {
        "duration": duration,
        "rms": float(rms),
        "max_amplitude": float(max_amplitude),
        "zero_crossing_rate": float(zero_crossing_rate),
        "spectral_centroid": float(spectral_centroid)
    }


def validate_audio_quality(audio: np.ndarray, sample_rate: int = 16000, 
                          min_duration: float = 0.1, max_duration: float = 30.0,
                          min_rms: float = 1e-6) -> Tuple[bool, str]:
    """验证音频质量"""
    if len(audio) == 0:
        return False, "音频数据为空"
    
    duration = len(audio) / sample_rate
    
    if duration < min_duration:
        return False, f"音频时长过短: {duration:.2f}s < {min_duration}s"
    
    if duration > max_duration:
        return False, f"音频时长过长: {duration:.2f}s > {max_duration}s"
    
    rms = np.sqrt(np.mean(audio ** 2))
    if rms < min_rms:
        return False, f"音频信号过弱: RMS={rms:.2e} < {min_rms:.2e}"
    
    # 检查是否有异常值
    max_amplitude = np.max(np.abs(audio))
    if max_amplitude > 1.0:
        return False, f"音频幅度过大: {max_amplitude:.2f} > 1.0"
    
    # 检查是否有NaN或无穷值
    if np.any(np.isnan(audio)) or np.any(np.isinf(audio)):
        return False, "音频包含无效值(NaN或Inf)"
    
    return True, "音频质量正常"
