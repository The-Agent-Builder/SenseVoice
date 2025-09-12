# 🚀 GitLab CI/CD 部署配置指南

本指南详细说明如何在 GitLab 上配置 SenseVoice 项目的 CI/CD 自动化部署流程。

## 📋 目录

- [GitLab 项目配置](#gitlab-项目配置)
- [CI/CD 变量配置](#cicd-变量配置)
- [SSH 密钥配置](#ssh-密钥配置)
- [流水线触发方式](#流水线触发方式)
- [监控和维护](#监控和维护)

## 🔧 GitLab 项目配置

### 1. 项目地址

```
GitLab 仓库: http://gitlab.sensedeal.wiki:8060/ketd/sensevoice
```

### 2. 启用 CI/CD

1. 进入项目页面
2. 点击左侧菜单 **"Settings"** → **"CI/CD"**
3. 确保 **"Pipelines"** 已启用

## 🔐 CI/CD 变量配置

在 GitLab 项目中配置以下 CI/CD 变量：

**路径**: `Settings → CI/CD → Variables`

### 必需变量

| 变量名 | 类型 | 值 | 说明 |
|--------|------|----|----|
| `SERVER_HOST` | Variable | `your-server-ip` | 服务器 IP 地址 |
| `SERVER_USER` | Variable | `ubuntu` | 服务器用户名 |
| `SERVER_PORT` | Variable | `22` | SSH 端口 |
| `SSH_PRIVATE_KEY` | File | `私钥内容` | SSH 私钥 |

### 可选变量

| 变量名 | 类型 | 默认值 | 说明 |
|--------|------|--------|------|
| `GPU_DEVICE` | Variable | `auto` | GPU 设备选择 |
| `ENVIRONMENT` | Variable | `production` | 部署环境 |
| `FORCE_DEPLOY` | Variable | `false` | 强制部署 |

### 变量配置步骤

1. 进入项目页面
2. 点击 **"Settings"** → **"CI/CD"**
3. 展开 **"Variables"** 部分
4. 点击 **"Add variable"**
5. 配置变量：
   - **Key**: 变量名
   - **Value**: 变量值
   - **Type**: Variable 或 File
   - **Environment scope**: All (default)
   - **Protect variable**: ✅ (推荐)
   - **Mask variable**: ✅ (对于敏感信息)

## 🔑 SSH 密钥配置

### 1. 生成 SSH 密钥

在本地机器上生成 SSH 密钥：

```bash
# 生成 SSH 密钥对
ssh-keygen -t rsa -b 4096 -C "gitlab-ci@sensevoice" -f ~/.ssh/sensevoice_gitlab

# 查看公钥（复制到服务器）
cat ~/.ssh/sensevoice_gitlab.pub

# 查看私钥（复制到 GitLab Variables）
cat ~/.ssh/sensevoice_gitlab
```

### 2. 配置服务器

将公钥添加到服务器：

```bash
# 在服务器上执行
mkdir -p ~/.ssh
echo "your-public-key-content" >> ~/.ssh/authorized_keys
chmod 600 ~/.ssh/authorized_keys
chmod 700 ~/.ssh
```

### 3. 配置 GitLab

1. 进入 **"Settings"** → **"CI/CD"** → **"Variables"**
2. 添加 `SSH_PRIVATE_KEY` 变量：
   - **Type**: File
   - **Value**: 完整的私钥内容（包括 BEGIN/END 行）
   - **Protect variable**: ✅
   - **Mask variable**: ❌ (文件类型不能 mask)

### 4. 测试 SSH 连接

```bash
# 测试 SSH 连接
ssh -i ~/.ssh/sensevoice_gitlab -p 22 ubuntu@your-server-ip

# 测试 Docker 权限
docker ps

# 测试部署目录权限
ls -la /opt/sensevoice
```

## 🚀 流水线触发方式

### 1. 自动触发

以下操作会自动触发 CI/CD 流水线：

```bash
# 推送到 main 分支
git push origin main

# 推送到 develop 分支
git push origin develop

# 创建版本标签
git tag v1.0.0
git push origin v1.0.0

# 创建 Merge Request
# (只运行测试，不部署)
```

### 2. 手动触发

#### 通过 GitLab Web 界面

1. 进入项目页面
2. 点击左侧菜单 **"CI/CD"** → **"Pipelines"**
3. 点击 **"Run pipeline"** 按钮
4. 选择分支（通常是 `main`）
5. 设置变量（可选）：
   ```
   GPU_DEVICE: cuda:4
   ENVIRONMENT: production
   FORCE_DEPLOY: false
   ```
6. 点击 **"Run pipeline"**

#### 通过 GitLab CLI

```bash
# 安装 GitLab CLI
pip install python-gitlab

# 配置访问令牌
export GITLAB_PRIVATE_TOKEN="your-access-token"

# 触发流水线
gitlab-ci trigger --project-id=your-project-id --ref=main
```

### 3. API 触发

```bash
# 使用 GitLab API 触发流水线
curl -X POST \
  -F token=your-trigger-token \
  -F ref=main \
  -F "variables[GPU_DEVICE]=cuda:4" \
  -F "variables[ENVIRONMENT]=production" \
  http://gitlab.sensedeal.wiki:8060/api/v4/projects/your-project-id/trigger/pipeline
```

## 📊 流水线阶段说明

### 1. Test 阶段

- **代码质量检查**: 使用 flake8 进行代码风格检查
- **基础测试**: 验证模块导入和基本功能
- **条件执行**: 可通过 `FORCE_DEPLOY=true` 跳过

### 2. Build 阶段

- **Docker 镜像构建**: 构建 GPU 和 CPU 版本镜像
- **镜像保存**: 将镜像保存为 tar.gz 文件
- **构件存储**: 保存构建产物供部署使用

### 3. Deploy 阶段

- **文件传输**: 将镜像和配置文件传输到服务器
- **服务部署**: 自动部署和启动服务
- **健康检查**: 验证服务是否正常运行
- **状态报告**: 显示部署结果和服务状态

## 🔍 监控和维护

### 1. 查看流水线状态

1. 进入项目页面
2. 点击 **"CI/CD"** → **"Pipelines"**
3. 查看流水线状态：
   - 🟢 **passed**: 成功
   - 🔴 **failed**: 失败
   - 🟡 **running**: 运行中
   - ⚪ **canceled**: 已取消

### 2. 查看详细日志

1. 点击流水线 ID
2. 点击具体的 Job 名称
3. 查看详细的执行日志

### 3. 服务器状态检查

```bash
# 健康检查
curl http://your-server-ip:50000/health

# 服务状态
curl http://your-server-ip:50000/api/v1/status

# 查看容器状态
ssh your-server "cd /opt/sensevoice && docker-compose ps"

# 查看服务日志
ssh your-server "cd /opt/sensevoice && docker-compose logs -f sensevoice"
```

## 🔧 故障排除

### 常见问题

#### 1. SSH 连接失败

**症状**: `Permission denied (publickey)`

**解决方案**:
```bash
# 检查 SSH 密钥格式
cat ~/.ssh/sensevoice_gitlab

# 测试连接
ssh -i ~/.ssh/sensevoice_gitlab -v ubuntu@your-server-ip

# 检查服务器 authorized_keys
ssh your-server "cat ~/.ssh/authorized_keys"
```

#### 2. Docker 构建失败

**症状**: `Cannot connect to the Docker daemon`

**解决方案**:
- 确保 GitLab Runner 支持 Docker
- 检查 `docker:dind` 服务配置
- 验证 Dockerfile 语法

#### 3. 部署失败

**症状**: 部署阶段失败

**排查步骤**:
1. 检查服务器连接状态
2. 验证部署目录权限
3. 检查磁盘空间
4. 查看详细错误日志

```bash
# 检查服务器状态
ssh your-server "df -h && docker ps"

# 检查部署目录
ssh your-server "ls -la /opt/sensevoice"

# 手动执行部署脚本
ssh your-server "cd /opt/sensevoice && ./scripts/deploy.sh"
```

## 💡 最佳实践

### 1. 分支策略

- **main**: 生产环境部署
- **develop**: 开发环境测试
- **feature/***: 功能开发分支

### 2. 变量管理

- 使用 **Protected variables** 保护敏感信息
- 使用 **Masked variables** 隐藏日志中的敏感值
- 按环境分组管理变量

### 3. 流水线优化

- 使用缓存加速构建
- 并行执行独立任务
- 合理设置超时时间

## 📞 获取帮助

如果遇到 CI/CD 问题：

1. **查看流水线日志**: GitLab CI/CD → Pipelines → Job logs
2. **检查变量配置**: Settings → CI/CD → Variables
3. **验证 SSH 连接**: 测试服务器连接状态
4. **参考文档**: 查看相关配置文档

---

🎉 现在您的 SenseVoice 项目已经配置了完整的 GitLab CI/CD 自动化部署流程！
