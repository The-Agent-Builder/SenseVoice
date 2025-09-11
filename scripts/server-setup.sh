#!/bin/bash

# SenseVoice 服务器初始化脚本
# 用于在新的 GPU 服务器上安装必要的依赖和配置环境

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

# 检查是否为 root 用户
check_root() {
    if [[ $EUID -eq 0 ]]; then
        error "This script should not be run as root. Please run as a regular user with sudo privileges."
    fi
}

# 更新系统
update_system() {
    log "Updating system packages..."
    sudo apt update && sudo apt upgrade -y
    sudo apt install -y curl wget git vim htop
    log "System update completed"
}

# 安装 Docker
install_docker() {
    if command -v docker &> /dev/null; then
        log "Docker is already installed"
        docker --version
        return
    fi
    
    log "Installing Docker..."
    
    # 卸载旧版本
    sudo apt remove -y docker docker-engine docker.io containerd runc || true
    
    # 安装依赖
    sudo apt install -y \
        ca-certificates \
        curl \
        gnupg \
        lsb-release
    
    # 添加 Docker 官方 GPG key
    sudo mkdir -p /etc/apt/keyrings
    curl -fsSL https://download.docker.com/linux/ubuntu/gpg | sudo gpg --dearmor -o /etc/apt/keyrings/docker.gpg
    
    # 添加 Docker 仓库
    echo \
        "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu \
        $(lsb_release -cs) stable" | sudo tee /etc/apt/sources.list.d/docker.list > /dev/null
    
    # 安装 Docker Engine
    sudo apt update
    sudo apt install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
    
    # 将用户添加到 docker 组
    sudo usermod -aG docker $USER
    
    log "Docker installation completed"
    log "Please log out and log back in for group changes to take effect"
}

# 安装 Docker Compose
install_docker_compose() {
    if command -v docker-compose &> /dev/null; then
        log "Docker Compose is already installed"
        docker-compose --version
        return
    fi
    
    log "Installing Docker Compose..."
    
    # 下载最新版本的 Docker Compose
    DOCKER_COMPOSE_VERSION=$(curl -s https://api.github.com/repos/docker/compose/releases/latest | grep 'tag_name' | cut -d\" -f4)
    sudo curl -L "https://github.com/docker/compose/releases/download/${DOCKER_COMPOSE_VERSION}/docker-compose-$(uname -s)-$(uname -m)" -o /usr/local/bin/docker-compose
    
    # 设置执行权限
    sudo chmod +x /usr/local/bin/docker-compose
    
    log "Docker Compose installation completed"
    docker-compose --version
}

# 安装 NVIDIA Docker (如果有 GPU)
install_nvidia_docker() {
    if ! command -v nvidia-smi &> /dev/null; then
        warn "NVIDIA GPU not detected, skipping NVIDIA Docker installation"
        return
    fi
    
    log "Installing NVIDIA Docker..."
    
    # 添加 NVIDIA Docker 仓库
    distribution=$(. /etc/os-release;echo $ID$VERSION_ID) \
        && curl -fsSL https://nvidia.github.io/libnvidia-container/gpgkey | sudo gpg --dearmor -o /usr/share/keyrings/nvidia-container-toolkit-keyring.gpg \
        && curl -s -L https://nvidia.github.io/libnvidia-container/$distribution/libnvidia-container.list | \
            sed 's#deb https://#deb [signed-by=/usr/share/keyrings/nvidia-container-toolkit-keyring.gpg] https://#g' | \
            sudo tee /etc/apt/sources.list.d/nvidia-container-toolkit.list
    
    sudo apt update
    sudo apt install -y nvidia-container-toolkit
    
    # 重启 Docker 服务
    sudo systemctl restart docker
    
    log "NVIDIA Docker installation completed"
}

# 配置防火墙
configure_firewall() {
    log "Configuring firewall..."
    
    # 安装 ufw
    sudo apt install -y ufw
    
    # 配置基本规则
    sudo ufw default deny incoming
    sudo ufw default allow outgoing
    
    # 允许 SSH
    sudo ufw allow ssh
    
    # 允许 SenseVoice 端口
    sudo ufw allow 50000/tcp
    
    # 如果需要 HTTPS
    sudo ufw allow 443/tcp
    sudo ufw allow 80/tcp
    
    # 启用防火墙
    sudo ufw --force enable
    
    log "Firewall configuration completed"
}

# 创建部署目录
setup_deploy_directory() {
    log "Setting up deployment directory..."
    
    DEPLOY_PATH="/opt/sensevoice"
    sudo mkdir -p "$DEPLOY_PATH"
    sudo chown $USER:$USER "$DEPLOY_PATH"
    
    # 创建子目录
    mkdir -p "$DEPLOY_PATH/logs"
    mkdir -p "$DEPLOY_PATH/backups"
    mkdir -p "$DEPLOY_PATH/temp"
    
    log "Deployment directory setup completed: $DEPLOY_PATH"
}

# 配置系统服务
configure_system_service() {
    log "Configuring system service..."
    
    # 创建 systemd 服务文件
    sudo tee /etc/systemd/system/sensevoice.service > /dev/null <<EOF
[Unit]
Description=SenseVoice Speech Recognition Service
Requires=docker.service
After=docker.service

[Service]
Type=oneshot
RemainAfterExit=yes
WorkingDirectory=/opt/sensevoice
ExecStart=/usr/local/bin/docker-compose up -d
ExecStop=/usr/local/bin/docker-compose down
TimeoutStartSec=0

[Install]
WantedBy=multi-user.target
EOF
    
    # 重新加载 systemd
    sudo systemctl daemon-reload
    
    # 启用服务
    sudo systemctl enable sensevoice.service
    
    log "System service configuration completed"
}

# 显示系统信息
show_system_info() {
    log "=== System Information ==="
    echo "OS: $(lsb_release -d | cut -f2)"
    echo "Kernel: $(uname -r)"
    echo "Architecture: $(uname -m)"
    echo "Memory: $(free -h | grep '^Mem:' | awk '{print $2}')"
    echo "Disk: $(df -h / | tail -1 | awk '{print $2}')"
    
    if command -v nvidia-smi &> /dev/null; then
        echo ""
        log "=== GPU Information ==="
        nvidia-smi --query-gpu=name,memory.total,driver_version --format=csv,noheader,nounits
    fi
    
    echo ""
    log "=== Docker Information ==="
    docker --version
    docker-compose --version
    
    if command -v nvidia-docker &> /dev/null; then
        echo "NVIDIA Docker: Available"
    fi
}

# 主函数
main() {
    log "Starting SenseVoice server setup..."
    
    check_root
    update_system
    install_docker
    install_docker_compose
    install_nvidia_docker
    configure_firewall
    setup_deploy_directory
    configure_system_service
    
    echo ""
    show_system_info
    
    echo ""
    log "=== Setup Completed Successfully! ==="
    info "Next steps:"
    info "1. Log out and log back in for Docker group changes to take effect"
    info "2. Configure GitHub Actions secrets for CI/CD deployment"
    info "3. Push code to trigger automatic deployment"
    info ""
    info "Manual deployment command: sudo systemctl start sensevoice"
    info "Check service status: sudo systemctl status sensevoice"
    info "View logs: docker-compose -f /opt/sensevoice/docker-compose.yml logs -f"
}

# 如果脚本被直接执行
if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
    main "$@"
fi
