# STT

會議、訪談、podcast，一行指令變成逐字稿。說話者自動標記，時間戳精準對齊，再長的音檔也不遺漏。

## Features

- 🎙️ **多說話者辨識**：自動標記 Speaker 1、Speaker 2，跨段落保持一致
- ✂️ **智慧切塊**：以靜音點將音檔切成小塊分別轉錄再合併，解決 Gemini 在長音檔提早截止的問題
- 🔄 **自動續跑**：遇到輸出 token 上限或提前截止時自動重試，確保每塊都轉完
- 💰 **費用追蹤**：輸出 JSON 附本次 API 用量與估算費用（USD / TWD）

## 安裝與使用

### 安裝
需要先安裝 [ffmpeg](https://ffmpeg.org/download.html) 並加入 PATH。

```bash
uv sync
cp .env.example .env  # 填入 GOOGLE_API_KEY
```

## 使用
```bash
uv run python main.py <音檔路徑> [輸出目錄]
```

如果沒帶輸出目錄，會與音檔路徑同個目錄建立 json
```bash
uv run python main.py <音檔路徑>
```

## 設定 .env

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
