# Speak TTS MCP

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

The script handles everything: finds a compatible Python (3.10–3.12), creates a venv, installs PyTorch (auto-detects GPU vs CPU), installs dependencies, and registers with Claude Code if the CLI is available.

### 2. Register (if not auto-registered)

The setup script auto-registers with Claude Code when the `claude` CLI is on PATH. If it wasn't found, register manually:

**Windows:**

```bash
claude mcp add-json speak-tts '{"type":"stdio","command":"C:/absolute/path/to/speak-tts-mcp/run.cmd"}' --scope user
```

**Linux / macOS:**

```bash
claude mcp add-json speak-tts '{"type":"stdio","command":"/absolute/path/to/speak-tts-mcp/run.sh"}' --scope user
```

> Absolute paths are required. Relative paths will not work.

### 3. Restart Claude Code

The server will be available after restart. The model (~300 MB) downloads automatically on the first `speak()` call and is cached locally in the `.models/` directory.

## Claude Desktop

Add to the `mcpServers` object in your config file:

| OS      | Config path                                                       |
| ------- | ----------------------------------------------------------------- |
| Windows | `%APPDATA%\Claude\claude_desktop_config.json`                     |
| macOS   | `~/Library/Application Support/Claude/claude_desktop_config.json` |

**Windows:**

```json
"speak-tts": {
  "command": "C:\\absolute\\path\\to\\speak-tts-mcp\\run.cmd"
}
```

**Linux / macOS:**

```json
"speak-tts": {
  "command": "/absolute/path/to/speak-tts-mcp/run.sh"
}
```

Restart Claude Desktop after saving.

## Tools

### `speak(text, voice?, speed?)`

Speaks text aloud through the system speakers. Text must be in English — non-Latin characters are not pronounced correctly. Non-English voices apply their accent to English text.

| Parameter | Type   | Default      | Description                    |
| --------- | ------ | ------------ | ------------------------------ |
| `text`    | string | _(required)_ | The text to speak              |
| `voice`   | string | `af_nicole`  | Voice ID — see `list_voices()` |
| `speed`   | float  | `1.0`        | Playback speed, `0.5` to `2.0` |

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

## Notes

- **GPU selection:** Uses `cuda:1` when multiple GPUs are available, otherwise `cuda:0`, with CPU as fallback. Edit `_get_pipeline()` in `server.py` to change this.
- **Model cache:** Models are stored in `.models/` next to `server.py`. Delete this directory to force a fresh download.
- **espeak-ng:** Bundled via `espeakng-loader` — no system install needed. Override with `PHONEMIZER_ESPEAK_LIBRARY` and `ESPEAK_DATA_PATH` env vars if needed.
