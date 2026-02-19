# Kokoro-TTS-MCP

MCP server that lets agents like Claude Code speak to you in real-time using [Kokoro-82M](https://huggingface.co/hexgrad/Kokoro-82M) — a fast, open-source TTS model with 54 voices across 10 languages.

- Apache 2.0 — completely free, no API keys
- ~210x real-time on an RTX 4090, runs on CPU too
- <1 GB VRAM for the 82M parameter model
- Lazy model loading — only downloads/loads on first `speak()` call

## Prerequisites

- **Python 3.10+**
- **NVIDIA GPU** (optional but recommended — falls back to CPU)
- **espeak-ng** — required by Kokoro for phoneme conversion

### Install espeak-ng

**Windows (winget):**
```
winget install espeak-ng
```

**Windows (manual):** Download the installer from [espeak-ng releases](https://github.com/espeak-ng/espeak-ng/releases) and install to the default location (`C:\Program Files\eSpeak NG`).

**Linux:**
```bash
sudo apt install espeak-ng
```

**macOS:**
```bash
brew install espeak-ng
```

## Setup

### Option A: Run the batch file (Windows)

Double-click **`setup_venv.bat`** or run it from a terminal. It creates the virtual environment, installs PyTorch with CUDA, and installs the remaining dependencies.

### Option B: Manual setup

1. **Create a virtual environment:**
	```bash
	python -m venv .venv
	```

2. **Activate it:**
	```bash
	# Windows
	.venv\Scripts\activate

	# Linux/macOS
	source .venv/bin/activate
	```

3. **Install PyTorch with CUDA support** (skip `--index-url` for CPU-only):
	```bash
	pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu126
	```

4. **Install remaining dependencies:**
	```bash
	pip install kokoro>=0.9.4 soundfile sounddevice numpy "fastmcp>=2.0"
	```

## Register with Claude Code

Add the server to your user-level MCP config (`~/.claude.json`):

```bash
claude mcp add-json kokoro-tts '{
  "type": "stdio",
  "command": "/path/to/kokoro-mcp/.venv/Scripts/python.exe",
  "args": ["/path/to/kokoro-mcp/server.py"],
  "env": {
    "PHONEMIZER_ESPEAK_LIBRARY": "C:/Program Files/eSpeak NG/libespeak-ng.dll",
    "PHONEMIZER_ESPEAK_PATH": "C:/Program Files/eSpeak NG/espeak-ng.exe",
    "ESPEAK_DATA_PATH": "C:/Program Files/eSpeak NG/espeak-ng-data"
  }
}' --scope user
```

Replace `/path/to/kokoro-mcp/` with the actual path to this repo.

On Linux/macOS, update the `env` paths to match your espeak-ng installation (typically `/usr/lib/x86_64-linux-gnu/libespeak-ng.so.1` and `/usr/bin/espeak-ng`).

Restart Claude Code after registering.

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
