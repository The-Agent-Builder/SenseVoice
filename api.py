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
):
    audios = []
    for file in files:
        file_io = BytesIO(await file.read())
        data_or_path_or_list, audio_fs = torchaudio.load(file_io)

        # transform to target sample
        if audio_fs != TARGET_FS:
            resampler = torchaudio.transforms.Resample(orig_freq=audio_fs, new_freq=TARGET_FS)
            data_or_path_or_list = resampler(data_or_path_or_list)

        data_or_path_or_list = data_or_path_or_list.mean(0)
        audios.append(data_or_path_or_list)

    if lang == "":
        lang = "auto"

    if not keys:
        key = [f.filename for f in files]
    else:
        key = keys.split(",")

    res = m.inference(
        data_in=audios,
        language=lang,  # "zh", "en", "yue", "ja", "ko", "nospeech"
        use_itn=False,  # 关闭逆文本标准化，保留原始标记
        ban_emo_unk=False,  # 允许情感标记输出
        key=key,
        fs=TARGET_FS,
        **kwargs,
    )
    if len(res) == 0:
        return {"result": []}
    for it in res[0]:
        it["raw_text"] = it["text"]
        it["clean_text"] = re.sub(regex, "", it["text"], 0, re.MULTILINE)
        it["text"] = rich_transcription_postprocess(it["text"])
    return {"result": res[0]}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=50000)
