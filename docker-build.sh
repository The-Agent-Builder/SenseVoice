#!/bin/bash
# SenseVoice Docker 构建和部署脚本

set -e

echo "🐳 SenseVoice Docker 构建向导"
echo "============================="

# 帮助信息
show_help() {
    echo "使用方法: $0 [选项]"
    echo ""
    echo "选项:"
    echo "  --cpu          构建 CPU 版本镜像"
    echo "  --gpu          构建 GPU 版本镜像"
    echo "  --both         构建 CPU 和 GPU 版本"
    echo "  --run-cpu      运行 CPU 版本服务"
    echo "  --run-gpu      运行 GPU 版本服务"
    echo "  --stop         停止所有服务"
    echo "  --logs         查看服务日志"
    echo "  --help         显示此帮助信息"
    echo ""
    echo "示例:"
    echo "  $0 --cpu               # 构建CPU版本"
    echo "  $0 --gpu               # 构建GPU版本"
    echo "  $0 --run-gpu           # 运行GPU服务"
    echo "  docker-compose up -d   # 直接使用docker-compose"
}

# 构建 CPU 版本
build_cpu() {
    echo "🏗️ 构建 CPU 版本镜像..."
    docker build -t sensevoice-api:cpu \
        --build-arg PYTORCH_INDEX_URL="https://download.pytorch.org/whl/cpu" \
        --build-arg INSTALL_GPU="false" \
        -f Dockerfile .
    echo "✅ CPU 版本构建完成"
}

# 构建 GPU 版本
build_gpu() {
    echo "🎮 构建 GPU 版本镜像..."
    # 检查是否支持 NVIDIA Docker
    if ! docker info 2>/dev/null | grep -q "nvidia"; then
        echo "⚠️  警告: 未检测到 NVIDIA Docker 支持"
        echo "请确保已安装 nvidia-docker2"
    fi
    
    docker build -t sensevoice-api:gpu -f Dockerfile.gpu .
    echo "✅ GPU 版本构建完成"
}

# 运行服务
run_service() {
    local service=$1
    echo "🚀 启动 $service 服务..."
    
    if [ "$service" = "cpu" ]; then
        docker-compose up -d sensevoice-cpu
        echo "🌐 CPU 服务已启动: http://localhost:50000"
    elif [ "$service" = "gpu" ]; then
        docker-compose --profile gpu up -d sensevoice-gpu
        echo "🌐 GPU 服务已启动: http://localhost:50001"
    fi
    
    echo "📊 测试页面: http://localhost:5000x/static/ws_test.html"
    echo "📖 API 文档: http://localhost:5000x/docs"
}

# 停止服务
stop_services() {
    echo "🛑 停止所有服务..."
    docker-compose down
    echo "✅ 服务已停止"
}

# 查看日志
show_logs() {
    echo "📋 服务日志:"
    docker-compose logs -f
}

# 解析命令行参数
case "${1:-}" in
    --cpu)
        build_cpu
        ;;
    --gpu)
        build_gpu
        ;;
    --both)
        build_cpu
        build_gpu
        ;;
    --run-cpu)
        run_service "cpu"
        ;;
    --run-gpu)
        run_service "gpu"
        ;;
    --stop)
        stop_services
        ;;
    --logs)
        show_logs
        ;;
    --help)
        show_help
        ;;
    "")
        echo "❌ 请指定操作选项"
        show_help
        exit 1
        ;;
    *)
        echo "❌ 未知选项: $1"
        show_help
        exit 1
        ;;
esac