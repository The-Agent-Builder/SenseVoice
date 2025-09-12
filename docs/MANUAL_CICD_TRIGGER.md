# 🚀 手动执行 CI/CD 部署指南

本文档详细说明如何在 GitHub 上手动触发 SenseVoice 的 CI/CD 部署流程。

## 📋 目录

- [GitHub Actions 页面手动触发](#github-actions-页面手动触发)
- [推送代码触发](#推送代码触发)
- [创建标签触发](#创建标签触发)
- [API 触发](#api-触发)
- [故障排除](#故障排除)

## 🖱️ GitHub Actions 页面手动触发

### 1. 进入 Actions 页面

1. 打开您的 GitHub 仓库: `https://github.com/The-Agent-Builder/SenseVoice`
2. 点击顶部导航栏的 **"Actions"** 标签
3. 在左侧工作流列表中找到 **"SenseVoice CI/CD Pipeline"**

### 2. 手动运行工作流

1. 点击 **"SenseVoice CI/CD Pipeline"** 工作流
2. 点击右侧的 **"Run workflow"** 下拉按钮
3. 配置部署参数：

#### 📝 部署参数说明

| 参数 | 说明 | 可选值 | 默认值 |
|------|------|--------|--------|
| **部署环境** | 目标部署环境 | `production`, `staging`, `development` | `production` |
| **强制部署** | 跳过测试直接部署 | `true`, `false` | `false` |
| **GPU设备选择** | 指定GPU设备 | `auto`, `cuda:0-7`, `cpu` | `auto` |

#### 🎯 常用配置示例

**生产环境部署 (推荐)**:
```
部署环境: production
强制部署: false
GPU设备选择: cuda:4
```

**快速部署 (跳过测试)**:
```
部署环境: production  
强制部署: true
GPU设备选择: cuda:4
```

**CPU模式部署**:
```
部署环境: production
强制部署: false
GPU设备选择: cpu
```

### 3. 执行部署

1. 选择要部署的分支（通常是 `main`）
2. 配置好参数后，点击绿色的 **"Run workflow"** 按钮
3. 工作流将立即开始执行

### 4. 监控部署进度

1. 在 Actions 页面可以看到正在运行的工作流
2. 点击工作流名称查看详细日志
3. 可以实时查看每个步骤的执行状态

## 📤 推送代码触发

### 自动触发条件

以下操作会自动触发 CI/CD：

```bash
# 推送到 main 分支
git push origin main

# 推送到 develop 分支  
git push origin develop

# 创建 Pull Request 到 main 分支
# (只运行测试，不部署)
```

### 手动推送触发

```bash
# 1. 提交代码
git add .
git commit -m "feat: 触发部署"

# 2. 推送到 main 分支触发部署
git push origin main

# 3. 或推送到 develop 分支进行测试
git push origin develop
```

## 🏷️ 创建标签触发

### 版本发布部署

```bash
# 1. 创建版本标签
git tag v1.0.0
git push origin v1.0.0

# 2. 或者创建带注释的标签
git tag -a v1.0.0 -m "Release version 1.0.0"
git push origin v1.0.0

# 3. 批量推送所有标签
git push origin --tags
```

### 标签命名规范

- **主版本**: `v1.0.0`, `v2.0.0`
- **次版本**: `v1.1.0`, `v1.2.0`  
- **补丁版本**: `v1.0.1`, `v1.0.2`
- **预发布**: `v1.0.0-beta.1`, `v1.0.0-rc.1`

## 🔧 API 触发

### 使用 GitHub CLI

```bash
# 安装 GitHub CLI
# macOS: brew install gh
# Ubuntu: sudo apt install gh

# 登录
gh auth login

# 手动触发工作流
gh workflow run "SenseVoice CI/CD Pipeline" \
  --field environment=production \
  --field force_deploy=false \
  --field gpu_device=cuda:4
```

### 使用 REST API

```bash
# 获取 Personal Access Token
# Settings → Developer settings → Personal access tokens

# 触发工作流
curl -X POST \
  -H "Accept: application/vnd.github.v3+json" \
  -H "Authorization: token YOUR_TOKEN" \
  https://api.github.com/repos/The-Agent-Builder/SenseVoice/actions/workflows/ci-cd.yml/dispatches \
  -d '{
    "ref": "main",
    "inputs": {
      "environment": "production",
      "force_deploy": "false", 
      "gpu_device": "cuda:4"
    }
  }'
```

## 📊 部署状态监控

### 1. GitHub Actions 页面

- **运行中**: 🟡 黄色圆圈
- **成功**: ✅ 绿色对勾
- **失败**: ❌ 红色叉号
- **取消**: ⚪ 灰色圆圈

### 2. 服务器状态检查

部署完成后，验证服务状态：

```bash
# 健康检查
curl http://your-server-ip:50000/health

# 服务状态
curl http://your-server-ip:50000/api/v1/status

# 查看容器状态
ssh your-server "cd /opt/sensevoice && docker-compose ps"
```

### 3. 实时日志监控

```bash
# 查看部署日志
ssh your-server "cd /opt/sensevoice && docker-compose logs -f sensevoice"

# 查看系统日志
ssh your-server "sudo journalctl -u sensevoice -f"
```

## 🔍 故障排除

### 常见问题

#### 1. 工作流无法找到

**问题**: 在 Actions 页面看不到工作流

**解决方案**:
```bash
# 检查工作流文件是否存在
ls -la .github/workflows/

# 检查文件语法
cat .github/workflows/ci-cd.yml

# 推送工作流文件
git add .github/workflows/ci-cd.yml
git commit -m "fix: 修复工作流配置"
git push origin main
```

#### 2. 手动触发按钮不显示

**问题**: 没有 "Run workflow" 按钮

**原因**: 工作流文件中缺少 `workflow_dispatch` 触发器

**解决方案**: 确保工作流文件包含：
```yaml
on:
  workflow_dispatch:
    inputs:
      # 输入参数配置
```

#### 3. 部署失败

**问题**: 部署过程中出现错误

**排查步骤**:
1. 查看 GitHub Actions 详细日志
2. 检查服务器连接状态
3. 验证 GitHub Secrets 配置
4. 检查服务器磁盘空间和权限

```bash
# 检查服务器连接
ssh -i ~/.ssh/sensevoice_deploy your-username@your-server-ip

# 检查磁盘空间
df -h

# 检查 Docker 状态
docker ps
docker-compose ps
```

#### 4. GPU 设备选择无效

**问题**: 指定的 GPU 设备不生效

**解决方案**:
```bash
# 在服务器上检查 .env 文件
cat /opt/sensevoice/.env

# 手动设置 GPU 设备
echo "SENSEVOICE_DEVICE=cuda:4" >> /opt/sensevoice/.env

# 重启服务
cd /opt/sensevoice
docker-compose restart
```

## 💡 最佳实践

### 1. 部署前检查

- ✅ 确认代码已经过测试
- ✅ 检查服务器资源状态
- ✅ 备份当前运行版本
- ✅ 通知相关人员

### 2. 部署参数选择

- **生产环境**: 使用 `force_deploy=false` 确保测试通过
- **紧急修复**: 可以使用 `force_deploy=true` 快速部署
- **GPU选择**: 根据服务器状态选择合适的GPU设备

### 3. 部署后验证

- ✅ 检查服务健康状态
- ✅ 验证API功能正常
- ✅ 监控服务日志
- ✅ 确认性能指标

## 📞 获取帮助

如果遇到部署问题：

1. **查看 Actions 日志**: GitHub Actions 页面的详细日志
2. **检查服务器状态**: SSH 登录服务器查看状态
3. **参考文档**: `docs/CICD_DEPLOYMENT.md`
4. **提交 Issue**: 附上错误日志和环境信息

---

🎉 现在您可以灵活地手动触发 CI/CD 部署，根据需要选择不同的部署参数和环境配置！
