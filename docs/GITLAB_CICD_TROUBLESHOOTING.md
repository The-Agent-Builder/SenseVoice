# 🔧 GitLab CI/CD 故障排除指南

本文档详细说明 GitLab CI/CD 流水线常见问题的解决方案。

## 📋 目录

- [Docker 镜像拉取失败](#docker-镜像拉取失败)
- [网络连接问题](#网络连接问题)
- [SSH 连接失败](#ssh-连接失败)
- [构建失败](#构建失败)
- [部署失败](#部署失败)

## 🐳 Docker 镜像拉取失败

### 问题症状

```
ERROR: Job failed: failed to pull image "python:3.11-slim" with specified policies [if-not-present]: 
Error response from daemon: Get "https://registry-1.docker.io/v2/": 
net/http: request canceled while waiting for connection (Client.Timeout exceeded while awaiting headers)
```

### 解决方案

#### 1. 使用国内镜像源（推荐）

已在 `.gitlab-ci.yml` 中配置：

```yaml
# 使用阿里云镜像源
image: registry.cn-hangzhou.aliyuncs.com/library/python:3.11-slim

# 使用清华大学 PyPI 源
pip install -i https://pypi.tuna.tsinghua.edu.cn/simple
```

#### 2. 配置 GitLab Runner

在 GitLab Runner 服务器上配置 Docker 镜像源：

```bash
# 编辑 Docker 配置
sudo mkdir -p /etc/docker
sudo tee /etc/docker/daemon.json <<EOF
{
  "registry-mirrors": [
    "https://registry.cn-hangzhou.aliyuncs.com",
    "https://docker.mirrors.ustc.edu.cn",
    "https://hub-mirror.c.163.com"
  ],
  "insecure-registries": [],
  "debug": false,
  "experimental": false
}
EOF

# 重启 Docker 服务
sudo systemctl daemon-reload
sudo systemctl restart docker

# 重启 GitLab Runner
sudo systemctl restart gitlab-runner
```

#### 3. 预拉取镜像

在 GitLab Runner 服务器上预拉取常用镜像：

```bash
# 拉取常用镜像
docker pull registry.cn-hangzhou.aliyuncs.com/library/python:3.11-slim
docker pull registry.cn-hangzhou.aliyuncs.com/library/python:3.11-alpine
docker pull registry.cn-hangzhou.aliyuncs.com/library/docker:24.0.5
docker pull registry.cn-hangzhou.aliyuncs.com/library/alpine:latest

# 标记为本地镜像
docker tag registry.cn-hangzhou.aliyuncs.com/library/python:3.11-slim python:3.11-slim
docker tag registry.cn-hangzhou.aliyuncs.com/library/alpine:latest alpine:latest
```

## 🌐 网络连接问题

### 问题症状

- 连接超时
- DNS 解析失败
- 无法访问外网资源

### 解决方案

#### 1. 配置 DNS

```bash
# 在 GitLab Runner 服务器上配置 DNS
sudo tee /etc/resolv.conf <<EOF
nameserver 8.8.8.8
nameserver 114.114.114.114
nameserver 223.5.5.5
EOF
```

#### 2. 配置代理（如果需要）

在 `.gitlab-ci.yml` 中添加代理配置：

```yaml
variables:
  HTTP_PROXY: "http://proxy.company.com:8080"
  HTTPS_PROXY: "http://proxy.company.com:8080"
  NO_PROXY: "localhost,127.0.0.1,gitlab.sensedeal.wiki"
```

#### 3. 使用内网资源

```yaml
# 使用内网 PyPI 源
variables:
  PIP_INDEX_URL: "http://internal-pypi.company.com/simple"
  PIP_TRUSTED_HOST: "internal-pypi.company.com"
```

## 🔑 SSH 连接失败

### 问题症状

```
Permission denied (publickey)
Host key verification failed
Connection refused
```

### 解决方案

#### 1. 检查 SSH 密钥配置

```bash
# 验证私钥格式
cat ~/.ssh/sensevoice_gitlab

# 应该看到类似内容：
# -----BEGIN OPENSSH PRIVATE KEY-----
# ...
# -----END OPENSSH PRIVATE KEY-----
```

#### 2. 测试 SSH 连接

```bash
# 详细调试 SSH 连接
ssh -vvv -i ~/.ssh/sensevoice_gitlab -p 22 ubuntu@your-server-ip

# 检查服务器 authorized_keys
ssh your-server "cat ~/.ssh/authorized_keys"
```

#### 3. 修复权限问题

```bash
# 在服务器上修复 SSH 权限
chmod 700 ~/.ssh
chmod 600 ~/.ssh/authorized_keys
chmod 600 ~/.ssh/id_rsa
```

#### 4. GitLab Variables 配置检查

确保在 GitLab 中正确配置：

- `SSH_PRIVATE_KEY`: 类型必须是 **File**
- 包含完整的私钥内容（包括 BEGIN/END 行）
- 启用 **Protect variable**
- 不要启用 **Mask variable**（File 类型不支持）

## 🏗️ 构建失败

### 问题症状

- Docker 构建超时
- 依赖安装失败
- 内存不足

### 解决方案

#### 1. 增加构建超时时间

在 `.gitlab-ci.yml` 中添加：

```yaml
build_images:
  timeout: 2h  # 增加超时时间
  script:
    - echo "构建开始..."
```

#### 2. 使用构建缓存

```yaml
build_images:
  cache:
    key: docker-build-cache
    paths:
      - .docker-cache/
  before_script:
    - mkdir -p .docker-cache
    - docker load -i .docker-cache/cache.tar || true
  after_script:
    - docker save -o .docker-cache/cache.tar $DOCKER_IMAGE_NAME:latest || true
```

#### 3. 分阶段构建

```yaml
# 分别构建 GPU 和 CPU 版本
build_gpu:
  stage: build
  script:
    - docker build -f Dockerfile.gpu -t $DOCKER_IMAGE_NAME:gpu-latest .

build_cpu:
  stage: build
  script:
    - docker build -f Dockerfile -t $DOCKER_IMAGE_NAME:cpu-latest .
```

## 🚀 部署失败

### 问题症状

- 文件传输失败
- 服务启动失败
- 健康检查失败

### 解决方案

#### 1. 检查服务器资源

```bash
# 检查磁盘空间
df -h

# 检查内存使用
free -h

# 检查 Docker 状态
docker system df
docker system prune -f
```

#### 2. 增加部署超时

```yaml
deploy_production:
  timeout: 30m  # 增加部署超时
  script:
    - echo "部署开始..."
    # 增加健康检查等待时间
    - sleep 60
```

#### 3. 添加详细日志

```yaml
deploy_production:
  script:
    - set -x  # 启用详细日志
    - echo "开始部署到 $SERVER_HOST"
    # ... 部署脚本
  after_script:
    - echo "=== 部署后状态检查 ==="
    - ssh $SERVER_USER@$SERVER_HOST "docker ps -a"
    - ssh $SERVER_USER@$SERVER_HOST "docker logs sensevoice --tail=50"
```

## 🔍 调试技巧

### 1. 启用详细日志

```yaml
variables:
  CI_DEBUG_TRACE: "true"  # 启用详细日志
```

### 2. 手动调试

```yaml
debug_job:
  stage: test
  script:
    - echo "调试信息："
    - env | sort
    - docker --version
    - python --version
    - pip list
  when: manual
```

### 3. 保留构建产物

```yaml
build_images:
  artifacts:
    when: always  # 即使失败也保留
    expire_in: 1 day
    paths:
      - "*.log"
      - "build-output/"
```

## 📞 获取帮助

如果问题仍未解决：

1. **查看完整日志**: GitLab CI/CD → Pipelines → Job → 完整日志
2. **检查 Runner 状态**: Settings → CI/CD → Runners
3. **验证变量配置**: Settings → CI/CD → Variables
4. **测试本地构建**: 在本地环境复现问题
5. **联系管理员**: 提供详细的错误日志和环境信息

## 🎯 预防措施

1. **定期更新镜像**: 使用最新的稳定版本
2. **监控资源使用**: 定期清理 Docker 缓存
3. **备份配置**: 定期备份 CI/CD 配置
4. **测试环境**: 在测试环境验证配置
5. **文档更新**: 及时更新部署文档
