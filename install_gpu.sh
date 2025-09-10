#!/bin/bash
# SenseVoice GPU环境安装脚本

set -e

echo "🚀 SenseVoice GPU环境安装向导"
echo "================================"

# 检测操作系统
if [[ "$OSTYPE" == "darwin"* ]]; then
    echo "📱 检测到 macOS 环境"
    echo "🔧 将安装支持 MPS (Metal Performance Shaders) 的版本"
    pip install torch torchaudio --index-url https://download.pytorch.org/whl/cpu
    echo "✅ PyTorch (MPS支持) 安装完成"
elif command -v nvidia-smi &> /dev/null; then
    echo "🎮 检测到 NVIDIA GPU 环境"
    
    # 检测CUDA版本
    CUDA_VERSION=$(nvidia-smi | grep "CUDA Version" | awk '{print $9}' | cut -d. -f1,2)
    echo "🔍 检测到 CUDA 版本: $CUDA_VERSION"
    
    if [[ "$CUDA_VERSION" == "11."* ]]; then
        echo "🔧 安装 CUDA 11.8 版本的 PyTorch"
        pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu118
    elif [[ "$CUDA_VERSION" == "12."* ]]; then
        echo "🔧 安装 CUDA 12.1 版本的 PyTorch"  
        pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu121
    else
        echo "⚠️  未识别的CUDA版本，安装默认GPU版本"
        pip install torch torchvision torchaudio
    fi
    echo "✅ PyTorch (CUDA支持) 安装完成"
else
    echo "💻 未检测到GPU，安装CPU版本"
    pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cpu
    echo "✅ PyTorch (CPU版本) 安装完成"
fi

echo ""
echo "📦 安装其他依赖..."
pip install -r requirements.txt

echo ""
echo "🧪 测试GPU支持..."
python3 -c "
import torch
print('✅ PyTorch 版本:', torch.__version__)
if torch.cuda.is_available():
    print('🎮 CUDA 可用:', torch.cuda.device_count(), '个GPU')
    for i in range(torch.cuda.device_count()):
        print(f'   GPU {i}: {torch.cuda.get_device_name(i)}')
elif hasattr(torch.backends, 'mps') and torch.backends.mps.is_available():
    print('📱 MPS (Apple GPU) 可用')
else:
    print('💻 使用 CPU 模式')
"

echo ""
echo "🎉 安装完成！"
echo ""
echo "🚀 启动服务:"
echo "   python3 main.py"
echo ""
echo "🌐 访问测试页面:"
echo "   http://localhost:50000/static/ws_test.html"