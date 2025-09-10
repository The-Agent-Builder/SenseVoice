#!/usr/bin/env python3
"""
SenseVoice API 服务启动入口
"""
import logging
import os
import uvicorn

# 加载 .env 文件
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    # python-dotenv 未安装时忽略
    pass

from config.settings import get_settings

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def main():
    """启动应用"""
    settings = get_settings()
    
    logger.info("正在启动SenseVoice API服务...")
    logger.info(f"设备: {settings.device}")
    logger.info(f"模型目录: {settings.model_dir}")
    logger.info(f"监听地址: {settings.host}:{settings.port}")
    
    # 显示详细的设备信息
    device_info = settings.get_device_info()
    logger.info("="*50)
    logger.info("设备配置信息:")
    logger.info(f"  选择的设备: {device_info['device']}")
    
    if device_info['device'] == 'cuda':
        logger.info(f"  CUDA版本: {device_info.get('cuda_version', 'N/A')}")
        logger.info(f"  GPU数量: {device_info.get('gpu_count', 0)}")
        for i, gpu_name in enumerate(device_info.get('gpu_names', [])):
            logger.info(f"  GPU {i}: {gpu_name}")
        logger.info(f"  显存已分配: {device_info.get('memory_allocated', '0MB')}")
        logger.info(f"  显存已保留: {device_info.get('memory_reserved', '0MB')}")
    elif device_info['device'] == 'mps':
        logger.info(f"  MPS可用: {device_info.get('mps_available', False)}")
        logger.info(f"  MPS已构建: {device_info.get('mps_built', False)}")
    elif device_info['device'] == 'cpu':
        logger.info("  使用CPU进行推理")
    
    if 'error' in device_info:
        logger.warning(f"  设备信息获取异常: {device_info['error']}")
    
    logger.info("="*50)
    logger.info("环境变量配置:")
    logger.info(f"  SENSEVOICE_DEVICE: {os.getenv('SENSEVOICE_DEVICE', 'auto (默认)')}")
    logger.info(f"  SENSEVOICE_HOST: {settings.host}")
    logger.info(f"  SENSEVOICE_PORT: {settings.port}")
    logger.info(f"  SENSEVOICE_LOG_LEVEL: {settings.log_level}")
    logger.info("="*50)
    
    # 启动服务
    uvicorn.run(
        "api:app",
        host=settings.host,
        port=settings.port,
        log_level=settings.log_level.lower(),
        reload=False,  # 生产环境建议关闭
        access_log=True
    )


if __name__ == "__main__":
    main()
