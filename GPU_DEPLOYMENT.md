# GPU部署配置指南

SenseVoice支持CPU、CUDA GPU和MPS（Mac）加速。系统会自动检测最佳设备，也可通过环境变量手动指定。

## 环境变量配置

### 设备选择
```bash
# 自动检测最佳设备（默认，推荐）
export SENSEVOICE_DEVICE=auto

# 强制使用CUDA GPU
export SENSEVOICE_DEVICE=cuda

# 强制使用CPU
export SENSEVOICE_DEVICE=cpu

# Mac上使用Metal Performance Shaders
export SENSEVOICE_DEVICE=mps
```

### 其他配置
```bash
# 服务配置
export SENSEVOICE_HOST=0.0.0.0
export SENSEVOICE_PORT=50000
export SENSEVOICE_LOG_LEVEL=INFO

# 音频处理参数
export SENSEVOICE_TARGET_SAMPLE_RATE=16000
export SENSEVOICE_DEFAULT_CHUNK_DURATION=3.0
export SENSEVOICE_MAX_CONNECTIONS=100
```

## PyTorch GPU版本安装

### CUDA 11.8
```bash
pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu118
```

### CUDA 12.1
```bash
pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu121
```

### CPU版本（开发测试）
```bash
pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cpu
```

## Docker部署示例

### GPU版本Dockerfile
```dockerfile
FROM nvidia/cuda:11.8-runtime-ubuntu20.04

# 安装Python和依赖
RUN apt-get update && apt-get install -y python3 python3-pip

# 复制项目文件
COPY . /app
WORKDIR /app

# 安装GPU版本PyTorch
RUN pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu118

# 安装其他依赖
RUN pip install -r requirements.txt

# 设置环境变量
ENV SENSEVOICE_DEVICE=cuda
ENV SENSEVOICE_HOST=0.0.0.0
ENV SENSEVOICE_PORT=50000

EXPOSE 50000

CMD ["python3", "main.py"]
```

### docker-compose.yml
```yaml
version: '3.8'
services:
  sensevoice:
    build: .
    ports:
      - "50000:50000"
    environment:
      - SENSEVOICE_DEVICE=cuda
      - SENSEVOICE_HOST=0.0.0.0
      - SENSEVOICE_PORT=50000
      - SENSEVOICE_LOG_LEVEL=INFO
    deploy:
      resources:
        reservations:
          devices:
            - driver: nvidia
              count: 1
              capabilities: [gpu]
```

## 设备检测逻辑

系统启动时会按以下优先级自动检测：

1. **CUDA GPU** - 优先级最高，适合NVIDIA显卡
2. **MPS** - Apple Silicon Mac的GPU加速
3. **CPU** - 兜底方案，所有平台都支持

## 启动日志示例

### GPU模式
```
2025-01-15 10:00:00 - 正在启动SenseVoice API服务...
==================================================
设备配置信息:
  选择的设备: cuda
  CUDA版本: 11.8
  GPU数量: 1
  GPU 0: NVIDIA GeForce RTX 4090
  显存已分配: 0.00MB
  显存已保留: 0.00MB
==================================================
环境变量配置:
  SENSEVOICE_DEVICE: auto (默认)
  SENSEVOICE_HOST: 0.0.0.0
  SENSEVOICE_PORT: 50000
  SENSEVOICE_LOG_LEVEL: INFO
==================================================
```

### CPU模式
```
2025-01-15 10:00:00 - 正在启动SenseVoice API服务...
==================================================
设备配置信息:
  选择的设备: cpu
  使用CPU进行推理
==================================================
```

## 性能对比

| 设备类型 | 相对性能 | 内存占用 | 推荐场景 |
|---------|---------|---------|---------|
| CUDA GPU | 100% | 高 | 生产环境，大并发 |
| MPS | 80% | 中 | Mac开发，中等负载 |
| CPU | 30% | 低 | 开发测试，低并发 |

## 故障排除

### CUDA不可用
- 检查NVIDIA驱动是否安装
- 检查CUDA版本是否与PyTorch匹配
- 运行 `nvidia-smi` 验证GPU状态

### 内存不足
- 降低 `SENSEVOICE_MAX_CONNECTIONS`
- 增加GPU显存或使用更大的GPU
- 考虑使用CPU模式

### 性能优化
- 使用 `SENSEVOICE_DEVICE=cuda` 确保使用GPU
- 调整 `SENSEVOICE_DEFAULT_CHUNK_DURATION` 平衡延迟和性能
- 监控GPU利用率和显存使用