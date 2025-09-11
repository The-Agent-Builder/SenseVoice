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
from handlers.vad_processor import vad_processor
from config.settings import get_settings

logger = logging.getLogger(__name__)


class StreamingASRHandler:
    """流式ASR处理器"""
    
    def __init__(self):
        self.settings = get_settings()
        self.audio_processor = AudioProcessor()
        self.regex = r"<\|.*\|>"
        
    async def process_audio_chunk(self, audio_chunk: np.ndarray, language: str = "auto", **kwargs) -> Dict[str, Any]:
        """处理音频块并返回识别结果（保持向后兼容）"""
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

    async def process_audio_with_vad(self, audio_data: np.ndarray, cache: dict, language: str = "auto", **kwargs) -> Dict[str, Any]:
        """使用VAD驱动的音频处理方法"""
        try:
            if len(audio_data) == 0:
                return self._create_empty_result()

            # 验证音频格式
            if not self.audio_processor.validate_audio_format(audio_data):
                return self._create_empty_result("音频格式无效")

            # 预处理音频
            audio_tensor = self.audio_processor.preprocess_audio(audio_data)
            if len(audio_tensor) == 0:
                return self._create_empty_result("音频预处理失败")

            # 使用流式模型进行VAD驱动处理
            if model_manager.has_streaming_model():
                result = await self._process_with_streaming_model_vad(audio_tensor, cache, language, **kwargs)
                return result

            # 回退到基础模型
            return await self._process_with_base_model(audio_tensor, language, **kwargs)

        except Exception as e:
            logger.error(f"VAD驱动音频处理失败: {e}")
            return self._create_error_result(f"处理失败: {str(e)}")
    
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
                use_itn=False,  # 关闭逆文本标准化，保留原始标记
                batch_size_s=60,
                merge_vad=True,
                merge_length_s=kwargs.get("merge_length_s", 2),
            )
            
            if res and len(res) > 0:
                # 解析结果
                result_data = res[0] if isinstance(res, list) else res
                text = result_data.get("text", "") if isinstance(result_data, dict) else str(result_data)
                
                if text and text.strip():
                    return self._create_success_result(text.strip(), "streaming", confidence=0.9)
            
            return self._create_empty_result()
            
        except Exception as e:
            logger.warning(f"流式模型处理失败: {e}")
            return self._create_empty_result(f"流式模型错误: {str(e)}")

    async def _process_with_streaming_model_vad(self, audio_tensor: torch.Tensor, cache: dict, language: str, **kwargs) -> Dict[str, Any]:
        """使用流式模型进行VAD驱动处理"""
        try:
            streaming_model = model_manager.get_streaming_model()
            if streaming_model is None:
                return self._create_empty_result("流式模型不可用")

            # 使用持久cache进行流式识别
            res = streaming_model.generate(
                input=audio_tensor.numpy(),
                cache=cache,  # 使用持久的cache
                language=language,
                use_itn=False,  # 关闭逆文本标准化，保留原始标记
                batch_size_s=60,
                merge_vad=True,  # 启用VAD合并
                merge_length_s=kwargs.get("merge_length_s", 0),  # 让VAD决定分割点
            )

            if res and len(res) > 0:
                # 解析结果
                result_data = res[0] if isinstance(res, list) else res
                text = result_data.get("text", "") if isinstance(result_data, dict) else str(result_data)

                if text and text.strip():
                    logger.info(f"VAD驱动识别结果: {text.strip()}")
                    return self._create_success_result(text.strip(), "streaming_vad", confidence=0.9)

            # 即使没有文本输出，也返回成功（VAD可能还在等待更多音频）
            return self._create_empty_result()

        except Exception as e:
            logger.error(f"VAD驱动流式模型处理失败: {e}")
            return self._create_error_result(f"VAD驱动处理失败: {str(e)}")

    async def process_audio_with_independent_vad(self, audio_buffer, language: str = "auto") -> Dict[str, Any]:
        """使用独立VAD模型进行连续音频处理

        简化的缓冲区消费方式：
        1. VAD检测整个缓冲区（从0开始）
        2. 当检测到完整的语音片段时，消费掉这部分
        3. 缓冲区重新从0开始，继续累积新数据
        """
        try:
            # 确保VAD模型已初始化
            if not vad_processor.is_initialized():
                if not vad_processor.initialize():
                    return self._create_error_result("VAD模型初始化失败")

            # 获取整个缓冲区的音频数据
            buffer_audio = audio_buffer.get_all_audio()

            if len(buffer_audio) == 0:
                return self._create_empty_result("缓冲区为空")

            buffer_duration = len(buffer_audio) / self.settings.target_sample_rate
            logger.debug(f"VAD处理整个缓冲区: 音频长度={len(buffer_audio)}, 时长={buffer_duration:.2f}s")

            # 对整个缓冲区进行VAD检测（从0开始）
            speech_segments = vad_processor.detect_speech_segments(
                buffer_audio,
                self.settings.target_sample_rate
            )

            logger.debug(f"VAD检测到 {len(speech_segments)} 个语音片段")
            for i, seg in enumerate(speech_segments):
                logger.debug(f"  片段{i+1}: {seg.start_time:.2f}s-{seg.end_time:.2f}s")

            # 查找可以消费的完整语音片段
            consumable_segments = self._find_consumable_segments(speech_segments, buffer_duration)

            results = []
            total_consumed_duration = 0

            for segment in consumable_segments:
                # 提取语音片段的音频数据
                start_sample = int(segment.start_time * self.settings.target_sample_rate)
                end_sample = int(segment.end_time * self.settings.target_sample_rate)
                segment_audio = buffer_audio[start_sample:end_sample]

                if len(segment_audio) > 0:
                    # 对语音片段进行ASR
                    asr_result = await self._process_speech_segment(segment_audio, language)

                    if asr_result.get("text") and asr_result["text"].strip():
                        # 添加时间信息
                        asr_result["segment_start_time"] = segment.start_time
                        asr_result["segment_end_time"] = segment.end_time
                        asr_result["segment_duration"] = segment.duration()

                        results.append(asr_result)
                        logger.info(f"处理语音片段 {segment.start_time:.2f}s-{segment.end_time:.2f}s: {asr_result['text']}")

                        # 更新已消费的时长
                        total_consumed_duration = max(total_consumed_duration, segment.end_time)

            # 消费已处理的音频数据
            if total_consumed_duration > 0:
                consumed_samples = int(total_consumed_duration * self.settings.target_sample_rate)
                audio_buffer.consume_audio(consumed_samples)
                logger.info(f"消费音频: {total_consumed_duration:.2f}s ({consumed_samples} 样本)")

            # 返回最新的识别结果
            if results:
                return results[-1]  # 返回最后一个结果
            else:
                return self._create_empty_result("没有检测到可消费的语音片段")

        except Exception as e:
            logger.error(f"独立VAD音频处理失败: {e}")
            return self._create_error_result(f"独立VAD处理失败: {str(e)}")

    def _find_consumable_segments(self, speech_segments, buffer_duration):
        """查找可以消费的完整语音片段

        简化逻辑：VAD已经处理好了语音边界检测，直接消费所有检测到的片段
        """
        if not speech_segments:
            return []

        # 简化逻辑：VAD已经处理好了语音边界，直接消费所有检测到的片段
        logger.info(f"VAD检测到 {len(speech_segments)} 个语音片段，全部可消费")
        for i, segment in enumerate(speech_segments):
            logger.info(f"  片段{i+1}: {segment.start_time:.2f}s-{segment.end_time:.2f}s (时长: {segment.duration():.2f}s)")

        return speech_segments

    def _update_speech_state(self, audio_buffer, new_segments, audio_start_time):
        """更新语音状态，实现无缝的连续处理

        策略：
        1. 检查新检测到的语音片段
        2. 与现有的语音片段进行合并或扩展
        3. 避免重复添加相同的语音区间
        4. 维护连续的语音边界
        """
        if not new_segments:
            return

        current_segments = audio_buffer.speech_segments

        for new_segment in new_segments:
            # 检查是否与现有片段重叠或相邻
            merged = False

            for i, existing_segment in enumerate(current_segments):
                # 如果已处理，跳过
                if existing_segment.processed:
                    continue

                # 检查是否重叠或相邻（允许小间隔）
                gap_threshold = 0.1  # 0.1秒内认为是连续的

                # 新片段在现有片段之前且相邻
                if (new_segment.end_time >= existing_segment.start_time - gap_threshold and
                    new_segment.start_time <= existing_segment.start_time):
                    # 扩展现有片段的开始时间
                    existing_segment.start_time = min(existing_segment.start_time, new_segment.start_time)
                    existing_segment.start_sample = int(existing_segment.start_time * self.settings.target_sample_rate)
                    merged = True
                    logger.debug(f"扩展片段开始: {existing_segment}")
                    break

                # 新片段在现有片段之后且相邻
                elif (new_segment.start_time <= existing_segment.end_time + gap_threshold and
                      new_segment.end_time >= existing_segment.end_time):
                    # 扩展现有片段的结束时间
                    existing_segment.end_time = max(existing_segment.end_time, new_segment.end_time)
                    existing_segment.end_sample = int(existing_segment.end_time * self.settings.target_sample_rate)
                    merged = True
                    logger.debug(f"扩展片段结束: {existing_segment}")
                    break

                # 新片段完全包含在现有片段内
                elif (new_segment.start_time >= existing_segment.start_time and
                      new_segment.end_time <= existing_segment.end_time):
                    # 不需要添加，已经包含
                    merged = True
                    logger.debug(f"片段已包含: {new_segment} 在 {existing_segment} 内")
                    break

                # 现有片段完全包含在新片段内
                elif (existing_segment.start_time >= new_segment.start_time and
                      existing_segment.end_time <= new_segment.end_time):
                    # 扩展现有片段
                    existing_segment.start_time = new_segment.start_time
                    existing_segment.end_time = new_segment.end_time
                    existing_segment.start_sample = new_segment.start_sample
                    existing_segment.end_sample = new_segment.end_sample
                    merged = True
                    logger.debug(f"扩展片段范围: {existing_segment}")
                    break

            # 如果没有合并，添加为新片段
            if not merged:
                audio_buffer.speech_segments.append(new_segment)
                logger.debug(f"添加新语音片段: {new_segment}")

    def _find_completed_speech_segments(self, audio_buffer):
        """查找已完成的语音片段（有明确结束边界的）

        判断标准：
        1. 语音片段后面有足够的静音间隔
        2. 语音片段不是最后一个（最后一个可能还在进行中）
        3. 语音片段的结束时间距离当前缓冲区末尾有一定距离
        """
        all_segments = audio_buffer.speech_segments
        if not all_segments:
            return []

        completed_segments = []
        current_time = audio_buffer.get_duration()  # 当前缓冲区的总时长

        # 最小静音间隔（秒）- 用于判断语音是否真正结束
        min_silence_gap = 0.3  # 降低到0.3秒，更容易触发

        logger.debug(f"检查 {len(all_segments)} 个语音片段，当前缓冲区时长: {current_time:.2f}s")

        for i, segment in enumerate(all_segments):
            # 跳过已处理的片段
            if segment.processed:
                continue

            # 检查是否是最后一个片段
            is_last_segment = (i == len(all_segments) - 1)

            if is_last_segment:
                # 最后一个片段：检查是否距离当前时间有足够的间隔
                time_since_end = current_time - segment.end_time
                if time_since_end >= min_silence_gap:
                    completed_segments.append(segment)
                    logger.info(f"最后片段已完成: {segment}, 静音时长: {time_since_end:.2f}s")
                else:
                    logger.debug(f"最后片段未完成: {segment}, 静音时长不足: {time_since_end:.2f}s < {min_silence_gap}s")
            else:
                # 非最后片段：检查与下一个片段的间隔
                next_segment = all_segments[i + 1]
                silence_gap = next_segment.start_time - segment.end_time

                if silence_gap >= min_silence_gap:
                    completed_segments.append(segment)
                    logger.info(f"片段已完成: {segment}, 静音间隔: {silence_gap:.2f}s")
                else:
                    # 间隔太短，可能是连续语音，暂不处理
                    logger.debug(f"片段未完成: {segment}, 静音间隔太短: {silence_gap:.2f}s < {min_silence_gap}s")

        logger.info(f"找到 {len(completed_segments)} 个已完成的语音片段")
        return completed_segments

    async def _process_speech_segment(self, audio_data: np.ndarray, language: str) -> Dict[str, Any]:
        """使用SenseVoice处理单个语音片段"""
        try:
            # 验证音频格式
            if not self.audio_processor.validate_audio_format(audio_data):
                return self._create_empty_result("语音片段格式无效")

            # 预处理音频
            audio_tensor = self.audio_processor.preprocess_audio(audio_data)
            if len(audio_tensor) == 0:
                return self._create_empty_result("语音片段预处理失败")

            # 使用SenseVoice模型进行识别
            sense_voice_model, sense_voice_kwargs = model_manager.get_sense_voice_model()
            if sense_voice_model is None:
                return self._create_error_result("SenseVoice模型不可用")

            # 使用SenseVoice模型进行识别
            res = sense_voice_model.inference(
                data_in=[audio_tensor],
                language=language,
                use_itn=False,  # 关闭逆文本标准化，保留原始标记
                ban_emo_unk=False,  # 允许情感标记输出
                key=["vad_segment"],
                fs=self.settings.target_sample_rate,
                **sense_voice_kwargs,
            )

            if res and len(res) > 0 and len(res[0]) > 0:
                result = res[0][0]
                text = result.get("text", "")
                if text and text.strip():
                    return self._create_success_result(text.strip(), "sensevoice_vad", confidence=0.9)

            return self._create_empty_result("语音片段无识别结果")

        except Exception as e:
            logger.error(f"SenseVoice语音片段处理失败: {e}")
            return self._create_error_result(f"SenseVoice处理失败: {str(e)}")
    
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
                use_itn=False,  # 关闭逆文本标准化，保留原始标记
                ban_emo_unk=False,  # 允许情感标记输出
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
