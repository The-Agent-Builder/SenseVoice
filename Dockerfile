# SenseVoice API Docker 镜像
# 默认CPU版本，通过构建参数支持GPU

FROM hub.sensedeal.vip/library/ubuntu-python-base:22.04-20240612

# 设置工作目录
WORKDIR /app

# ubuntu-python-base 镜像应该已经配置好了源，但为了保险起见仍然配置
RUN if [ -f /etc/apt/sources.list ]; then \
        sed -i 's|http://archive.ubuntu.com|https://mirrors.tuna.tsinghua.edu.cn|g' /etc/apt/sources.list && \
        sed -i 's|http://security.ubuntu.com|https://mirrors.tuna.tsinghua.edu.cn|g' /etc/apt/sources.list; \
    fi

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

# 配置 pip 使用清华源
RUN pip config set global.index-url https://pypi.tuna.tsinghua.edu.cn/simple && \
    pip config set global.trusted-host pypi.tuna.tsinghua.edu.cn

# 分层安装依赖以优化构建缓存
# 1. 先安装基础 Web 框架依赖
RUN pip install --no-cache-dir \
    fastapi>=0.111.1 \
    uvicorn[standard] \
    python-multipart \
    websockets \
    python-dotenv

# 2. 安装数据处理依赖
RUN pip install --no-cache-dir \
    "numpy<=2.3.3" \
    "pydub>=0.25.1"

# 3. 安装 PyTorch CPU 版本 (避免重复安装)
ARG PYTORCH_INDEX_URL="https://download.pytorch.org/whl/cpu"
RUN pip install --no-cache-dir torch torchvision torchaudio --index-url ${PYTORCH_INDEX_URL}

# 4. 安装 SenseVoice 相关依赖
RUN pip install --no-cache-dir \
    modelscope \
    huggingface_hub \
    "funasr>=1.1.3" \
    gradio \
    pynvml

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