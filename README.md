# SenseVoice API 服务

基于 SenseVoice 模型的实时语音识别 API 服务，支持多语言语音识别、情感识别和音频事件检测。

## ✨ 功能特性

- 🎤 **实时语音识别** - WebSocket 流式音频处理，低延迟识别
- 🌍 **多语言支持** - 支持中文、英文、粤语、日语、韩语等 50+ 种语言  
- 🎭 **情感识别** - 识别语音中的情感状态
- 🔊 **音频事件检测** - 检测背景音乐、掌声、笑声等音频事件
- ⚡ **高性能推理** - GPU 加速，支持 CUDA、MPS 和 CPU 多种设备
- 🚀 **易于部署** - Docker 支持，环境变量配置

## 🏗️ 项目架构

```
SenseVoice/
├── api.py                 # FastAPI 主应用
├── main.py               # 服务启动入口
├── config/               # 配置模块
│   └── settings.py       # 环境配置
├── models/               # 模型管理
│   └── sense_voice_model.py
├── handlers/             # 音频处理
│   ├── audio_handler.py  # 音频解码和处理
│   └── streaming_asr.py  # 流式语音识别
├── websocket/            # WebSocket 服务
│   ├── connection_manager.py
│   └── streaming_handler.py
├── static/               # 测试页面
│   └── ws_test.html     # WebSocket 测试界面
└── utils/               # 工具模块
    └── audio_utils.py   # 音频处理工具
```

## 🚀 快速开始

### 环境要求

- Python 3.8+
- PyTorch 2.0+
- CUDA (可选，用于 GPU 加速)

### 安装依赖

#### 🚀 自动安装（推荐）

使用自动安装脚本，会根据你的环境自动选择合适的PyTorch版本：

```bash
# 克隆仓库
git clone <repository-url>
cd SenseVoice

# 运行自动安装脚本
./install_gpu.sh
```

#### 🔧 手动安装

**GPU环境（生产推荐）**:
```bash
# 1. 先安装GPU版本PyTorch
# CUDA 11.8
pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu118

# CUDA 12.1
pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu121

# 2. 安装其他依赖
pip install -r requirements.txt
```

**CPU环境（开发测试）**:
```bash
# 直接安装所有依赖（默认CPU版本）
pip install -r requirements.txt
```

### 配置环境

复制环境配置模板：

```bash
cp .env.example .env
```

编辑 `.env` 文件配置参数：

```bash
# 设备选择：auto(自动检测)、cuda(NVIDIA GPU)、mps(Apple GPU)、cpu(仅CPU)
SENSEVOICE_DEVICE=auto

# 服务配置
SENSEVOICE_HOST=0.0.0.0
SENSEVOICE_PORT=50000
SENSEVOICE_LOG_LEVEL=INFO

# 音频参数
SENSEVOICE_TARGET_SAMPLE_RATE=16000
SENSEVOICE_DEFAULT_CHUNK_DURATION=3.0
SENSEVOICE_MAX_CONNECTIONS=100
```

### 启动服务

```bash
# 使用 .env 配置启动
python main.py

# 或临时指定设备
SENSEVOICE_DEVICE=cuda python main.py
```

服务启动后访问：
- **API 文档**: http://localhost:50000/docs  
- **WebSocket 测试**: http://localhost:50000/static/ws_test.html

## 📖 API 使用

### HTTP 接口

#### 文件上传识别

```bash
curl -X POST "http://localhost:50000/recognize" \
  -F "file=@audio.wav" \
  -F "language=auto"
```

#### 健康检查

```bash
curl http://localhost:50000/health
```

### WebSocket 接口

连接地址：`ws://localhost:50000/ws/asr`

#### 配置消息
```json
{
  "type": "config",
  "config": {
    "language": "auto",
    "chunk_duration": 3.0,
    "use_vad": true,
    "encoding": "base64"
  }
}
```

#### 发送音频
```json
{
  "type": "audio", 
  "data": "base64_encoded_audio_data",
  "format": "opus"
}
```

#### 识别结果
```json
{
  "type": "result",
  "text": "识别文本",
  "raw_text": "原始文本", 
  "clean_text": "清理后文本",
  "confidence": 0.95,
  "is_final": true,
  "model_type": "SenseVoiceSmall"
}
```

## 🎯 支持的音频格式

- **实时录音**: Opus (WebM 容器)
- **文件上传**: MP3, M4A, WAV, FLAC, OGG 等常见格式
- **采样率**: 自动转换为 16kHz 单声道

## 🔧 部署选项

### Docker 部署（推荐）

#### 🚀 快速部署

```bash
# 默认GPU版本（生产环境推荐）
./docker-build.sh                      # 构建并启动GPU版本

# 或分步执行
./docker-build.sh --gpu                # 构建GPU版本
./docker-build.sh --run                # 运行GPU服务

# CPU版本（开发测试）
./docker-build.sh --cpu                # 构建CPU版本  
./docker-build.sh --run-cpu            # 运行CPU服务

# 使用 docker-compose
docker-compose up -d                    # GPU 版本（默认）
docker-compose --profile cpu up -d     # CPU 版本
```

#### 🐳 Docker 镜像构建

**GPU 版本（默认）**:
```bash
docker build -t sensevoice-api:gpu -f Dockerfile.gpu .
docker run -d -p 50000:50000 --gpus all --name sensevoice-gpu sensevoice-api:gpu
```

**CPU 版本（开发测试）**:
```bash
docker build -t sensevoice-api:cpu .
docker run -d -p 50000:50000 --name sensevoice-cpu sensevoice-api:cpu
```

#### 📋 Docker Compose 配置

```bash
# 基本使用
docker-compose up -d                    # GPU 服务 (端口 50000)
docker-compose --profile cpu up -d      # CPU 服务 (端口 50001)  
docker-compose --profile nginx up -d    # 带 Nginx 代理

# 查看日志
docker-compose logs -f

# 停止服务  
docker-compose down
```

### 直接部署

#### 环境要求

- Python 3.8+
- PyTorch 2.0+
- CUDA (可选，用于 GPU 加速)

### 环境变量配置

| 变量名 | 说明 | 默认值 |
|--------|------|--------|
| `SENSEVOICE_DEVICE` | 计算设备 (auto/cuda/mps/cpu) | auto |
| `SENSEVOICE_HOST` | 监听地址 | 0.0.0.0 |
| `SENSEVOICE_PORT` | 监听端口 | 50000 |
| `SENSEVOICE_LOG_LEVEL` | 日志级别 | INFO |
| `SENSEVOICE_MAX_CONNECTIONS` | 最大连接数 | 100 |
| `SENSEVOICE_TARGET_SAMPLE_RATE` | 目标采样率 | 16000 |
| `SENSEVOICE_DEFAULT_CHUNK_DURATION` | 音频块时长(秒) | 3.0 |

详细部署说明请参考：[GPU_DEPLOYMENT.md](./GPU_DEPLOYMENT.md)

## 🧪 测试

启动服务后，打开测试页面进行功能验证：

```
http://localhost:50000/static/ws_test.html
```

测试页面功能：
- ✅ 实时麦克风录音识别
- ✅ 文件上传流式识别  
- ✅ 音频可视化显示
- ✅ 多语言配置
- ✅ 识别结果导出

## 📊 性能指标

| 设备类型 | 相对性能 | 内存占用 | 推荐场景 |
|---------|---------|---------|---------|
| CUDA GPU | 100% | 高 | 生产环境，大并发 |
| MPS (Apple) | 80% | 中 | Mac 开发，中等负载 |
| CPU | 30% | 低 | 开发测试，低并发 |

## 🔍 故障排除

### CUDA 不可用
```bash
# 检查 GPU 状态
nvidia-smi

# 检查 PyTorch CUDA 支持
python -c "import torch; print(torch.cuda.is_available())"
```

### 内存不足
- 降低 `SENSEVOICE_MAX_CONNECTIONS` 
- 使用 CPU 模式：`SENSEVOICE_DEVICE=cpu`
- 减少音频块时长：`SENSEVOICE_DEFAULT_CHUNK_DURATION=2.0`

### 连接问题
- 检查防火墙设置
- 确认端口未被占用：`lsof -i :50000`
- 查看服务日志排查问题

## 📄 许可证

本项目基于原始 SenseVoice 项目开发，遵循相应的开源许可证。

## 🤝 贡献

欢迎提交 Issue 和 Pull Request 来改进项目。

## 📞 支持

如有问题，请：
1. 查看文档和故障排除章节
2. 搜索已有 Issue
3. 提交新的 Issue 描述问题

---

**SenseVoice API** - 高性能多语言语音识别服务 🎤✨