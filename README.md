# TTS MCP

MCP server that gives agents the ability to speak aloud, powered by [Kokoro-82M](https://huggingface.co/hexgrad/Kokoro-82M) — a fast, lightweight, open-source text-to-speech model.

- 53 voices across 9 languages
- Apache 2.0 — free, no API keys
- ~210x real-time on RTX 4090, works on CPU too
- <1 GB VRAM
- Lazy loading — model downloads on first `speak()` call

## Quick Start

### 1. Install

**Windows:**

```
setup_venv.bat
```

**Linux / macOS:**

```bash
chmod +x setup_venv.sh && ./setup_venv.sh
```

The script handles everything: finds Python 3.12 (Kokoro requires Python <3.13), creates a venv, installs PyTorch (auto-detects GPU vs CPU), installs dependencies, and registers with Claude Code if the CLI is available.

### 2. Register (if not auto-registered)

The setup script auto-registers with Claude Code when the `claude` CLI is on PATH. If it wasn't found, register manually:

**Linux / macOS:**

```bash
claude mcp add-json tts-mcp '{"type":"stdio","command":"/absolute/path/to/tts-mcp/.venv/bin/python","args":["/absolute/path/to/tts-mcp/server.py"]}' --scope user
```

**Windows:**

```bash
claude mcp add-json tts-mcp "{\"type\":\"stdio\",\"command\":\"C:\\absolute\\path\\to\\tts-mcp\\.venv\\Scripts\\python.exe\",\"args\":[\"C:\\absolute\\path\\to\\tts-mcp\\server.py\"]}" --scope user
```

### 3. Restart Claude Code

The server will be available after restart. The model (~300 MB) downloads automatically on the first `speak()` call and is cached locally in the `.models/` directory.

## Claude Desktop

Add to the `mcpServers` object in your config file:

| OS      | Config path                                                       |
| ------- | ----------------------------------------------------------------- |
| Windows | `%APPDATA%\Claude\claude_desktop_config.json`                     |
| macOS   | `~/Library/Application Support/Claude/claude_desktop_config.json` |

**Linux / macOS:**

```json
"tts-mcp": {
  "command": "/absolute/path/to/tts-mcp/.venv/bin/python",
  "args": ["/absolute/path/to/tts-mcp/server.py"]
}
```

**Windows:**

```json
"tts-mcp": {
  "command": "C:\\absolute\\path\\to\\tts-mcp\\.venv\\Scripts\\python.exe",
  "args": ["C:\\absolute\\path\\to\\tts-mcp\\server.py"]
}
```

> Restart Claude Desktop after saving.

## Tools

### `speak(text, voice?, speed?)`

Queues text to be spoken aloud through the system speakers. Returns immediately — audio generates and plays in the background. Multiple calls queue up and play sequentially. Text must be in English — non-Latin characters are not pronounced correctly. Non-English voices apply their accent to English text.

| Parameter | Type   | Default      | Description                    |
| --------- | ------ | ------------ | ------------------------------ |
| `text`    | string | _(required)_ | The text to speak              |
| `voice`   | string | `af_nicole`  | Voice ID — see `list_voices()` |
| `speed`   | float  | `1.0`        | Playback speed, `0.5` to `2.0` |

### `stop_all_speech()`

Stops any currently playing speech and clears the speech queue.

### `list_voices()`

Returns all 53 voices organized by language and gender.

| Language             | Female                                                                                                                      | Male                                                                                  |
| -------------------- | --------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------- |
| American English     | af_heart, af_alloy, af_aoede, af_bella, af_jessica, af_kore, **af_nicole** _(default)_, af_nova, af_river, af_sarah, af_sky | am_adam, am_echo, am_eric, am_fenrir, am_liam, am_michael, am_onyx, am_puck, am_santa |
| British English      | bf_alice, bf_emma, bf_isabella, bf_lily                                                                                     | bm_daniel, bm_fable, bm_george, bm_lewis                                              |
| Japanese             | jf_alpha, jf_gongitsune, jf_nezumi, jf_tebukuro                                                                             | jm_kumo                                                                               |
| Mandarin Chinese     | zf_xiaobei, zf_xiaoni, zf_xiaoyi                                                                                            | zm_yunjian, zm_yunxi, zm_yunxia, zm_yunyang                                           |
| Spanish              | ef_dora                                                                                                                     | em_alex, em_santa                                                                     |
| French               | ff_siwis                                                                                                                    | —                                                                                     |
| Hindi                | hf_alpha, hf_beta                                                                                                           | hm_omega, hm_psi                                                                      |
| Italian              | if_sara                                                                                                                     | im_nicola                                                                             |
| Brazilian Portuguese | pf_dora                                                                                                                     | pm_alex, pm_santa                                                                     |

## Manual Setup

If you prefer not to use the setup script:

```bash
# 1. Create venv
python -m venv .venv

# 2. Activate
# Windows:   .venv\Scripts\activate
# Linux/Mac: source .venv/bin/activate

# 3. Install PyTorch
# GPU:  pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu126
# CPU:  pip install torch torchvision torchaudio

# 4. Install dependencies
pip install -r requirements.txt
```

## Architecture

The server uses a **coordinator architecture** to support all types of MCP clients:

```
┌─────────────┐    ┌─────────────┐    ┌─────────────┐
│ Claude Code  │    │ mcporter     │    │ Claude Desktop│
│ (persistent) │    │ (transient)  │    │ (persistent)  │
└──────┬───────┘    └──────┬───────┘    └──────┬────────┘
       │                   │                   │
       │  server.py        │  server.py        │  server.py
       │  (thin client)    │  (thin client)    │  (thin client)
       └───────────────────┼───────────────────┘
                           │ Unix socket / TCP
                    ┌──────▼───────┐
                    │ _coordinator │
                    │   (1 proc)   │
                    │              │
                    │ Kokoro model │
                    │ Audio queue  │
                    │ sounddevice  │
                    └──────────────┘
```

- **`server.py`** — MCP server (thin client). Validates inputs and sends JSON commands to the coordinator over a Unix domain socket (macOS/Linux) or TCP localhost (Windows).
- **`_coordinator.py`** — Background process that loads the Kokoro model once, manages a shared speech queue, and plays audio sequentially. Auto-spawned by `server.py` on first `speak()` call.

### Benefits

- **No audio cutoff** — audio lives in the coordinator, not the MCP server process. Transient clients can die immediately after queueing speech.
- **Shared queue** — speech from all connected agents plays in order, no overlapping.
- **`stop_all_speech()` works across processes** — any client can stop audio that another client queued.
- **Model loaded once** — first call takes ~4s (model loading), subsequent calls are instant.
- **Auto-lifecycle** — the coordinator spawns on demand and exits after 60 seconds of inactivity.

### Coordinator Details

- **Socket:** `/tmp/kokoro-tts.sock` (Unix) or TCP `127.0.0.1` on a dynamic port stored in `/tmp/kokoro-tts.port` (Windows)
- **PID file:** `/tmp/kokoro-tts.pid`
- **Log file:** `/tmp/kokoro-tts-coordinator.log`
- **Idle timeout:** 60 seconds (configurable via `--idle-timeout`)
- **Manual shutdown:** Send `{"cmd": "shutdown"}` to the socket, or kill the PID

No configuration is required — everything is automatic.

## Notes

- **GPU selection:** Uses `cuda:1` when multiple GPUs are available, otherwise `cuda:0`, with CPU as fallback. Edit `_get_pipeline()` in `_coordinator.py` to change this.
- **Model cache:** Models are stored in `.models/` next to `server.py`. Delete this directory to force a fresh download.
- **espeak-ng:** Bundled via `espeakng-loader` — no system install needed. Override with `PHONEMIZER_ESPEAK_LIBRARY` and `ESPEAK_DATA_PATH` env vars if needed.
