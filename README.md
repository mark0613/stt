# STT

會議、訪談、podcast，一行指令變成逐字稿。說話者自動標記，時間戳精準對齊，再長的音檔也不遺漏。

## Features

- 🎙️ **多說話者辨識**：自動標記 Speaker 1、Speaker 2，跨段落保持一致
- ✂️ **智慧切塊**：以靜音點將音檔切成小塊分別轉錄再合併，解決 Gemini 在長音檔提早截止的問題
- 🔄 **自動續跑**：遇到輸出 token 上限或提前截止時自動重試，確保每塊都轉完
- 💰 **費用追蹤**：輸出 JSON 附本次 API 用量與估算費用（USD / TWD）

## 前置需求

[ffmpeg](https://ffmpeg.org/download.html) 必須先安裝並加入 PATH。

ffmpeg 是外部執行檔，不會隨套件一起安裝。當成套件使用時，呼叫端的執行環境（含 Docker 容器、CI runner）必須自己準備好 ffmpeg，否則會在切塊那一步失敗。

## 當成指令使用

```bash
uv sync
cp .env.example .env  # 填入 GOOGLE_API_KEY
```

```bash
uv run stt <音檔路徑> [輸出目錄]
```

如果沒帶輸出目錄，會與音檔路徑同個目錄建立 json
```bash
uv run stt <音檔路徑>
```

### 選用參數

| 參數 | 說明 |
|------|------|
| `-n`, `--num-speakers` | 說話者人數，會帶入 prompt 協助辨識 |
| `-p`, `--prompt` | 額外說明（例如主題、講者姓名），會帶入 prompt |

```bash
uv run stt meeting.mp3 -n 3 -p "這是一場關於 AI 的訪談"
```

## 當成套件使用

### 安裝

尚未發佈到 PyPI，也還沒有 tag，請直接釘 commit SHA：

```bash
uv add "stt @ git+ssh://git@github.com/mark0613/stt.git@<commit-sha>"
```

### 最小範例

```python
from google import genai
from stt import transcribe

result = transcribe('meeting.mp3', client=genai.Client(api_key='...'))

for segment in result.segments:
    print(segment.timestamp, segment.speaker, segment.content)
```

`transcribe()` 不會讀取任何環境變數，也不會自己建立目錄或設定 logging。API 金鑰、參數、進度回報全部由呼叫端傳入。

### 完整參數

```python
from google import genai
from stt import ProgressHooks, Settings, transcribe

result = transcribe(
    'meeting.mp3',
    output_path='meeting.json',  # 不給就只回傳結果，不寫檔
    speaker_count=3,
    extra_instructions='這是一場關於 AI 的訪談',
    client=genai.Client(api_key='...'),
    settings=Settings(target_chunk_seconds=480),
    hooks=ProgressHooks(
        on_chunks_ready=lambda total: print(f'共 {total} 塊'),
        on_upload_done=lambda: print('上傳完一塊'),
        on_chunk_done=lambda: print('轉錄完一塊'),
    ),
)
```

### 回傳值

`TranscriptResult.segments` 是一串 `TranscriptSegment`，每一段有 `speaker`、`timestamp`、`content`、`lang_code` 四個欄位。時間戳已經換算成整支音檔的絕對時間。

有指定 `output_path` 時會另外寫出 JSON，內容除了 `segments` 還附上本次的 `token_usage`。

### 調整參數

`Settings` 是 frozen 的 pydantic model，不傳就全部使用預設值。大部分欄位對應到下方的環境變數（對照表在 `stt.config.ENV_ALIASES`），費用估算用的 `audio_input_price_per_m`、`output_price_per_m`、`usd_to_twd` 沒有對應的環境變數，只能用程式碼傳入。

如果呼叫端也想沿用環境變數，可以自己讀進來：

```python
from stt import settings_from_env

settings = settings_from_env()  # 預設讀 os.environ，也可以傳入自己的 mapping
```

### 記錄 log

套件只在 `stt` 這個 logger 上掛了 `NullHandler`，不會動到呼叫端的 logging 設定。想看細節自己接：

```python
import logging

logging.getLogger('stt').setLevel(logging.INFO)
```

## 設定 .env

以下環境變數只影響 CLI。library 呼叫端請直接傳 `Settings`，不會受環境變數影響。

### 必填

| 變數 | 說明 |
|------|------|
| `GOOGLE_API_KEY` | 從 [Google AI Studio](https://aistudio.google.com/apikey) 取得 |

### Gemini 模型

| 變數 | 預設值 | 說明 |
|------|--------|------|
| `GEMINI_STT_MODEL` | `gemini-3.5-flash` | 使用的模型 |
| `GEMINI_MAX_OUTPUT_TOKENS` | `65536` | 單次回應最大 token 數 |
| `GEMINI_THINKING_BUDGET` | `0` | Thinking token 預算，0 表示關閉 |
| `GEMINI_STT_TRANSIENT_RETRIES` | `3` | 遇到 429/5xx 時的重試次數 |
| `GEMINI_STT_TRANSIENT_RETRY_DELAY_SECONDS` | `60` | 每次重試的等待秒數 |

### 音檔切割

| 變數 | 預設值 | 說明 |
|------|--------|------|
| `CHUNKED_TARGET_SECONDS` | `720` | 目標切塊長度（秒）。語速快的音檔可調低至 `480` |
| `CHUNKED_MAX_SECONDS` | `1500` | 超過此長度找不到靜音點時強制硬切 |
| `CHUNKED_SILENCE_NOISE_DB` | `-30` | 靜音偵測噪音閾值（dB）。環境吵可調高至 `-25` |
| `CHUNKED_SILENCE_MIN_DURATION` | `0.5` | 最短靜音長度（秒） |

### 轉錄流程

| 變數 | 預設值 | 說明 |
|------|--------|------|
| `CHUNKED_TAIL_CONTEXT_SEGMENTS` | `5` | 傳給下一塊的前文 segment 數，維持說話者標籤連貫 |
| `CHUNKED_MAX_CONTINUATIONS` | `10` | 單塊因 MAX_TOKENS 續跑的上限次數 |
| `CHUNKED_PREMATURE_STOP_GAP` | `60` | 最後時間戳距塊結尾超過此秒數視為提前截止，觸發重試 |
| `CHUNKED_PREMATURE_STOP_RETRIES` | `2` | 提前截止的最大重試次數 |
