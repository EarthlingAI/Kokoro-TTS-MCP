"""Kokoro TTS MCP Server - Enables Claude Code to speak aloud via Kokoro-82M."""

import os
import sys

# Cache models locally in .models/ (next to server.py) so they're visible and easy to clean up.
_server_dir = os.path.dirname(os.path.abspath(__file__))
os.environ.setdefault("HF_HUB_CACHE", os.path.join(_server_dir, ".models"))

# Auto-detect espeak-ng paths (works on Windows, Linux, and macOS).
# Manual env var overrides are still respected thanks to setdefault.
import espeakng_loader

os.environ.setdefault("PHONEMIZER_ESPEAK_LIBRARY", espeakng_loader.get_library_path())
os.environ.setdefault("ESPEAK_DATA_PATH", espeakng_loader.get_data_path())

import numpy as np
import sounddevice as sd
from fastmcp import FastMCP

mcp = FastMCP("kokoro-tts")

# Lazy-loaded pipeline (loads model on first speak call)
_pipeline = None

VOICES = {
    "American English (Female)": [
        "af_heart", "af_alloy", "af_aoede", "af_bella", "af_jessica",
        "af_kore", "af_nicole", "af_nova", "af_river", "af_sarah", "af_sky",
    ],
    "American English (Male)": [
        "am_adam", "am_echo", "am_eric", "am_fenrir", "am_liam",
        "am_michael", "am_onyx", "am_puck", "am_santa",
    ],
    "British English (Female)": [
        "bf_alice", "bf_emma", "bf_isabella", "bf_lily",
    ],
    "British English (Male)": [
        "bm_daniel", "bm_fable", "bm_george", "bm_lewis",
    ],
    "Japanese (Female)": [
        "jf_alpha", "jf_gongitsune", "jf_nezumi", "jf_tebukuro",
    ],
    "Japanese (Male)": [
        "jm_kumo",
    ],
    "Mandarin Chinese (Female)": [
        "zf_xiaobei", "zf_xiaoni", "zf_xiaoyi",
    ],
    "Mandarin Chinese (Male)": [
        "zm_yunjian", "zm_yunxi", "zm_yunxia", "zm_yunyang",
    ],
    "Spanish (Female)": [
        "ef_dora",
    ],
    "Spanish (Male)": [
        "em_alex", "em_santa",
    ],
    "French (Female)": [
        "ff_siwis",
    ],
    "Hindi (Female)": [
        "hf_alpha", "hf_beta",
    ],
    "Hindi (Male)": [
        "hm_omega", "hm_psi",
    ],
    "Italian (Female)": [
        "if_sara",
    ],
    "Italian (Male)": [
        "im_nicola",
    ],
    "Brazilian Portuguese (Female)": [
        "pf_dora",
    ],
    "Brazilian Portuguese (Male)": [
        "pm_alex", "pm_santa",
    ],
}

ALL_VOICE_IDS = [v for voices in VOICES.values() for v in voices]


def _get_pipeline():
    """Lazily initialize the Kokoro pipeline (downloads model on first call)."""
    global _pipeline
    if _pipeline is None:
        import io
        import torch
        from kokoro import KPipeline

        if torch.cuda.is_available():
            device = "cuda:1" if torch.cuda.device_count() > 1 else "cuda"
        else:
            device = "cpu"
        lang_code = "a"  # American English default
        # Redirect stdout during init to prevent stray prints (e.g. Kokoro's
        # repo_id warning) from corrupting the MCP stdio protocol.
        old_stdout = sys.stdout
        sys.stdout = io.StringIO()
        try:
            _pipeline = KPipeline(
                lang_code=lang_code, repo_id="hexgrad/Kokoro-82M", device=device,
            )
        finally:
            sys.stdout = old_stdout
        print(f"Kokoro pipeline loaded on {device}", file=sys.stderr)
    return _pipeline


@mcp.tool()
def speak(
    text: str,
    voice: str = "af_nicole",
    speed: float = 1.0,
) -> str:
    """Speak text aloud using Kokoro TTS. Plays audio through the system speakers.
    Text must be in English. Non-Latin characters are not pronounced correctly.

    Args:
        text: The text to speak aloud. Must be in English.
        voice: Voice ID to use. Default is af_nicole (American English female).
               Use list_voices() to see all available voices.
        speed: Speech speed multiplier. Default 1.0, range 0.5 to 2.0.
    """
    try:
        if not text or not text.strip():
            return "Error: No text provided."

        if voice not in ALL_VOICE_IDS:
            return f"Error: Unknown voice '{voice}'. Use list_voices() to see available voices."

        speed = max(0.5, min(2.0, speed))

        pipeline = _get_pipeline()

        # Generate audio - pipeline yields chunks for long text
        audio_chunks = []
        for _, _, audio in pipeline(text, voice=voice, speed=speed):
            if audio is not None:
                audio_chunks.append(audio)

        if not audio_chunks:
            return "Error: No audio generated. The text may be too short or invalid."

        # Concatenate all chunks
        audio = np.concatenate(audio_chunks)

        # Normalize to prevent clipping
        peak = np.max(np.abs(audio))
        if peak > 0:
            audio = audio / peak * 0.95

        # Play audio and wait for completion
        sample_rate = 24000
        sd.play(audio, samplerate=sample_rate)
        sd.wait()

        duration = len(audio) / sample_rate
        return f"Spoke {len(text)} characters in {duration:.1f}s using voice '{voice}'."

    except Exception as e:
        return f"Error during speech: {e}"


@mcp.tool()
def list_voices() -> dict:
    """List all available Kokoro TTS voices organized by language and gender.

    Returns a dictionary mapping language/gender categories to lists of voice IDs.
    The default voice is af_nicole (American English female).
    """
    return VOICES


if __name__ == "__main__":
    mcp.run()
