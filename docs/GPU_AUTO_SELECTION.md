# GPU 自动选择功能说明

## 概述

SenseVoice 现在支持自动选择显存最空闲的 GPU，避免在多 GPU 环境中因显存不足导致模型加载失败。

## 问题背景

在多 GPU 服务器上，如果多个进程同时使用 GPU，可能会出现以下问题：
- 默认使用 GPU 0，但 GPU 0 显存可能已被其他进程占满
- 导致模型加载失败，报错 `CUDA out of memory`
- 而其他 GPU 可能有充足的空闲显存

## 解决方案

### 1. 自动 GPU 选择（推荐）

系统会自动检测所有 GPU 的显存使用情况，并选择显存最空闲的 GPU：

```bash
# 不设置任何环境变量，系统自动选择
python main.py
```

**输出示例：**
```
检测到 8 个CUDA设备，使用GPU加速
正在检测GPU显存使用情况...
  GPU 0 (NVIDIA GeForce RTX 4090): 总显存 23.69GB, 已用 21.23GB, 空闲 2.46GB
  GPU 1 (NVIDIA GeForce RTX 4090): 总显存 23.69GB, 已用 0.23GB, 空闲 23.46GB
  GPU 2 (NVIDIA GeForce RTX 4090): 总显存 23.69GB, 已用 15.42GB, 空闲 8.27GB
  ...
自动选择显存空闲最多的GPU: cuda:1 (空闲 23.46GB)
```

### 2. 手动指定 GPU

如果需要使用特定的 GPU，可以通过环境变量指定：

```bash
# 使用 GPU 1
export SENSEVOICE_DEVICE=cuda:1
python main.py

# 或者一行命令
SENSEVOICE_DEVICE=cuda:1 python main.py
```

### 3. 使用 CPU

在显存不足或测试环境下，可以使用 CPU 模式：

```bash
export SENSEVOICE_DEVICE=cpu
python main.py
```

## GPU 显存检查工具

我们提供了一个便捷的工具来查看 GPU 显存使用情况：

```bash
python scripts/check_gpu_memory.py
```

**输出示例：**
```
🔍 GPU 显存检查工具
================================================================================
✅ 检测到 8 个 GPU 设备

📊 GPU 显存使用情况:
--------------------------------------------------------------------------------
🔴 GPU 0: NVIDIA GeForce RTX 4090
   总显存:   23.69 GB
   已使用:   21.23 GB
   可用:     2.46 GB
   使用率:   89.6%
   占用进程: 3 个
      - PID 1863729: 20.55 GB
      - PID 1004031: 1.12 GB
      - PID 1003902: 828.00 MB

🟢 GPU 1: NVIDIA GeForce RTX 4090
   总显存:   23.69 GB
   已使用:   0.23 GB
   可用:     23.46 GB
   使用率:   1.0%
   占用进程: 0 个

...

💡 推荐使用 GPU 1 (显存使用率最低)
   环境变量设置: export SENSEVOICE_DEVICE=cuda:1
```

## 依赖安装

为了获取更准确的 GPU 显存信息（包括其他进程占用），建议安装 `pynvml` 库：

```bash
pip install pynvml
```

如果不安装 `pynvml`：
- 系统仍可运行，但只能看到当前进程的显存使用
- 无法准确检测其他进程占用的显存
- 可能选择到被其他进程占用的 GPU

## 环境变量说明

| 环境变量 | 说明 | 默认值 | 示例 |
|---------|------|--------|------|
| `SENSEVOICE_DEVICE` | 指定设备 | `auto` | `cuda:0`, `cuda:1`, `cpu`, `auto` |
| `SENSEVOICE_HOST` | 服务监听地址 | `0.0.0.0` | `0.0.0.0`, `127.0.0.1` |
| `SENSEVOICE_PORT` | 服务端口 | `50000` | `50000`, `8000` |

### SENSEVOICE_DEVICE 选项

- `auto`（默认）：自动选择显存最空闲的 GPU
- `cuda`：自动选择显存最空闲的 GPU（同 `auto`）
- `cuda:N`：使用指定的 GPU（N 为 GPU 编号）
- `cpu`：使用 CPU 模式

## 常见问题

### Q1: 为什么报错 "CUDA out of memory"？

**原因：** GPU 显存不足，可能被其他进程占用。

**解决方案：**
1. 运行 `python scripts/check_gpu_memory.py` 查看显存使用情况
2. 使用自动选择功能（默认已启用）
3. 手动指定空闲的 GPU：`export SENSEVOICE_DEVICE=cuda:N`
4. 释放其他进程占用的显存：`kill -9 <PID>`
5. 使用 CPU 模式：`export SENSEVOICE_DEVICE=cpu`

### Q2: 如何查看哪些进程在使用 GPU？

```bash
# 方法 1：使用我们的工具
python scripts/check_gpu_memory.py

# 方法 2：使用 nvidia-smi
nvidia-smi

# 方法 3：持续监控
watch -n 1 nvidia-smi
```

### Q3: 如何释放 GPU 显存？

```bash
# 1. 找到占用 GPU 的进程
nvidia-smi

# 2. 杀死特定进程
kill -9 <PID>

# 3. 清理 PyTorch 缓存（在 Python 中运行）
python -c "import torch; torch.cuda.empty_cache()"
```

### Q4: pynvml 库的作用是什么？

`pynvml` 是 NVIDIA Management Library 的 Python 绑定，它可以：
- 获取所有进程的 GPU 显存使用情况（不只是当前进程）
- 获取更准确的显存信息
- 列出占用 GPU 的进程 PID 和显存使用量

**不安装 pynvml 的影响：**
- 系统会回退到 PyTorch API
- 只能看到当前进程的显存使用
- 自动选择可能不准确

### Q5: 我的服务器有 8 个 GPU，如何让不同服务使用不同 GPU？

**方案 1：手动分配**
```bash
# 服务 1 使用 GPU 0
SENSEVOICE_DEVICE=cuda:0 SENSEVOICE_PORT=50000 python main.py &

# 服务 2 使用 GPU 1
SENSEVOICE_DEVICE=cuda:1 SENSEVOICE_PORT=50001 python main.py &
```

**方案 2：自动选择（推荐）**
```bash
# 每个服务自动选择空闲 GPU
SENSEVOICE_PORT=50000 python main.py &
SENSEVOICE_PORT=50001 python main.py &
SENSEVOICE_PORT=50002 python main.py &
```

## 技术细节

### GPU 选择算法

1. 使用 `pynvml` 获取所有 GPU 的显存信息（如果可用）
2. 计算每个 GPU 的空闲显存
3. 选择空闲显存最多的 GPU
4. 如果空闲显存 < 2GB，发出警告但仍尝试使用

### 显存管理策略

- 限制使用 80% 的 GPU 显存（通过 `torch.cuda.memory.set_per_process_memory_fraction(0.8)`）
- 启动前清理显存缓存
- 自动垃圾回收

## 相关文档

- [GPU 内存管理](GPU_MEMORY_MANAGEMENT.md)
- [GPU 部署指南](../GPU_DEPLOYMENT.md)

## 更新日志

- **2025-10-28**: 添加自动 GPU 选择功能
- **2025-10-28**: 添加 pynvml 支持以获取准确的显存信息
- **2025-10-28**: 更新 GPU 显存检查工具

