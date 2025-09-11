# 🚀 SenseVoice GPU 显存管理指南

本文档详细说明如何在多GPU服务器上管理显存，避免显存不足的问题。

## 🔍 问题诊断

### 常见显存问题

1. **启动时显存不足**: `CUDA error: out of memory`
2. **模型加载失败**: 显存被其他进程占用
3. **性能下降**: GPU显存碎片化

### 快速检查显存状态

```bash
# 方法1: 使用我们的检查脚本 (推荐)
python scripts/check_gpu_memory.py

# 方法2: 使用 nvidia-smi
nvidia-smi

# 方法3: 使用 PyTorch 检查
python -c "import torch; print(f'GPU数量: {torch.cuda.device_count()}'); [print(f'GPU {i}: {torch.cuda.get_device_properties(i).name}') for i in range(torch.cuda.device_count())]"
```

## 🛠️ 解决方案

### 1. 使用智能启动脚本 (推荐)

```bash
# 自动选择最佳GPU并启动
./scripts/start_sensevoice.sh --auto

# 指定特定GPU
./scripts/start_sensevoice.sh --device=cuda:4 --auto

# 使用CPU模式
./scripts/start_sensevoice.sh --device=cpu --auto
```

### 2. 手动指定GPU设备

```bash
# 方法1: 环境变量
export SENSEVOICE_DEVICE=cuda:4
python main.py

# 方法2: .env 文件
echo "SENSEVOICE_DEVICE=cuda:4" > .env
python main.py
```

### 3. 清理显存

```bash
# 清理PyTorch显存缓存
python -c "import torch; torch.cuda.empty_cache(); print('显存缓存已清理')"

# 杀死占用显存的进程
nvidia-smi  # 查看进程PID
kill -9 <PID>  # 替换为实际PID

# 重启CUDA服务 (谨慎使用)
sudo systemctl restart nvidia-persistenced
```

## 📊 GPU选择策略

### 自动选择逻辑

1. **检查所有GPU**: 扫描所有可用的CUDA设备
2. **计算显存使用率**: `(已保留显存 / 总显存) * 100%`
3. **选择最空闲GPU**: 显存使用率最低的设备
4. **验证可用性**: 确保设备可以正常初始化

### 手动选择建议

根据您的服务器配置：

```bash
# 8个RTX 4090的服务器
# GPU 0-3: 通常被其他任务占用
# GPU 4-7: 相对空闲，推荐使用

# 推荐配置
export SENSEVOICE_DEVICE=cuda:4  # 或 cuda:5, cuda:6, cuda:7
```

## ⚙️ 显存优化配置

### 1. 环境变量优化

```bash
# 限制显存分配
export PYTORCH_CUDA_ALLOC_CONF="max_split_size_mb:512"

# 启用显存回收
export CUDA_LAUNCH_BLOCKING=0

# 设置显存分配策略
export CUDA_MEMORY_FRACTION=0.8  # 使用80%显存
```

### 2. 代码级优化

我们已经在代码中实现了以下优化：

- **显存分配限制**: 限制使用80%显存
- **自动清理缓存**: 启动前清理显存
- **设备绑定**: 强制绑定到指定GPU
- **内存回收**: 启用垃圾回收机制

## 🔧 故障排除

### 问题1: 启动时显存不足

**症状**: `CUDA error: out of memory`

**解决方案**:
```bash
# 1. 检查显存使用
python scripts/check_gpu_memory.py

# 2. 选择空闲GPU
export SENSEVOICE_DEVICE=cuda:4  # 替换为空闲GPU

# 3. 清理显存
python -c "import torch; torch.cuda.empty_cache()"

# 4. 重新启动
python main.py
```

### 问题2: 模型初始化失败

**症状**: `RuntimeError: 模型未初始化`

**解决方案**:
```bash
# 1. 检查设备配置
echo $SENSEVOICE_DEVICE

# 2. 验证GPU可用性
python -c "import torch; print(torch.cuda.is_available()); print(torch.cuda.device_count())"

# 3. 使用CPU模式测试
export SENSEVOICE_DEVICE=cpu
python main.py
```

### 问题3: 性能下降

**症状**: 推理速度慢，显存碎片化

**解决方案**:
```bash
# 1. 重启服务清理显存
pkill -f "python main.py"
python -c "import torch; torch.cuda.empty_cache()"
python main.py

# 2. 调整显存分配策略
export PYTORCH_CUDA_ALLOC_CONF="max_split_size_mb:256"

# 3. 使用专用GPU
export SENSEVOICE_DEVICE=cuda:7  # 使用最后一个GPU
```

## 📋 最佳实践

### 1. 生产环境配置

```bash
# .env 文件配置
SENSEVOICE_DEVICE=cuda:4
SENSEVOICE_HOST=0.0.0.0
SENSEVOICE_PORT=50000
SENSEVOICE_LOG_LEVEL=INFO

# 系统环境变量
export PYTORCH_CUDA_ALLOC_CONF="max_split_size_mb:512"
export CUDA_LAUNCH_BLOCKING=0
```

### 2. 多服务部署

如果在同一台服务器上部署多个SenseVoice实例：

```bash
# 实例1: 使用GPU 4
export SENSEVOICE_DEVICE=cuda:4
export SENSEVOICE_PORT=50000

# 实例2: 使用GPU 5  
export SENSEVOICE_DEVICE=cuda:5
export SENSEVOICE_PORT=50001

# 实例3: 使用GPU 6
export SENSEVOICE_DEVICE=cuda:6
export SENSEVOICE_PORT=50002
```

### 3. 监控脚本

创建定期监控脚本：

```bash
#!/bin/bash
# monitor_gpu.sh

while true; do
    echo "=== $(date) ==="
    python scripts/check_gpu_memory.py
    echo ""
    sleep 300  # 每5分钟检查一次
done
```

## 🚀 快速启动指南

### 新服务器首次部署

```bash
# 1. 检查GPU状态
python scripts/check_gpu_memory.py

# 2. 选择推荐的GPU
export SENSEVOICE_DEVICE=cuda:4  # 替换为推荐的GPU

# 3. 启动服务
./scripts/start_sensevoice.sh --auto
```

### 日常运维

```bash
# 检查服务状态
curl http://localhost:50000/health

# 查看显存使用
python scripts/check_gpu_memory.py

# 重启服务
pkill -f "python main.py"
./scripts/start_sensevoice.sh --auto
```

## 📞 获取帮助

如果遇到显存相关问题：

1. **运行诊断脚本**: `python scripts/check_gpu_memory.py`
2. **查看详细日志**: 检查启动日志中的错误信息
3. **尝试CPU模式**: `export SENSEVOICE_DEVICE=cpu`
4. **提交Issue**: 附上GPU状态和错误日志

---

💡 **提示**: 在多GPU服务器上，建议为SenseVoice专门分配1-2个GPU，避免与其他任务竞争显存资源。
