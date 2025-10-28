# GPU 显存问题排查指南

## 常见问题

### 1. CUDA Out of Memory (显存碎片化)

#### 错误信息
```
torch.OutOfMemoryError: CUDA out of memory. Tried to allocate 120.00 MiB. GPU 4 has a total capacity of 23.53 GiB of which 4.33 GiB is free. Including non-PyTorch memory, this process has 19.19 GiB memory in use.
...
If reserved but unallocated memory is large try setting PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True to avoid fragmentation.
```

#### 原因分析
- GPU显存碎片化导致无法分配连续的内存块
- 虽然有足够的空闲显存，但由于碎片化，无法分配所需的连续空间
- 这在加载多个模型（SenseVoice + VAD模型）时尤其常见

#### 解决方案

**方案1：自动修复（推荐）**

代码已经更新，会自动启用显存碎片化优化。直接重启服务即可：

```bash
python3 main.py
```

**方案2：手动设置环境变量**

如果自动修复不生效，手动设置环境变量：

```bash
export PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True
python3 main.py
```

**方案3：清理显存后重启**

```bash
# 查找占用GPU的进程
nvidia-smi

# 杀死相关进程（谨慎操作）
kill -9 <PID>

# 或者使用脚本清理
python3 -c "import torch; torch.cuda.empty_cache()"

# 重启服务
export PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True
python3 main.py
```

**方案4：选择其他GPU**

如果某个GPU显存使用较多，手动指定显存更充足的GPU：

```bash
# 查看所有GPU状态
nvidia-smi

# 指定使用GPU 5（根据实际情况选择）
export SENSEVOICE_DEVICE=cuda:5
python3 main.py
```

**方案5：降低显存使用（如果上述方案都不行）**

修改 `config/settings.py` 或设置环境变量：

```bash
# 限制批处理大小（如果支持）
export SENSEVOICE_BATCH_SIZE=1

# 使用混合精度
export SENSEVOICE_USE_FP16=true
```

### 2. GPU被其他进程占用

#### 症状
- 所有GPU显存都被占用
- 自动选择的GPU仍然显存不足

#### 解决方案

**查看GPU占用情况：**
```bash
nvidia-smi
# 或者更详细的信息
watch -n 1 nvidia-smi
```

**选项1：等待其他任务完成**

**选项2：手动指定空闲GPU**
```bash
export SENSEVOICE_DEVICE=cuda:N  # N为空闲GPU编号
python3 main.py
```

**选项3：使用CPU模式（不推荐，性能较差）**
```bash
export SENSEVOICE_DEVICE=cpu
python3 main.py
```

### 3. 多GPU服务器上的最佳实践

#### 启动前检查
```bash
# 安装检查工具
pip3 install pynvml

# 运行显存检查脚本
python3 scripts/check_gpu_memory.py
```

#### 自动GPU选择
服务会自动选择显存空闲最多的GPU。如果需要手动控制：

```bash
# 方式1：指定特定GPU
export SENSEVOICE_DEVICE=cuda:4
python3 main.py

# 方式2：使用CUDA_VISIBLE_DEVICES隐藏某些GPU
export CUDA_VISIBLE_DEVICES=4,5,6,7  # 只让服务看到这4个GPU
export SENSEVOICE_DEVICE=auto        # 从可见GPU中自动选择
python3 main.py
```

## Docker 环境中的显存管理

### Dockerfile 配置

确保 Dockerfile 中包含显存优化配置：

```dockerfile
# 设置CUDA内存分配配置
ENV PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True

# 其他优化
ENV CUDA_LAUNCH_BLOCKING=0
ENV TORCH_CUDNN_V8_API_ENABLED=1
```

### Docker Compose 配置

```yaml
services:
  sensevoice:
    environment:
      - PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True
      - SENSEVOICE_DEVICE=auto
    deploy:
      resources:
        reservations:
          devices:
            - driver: nvidia
              device_ids: ['0']  # 或 ['all'] 使用所有GPU
              capabilities: [gpu]
```

### 启动容器

```bash
# 指定GPU
docker run --gpus '"device=4"' \
  -e PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True \
  sensevoice:latest

# 使用所有GPU
docker run --gpus all \
  -e SENSEVOICE_DEVICE=auto \
  -e PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True \
  sensevoice:latest
```

## 性能优化建议

### 1. 显存监控

创建显存监控脚本：

```python
# scripts/monitor_gpu.py
import time
import torch

while True:
    if torch.cuda.is_available():
        for i in range(torch.cuda.device_count()):
            allocated = torch.cuda.memory_allocated(i) / 1024**3
            reserved = torch.cuda.memory_reserved(i) / 1024**3
            total = torch.cuda.get_device_properties(i).total_memory / 1024**3
            print(f"GPU {i}: {allocated:.2f}GB / {reserved:.2f}GB / {total:.2f}GB")
    time.sleep(5)
```

### 2. 定期清理

在请求处理后清理缓存（如果内存紧张）：

```python
# 在 api.py 中添加
import torch
import gc

@app.middleware("http")
async def cleanup_middleware(request, call_next):
    response = await call_next(request)
    if torch.cuda.is_available():
        torch.cuda.empty_cache()
        gc.collect()
    return response
```

### 3. 预热模型

首次请求可能触发额外的显存分配。建议启动后进行预热：

```bash
# 启动服务后
curl -X POST http://localhost:50000/api/v1/asr \
  -F "audio=@test.wav" \
  -F "language=auto"
```

## 环境变量参考

| 变量名 | 默认值 | 说明 |
|--------|--------|------|
| `PYTORCH_CUDA_ALLOC_CONF` | `expandable_segments:True` | CUDA内存分配策略 |
| `SENSEVOICE_DEVICE` | `auto` | 设备选择：auto/cpu/cuda/cuda:N |
| `CUDA_VISIBLE_DEVICES` | 未设置 | 限制可见的GPU |
| `CUDA_LAUNCH_BLOCKING` | `0` | 是否同步CUDA操作 |

## 故障排查流程

1. **检查GPU状态**
   ```bash
   nvidia-smi
   python3 scripts/check_gpu_memory.py
   ```

2. **确认环境变量**
   ```bash
   echo $PYTORCH_CUDA_ALLOC_CONF
   echo $SENSEVOICE_DEVICE
   ```

3. **尝试不同GPU**
   ```bash
   export SENSEVOICE_DEVICE=cuda:N
   python3 main.py
   ```

4. **检查日志**
   查看启动日志中的显存信息：
   ```
   自动选择显存空闲最多的GPU: cuda:4 (空闲 23.52GB)
   设置显存使用上限为 95.0%
   显存管理设置完成（已启用expandable_segments避免碎片化）
   ```

5. **如果问题持续**
   - 检查是否有其他进程占用GPU
   - 考虑使用CPU模式（临时方案）
   - 联系系统管理员检查GPU硬件状态

## 参考资料

- [PyTorch CUDA Memory Management](https://pytorch.org/docs/stable/notes/cuda.html#environment-variables)
- [NVIDIA GPU Memory Allocation](https://docs.nvidia.com/cuda/cuda-c-programming-guide/index.html#memory-management)
- [FunASR GPU Configuration](https://github.com/alibaba-damo-academy/FunASR)

