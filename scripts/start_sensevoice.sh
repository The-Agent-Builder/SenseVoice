#!/bin/bash

# SenseVoice 智能启动脚本
# 自动检测最佳GPU并启动服务

set -e

# 颜色输出
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# 日志函数
log() {
    echo -e "${GREEN}[$(date +'%Y-%m-%d %H:%M:%S')] $1${NC}"
}

warn() {
    echo -e "${YELLOW}[$(date +'%Y-%m-%d %H:%M:%S')] WARNING: $1${NC}"
}

error() {
    echo -e "${RED}[$(date +'%Y-%m-%d %H:%M:%S')] ERROR: $1${NC}"
    exit 1
}

info() {
    echo -e "${BLUE}[$(date +'%Y-%m-%d %H:%M:%S')] INFO: $1${NC}"
}

# 检查依赖
check_dependencies() {
    log "检查依赖..."
    
    if ! command -v python &> /dev/null; then
        error "Python 未安装"
    fi
    
    if ! python -c "import torch" &> /dev/null; then
        error "PyTorch 未安装"
    fi
    
    log "依赖检查通过"
}

# 检查GPU状态并选择最佳设备
select_best_device() {
    log "检查GPU状态..."
    
    # 运行GPU检查脚本
    if [ -f "scripts/check_gpu_memory.py" ]; then
        python scripts/check_gpu_memory.py > /tmp/gpu_check.log 2>&1
        
        # 从输出中提取推荐的GPU
        if grep -q "推荐使用 GPU" /tmp/gpu_check.log; then
            RECOMMENDED_GPU=$(grep "推荐使用 GPU" /tmp/gpu_check.log | sed 's/.*GPU \([0-9]\+\).*/\1/')
            BEST_DEVICE="cuda:$RECOMMENDED_GPU"
            log "自动选择GPU设备: $BEST_DEVICE"
        else
            warn "无法自动选择GPU，使用默认设备"
            BEST_DEVICE="auto"
        fi
    else
        warn "GPU检查脚本不存在，使用默认设备选择"
        BEST_DEVICE="auto"
    fi
    
    # 如果用户指定了设备，优先使用用户指定的设备
    if [ ! -z "$SENSEVOICE_DEVICE" ]; then
        log "使用用户指定的设备: $SENSEVOICE_DEVICE"
        BEST_DEVICE="$SENSEVOICE_DEVICE"
    fi
    
    export SENSEVOICE_DEVICE="$BEST_DEVICE"
}

# 清理显存
cleanup_gpu_memory() {
    if [[ "$SENSEVOICE_DEVICE" == cuda* ]]; then
        log "清理GPU显存缓存..."
        python -c "import torch; torch.cuda.empty_cache(); print('GPU显存缓存已清理')" || warn "显存清理失败"
    fi
}

# 设置环境变量
setup_environment() {
    log "设置环境变量..."
    
    # 设置默认值
    export SENSEVOICE_HOST="${SENSEVOICE_HOST:-0.0.0.0}"
    export SENSEVOICE_PORT="${SENSEVOICE_PORT:-50000}"
    export SENSEVOICE_LOG_LEVEL="${SENSEVOICE_LOG_LEVEL:-INFO}"
    
    # 显存优化设置
    export PYTORCH_CUDA_ALLOC_CONF="max_split_size_mb:512"
    export CUDA_LAUNCH_BLOCKING="0"  # 异步执行，提高性能
    
    log "环境变量设置完成"
}

# 显示启动信息
show_startup_info() {
    log "=== SenseVoice 启动信息 ==="
    info "设备: $SENSEVOICE_DEVICE"
    info "主机: $SENSEVOICE_HOST"
    info "端口: $SENSEVOICE_PORT"
    info "日志级别: $SENSEVOICE_LOG_LEVEL"
    
    if [[ "$SENSEVOICE_DEVICE" == cuda* ]]; then
        info "GPU加速: 启用"
        if command -v nvidia-smi &> /dev/null; then
            info "NVIDIA驱动版本: $(nvidia-smi --query-gpu=driver_version --format=csv,noheader,nounits | head -1)"
        fi
    else
        info "GPU加速: 禁用"
    fi
    
    log "=========================="
}

# 启动服务
start_service() {
    log "启动 SenseVoice 服务..."
    
    # 检查端口是否被占用
    if netstat -tlnp 2>/dev/null | grep -q ":$SENSEVOICE_PORT "; then
        warn "端口 $SENSEVOICE_PORT 已被占用"
        info "正在查找占用进程..."
        netstat -tlnp 2>/dev/null | grep ":$SENSEVOICE_PORT " || true

        # 如果是自动模式，直接杀死占用进程
        if [ "$AUTO_START" = true ]; then
            log "自动模式：正在杀死占用进程..."
            PID=$(netstat -tlnp 2>/dev/null | grep ":$SENSEVOICE_PORT " | awk '{print $7}' | cut -d'/' -f1)
            if [ ! -z "$PID" ]; then
                kill -9 "$PID" 2>/dev/null || true
                log "已杀死进程 $PID"
                sleep 2
            fi
        else
            read -p "是否要杀死占用进程并继续？(y/N): " -n 1 -r
            echo
            if [[ $REPLY =~ ^[Yy]$ ]]; then
                PID=$(netstat -tlnp 2>/dev/null | grep ":$SENSEVOICE_PORT " | awk '{print $7}' | cut -d'/' -f1)
                if [ ! -z "$PID" ]; then
                    kill -9 "$PID" 2>/dev/null || true
                    log "已杀死进程 $PID"
                    sleep 2
                fi
            else
                error "端口被占用，启动取消"
            fi
        fi
    fi
    
    # 启动服务
    log "正在启动服务..."
    python main.py
}

# 错误处理
handle_error() {
    error "启动失败！"
    
    log "=== 故障排除建议 ==="
    info "1. 检查GPU显存使用情况: python scripts/check_gpu_memory.py"
    info "2. 清理显存缓存: python -c \"import torch; torch.cuda.empty_cache()\""
    info "3. 查看详细错误日志"
    info "4. 尝试使用CPU模式: export SENSEVOICE_DEVICE=cpu"
    info "5. 检查依赖安装: pip install -r requirements.txt"
    
    exit 1
}

# 主函数
main() {
    log "SenseVoice 智能启动脚本"
    
    # 设置错误处理
    trap handle_error ERR
    
    check_dependencies
    setup_environment
    select_best_device
    cleanup_gpu_memory
    show_startup_info
    
    # 等待用户确认
    if [ "$AUTO_START" != true ]; then
        read -p "按 Enter 键继续启动，或 Ctrl+C 取消..."
    fi
    
    start_service
}

# 显示帮助信息
show_help() {
    echo "SenseVoice 智能启动脚本"
    echo ""
    echo "用法:"
    echo "  $0 [选项]"
    echo ""
    echo "选项:"
    echo "  --auto          自动启动，不等待用户确认"
    echo "  --device=DEVICE 指定设备 (cpu, cuda, cuda:0, cuda:1, etc.)"
    echo "  --port=PORT     指定端口 (默认: 50000)"
    echo "  --host=HOST     指定主机 (默认: 0.0.0.0)"
    echo "  --help          显示此帮助信息"
    echo ""
    echo "环境变量:"
    echo "  SENSEVOICE_DEVICE    设备选择"
    echo "  SENSEVOICE_HOST      监听主机"
    echo "  SENSEVOICE_PORT      监听端口"
    echo "  SENSEVOICE_LOG_LEVEL 日志级别"
    echo ""
    echo "示例:"
    echo "  $0                           # 交互式启动"
    echo "  $0 --auto                    # 自动启动"
    echo "  $0 --device=cuda:4 --auto    # 指定GPU 4自动启动"
    echo "  $0 --device=cpu --auto       # 使用CPU自动启动"
}

# 解析命令行参数
while [[ $# -gt 0 ]]; do
    case $1 in
        --auto)
            AUTO_START=true
            shift
            ;;
        --device=*)
            export SENSEVOICE_DEVICE="${1#*=}"
            shift
            ;;
        --port=*)
            export SENSEVOICE_PORT="${1#*=}"
            shift
            ;;
        --host=*)
            export SENSEVOICE_HOST="${1#*=}"
            shift
            ;;
        --help)
            show_help
            exit 0
            ;;
        *)
            error "未知参数: $1"
            ;;
    esac
done

# 如果脚本被直接执行
if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
    main "$@"
fi
