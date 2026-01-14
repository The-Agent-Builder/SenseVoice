# Set the device with environment, default is cuda:0
# export SENSEVOICE_DEVICE=cuda:1

import os, re
from fastapi import FastAPI, File, Form, UploadFile, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from typing_extensions import Annotated
from typing import List
from enum import Enum
import torchaudio
from funasr.utils.postprocess_utils import rich_transcription_postprocess
from io import BytesIO

# 导入新的模块
from config.settings import get_settings
from models.sense_voice_model import model_manager
from websocket.connection_manager import ConnectionManager
from websocket.streaming_handler import WebSocketStreamingHandler

TARGET_FS = 16000


class Language(str, Enum):
    auto = "auto"
    zh = "zh"
    en = "en"
    yue = "yue"
    ja = "ja"
    ko = "ko"
    nospeech = "nospeech"


# 初始化配置和模型
settings = get_settings()
# 根据配置决定是否在启动时加载流式模型（默认延迟加载以节省显存）
model_manager.initialize(load_streaming=settings.enable_streaming_on_startup)

# 获取模型
m, kwargs = model_manager.get_sense_voice_model()
regex = r"<\|.*\|>"

# 初始化FastAPI应用
app = FastAPI(
    title=settings.api_title,
    description=settings.api_description,
    version=settings.api_version
)

# 挂载静态文件
app.mount("/static", StaticFiles(directory="static"), name="static")

# 初始化WebSocket管理器
connection_manager = ConnectionManager()
ws_handler = WebSocketStreamingHandler(connection_manager)


@app.get("/", response_class=HTMLResponse)
async def root():
    return """
    <!DOCTYPE html>
    <html>
        <head>
            <meta charset=utf-8>
            <title>SenseVoice API</title>
            <style>
                body { font-family: Arial, sans-serif; margin: 40px; }
                .api-section { margin: 20px 0; padding: 20px; border: 1px solid #ddd; border-radius: 5px; }
                .endpoint { background-color: #f5f5f5; padding: 10px; margin: 10px 0; border-radius: 3px; }
                code { background-color: #f0f0f0; padding: 2px 4px; border-radius: 2px; }
            </style>
        </head>
        <body>
            <h1>SenseVoice API 服务</h1>

            <div class="api-section">
                <h2>HTTP 接口</h2>
                <div class="endpoint">
                    <strong>POST /api/v1/asr</strong><br>
                    上传音频文件进行语音识别
                </div>
                <p><a href='./docs'>查看完整API文档</a></p>
            </div>

            <div class="api-section">
                <h2>WebSocket 流式接口</h2>
                <div class="endpoint">
                    <strong>WS /ws/asr</strong><br>
                    实时语音识别WebSocket接口
                </div>
                <p>支持实时音频流处理，适用于语音对话、实时转录等场景。</p>
                <p><a href='/ws-test'>测试WebSocket接口</a></p>
            </div>

            <div class="api-section">
                <h2>支持的语言</h2>
                <p><code>auto</code>, <code>zh</code>, <code>en</code>, <code>yue</code>, <code>ja</code>, <code>ko</code>, <code>nospeech</code></p>
            </div>
        </body>
    </html>
    """


@app.get("/ws-test", response_class=HTMLResponse)
async def websocket_test():
    """WebSocket测试页面"""
    return FileResponse("static/ws_test.html")


@app.websocket("/ws/asr")
async def websocket_asr_endpoint(websocket: WebSocket):
    """WebSocket流式ASR端点"""
    await ws_handler.handle_websocket(websocket)


@app.get("/health")
async def health_check():
    """健康检查端点 - 用于 Docker 和负载均衡器"""
    try:
        # 基础健康检查
        if not model_manager.is_initialized():
            return {"status": "unhealthy", "reason": "model_not_initialized"}

        return {"status": "healthy"}
    except Exception as e:
        return {"status": "unhealthy", "reason": str(e)}


@app.get("/api/v1/status")
async def get_status():
    """获取详细服务状态"""
    return {
        "status": "running",
        "model_initialized": model_manager.is_initialized(),
        "has_streaming_model": model_manager.has_streaming_model(),
        "connections": connection_manager.get_connection_count(),
        "connection_stats": connection_manager.get_connection_stats(),
        "settings": {
            "device": settings.device,
            "model_dir": settings.model_dir,
            "target_sample_rate": settings.target_sample_rate
        }
    }


@app.post("/api/v1/asr")
async def turn_audio_to_text(
    files: Annotated[List[UploadFile], File(description="WebM audio files (recommended) or other audio formats in 16KHz")],
    keys: Annotated[str, Form(description="name of each audio joined with comma")] = None,
    lang: Annotated[Language, Form(description="language of audio content")] = "auto",
    chunk_size: Annotated[int, Form(description="chunk size in seconds for long audio processing, 0 to disable chunking")] = 60,
):
    import torch

    audios = []
    audio_durations = []

    for file in files:
        file_io = BytesIO(await file.read())
        data_or_path_or_list, audio_fs = torchaudio.load(file_io)

        # transform to target sample
        if audio_fs != TARGET_FS:
            resampler = torchaudio.transforms.Resample(orig_freq=audio_fs, new_freq=TARGET_FS)
            data_or_path_or_list = resampler(data_or_path_or_list)

        data_or_path_or_list = data_or_path_or_list.mean(0)
        audios.append(data_or_path_or_list)

        # 计算音频时长（秒）
        duration = len(data_or_path_or_list) / TARGET_FS
        audio_durations.append(duration)

    if lang == "":
        lang = "auto"

    if not keys:
        key = [f.filename for f in files]
    else:
        key = keys.split(",")

    # 处理每个音频文件
    all_results = []

    for audio, duration, audio_key in zip(audios, audio_durations, key):
        # 判断是否需要分块处理（音频时长超过chunk_size且chunk_size > 0）
        if chunk_size > 0 and duration > chunk_size:
            # 分块处理长音频
            result = await _process_long_audio_chunked(
                audio=audio,
                audio_key=audio_key,
                lang=lang,
                chunk_size=chunk_size,
                model=m,
                kwargs=kwargs
            )
        else:
            # 短音频直接处理
            result = await _process_short_audio(
                audio=audio,
                audio_key=audio_key,
                lang=lang,
                model=m,
                kwargs=kwargs
            )

        all_results.extend(result)

    return {"result": all_results}


async def _process_short_audio(audio, audio_key: str, lang: str, model, kwargs: dict):
    """处理短音频（不分块）"""
    import torch

    with torch.no_grad():
        res = model.inference(
            data_in=[audio],
            language=lang,
            use_itn=False,
            ban_emo_unk=False,
            key=[audio_key],
            fs=TARGET_FS,
            **kwargs,
        )

        # 清理显存
        if settings.device.startswith("cuda"):
            torch.cuda.empty_cache()

    if len(res) == 0:
        return []

    for it in res[0]:
        it["raw_text"] = it["text"]
        it["clean_text"] = re.sub(regex, "", it["text"], 0, re.MULTILINE)
        it["text"] = rich_transcription_postprocess(it["text"])

    return res[0]


async def _process_long_audio_chunked(audio, audio_key: str, lang: str, chunk_size: int, model, kwargs: dict):
    """分块处理长音频，并合并结果"""
    import torch
    import logging

    logger = logging.getLogger(__name__)

    total_samples = len(audio)
    total_duration = total_samples / TARGET_FS
    chunk_samples = chunk_size * TARGET_FS
    overlap_samples = int(settings.chunk_overlap * TARGET_FS)  # 使用配置的重叠时间

    chunk_raw_texts = []  # 存储每个块的原始文本
    chunk_clean_texts = []  # 存储每个块清理后的文本
    chunk_index = 0

    logger.info(f"长音频分块处理: 总时长={total_duration:.2f}s, 分块大小={chunk_size}s, 重叠={settings.chunk_overlap}s")

    start_pos = 0
    while start_pos < total_samples:
        end_pos = min(start_pos + chunk_samples, total_samples)

        # 提取音频块
        audio_chunk = audio[start_pos:end_pos]
        chunk_duration = len(audio_chunk) / TARGET_FS

        logger.info(f"处理音频块 {chunk_index + 1}: 起始={start_pos/TARGET_FS:.2f}s, "
                   f"结束={end_pos/TARGET_FS:.2f}s, 时长={chunk_duration:.2f}s")

        # 使用 torch.no_grad() 禁用梯度计算
        with torch.no_grad():
            try:
                chunk_key = f"{audio_key}_chunk_{chunk_index}"
                res = model.inference(
                    data_in=[audio_chunk],
                    language=lang,
                    use_itn=False,
                    ban_emo_unk=False,
                    key=[chunk_key],
                    fs=TARGET_FS,
                    **kwargs,
                )

                # 立即清理显存
                if settings.device.startswith("cuda"):
                    torch.cuda.empty_cache()

                if len(res) > 0 and len(res[0]) > 0:
                    # 提取原始文本内容（未经过后处理的）
                    chunk_text = res[0][0].get("text", "")
                    chunk_raw_texts.append(chunk_text)

                    # 对每个块单独清理标记
                    chunk_clean = re.sub(regex, "", chunk_text, 0, re.MULTILINE)
                    chunk_clean_texts.append(chunk_clean)

                    # logger.info(f"音频块 {chunk_index + 1} 处理完成，识别文本: {chunk_clean[:50]}...")

            except Exception as e:
                logger.error(f"音频块 {chunk_index + 1} 处理失败: {e}")
                # 继续处理下一块

        # 移动到下一块（考虑重叠）
        if end_pos >= total_samples:
            break

        start_pos = end_pos - overlap_samples
        chunk_index += 1

    logger.info(f"长音频分块处理完成，共处理 {chunk_index + 1} 个音频块，正在合并结果...")
    # logger.info(f"收集到的原始文本块数量: {len(chunk_raw_texts)}")

    # 合并原始文本（包含标记）
    merged_raw_text = "".join(chunk_raw_texts)
    logger.info(f"合并后的原始文本长度: {len(merged_raw_text)} 字符")

    # 合并清理后的文本（已去除标记）
    merged_clean_text = "".join(chunk_clean_texts)
    logger.info(f"合并后的清理文本长度: {len(merged_clean_text)} 字符")

    # 构造与短音频相同格式的返回结果
    result = {
        "key": audio_key,
        "text": rich_transcription_postprocess(merged_raw_text),
        "raw_text": merged_raw_text,
        "clean_text": merged_clean_text
    }

    return [result]


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=50000)
