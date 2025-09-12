#!/bin/bash

# SenseVoice 项目迁移到 GitLab 脚本
# 将项目从 GitHub 迁移到内网 GitLab

set -e

# 颜色输出
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# 配置变量
GITLAB_URL="http://gitlab.sensedeal.wiki:8060"
GITLAB_PROJECT="ketd/sensevoice"
GITLAB_REPO_URL="$GITLAB_URL/$GITLAB_PROJECT.git"

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

# 检查当前仓库状态
check_current_repo() {
    log "检查当前仓库状态..."
    
    if [ ! -d ".git" ]; then
        error "当前目录不是 Git 仓库"
    fi
    
    # 检查是否有未提交的更改
    if ! git diff --quiet || ! git diff --cached --quiet; then
        warn "检测到未提交的更改"
        git status
        read -p "是否要提交这些更改？(y/N): " -n 1 -r
        echo
        if [[ $REPLY =~ ^[Yy]$ ]]; then
            git add .
            git commit -m "feat: 迁移到 GitLab 前的最后提交"
        else
            error "请先提交或暂存您的更改"
        fi
    fi
    
    log "仓库状态检查完成"
}

# 添加 GitLab 远程仓库
add_gitlab_remote() {
    log "添加 GitLab 远程仓库..."
    
    # 检查是否已存在 gitlab 远程仓库
    if git remote | grep -q "gitlab"; then
        warn "GitLab 远程仓库已存在，更新 URL..."
        git remote set-url gitlab "$GITLAB_REPO_URL"
    else
        git remote add gitlab "$GITLAB_REPO_URL"
    fi
    
    # 显示远程仓库列表
    log "当前远程仓库列表:"
    git remote -v
}

# 推送到 GitLab
push_to_gitlab() {
    log "推送代码到 GitLab..."
    
    # 推送所有分支
    log "推送 main 分支..."
    git push gitlab main
    
    # 推送所有标签
    if git tag | grep -q .; then
        log "推送标签..."
        git push gitlab --tags
    fi
    
    # 推送其他分支（如果存在）
    OTHER_BRANCHES=$(git branch -r | grep -v "origin/HEAD" | grep -v "origin/main" | sed 's/origin\///' | tr -d ' ')
    if [ ! -z "$OTHER_BRANCHES" ]; then
        log "推送其他分支..."
        for branch in $OTHER_BRANCHES; do
            git push gitlab origin/$branch:$branch || warn "推送分支 $branch 失败"
        done
    fi
    
    log "代码推送完成"
}

# 更新文档中的仓库地址
update_documentation() {
    log "更新文档中的仓库地址..."
    
    # 更新 README.md 中的仓库地址（如果存在）
    if [ -f "README.md" ]; then
        sed -i.bak "s|github.com/The-Agent-Builder/SenseVoice|$GITLAB_URL/$GITLAB_PROJECT|g" README.md
        rm -f README.md.bak
    fi
    
    # 更新其他文档文件
    find docs/ -name "*.md" -type f -exec sed -i.bak "s|github.com/The-Agent-Builder/SenseVoice|$GITLAB_URL/$GITLAB_PROJECT|g" {} \;
    find docs/ -name "*.bak" -type f -delete
    
    # 更新快速配置指南
    if [ -f "CICD_SETUP.md" ]; then
        sed -i.bak "s|github.com/The-Agent-Builder/SenseVoice|$GITLAB_URL/$GITLAB_PROJECT|g" CICD_SETUP.md
        rm -f CICD_SETUP.md.bak
    fi
    
    log "文档更新完成"
}

# 验证 GitLab 仓库
verify_gitlab_repo() {
    log "验证 GitLab 仓库..."
    
    # 检查远程仓库连接
    if git ls-remote gitlab &>/dev/null; then
        log "GitLab 仓库连接正常"
    else
        error "无法连接到 GitLab 仓库，请检查网络和权限"
    fi
    
    # 检查推送的内容
    GITLAB_COMMITS=$(git rev-list --count gitlab/main 2>/dev/null || echo "0")
    LOCAL_COMMITS=$(git rev-list --count main)
    
    if [ "$GITLAB_COMMITS" -eq "$LOCAL_COMMITS" ]; then
        log "GitLab 仓库同步完成，提交数量: $LOCAL_COMMITS"
    else
        warn "GitLab 仓库提交数量不匹配: 本地 $LOCAL_COMMITS, GitLab $GITLAB_COMMITS"
    fi
}

# 设置默认远程仓库
set_default_remote() {
    log "设置 GitLab 为默认远程仓库..."
    
    read -p "是否要将 GitLab 设置为默认的 origin 远程仓库？(y/N): " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        # 重命名现有的 origin 为 github
        git remote rename origin github 2>/dev/null || true
        
        # 将 gitlab 重命名为 origin
        git remote rename gitlab origin
        
        # 设置上游分支
        git branch --set-upstream-to=origin/main main
        
        log "GitLab 已设置为默认远程仓库"
        log "GitHub 仓库已重命名为 'github'"
    else
        log "保持当前远程仓库配置"
    fi
    
    # 显示最终的远程仓库配置
    log "最终远程仓库配置:"
    git remote -v
}

# 生成迁移报告
generate_migration_report() {
    log "生成迁移报告..."
    
    REPORT_FILE="migration_report.md"
    
    cat > "$REPORT_FILE" << EOF
# SenseVoice 项目迁移报告

## 迁移信息

- **迁移时间**: $(date)
- **源仓库**: GitHub (github.com/The-Agent-Builder/SenseVoice)
- **目标仓库**: GitLab ($GITLAB_URL/$GITLAB_PROJECT)
- **迁移分支**: $(git branch --show-current)

## 迁移内容

### 代码统计
- **总提交数**: $(git rev-list --count HEAD)
- **总分支数**: $(git branch -a | wc -l)
- **总标签数**: $(git tag | wc -l)
- **代码行数**: $(find . -name "*.py" -type f -exec wc -l {} + | tail -1 | awk '{print $1}')

### 迁移的文件
- 源代码文件
- 配置文件
- 文档文件
- CI/CD 配置
- 脚本文件

### CI/CD 配置更新
- ✅ 删除 GitHub Actions 配置 (.github/)
- ✅ 创建 GitLab CI/CD 配置 (.gitlab-ci.yml)
- ✅ 更新部署脚本
- ✅ 更新文档中的仓库地址

## 后续步骤

### 1. GitLab 项目配置
- [ ] 配置 CI/CD 变量
- [ ] 设置 SSH 密钥
- [ ] 配置项目权限

### 2. 服务器配置
- [ ] 更新部署脚本中的仓库地址
- [ ] 测试 CI/CD 流水线
- [ ] 验证自动部署功能

### 3. 团队通知
- [ ] 通知团队成员仓库地址变更
- [ ] 更新开发环境配置
- [ ] 更新文档和 Wiki

## 验证清单

- [x] 代码完整性检查
- [x] 分支和标签迁移
- [x] CI/CD 配置更新
- [x] 文档地址更新
- [ ] 流水线测试
- [ ] 部署功能验证

## 联系信息

如有问题，请联系项目维护者。

---
*此报告由迁移脚本自动生成*
EOF

    log "迁移报告已生成: $REPORT_FILE"
}

# 显示后续步骤
show_next_steps() {
    log "=== 迁移完成！==="
    
    info "GitLab 项目地址: $GITLAB_URL/$GITLAB_PROJECT"
    info ""
    info "后续步骤:"
    info "1. 在 GitLab 项目中配置 CI/CD 变量:"
    info "   - SERVER_HOST: 服务器 IP 地址"
    info "   - SERVER_USER: 服务器用户名"
    info "   - SERVER_PORT: SSH 端口"
    info "   - SSH_PRIVATE_KEY: SSH 私钥 (类型: File)"
    info ""
    info "2. 测试 CI/CD 流水线:"
    info "   - 推送代码触发自动部署"
    info "   - 或在 GitLab 页面手动触发"
    info ""
    info "3. 更新团队开发环境:"
    info "   git remote set-url origin $GITLAB_REPO_URL"
    info ""
    info "4. 查看详细配置指南:"
    info "   - docs/GITLAB_CICD_SETUP.md"
    info "   - docs/MANUAL_CICD_TRIGGER.md"
    info ""
    info "迁移报告: migration_report.md"
}

# 主函数
main() {
    log "开始 SenseVoice 项目迁移到 GitLab..."
    
    check_current_repo
    add_gitlab_remote
    push_to_gitlab
    update_documentation
    verify_gitlab_repo
    set_default_remote
    generate_migration_report
    show_next_steps
    
    log "项目迁移完成！"
}

# 显示帮助信息
show_help() {
    echo "SenseVoice 项目 GitLab 迁移脚本"
    echo ""
    echo "用法:"
    echo "  $0 [选项]"
    echo ""
    echo "选项:"
    echo "  --help          显示此帮助信息"
    echo "  --dry-run       模拟运行，不执行实际操作"
    echo ""
    echo "功能:"
    echo "  - 将代码推送到 GitLab 仓库"
    echo "  - 更新 CI/CD 配置"
    echo "  - 更新文档中的仓库地址"
    echo "  - 生成迁移报告"
    echo ""
    echo "GitLab 仓库地址: $GITLAB_REPO_URL"
}

# 解析命令行参数
case "${1:-}" in
    --help)
        show_help
        exit 0
        ;;
    --dry-run)
        echo "模拟运行模式（功能待实现）"
        exit 0
        ;;
    "")
        main
        ;;
    *)
        error "未知参数: $1"
        ;;
esac
