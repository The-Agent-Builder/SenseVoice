#!/bin/bash

# SenseVoice 部署脚本
# 用于在 GPU 服务器上部署 SenseVoice 服务

set -e

# 配置变量
DEPLOY_PATH="/opt/sensevoice"
SERVICE_NAME="sensevoice"
BACKUP_DIR="$DEPLOY_PATH/backups"
LOG_FILE="$DEPLOY_PATH/deploy.log"

# 颜色输出
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# 日志函数
log() {
    echo -e "${GREEN}[$(date +'%Y-%m-%d %H:%M:%S')] $1${NC}" | tee -a "$LOG_FILE"
}

warn() {
    echo -e "${YELLOW}[$(date +'%Y-%m-%d %H:%M:%S')] WARNING: $1${NC}" | tee -a "$LOG_FILE"
}

error() {
    echo -e "${RED}[$(date +'%Y-%m-%d %H:%M:%S')] ERROR: $1${NC}" | tee -a "$LOG_FILE"
    exit 1
}

# 检查依赖
check_dependencies() {
    log "Checking dependencies..."
    
    if ! command -v docker &> /dev/null; then
        error "Docker is not installed"
    fi
    
    if ! command -v docker-compose &> /dev/null; then
        error "Docker Compose is not installed"
    fi
    
    if ! command -v nvidia-smi &> /dev/null; then
        warn "nvidia-smi not found, GPU support may not be available"
    fi
    
    log "Dependencies check passed"
}

# 创建目录结构
setup_directories() {
    log "Setting up directories..."
    
    sudo mkdir -p "$DEPLOY_PATH"
    sudo mkdir -p "$BACKUP_DIR"
    sudo mkdir -p "$DEPLOY_PATH/logs"
    sudo mkdir -p "$DEPLOY_PATH/temp"
    
    # 设置权限
    sudo chown -R $USER:$USER "$DEPLOY_PATH"
    
    log "Directories setup completed"
}

# 备份当前版本
backup_current_version() {
    if [ -f "$DEPLOY_PATH/docker-compose.yml" ]; then
        log "Creating backup of current version..."
        
        BACKUP_NAME="backup_$(date +%Y%m%d_%H%M%S)"
        mkdir -p "$BACKUP_DIR/$BACKUP_NAME"
        
        # 停止服务
        cd "$DEPLOY_PATH"
        docker-compose down || true
        
        # 备份配置文件
        cp docker-compose.yml "$BACKUP_DIR/$BACKUP_NAME/" 2>/dev/null || true
        cp .env "$BACKUP_DIR/$BACKUP_NAME/" 2>/dev/null || true
        
        # 备份日志
        cp -r logs "$BACKUP_DIR/$BACKUP_NAME/" 2>/dev/null || true
        
        log "Backup created: $BACKUP_DIR/$BACKUP_NAME"
    else
        log "No existing installation found, skipping backup"
    fi
}

# 部署新版本
deploy_new_version() {
    log "Deploying new version..."
    
    cd "$DEPLOY_PATH"
    
    # 如果有临时文件，使用它们
    if [ -f "temp/docker-compose.yml" ]; then
        cp temp/docker-compose.yml .
        log "Updated docker-compose.yml"
    fi
    
    if [ -f "temp/.env.example" ]; then
        if [ ! -f ".env" ]; then
            cp temp/.env.example .env
            log "Created .env from template"
        else
            log ".env already exists, keeping current configuration"
        fi
    fi
    
    # 加载 Docker 镜像
    if [ -f "temp/sensevoice-gpu-latest.tar.gz" ]; then
        log "Loading GPU Docker image..."
        docker load < temp/sensevoice-gpu-latest.tar.gz
    fi
    
    if [ -f "temp/sensevoice-cpu-latest.tar.gz" ]; then
        log "Loading CPU Docker image..."
        docker load < temp/sensevoice-cpu-latest.tar.gz
    fi
    
    # 清理旧镜像
    log "Cleaning up old Docker images..."
    docker image prune -f || true
    
    log "New version deployed"
}

# 启动服务
start_services() {
    log "Starting services..."
    
    cd "$DEPLOY_PATH"
    
    # 启动服务
    docker-compose up -d
    
    log "Services started"
}

# 健康检查
health_check() {
    log "Performing health check..."
    
    local max_attempts=10
    local attempt=1
    
    while [ $attempt -le $max_attempts ]; do
        if curl -f http://localhost:50000/api/v1/status &>/dev/null; then
            log "Health check passed!"
            return 0
        fi
        
        warn "Health check attempt $attempt/$max_attempts failed, retrying in 10 seconds..."
        sleep 10
        ((attempt++))
    done
    
    error "Health check failed after $max_attempts attempts"
}

# 清理临时文件
cleanup() {
    log "Cleaning up temporary files..."
    
    cd "$DEPLOY_PATH"
    rm -rf temp/
    
    log "Cleanup completed"
}

# 显示状态
show_status() {
    log "=== Deployment Status ==="
    
    cd "$DEPLOY_PATH"
    docker-compose ps
    
    echo ""
    log "=== Service Logs (last 20 lines) ==="
    docker-compose logs --tail=20 sensevoice
}

# 主函数
main() {
    log "Starting SenseVoice deployment..."
    
    check_dependencies
    setup_directories
    backup_current_version
    deploy_new_version
    start_services
    
    # 等待服务启动
    sleep 30
    
    health_check
    cleanup
    show_status
    
    log "SenseVoice deployment completed successfully!"
    log "Service is available at: http://localhost:50000"
    log "API documentation: http://localhost:50000/docs"
    log "WebSocket test: http://localhost:50000/ws-test"
}

# 如果脚本被直接执行
if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
    main "$@"
fi
