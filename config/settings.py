"""
配置管理模块
"""
import os
from typing import Optional


class Settings:
    """应用配置"""

    def __init__(self):
        # 模型配置
        self.model_dir = "iic/SenseVoiceSmall"
        
        # 设备选择逻辑
        self.device = self._determine_device()
        self.target_sample_rate = int(os.getenv("SENSEVOICE_TARGET_SAMPLE_RATE", "16000"))

        # WebSocket配置
        self.max_connections = int(os.getenv("SENSEVOICE_MAX_CONNECTIONS", "100"))
        self.audio_buffer_duration = float(os.getenv("SENSEVOICE_AUDIO_BUFFER_DURATION", "10.0"))
        self.default_chunk_duration = float(os.getenv("SENSEVOICE_DEFAULT_CHUNK_DURATION", "3.0"))  # 增加到3秒

        # API配置
        self.api_title = os.getenv("SENSEVOICE_API_TITLE", "SenseVoice API")
        self.api_description = os.getenv("SENSEVOICE_API_DESCRIPTION", "语音识别API，支持HTTP和WebSocket接口")
        self.api_version = os.getenv("SENSEVOICE_API_VERSION", "1.0.0")

        # SenseVoice模型配置
        self.enable_emotion_tags = os.getenv("SENSEVOICE_ENABLE_EMOTION_TAGS", "true").lower() == "true"
        self.enable_language_tags = os.getenv("SENSEVOICE_ENABLE_LANGUAGE_TAGS", "true").lower() == "true"
        self.use_itn = os.getenv("SENSEVOICE_USE_ITN", "false").lower() == "true"  # 默认关闭ITN以保留标记

        # 长音频分块处理配置
        self.default_chunk_size = int(os.getenv("SENSEVOICE_DEFAULT_CHUNK_SIZE", "120"))  # 默认120秒分块
        self.chunk_overlap = float(os.getenv("SENSEVOICE_CHUNK_OVERLAP", "1.0"))  # 默认1秒重叠

        # WebSocket流式功能配置
        # 延迟加载：默认不立即加载流式模型，仅在首次WebSocket连接时加载（节省显存约12GB）
        self.enable_streaming_on_startup = os.getenv("SENSEVOICE_ENABLE_STREAMING_ON_STARTUP", "false").lower() == "true"

        # 服务配置
        self.host = os.getenv("SENSEVOICE_HOST", "0.0.0.0")
        self.port = int(os.getenv("SENSEVOICE_PORT", "50000"))

        # 日志配置
        self.log_level = os.getenv("SENSEVOICE_LOG_LEVEL", "INFO")
    
    def _determine_device(self) -> str:
        """智能设备选择"""
        # 优先使用环境变量指定的设备
        env_device = os.getenv("SENSEVOICE_DEVICE", "").lower()

        # 支持具体的 CUDA 设备指定，如 cuda:0, cuda:1 等
        if env_device.startswith("cuda:"):
            return self._validate_specific_cuda_device(env_device)
        elif env_device in ["cpu", "cuda", "mps", "auto"]:
            if env_device == "auto":
                return self._auto_detect_device()
            elif env_device == "cuda":
                return self._validate_cuda_device()
            elif env_device == "mps":
                return self._validate_mps_device()
            else:
                return env_device

        # 默认自动检测最佳设备
        return self._auto_detect_device()
    
    def _auto_detect_device(self) -> str:
        """自动检测最佳可用设备"""
        try:
            import torch
            
            # 优先级：CUDA > MPS > CPU
            if torch.cuda.is_available():
                gpu_count = torch.cuda.device_count()
                print(f"检测到 {gpu_count} 个CUDA设备，使用GPU加速")
                # 自动选择显存使用最少的GPU
                return self._select_best_gpu()
            elif hasattr(torch.backends, 'mps') and torch.backends.mps.is_available():
                print("检测到Metal Performance Shaders，使用MPS加速")
                return "mps"
            else:
                print("未检测到GPU，使用CPU")
                return "cpu"
                
        except ImportError:
            print("PyTorch未安装，使用CPU")
            return "cpu"
        except Exception as e:
            print(f"设备检测异常，使用CPU: {e}")
            return "cpu"
    
    def _select_best_gpu(self) -> str:
        """选择显存使用最少的GPU"""
        try:
            import torch
            
            gpu_count = torch.cuda.device_count()
            if gpu_count == 0:
                print("未检测到可用的GPU，使用CPU")
                return "cpu"
            
            # 优先使用 pynvml 获取准确的显存信息（包括其他进程占用）
            try:
                import pynvml
                pynvml.nvmlInit()
                use_nvml = True
            except:
                use_nvml = False
                print("注意: pynvml 库不可用，显存检测可能不准确（无法检测其他进程占用）")
            
            # 查找显存空闲最多的GPU
            best_device = 0
            max_free_memory = 0
            
            print("正在检测GPU显存使用情况...")
            for i in range(gpu_count):
                try:
                    if use_nvml:
                        # 使用 NVML 获取准确的显存信息
                        handle = pynvml.nvmlDeviceGetHandleByIndex(i)
                        info = pynvml.nvmlDeviceGetMemoryInfo(handle)
                        gpu_name = pynvml.nvmlDeviceGetName(handle)
                        if isinstance(gpu_name, bytes):
                            gpu_name = gpu_name.decode('utf-8')
                        
                        total_memory = info.total
                        used_memory = info.used
                        free_memory = info.free
                        
                        print(f"  GPU {i} ({gpu_name}): "
                              f"总显存 {total_memory/1024**3:.2f}GB, "
                              f"已用 {used_memory/1024**3:.2f}GB, "
                              f"空闲 {free_memory/1024**3:.2f}GB")
                    else:
                        # 回退到 PyTorch API（仅能看到当前进程）
                        total_memory = torch.cuda.get_device_properties(i).total_memory
                        torch.cuda.set_device(i)
                        allocated = torch.cuda.memory_allocated(i)
                        reserved = torch.cuda.memory_reserved(i)
                        free_memory = total_memory - allocated - reserved
                        
                        gpu_name = torch.cuda.get_device_name(i)
                        print(f"  GPU {i} ({gpu_name}): "
                              f"总显存 {total_memory/1024**3:.2f}GB, "
                              f"当前进程已用 {(allocated + reserved)/1024**3:.2f}GB, "
                              f"估计空闲 {free_memory/1024**3:.2f}GB")
                    
                    if free_memory > max_free_memory:
                        max_free_memory = free_memory
                        best_device = i
                        
                except Exception as e:
                    print(f"  GPU {i} 检测失败: {e}")
                    continue
            
            if use_nvml:
                pynvml.nvmlShutdown()
            
            # 检查最佳设备是否有足够的显存（至少需要2GB）
            min_required_memory = 2 * 1024**3  # 2GB
            if max_free_memory < min_required_memory:
                print(f"警告: 所有GPU显存不足（最大空闲 {max_free_memory/1024**3:.2f}GB < 2GB）")
                print("请尝试以下解决方案：")
                print("  1. 释放其他进程占用的GPU显存")
                print("  2. 使用环境变量指定特定GPU: export SENSEVOICE_DEVICE=cuda:N")
                print("  3. 使用CPU模式: export SENSEVOICE_DEVICE=cpu")
                # 仍然尝试使用显存最多的GPU
            
            selected_device = f"cuda:{best_device}"
            print(f"自动选择显存空闲最多的GPU: {selected_device} (空闲 {max_free_memory/1024**3:.2f}GB)")
            
            return selected_device
            
        except Exception as e:
            print(f"GPU选择失败，使用 cuda:0: {e}")
            return "cuda:0"
    
    def _validate_specific_cuda_device(self, device: str) -> str:
        """验证指定的CUDA设备是否可用"""
        try:
            import torch
            if not torch.cuda.is_available():
                print("CUDA不可用，降级到CPU")
                return "cpu"

            # 解析设备编号
            device_id = int(device.split(":")[1])
            gpu_count = torch.cuda.device_count()

            if device_id >= gpu_count:
                print(f"指定的GPU设备 {device} 不存在（共有 {gpu_count} 个GPU），使用 cuda:0")
                return "cuda:0"

            # 检查指定GPU的显存使用情况
            torch.cuda.set_device(device_id)
            memory_allocated = torch.cuda.memory_allocated(device_id) / 1024**2  # MB
            memory_reserved = torch.cuda.memory_reserved(device_id) / 1024**2   # MB
            memory_total = torch.cuda.get_device_properties(device_id).total_memory / 1024**2  # MB

            print(f"使用指定的CUDA设备: {device}")
            print(f"GPU {device_id} 显存状态: {memory_allocated:.0f}MB 已分配, {memory_reserved:.0f}MB 已保留, 总计 {memory_total:.0f}MB")

            return device

        except Exception as e:
            print(f"指定CUDA设备验证失败，使用CPU: {e}")
            return "cpu"

    def _validate_cuda_device(self) -> str:
        """验证CUDA设备是否可用，自动选择最空闲的GPU"""
        try:
            import torch
            if not torch.cuda.is_available():
                print("CUDA不可用，降级到CPU")
                return "cpu"

            # 使用统一的GPU选择逻辑
            return self._select_best_gpu()

        except Exception as e:
            print(f"CUDA验证失败，使用CPU: {e}")
            return "cpu"
    
    def _validate_mps_device(self) -> str:
        """验证MPS设备是否可用"""
        try:
            import torch
            if hasattr(torch.backends, 'mps') and torch.backends.mps.is_available():
                print("使用Metal Performance Shaders加速")
                return "mps"
            else:
                print("MPS不可用，使用CPU")
                return "cpu"
        except Exception as e:
            print(f"MPS验证失败，使用CPU: {e}")
            return "cpu"
    
    def get_device_info(self) -> dict:
        """获取设备详细信息"""
        info = {"device": self.device}
        
        try:
            import torch
            if self.device == "cuda" and torch.cuda.is_available():
                info.update({
                    "cuda_version": torch.version.cuda,
                    "gpu_count": torch.cuda.device_count(),
                    "gpu_names": [torch.cuda.get_device_name(i) for i in range(torch.cuda.device_count())],
                    "current_device": torch.cuda.current_device(),
                    "memory_allocated": f"{torch.cuda.memory_allocated() / 1024**2:.2f}MB",
                    "memory_reserved": f"{torch.cuda.memory_reserved() / 1024**2:.2f}MB"
                })
            elif self.device == "mps":
                info.update({
                    "mps_available": torch.backends.mps.is_available(),
                    "mps_built": torch.backends.mps.is_built()
                })
        except Exception as e:
            info["error"] = str(e)
        
        return info


# 全局配置实例
_settings: Optional[Settings] = None


def get_settings() -> Settings:
    """获取配置实例"""
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings


def reload_settings():
    """重新加载配置"""
    global _settings
    _settings = None
    return get_settings()
