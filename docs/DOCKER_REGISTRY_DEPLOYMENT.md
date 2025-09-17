# 🐳 内网 Docker 仓库部署指南

本文档详细说明如何使用内网 Docker 仓库进行 SenseVoice 项目的 CI/CD 部署。

## 📋 目录

- [内网 Docker 仓库配置](#内网-docker-仓库配置)
- [GitLab CI/CD 变量配置](#gitlab-cicd-变量配置)
- [部署流程](#部署流程)
- [使用方法](#使用方法)
- [故障排除](#故障排除)

## 🏗️ 内网 Docker 仓库配置

### 仓库信息

- **仓库地址**: `hub.sensedeal.vip`
- **基础镜像**: `hub.sensedeal.vip/library/ubuntu-python-base:22.04-20240612`
- **构建镜像**: `hub.sensedeal.vip/library/docker:27.3.1-dind`

### 认证信息

使用 GitLab CI/CD 变量进行认证：
- `CI_REGISTRY_USER`: Docker 仓库用户名
- `CI_REGISTRY_PASSWORD`: Docker 仓库密码

## 🔐 GitLab CI/CD 变量配置

在 GitLab 项目中配置以下变量：

**路径**: `Settings → CI/CD → Variables`

### 必需变量

| 变量名 | 类型 | 值 | 说明 |
|--------|------|----|----|
| `CI_REGISTRY_USER` | Variable | `your-username` | Docker 仓库用户名 |
| `CI_REGISTRY_PASSWORD` | Variable | `your-password` | Docker 仓库密码 |

**配置要求**:
- **Protect variable**: ✅ (推荐)
- **Mask variable**: ✅ (对于密码)
- **Environment scope**: All (default)

### 可选变量

| 变量名 | 类型 | 默认值 | 说明 |
|--------|------|--------|------|
| `GPU_DEVICE` | Variable | `cuda` | GPU 设备选择 |
| `ENVIRONMENT` | Variable | `production` | 部署环境 |
| `FORCE_DEPLOY` | Variable | `false` | 强制部署 |

## 🚀 部署流程

### 1. 自动触发

推送代码到 `main` 分支将自动触发 CI/CD 流水线：

```bash
git add .
git commit -m "feat: 新功能"
git push origin main
```

### 2. 手动触发

1. 进入 GitLab 项目: http://gitlab.sensedeal.wiki:8060/ketd/sensevoice
2. 点击 **CI/CD → Pipelines**
3. 点击 **"Run pipeline"**
4. 选择 `main` 分支
5. 设置变量（可选）：
   ```
   GPU_DEVICE: cuda
   ENVIRONMENT: production
   FORCE_DEPLOY: false
   ```
6. 点击 **"Run pipeline"**

### 3. 流水线阶段

#### Stage 1: Test
- **code_quality**: 代码质量检查和基础测试
- **syntax_check**: 简化的语法检查（备用）

#### Stage 2: Build
- **build_images**: 构建 GPU 和 CPU Docker 镜像
- 推送镜像到内网仓库
- 生成部署配置文件

#### Stage 3: Deploy
- **deploy_docker**: 生成部署配置和说明
- 提供部署命令和镜像信息

## 📦 构建产物

流水线完成后，将生成以下产物：

### Docker 镜像

推送到内网仓库的镜像：
- `hub.sensedeal.vip/sensevoice:gpu-latest` - GPU 版本
- `hub.sensedeal.vip/sensevoice:cpu-latest` - CPU 版本
- `hub.sensedeal.vip/sensevoice:gpu-{commit-sha}` - GPU 版本（带版本标签）
- `hub.sensedeal.vip/sensevoice:cpu-{commit-sha}` - CPU 版本（带版本标签）

### 部署文件

- `docker-compose.deploy.yml` - 部署配置文件
- `sensevoice-gpu-latest.tar.gz` - GPU 镜像文件
- `sensevoice-cpu-latest.tar.gz` - CPU 镜像文件

## 🎯 使用方法

### 方法 1: 直接从内网仓库拉取

```bash
# 登录内网 Docker 仓库
docker login hub.sensedeal.vip

# 拉取并运行 GPU 版本
docker run -d \
  --name sensevoice-gpu \
  --gpus all \
  -p 50000:50000 \
  -e SENSEVOICE_DEVICE=cuda \
  hub.sensedeal.vip/sensevoice:gpu-latest

# 拉取并运行 CPU 版本
docker run -d \
  --name sensevoice-cpu \
  -p 50001:50000 \
  -e SENSEVOICE_DEVICE=cpu \
  hub.sensedeal.vip/sensevoice:cpu-latest
```

### 方法 2: 使用 Docker Compose

下载 CI/CD 生成的 `docker-compose.deploy.yml` 文件：

```bash
# GPU 版本部署
docker-compose -f docker-compose.deploy.yml up -d sensevoice-gpu

# CPU 版本部署
docker-compose -f docker-compose.deploy.yml --profile cpu up -d sensevoice-cpu

# 查看服务状态
docker-compose -f docker-compose.deploy.yml ps

# 查看日志
docker-compose -f docker-compose.deploy.yml logs -f
```

### 方法 3: 使用镜像文件

如果无法直接访问内网仓库，可以使用 CI/CD 生成的镜像文件：

```bash
# 加载镜像文件
docker load < sensevoice-gpu-latest.tar.gz
docker load < sensevoice-cpu-latest.tar.gz

# 运行服务
docker run -d \
  --name sensevoice \
  --gpus all \
  -p 50000:50000 \
  -e SENSEVOICE_DEVICE=cuda \
  hub.sensedeal.vip/sensevoice:gpu-latest
```

## 🔍 服务验证

部署完成后，验证服务是否正常运行：

```bash
# 健康检查
curl http://localhost:50000/health

# 服务状态
curl http://localhost:50000/api/v1/status

# API 文档
open http://localhost:50000/docs

# WebSocket 测试页面
open http://localhost:50000/static/ws_test.html
```

## 🔧 故障排除

### 1. Docker 仓库认证失败

**症状**: `unauthorized: authentication required`

**解决方案**:
```bash
# 检查 GitLab 变量配置
# 确保 CI_REGISTRY_USER 和 CI_REGISTRY_PASSWORD 正确

# 手动测试登录
docker login hub.sensedeal.vip
```

### 2. 镜像拉取失败

**症状**: `pull access denied` 或 `repository does not exist`

**解决方案**:
```bash
# 检查镜像名称和标签
docker images | grep sensevoice

# 检查仓库权限
curl -u username:password https://hub.sensedeal.vip/v2/_catalog
```

### 3. GPU 不可用

**症状**: `could not select device driver "" with capabilities: [[gpu]]`

**解决方案**:
```bash
# 检查 NVIDIA 驱动
nvidia-smi

# 检查 NVIDIA Docker
docker run --rm --gpus all nvidia/cuda:11.8-base-ubuntu20.04 nvidia-smi

# 使用 CPU 版本
docker-compose -f docker-compose.deploy.yml --profile cpu up -d sensevoice-cpu
```

### 4. 端口冲突

**症状**: `port is already allocated`

**解决方案**:
```bash
# 检查端口占用
sudo netstat -tlnp | grep 50000

# 停止冲突的服务
docker stop $(docker ps -q --filter "publish=50000")

# 或使用不同端口
docker run -p 50002:50000 hub.sensedeal.vip/sensevoice:gpu-latest
```

## 📊 监控和维护

### 查看服务状态

```bash
# 查看容器状态
docker ps

# 查看资源使用
docker stats

# 查看日志
docker logs sensevoice-gpu -f
```

### 更新服务

```bash
# 拉取最新镜像
docker pull hub.sensedeal.vip/sensevoice:gpu-latest

# 重启服务
docker-compose -f docker-compose.deploy.yml down
docker-compose -f docker-compose.deploy.yml up -d
```

### 清理资源

```bash
# 清理未使用的镜像
docker image prune -f

# 清理未使用的容器
docker container prune -f

# 清理系统资源
docker system prune -f
```

## 📞 获取帮助

如果遇到问题：

1. **查看 CI/CD 日志**: GitLab → CI/CD → Pipelines → Job logs
2. **检查变量配置**: Settings → CI/CD → Variables
3. **验证仓库访问**: 测试 Docker 仓库连接
4. **参考故障排除**: 查看本文档的故障排除部分
5. **联系管理员**: 提供详细的错误信息和环境描述

## 🎉 完成

现在您的 SenseVoice 项目已经配置为使用内网 Docker 仓库进行 CI/CD 部署！

主要优势：
- ✅ 内网访问，安全性高
- ✅ 镜像版本管理
- ✅ 自动化构建和部署
- ✅ 支持 GPU 和 CPU 版本
- ✅ 完整的监控和日志
