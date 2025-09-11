# SenseVoice CI/CD 部署指南

本文档详细说明如何设置 GitHub Actions CI/CD 流水线，实现 SenseVoice 项目的自动化部署到 GPU 服务器。

## 📋 目录

- [部署架构](#部署架构)
- [服务器准备](#服务器准备)
- [GitHub 配置](#github-配置)
- [部署流程](#部署流程)
- [监控和维护](#监控和维护)
- [故障排除](#故障排除)

## 🏗️ 部署架构

```
GitHub Repository
       ↓
GitHub Actions CI/CD
       ↓
Docker Build & Test
       ↓
SSH Deploy to GPU Server
       ↓
Docker Compose Deployment
```

### 部署特点

- **自动化部署**: 推送到 `main` 分支自动触发部署
- **多环境支持**: 支持 GPU 和 CPU 版本
- **零停机部署**: 使用 Docker Compose 实现平滑更新
- **健康检查**: 自动验证服务状态
- **回滚机制**: 自动备份，支持快速回滚

## 🖥️ 服务器准备

### 1. 服务器要求

**最低配置:**
- Ubuntu 20.04+ / CentOS 8+
- 8GB RAM (推荐 16GB+)
- 50GB 存储空间
- NVIDIA GPU (可选，用于 GPU 加速)

**推荐配置:**
- Ubuntu 22.04 LTS
- 32GB RAM
- 100GB SSD
- NVIDIA RTX 3080+ 或 Tesla V100+

### 2. 初始化服务器

在服务器上运行初始化脚本：

```bash
# 下载初始化脚本
wget https://raw.githubusercontent.com/your-username/SenseVoice/main/scripts/server-setup.sh

# 设置执行权限
chmod +x server-setup.sh

# 运行初始化脚本
./server-setup.sh
```

初始化脚本会自动安装：
- Docker & Docker Compose
- NVIDIA Docker (如果检测到 GPU)
- 防火墙配置
- 系统服务配置

### 3. 手动安装步骤 (可选)

如果需要手动安装，请参考以下步骤：

#### 安装 Docker

```bash
# 更新系统
sudo apt update && sudo apt upgrade -y

# 安装 Docker
curl -fsSL https://get.docker.com -o get-docker.sh
sudo sh get-docker.sh

# 将用户添加到 docker 组
sudo usermod -aG docker $USER

# 重新登录以应用组更改
```

#### 安装 Docker Compose

```bash
# 安装 Docker Compose
sudo curl -L "https://github.com/docker/compose/releases/latest/download/docker-compose-$(uname -s)-$(uname -m)" -o /usr/local/bin/docker-compose
sudo chmod +x /usr/local/bin/docker-compose
```

#### 安装 NVIDIA Docker (GPU 服务器)

```bash
# 安装 NVIDIA Container Toolkit
distribution=$(. /etc/os-release;echo $ID$VERSION_ID)
curl -s -L https://nvidia.github.io/nvidia-docker/gpgkey | sudo apt-key add -
curl -s -L https://nvidia.github.io/nvidia-docker/$distribution/nvidia-docker.list | sudo tee /etc/apt/sources.list.d/nvidia-docker.list

sudo apt update
sudo apt install -y nvidia-container-toolkit
sudo systemctl restart docker
```

## 🔐 GitHub 配置

### 1. 生成 SSH 密钥

在您的本地机器上生成 SSH 密钥对：

```bash
# 生成 SSH 密钥对
ssh-keygen -t rsa -b 4096 -C "github-actions@your-domain.com" -f ~/.ssh/sensevoice_deploy

# 查看公钥
cat ~/.ssh/sensevoice_deploy.pub

# 查看私钥 (用于 GitHub Secrets)
cat ~/.ssh/sensevoice_deploy
```

### 2. 配置服务器 SSH 访问

将公钥添加到服务器：

```bash
# 在服务器上执行
mkdir -p ~/.ssh
echo "your-public-key-content" >> ~/.ssh/authorized_keys
chmod 600 ~/.ssh/authorized_keys
chmod 700 ~/.ssh
```

### 3. 配置 GitHub Secrets

在 GitHub 仓库中设置以下 Secrets：

**Settings → Secrets and variables → Actions → New repository secret**

| Secret 名称 | 描述 | 示例值 |
|------------|------|--------|
| `SERVER_HOST` | 服务器 IP 地址或域名 | `192.168.1.100` 或 `your-server.com` |
| `SERVER_USER` | 服务器用户名 | `ubuntu` 或 `root` |
| `SERVER_PORT` | SSH 端口 | `22` (默认) 或自定义端口 |
| `SERVER_SSH_KEY` | SSH 私钥内容 | 完整的私钥内容 (包括 BEGIN/END 行) |

#### SSH 私钥格式示例

```
-----BEGIN OPENSSH PRIVATE KEY-----
b3BlbnNzaC1rZXktdjEAAAAABG5vbmUAAAAEbm9uZQAAAAAAAAABFwAAAAdzc2gtcn
NhAAAAAwEAAQAAAQEA1234567890abcdef...
...完整的私钥内容...
-----END OPENSSH PRIVATE KEY-----
```

### 4. 测试 SSH 连接

在本地测试 SSH 连接：

```bash
# 测试 SSH 连接
ssh -i ~/.ssh/sensevoice_deploy -p 22 ubuntu@your-server-ip

# 测试 Docker 权限
docker ps

# 测试部署目录权限
ls -la /opt/sensevoice
```

## 🚀 部署流程

### 1. 自动部署触发条件

- 推送到 `main` 分支
- 推送 `v*` 标签 (如 `v1.0.0`)
- 手动触发 (GitHub Actions 页面)

### 2. 部署步骤

CI/CD 流水线包含以下步骤：

1. **代码检查**: 代码质量检查和基础测试
2. **Docker 构建**: 构建 GPU 和 CPU 版本镜像
3. **文件传输**: 将镜像和配置文件传输到服务器
4. **服务部署**: 在服务器上部署新版本
5. **健康检查**: 验证服务是否正常运行
6. **状态通知**: 报告部署结果

### 3. 手动部署

如果需要手动部署：

```bash
# 在服务器上执行
cd /opt/sensevoice
sudo ./scripts/deploy.sh
```

## 📊 监控和维护

### 1. 查看服务状态

```bash
# 查看容器状态
docker-compose ps

# 查看服务日志
docker-compose logs -f sensevoice

# 查看系统资源使用
htop
nvidia-smi  # GPU 服务器
```

### 2. 服务管理命令

```bash
# 启动服务
sudo systemctl start sensevoice
docker-compose up -d

# 停止服务
sudo systemctl stop sensevoice
docker-compose down

# 重启服务
sudo systemctl restart sensevoice
docker-compose restart

# 查看服务状态
sudo systemctl status sensevoice
```

### 3. 健康检查

```bash
# API 健康检查
curl http://localhost:50000/api/v1/status

# WebSocket 测试
curl -i -N -H "Connection: Upgrade" -H "Upgrade: websocket" -H "Sec-WebSocket-Key: test" -H "Sec-WebSocket-Version: 13" http://localhost:50000/ws/asr
```

### 4. 日志管理

```bash
# 查看应用日志
docker-compose logs --tail=100 sensevoice

# 查看系统日志
sudo journalctl -u sensevoice -f

# 清理日志
docker-compose logs --tail=0 sensevoice
```

## 🔧 故障排除

### 常见问题

#### 1. SSH 连接失败

```bash
# 检查 SSH 配置
ssh -vvv -i ~/.ssh/sensevoice_deploy ubuntu@your-server-ip

# 常见解决方案:
# - 检查服务器防火墙设置
# - 验证 SSH 密钥格式
# - 确认用户名和端口正确
```

#### 2. Docker 权限问题

```bash
# 将用户添加到 docker 组
sudo usermod -aG docker $USER

# 重新登录或执行
newgrp docker
```

#### 3. GPU 不可用

```bash
# 检查 NVIDIA 驱动
nvidia-smi

# 检查 NVIDIA Docker
docker run --rm --gpus all nvidia/cuda:11.8-base-ubuntu20.04 nvidia-smi

# 重启 Docker 服务
sudo systemctl restart docker
```

#### 4. 服务启动失败

```bash
# 查看详细错误日志
docker-compose logs sensevoice

# 检查端口占用
sudo netstat -tlnp | grep 50000

# 检查磁盘空间
df -h
```

### 回滚操作

如果部署失败，可以快速回滚：

```bash
cd /opt/sensevoice

# 查看备份
ls -la backups/

# 回滚到指定版本
cp backups/backup_YYYYMMDD_HHMMSS/docker-compose.yml .
cp backups/backup_YYYYMMDD_HHMMSS/.env .

# 重启服务
docker-compose down
docker-compose up -d
```

## 📞 支持

如果遇到问题，请：

1. 查看 [GitHub Issues](https://github.com/your-username/SenseVoice/issues)
2. 检查服务日志和系统状态
3. 参考本文档的故障排除部分
4. 提交新的 Issue 并附上详细的错误信息
