## **生产级实时 ASR 系统设计与代码解析**

### 1. 概述

在生产环境中，实时语音识别系统通常采用客户端-服务器（Client/Server）架构。客户端负责采集音频并将其以流式数据发送给服务器；服务器则部署了高性能的 ASR 模型，对接收到的音频流进行实时处理，并将识别结果（中间结果和最终结果）返回给客户端。

这种架构的核心在于**低延迟的双向通信**，通常使用 **WebSocket** 或 **gRPC** 协议来实现。

*   **客户端 (Client)**：网页、手机 App、桌面应用或任何可以访问麦克风的设备。
*   **服务器端 (Server)**：运行 `funasr` 或其他 ASR 引擎的后端服务。

### 2. 系统核心架构

#### **A. 客户端职责**

客户端的核心任务是成为一个高效的“音频搬运工”。

1.  **音频采集**：通过浏览器 `navigator.mediaDevices.getUserMedia` API 或移动端原生 API 访问麦克风，获取原始音频数据（PCM 格式）。
2.  **音频分片 (Chunking)**：将连续的音频流按照固定的时间间隔（如 100ms - 200ms）切分成小数据块（Audio Chunk）。这个 `chunk_size` 需要与服务器的处理能力和模型要求相匹配。
3.  **数据发送**：建立与服务器的 WebSocket 连接，并通过该连接持续不断地发送音频块。
4.  **会话控制**：
    *   **开始信号**：在用户开始说话时，向服务器发送一个开始指令。
    *   **结束信号**：在用户明确结束说话（如点击停止按钮、松开“按住说话”按钮）时，向服务器发送一个明确的结束指令。这是触发 `is_final` 的一种重要方式。
5.  **结果接收与展示**：监听从服务器返回的消息，实时地将中间识别结果和最终识别结果展示在界面上。

#### **B. 服务器端职责**

服务器是整个系统的大脑，负责所有复杂的计算和状态管理。

1.  **连接管理**：为每一个客户端连接创建一个独立的会话（Session）。
2.  **状态维护**：为每个会话维护一个独立的 `cache`。这个 `cache` 用于存储模型的上下文状态，确保跨越多个音频块的语音识别是连贯的。**在多用户并发场景下，为每个连接隔离 `cache` 是至关重要的。**
3.  **音频处理与识别**：
    *   接收客户端发来的音频块。
    *   调用 `model.generate` 方法，传入当前音频块和该会话专属的 `cache`。
    *   根据返回结果，生成中间识别文本。
4.  **`is_final` 的智能判断（核心）**：
    *   **被动模式 (Client-Driven)**：接收到客户端发送的“结束信号”，将 `is_final` 设为 `True`，执行最后一次识别，并返回最终结果。
    *   **主动模式 (VAD-Driven)**：在服务器内部集成 VAD（语音活动检测）逻辑。当服务器连续接收到一段静音（例如超过700毫秒）时，系统会自动判断一句话已经结束，主动将 `is_final` 设为 `True`，并返回最终结果。这是实现自然对话体验的关键。
    *   **连接断开**：如果 WebSocket 连接异常断开，也视为一次会话的结束，进行最后的处理。
5.  **结果发送**：将带有状态（是否为最终结果）的识别结果通过 WebSocket 发送回对应的客户端。

### 3. 核心代码实现（概念示例）

下面的代码是生产环境的逻辑示意，而非可直接运行的完整项目。

#### **服务器端 (Python, 使用 `websockets` 库)**

```python
import asyncio
import websockets
from funasr import AutoModel

# 1. 全局加载模型（或按需加载）
# 在生产中，模型应作为单例加载，避免重复载入内存
model = AutoModel(model="iic/SenseVoiceSmall", model_revision="v2.0.4")

# VAD 静音超时配置 (毫秒)
VAD_TIMEOUT_MS = 800

async def asr_session(websocket, path):
    """
    为每一个客户端连接创建一个独立的处理会话
    """
    print("客户端已连接...")
    # 2. 为每个连接创建独立的状态 cache
    cache = {}
    last_speech_time = asyncio.get_event_loop().time()

    try:
        # 持续监听客户端消息
        async for message in websocket:
            # 检查是否是客户端发送的结束信号（JSON格式）
            if isinstance(message, str) and "end_signal" in message:
                print("收到客户端结束信号")
                is_final = True
            else:
                # 接收到的是音频二进制数据
                speech_chunk = message # 假设客户端直接发送 PCM 二进制数据
                is_final = False
                last_speech_time = asyncio.get_event_loop().time() # 更新最后一次收到音频的时间

            # 调用模型进行处理
            # 注意：实际生产中需要处理音频格式转换，这里简化为直接传入
            res = model.generate(input=speech_chunk, cache=cache, is_final=is_final, chunk_size=200)

            if res and res[0]["text"]:
                print(f"识别结果: {res[0]['text']}, is_final: {is_final}")
                # 3. 将结果封装成 JSON 发送回客户端
                await websocket.send(str(res[0]))

            # 4. VAD 主动超时判断
            # 这是一个简化的示例，实际 VAD 会更复杂，可能在模型内部完成
            current_time = asyncio.get_event_loop().time()
            if (current_time - last_speech_time) * 1000 > VAD_TIMEOUT_MS:
                print("检测到语音末端静音超时，主动结束句子。")
                # 传入一个空音频块和 is_final=True 来获取最终结果
                final_res = model.generate(input=None, cache=cache, is_final=True)
                if final_res and final_res[0]["text"]:
                     await websocket.send(str(final_res[0]))
                # 重置 cache，准备下一句话
                cache = {}

    except websockets.exceptions.ConnectionClosed:
        print("客户端连接已断开。")
    finally:
        # 清理资源
        print("会话结束。")


# 启动 WebSocket 服务器
start_server = websockets.serve(asr_session, "localhost", 8766)

asyncio.get_event_loop().run_until_complete(start_server)
asyncio.get_event_loop().run_forever()
```

#### **客户端 (JavaScript, 运行于浏览器)**

```javascript
const ASR_SERVER_URL = "ws://localhost:8766";
let socket;
let audioContext;
let scriptProcessor;

// UI 元素
const startButton = document.getElementById("startButton");
const stopButton = document.getElementById("stopButton");
const resultDiv = document.getElementById("result");

startButton.onclick = () => {
    navigator.mediaDevices.getUserMedia({ audio: true }).then(stream => {
        // 1. 建立 WebSocket 连接
        socket = new WebSocket(ASR_SERVER_URL);

        socket.onopen = () => {
            console.log("服务器连接成功");
            startButton.disabled = true;
            stopButton.disabled = false;
        };

        socket.onmessage = (event) => {
            // 5. 接收服务器结果并展示
            const res = JSON.parse(event.data);
            resultDiv.innerText = res.text; // 实时更新文本
            if (res.is_final) {
                console.log("收到最终结果:", res.text);
                // 可以在这里将最终结果固定下来，并清空临时结果
            }
        };

        socket.onclose = () => {
            console.log("服务器连接已断开");
            startButton.disabled = false;
            stopButton.disabled = true;
        };

        // 2. 音频处理
        audioContext = new (window.AudioContext || window.webkitAudioContext)();
        const source = audioContext.createMediaStreamSource(stream);
        scriptProcessor = audioContext.createScriptProcessor(4096, 1, 1); // 4096 采样点一个 chunk

        scriptProcessor.onaudioprocess = (event) => {
            const inputData = event.inputBuffer.getChannelData(0);
            // 3. 将音频块发送到服务器
            if (socket && socket.readyState === WebSocket.OPEN) {
                // 注意：生产环境需要进行合适的格式转换（如转为16k采样率，16-bit整型）
                socket.send(inputData.buffer); 
            }
        };

        source.connect(scriptProcessor);
        scriptProcessor.connect(audioContext.destination);
    });
};

stopButton.onclick = () => {
    // 4. 发送结束信号
    if (socket && socket.readyState === WebSocket.OPEN) {
        socket.send(JSON.stringify({ end_signal: true }));
    }

    // 清理资源
    if (scriptProcessor) scriptProcessor.disconnect();
    if (audioContext) audioContext.close();
    startButton.disabled = false;
    stopButton.disabled = true;
};
```

### 4. 生产环境的关键考量

*   **并发与扩展性**：单个 Python 进程无法处理大量并发连接。需要使用 **负载均衡器** + **多个 ASR 服务器实例** 的架构。模型的加载和计算可以放在独立的 GPU 服务器上，通过内部 RPC 调用。
*   **VAD 参数调优**：`VAD_TIMEOUT_MS` 的值需要根据具体应用场景（如客服对话、会议记录、语音输入）进行仔细调优。太短容易错误切分，太长则响应迟钝。
*   **音频格式**：客户端和服务器必须约定好统一的音频格式（采样率、位深、通道数）。在网络传输中，可以使用 Opus 等编码器对音频进行压缩，以节省带宽。
*   **错误处理与韧性**：网络可能抖动或中断。客户端和服务器都需要有重连和会话恢复机制。
*   **安全性**：在公网环境中，必须使用 `wss://` (安全的 WebSocket) 并进行身份验证，防止服务被滥用。