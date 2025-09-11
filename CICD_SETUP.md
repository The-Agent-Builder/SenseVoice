# 🚀 SenseVoice CI/CD 部署配置指南

本指南将帮助您快速设置 SenseVoice 项目的 GitHub Actions CI/CD 自动化部署流程。

## 📋 快速开始

### 1. 服务器准备

在您的 GPU 服务器上运行以下命令：

```bash
# 下载并运行服务器初始化脚本
curl -fsSL https://raw.githubusercontent.com/your-username/SenseVoice/main/scripts/server-setup.sh | bash

# 或者手动下载后执行
wget https://raw.githubusercontent.com/your-username/SenseVoice/main/scripts/server-setup.sh
chmod +x server-setup.sh
./server-setup.sh
```

### 2. SSH 密钥配置

在本地机器上生成 SSH 密钥：

```bash
# 生成 SSH 密钥对
ssh-keygen -t rsa -b 4096 -C "github-actions@your-domain.com" -f ~/.ssh/sensevoice_deploy

# 将公钥复制到服务器
ssh-copy-id -i ~/.ssh/sensevoice_deploy.pub your-username@your-server-ip

# 测试连接
ssh -i ~/.ssh/sensevoice_deploy your-username@your-server-ip
```

### 3. GitHub Secrets 配置

在 GitHub 仓库中配置以下 Secrets：

**路径**: `Settings → Secrets and variables → Actions → New repository secret`

| Secret 名称 | 值 | 说明 |
|------------|----|----|
| `SERVER_HOST` | `192.168.1.100` | 服务器 IP 地址或域名 |
| `SERVER_USER` | `ubuntu` | 服务器用户名 |
| `SERVER_PORT` | `22` | SSH 端口 (默认 22) |
| `SERVER_SSH_KEY` | `-----BEGIN OPENSSH PRIVATE KEY-----...` | 完整的 SSH 私钥内容 |

## 🔧 详细配置步骤

### 服务器要求

**最低配置:**
- Ubuntu 20.04+ / CentOS 8+
- 8GB RAM
- 50GB 存储
- 网络连接

**推荐配置:**
- Ubuntu 22.04 LTS
- 16GB+ RAM
- 100GB+ SSD
- NVIDIA GPU (RTX 3080+ 或 Tesla V100+)

### 获取服务器信息

您需要以下信息来配置 GitHub Secrets：

#### 1. 服务器 IP 地址

```bash
# 查看公网 IP
curl ifconfig.me

# 查看内网 IP
ip addr show
```

#### 2. SSH 用户名

```bash
# 查看当前用户
whoami

# 常见用户名: ubuntu, root, centos, admin
```

#### 3. SSH 端口

```bash
# 查看 SSH 端口配置
sudo grep "Port" /etc/ssh/sshd_config

# 默认端口是 22
```

#### 4. SSH 私钥

```bash
# 查看生成的私钥
cat ~/.ssh/sensevoice_deploy

# 复制完整内容，包括 BEGIN 和 END 行
```

### Docker 配置验证

在服务器上验证 Docker 配置：

```bash
# 检查 Docker 状态
sudo systemctl status docker

# 检查 Docker Compose
docker-compose --version

# 检查 GPU 支持 (如果有 GPU)
nvidia-smi
docker run --rm --gpus all nvidia/cuda:11.8-base-ubuntu20.04 nvidia-smi

# 检查部署目录
ls -la /opt/sensevoice
```

## 🚀 部署流程

### 自动部署

推送代码到 `main` 分支将自动触发部署：

```bash
git add .
git commit -m "feat: 新功能"
git push origin main
```

### 手动部署

在 GitHub Actions 页面手动触发部署：

1. 进入 GitHub 仓库
2. 点击 `Actions` 标签
3. 选择 `SenseVoice CI/CD Pipeline`
4. 点击 `Run workflow`

### 本地测试

在推送前本地测试：

```bash
# 构建 Docker 镜像
docker build -f Dockerfile.gpu -t sensevoice:test .

# 运行测试
docker run --rm sensevoice:test python -c "import config.settings; print('OK')"
```

## 📊 监控和验证

### 部署状态检查

```bash
# 在服务器上检查服务状态
cd /opt/sensevoice
docker-compose ps

# 查看服务日志
docker-compose logs -f sensevoice

# 健康检查
curl http://localhost:50000/health
curl http://localhost:50000/api/v1/status
```

### 服务访问

部署成功后，可以通过以下地址访问服务：

- **API 文档**: `http://your-server-ip:50000/docs`
- **健康检查**: `http://your-server-ip:50000/health`
- **服务状态**: `http://your-server-ip:50000/api/v1/status`
- **WebSocket 测试**: `http://your-server-ip:50000/ws-test`

## 🔧 故障排除

### 常见问题

#### 1. SSH 连接失败

```bash
# 详细调试 SSH 连接
ssh -vvv -i ~/.ssh/sensevoice_deploy your-username@your-server-ip

# 检查防火墙
sudo ufw status

# 检查 SSH 服务
sudo systemctl status ssh
```

#### 2. Docker 权限问题

```bash
# 将用户添加到 docker 组
sudo usermod -aG docker $USER

# 重新登录或执行
newgrp docker

# 测试 Docker 权限
docker ps
```

#### 3. 部署失败

```bash
# 查看 GitHub Actions 日志
# 在 GitHub 仓库的 Actions 页面查看详细错误

# 在服务器上查看日志
cd /opt/sensevoice
docker-compose logs sensevoice

# 检查磁盘空间
df -h

# 检查内存使用
free -h
```

#### 4. 服务无法访问

```bash
# 检查端口是否开放
sudo netstat -tlnp | grep 50000

# 检查防火墙规则
sudo ufw status

# 开放端口
sudo ufw allow 50000/tcp
```

### 回滚操作

如果部署出现问题，可以快速回滚：

```bash
cd /opt/sensevoice

# 查看备份
ls -la backups/

# 回滚到上一个版本
BACKUP_DIR=$(ls -t backups/ | head -1)
cp backups/$BACKUP_DIR/docker-compose.yml .
cp backups/$BACKUP_DIR/.env .

# 重启服务
docker-compose down
docker-compose up -d
```

## 📞 获取帮助

如果遇到问题：

1. **查看日志**: 检查 GitHub Actions 和服务器日志
2. **验证配置**: 确认所有 Secrets 配置正确
3. **测试连接**: 验证 SSH 连接和 Docker 权限
4. **提交 Issue**: 在 GitHub 仓库提交问题报告

## 🎉 完成

配置完成后，您的 SenseVoice 项目将具备：

- ✅ 自动化 CI/CD 部署
- ✅ 代码质量检查
- ✅ Docker 容器化部署
- ✅ 健康检查和监控
- ✅ 自动备份和回滚
- ✅ GPU 加速支持

现在您可以专注于开发，让 CI/CD 流水线自动处理部署工作！
