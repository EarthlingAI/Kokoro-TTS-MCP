# Kokoro-TTS-MCP

MCP server that lets agents like Claude Code speak to you in real-time using [Kokoro-82M](https://huggingface.co/hexgrad/Kokoro-82M) — a fast, open-source TTS model with 54 voices across 9 languages.

- Apache 2.0 — completely free, no API keys
- ~210x real-time on an RTX 4090, runs on CPU too
- <1 GB VRAM for the 82M parameter model
- Lazy model loading — only downloads/loads on first `speak()` call

## Prerequisites

- **Python 3.10+**
- **NVIDIA GPU** (optional but recommended — falls back to CPU)

> **Note:** espeak-ng is bundled automatically via the `espeakng-loader` pip package — no separate install required.

## Setup

### Option A: Run the setup script

The setup scripts create a virtual environment, install PyTorch with GPU support, and install the remaining dependencies from `requirements.txt`.

**Windows** — double-click or run from a terminal:
```
setup_venv.bat
```

**Linux/macOS:**
```bash
chmod +x setup_venv.sh
./setup_venv.sh
```

On Linux, PyTorch is installed with CUDA 12.6. On macOS, the default PyTorch build is used (includes MPS support for Apple Silicon).

### Option B: Manual setup

1. **Create and activate a virtual environment:**
	```bash
	python -m venv .venv

	# Windows
	.venv\Scripts\activate

	# Linux/macOS
	source .venv/bin/activate
	```

2. **Install PyTorch with CUDA support** (skip `--index-url` for CPU-only or macOS):
	```bash
	pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu126
	```

3. **Install remaining dependencies:**
	```bash
	pip install -r requirements.txt
	```

## Register with Claude Code

Add the server to your user-level MCP config. Replace `/path/to/kokoro-mcp` with the absolute path to this repo.

**Windows:**
```bash
claude mcp add-json kokoro-tts '{
  "type": "stdio",
  "command": "C:/path/to/kokoro-mcp/.venv/Scripts/python.exe",
  "args": ["C:/path/to/kokoro-mcp/server.py"]
}' --scope user
```

**Linux/macOS:**
```bash
claude mcp add-json kokoro-tts '{
  "type": "stdio",
  "command": "/path/to/kokoro-mcp/.venv/bin/python",
  "args": ["/path/to/kokoro-mcp/server.py"]
}' --scope user
```

Restart Claude Code after registering. Use **absolute paths** — relative paths will not work.

> **Tip:** espeak-ng paths are auto-detected via `espeakng-loader`. To override them, add an `env` block with `PHONEMIZER_ESPEAK_LIBRARY` and/or `ESPEAK_DATA_PATH`.

## Register with Claude Desktop

Add a `kokoro-tts` entry to the `mcpServers` object in your Claude Desktop config file:

- **Windows:** `%APPDATA%\Claude\claude_desktop_config.json`
- **macOS:** `~/Library/Application Support/Claude/claude_desktop_config.json`

**Windows:**
```json
"kokoro-tts": {
  "command": "C:\\path\\to\\kokoro-mcp\\.venv\\Scripts\\python.exe",
  "args": ["C:\\path\\to\\kokoro-mcp\\server.py"]
}
```

**Linux/macOS:**
```json
"kokoro-tts": {
  "command": "/path/to/kokoro-mcp/.venv/bin/python",
  "args": ["/path/to/kokoro-mcp/server.py"]
}
```

Replace the paths with the absolute path to this repo. Use `\\` (backslash) on Windows. Restart Claude Desktop after saving.

## Tools

### `speak(text, voice?, speed?)`
Generates speech and plays it through system speakers.
- `text` — the text to speak
- `voice` — voice ID (default: `af_heart`). See `list_voices()` for all options.
- `speed` — playback speed multiplier, 0.5–2.0 (default: `1.0`)

### `list_voices()`
Returns all 54 available voices organized by language and gender:

| Language | Female | Male |
|---|---|---|
| American English | af_heart, af_alloy, af_aoede, af_bella, af_jessica, af_kore, af_nicole, af_nova, af_river, af_sarah, af_sky | am_adam, am_echo, am_eric, am_fenrir, am_liam, am_michael, am_onyx, am_puck, am_santa |
| British English | bf_alice, bf_emma, bf_isabella, bf_lily | bm_daniel, bm_fable, bm_george, bm_lewis |
| Japanese | jf_alpha, jf_gongitsune, jf_nezumi, jf_tebukuro | jm_kumo |
| Mandarin Chinese | zf_xiaobei, zf_xiaoni, zf_xiaoxuan, zf_xiaoyi | zm_yunjian, zm_yunxi, zm_yunxia, zm_yunyang |
| Spanish | ef_dora | em_alex, em_santa |
| French | ff_siwis | — |
| Hindi | hf_alpha, hf_beta | hm_omega, hm_psi |
| Italian | if_sara | im_nicola |
| Brazilian Portuguese | pf_dora | pm_alex, pm_santa |

## GPU Selection

By default, the server selects `cuda:1` if multiple GPUs are available, otherwise `cuda:0`, with CPU as fallback. Edit the `_get_pipeline()` function in `server.py` to change this behavior.
