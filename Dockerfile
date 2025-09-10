# SenseVoice API Docker 镜像
# 默认CPU版本，通过构建参数支持GPU

FROM python:3.11-slim

# 设置工作目录
WORKDIR /app

# 安装系统依赖
RUN apt-get update && apt-get install -y \
    build-essential \
    curl \
    git \
    ffmpeg \
    libsndfile1 \
    && rm -rf /var/lib/apt/lists/*

# 复制项目文件
COPY requirements.txt .
COPY *.py ./
COPY config/ ./config/
COPY handlers/ ./handlers/
COPY models/ ./models/
COPY utils/ ./utils/
COPY websocket/ ./websocket/
COPY static/ ./static/
COPY .env.example .env

# 安装 Python 依赖
# 默认安装 CPU 版本，GPU 版本通过构建参数控制
ARG PYTORCH_INDEX_URL="https://download.pytorch.org/whl/cpu"
ARG INSTALL_GPU="false"

RUN if [ "$INSTALL_GPU" = "true" ]; then \
        echo "安装GPU版本PyTorch..." && \
        pip install torch torchvision torchaudio --index-url ${PYTORCH_INDEX_URL}; \
    fi && \
    pip install --no-cache-dir -r requirements.txt

# 创建缓存目录
RUN mkdir -p /root/.cache/modelscope

# 环境变量配置
ENV SENSEVOICE_DEVICE=auto
ENV SENSEVOICE_HOST=0.0.0.0
ENV SENSEVOICE_PORT=50000
ENV SENSEVOICE_LOG_LEVEL=INFO
ENV PYTHONPATH=/app

# 健康检查
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD curl -f http://localhost:${SENSEVOICE_PORT}/health || exit 1

# 暴露端口
EXPOSE 50000

# 启动服务
CMD ["python", "main.py"]