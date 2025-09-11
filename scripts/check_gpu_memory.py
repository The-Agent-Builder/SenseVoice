#!/usr/bin/env python3
"""
GPU 显存检查脚本
用于检查各个 GPU 的显存使用情况，帮助选择合适的 GPU 设备
"""

import torch
import subprocess
import sys
from typing import List, Dict, Tuple


def get_gpu_memory_info() -> List[Dict]:
    """获取所有GPU的显存信息"""
    if not torch.cuda.is_available():
        print("❌ CUDA 不可用")
        return []
    
    gpu_count = torch.cuda.device_count()
    gpu_info = []
    
    for i in range(gpu_count):
        try:
            # 获取GPU属性
            props = torch.cuda.get_device_properties(i)
            
            # 获取显存使用情况
            torch.cuda.set_device(i)
            memory_allocated = torch.cuda.memory_allocated(i)
            memory_reserved = torch.cuda.memory_reserved(i)
            memory_total = props.total_memory
            memory_free = memory_total - memory_reserved
            
            gpu_info.append({
                'id': i,
                'name': props.name,
                'total_memory': memory_total,
                'allocated_memory': memory_allocated,
                'reserved_memory': memory_reserved,
                'free_memory': memory_free,
                'utilization_percent': (memory_reserved / memory_total) * 100
            })
            
        except Exception as e:
            print(f"❌ 获取 GPU {i} 信息失败: {e}")
            
    return gpu_info


def get_nvidia_smi_info() -> str:
    """获取 nvidia-smi 输出"""
    try:
        result = subprocess.run(['nvidia-smi'], capture_output=True, text=True)
        return result.stdout
    except Exception as e:
        return f"❌ 无法运行 nvidia-smi: {e}"


def format_memory(bytes_value: int) -> str:
    """格式化内存大小"""
    for unit in ['B', 'KB', 'MB', 'GB']:
        if bytes_value < 1024.0:
            return f"{bytes_value:.1f} {unit}"
        bytes_value /= 1024.0
    return f"{bytes_value:.1f} TB"


def recommend_gpu(gpu_info: List[Dict]) -> int:
    """推荐最适合的GPU"""
    if not gpu_info:
        return -1
    
    # 选择显存使用率最低的GPU
    best_gpu = min(gpu_info, key=lambda x: x['utilization_percent'])
    return best_gpu['id']


def main():
    print("🔍 GPU 显存检查工具")
    print("=" * 60)
    
    # 检查CUDA可用性
    if not torch.cuda.is_available():
        print("❌ CUDA 不可用，请检查：")
        print("   1. NVIDIA 驱动是否正确安装")
        print("   2. PyTorch 是否支持 CUDA")
        print("   3. CUDA 版本是否兼容")
        sys.exit(1)
    
    # 获取GPU信息
    gpu_info = get_gpu_memory_info()
    
    if not gpu_info:
        print("❌ 无法获取 GPU 信息")
        sys.exit(1)
    
    print(f"✅ 检测到 {len(gpu_info)} 个 GPU 设备")
    print()
    
    # 显示详细信息
    print("📊 GPU 显存使用情况:")
    print("-" * 60)
    
    for gpu in gpu_info:
        status_icon = "🟢" if gpu['utilization_percent'] < 10 else "🟡" if gpu['utilization_percent'] < 50 else "🔴"
        
        print(f"{status_icon} GPU {gpu['id']}: {gpu['name']}")
        print(f"   总显存:   {format_memory(gpu['total_memory'])}")
        print(f"   已分配:   {format_memory(gpu['allocated_memory'])}")
        print(f"   已保留:   {format_memory(gpu['reserved_memory'])}")
        print(f"   可用:     {format_memory(gpu['free_memory'])}")
        print(f"   使用率:   {gpu['utilization_percent']:.1f}%")
        print()
    
    # 推荐GPU
    recommended_gpu = recommend_gpu(gpu_info)
    if recommended_gpu >= 0:
        print(f"💡 推荐使用 GPU {recommended_gpu} (显存使用率最低)")
        print(f"   环境变量设置: export SENSEVOICE_DEVICE=cuda:{recommended_gpu}")
        print()
    
    # 显示nvidia-smi输出
    print("📋 nvidia-smi 输出:")
    print("-" * 60)
    nvidia_smi_output = get_nvidia_smi_info()
    print(nvidia_smi_output)
    
    # 提供使用建议
    print("💡 使用建议:")
    print("-" * 60)
    
    free_gpus = [gpu for gpu in gpu_info if gpu['utilization_percent'] < 10]
    if free_gpus:
        print("✅ 可用的空闲 GPU:")
        for gpu in free_gpus:
            print(f"   - GPU {gpu['id']}: {gpu['name']} (使用率: {gpu['utilization_percent']:.1f}%)")
        print()
        print("🚀 启动命令示例:")
        best_gpu = free_gpus[0]['id']
        print(f"   export SENSEVOICE_DEVICE=cuda:{best_gpu}")
        print(f"   python main.py")
    else:
        print("⚠️  所有 GPU 都有较高的显存使用率")
        print("   建议:")
        print("   1. 释放其他进程占用的显存")
        print("   2. 使用显存使用率最低的 GPU")
        print("   3. 考虑使用 CPU 模式: export SENSEVOICE_DEVICE=cpu")
    
    print()
    print("🔧 显存管理命令:")
    print("   清理显存缓存: python -c \"import torch; torch.cuda.empty_cache()\"")
    print("   查看进程: nvidia-smi")
    print("   杀死进程: kill -9 <PID>")


if __name__ == "__main__":
    main()
