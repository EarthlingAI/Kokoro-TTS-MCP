#!/usr/bin/env python3
"""Speak TTS MCP Server - Enables Claude to speak aloud via Kokoro-82M."""

import os
import queue
import sys
import threading


def _bootstrap_venv():
	"""Re-exec under the .venv Python if we're not already in it.

	This makes server.py self-bootstrapping: any system Python can launch it
	and it will automatically find and use the project's virtual environment.
	Eliminates the need for platform-specific launcher scripts (run.sh, run.cmd).
	"""
	server_dir = os.path.dirname(os.path.abspath(__file__))

	if sys.platform == "win32":
		venv_python = os.path.join(server_dir, ".venv", "Scripts", "python.exe")
	else:
		venv_python = os.path.join(server_dir, ".venv", "bin", "python")

	if not os.path.isfile(venv_python):
		print(
			f"Warning: venv not found at {venv_python} — running with current interpreter.",
			file=sys.stderr,
		)
		return

	# Case-insensitive comparison on Windows (paths can differ in casing)
	current = os.path.realpath(sys.executable)
	target = os.path.realpath(venv_python)
	if sys.platform == "win32":
		already_in_venv = current.casefold() == target.casefold()
	else:
		already_in_venv = current == target

	if already_in_venv:
		return

	# Re-exec with the venv Python
	args = [venv_python, __file__] + sys.argv[1:]
	if sys.platform == "win32":
		# os.execv on Windows doesn't truly replace the process (CPython spawns
		# a child and exits the parent), which breaks MCP stdio pipes. Use
		# subprocess.run instead: the parent stays alive, child inherits stdio.
		import subprocess

		result = subprocess.run(args)
		sys.exit(result.returncode)
	else:
		os.execv(venv_python, args)


if __name__ == "__main__":
	_bootstrap_venv()

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

mcp = FastMCP("speak-tts")

# Lazy-loaded pipeline (loads model on first speak call)
_pipeline = None
_speak_queue: queue.Queue = queue.Queue()
_generation: int = 0
_worker_started: bool = False

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


def _speak_worker():
	"""Background worker — generates and plays queued speech sequentially."""
	while True:
		text, voice, speed, gen = _speak_queue.get()

		if gen != _generation:
			_speak_queue.task_done()
			continue

		try:
			pipeline = _get_pipeline()
			audio_chunks = []
			for _, _, chunk in pipeline(text, voice=voice, speed=speed):
				if gen != _generation:
					break
				if chunk is not None:
					audio_chunks.append(chunk)

			if gen != _generation or not audio_chunks:
				continue

			audio = np.concatenate(audio_chunks)
			peak = np.max(np.abs(audio))
			if peak > 0:
				audio = audio / peak * 0.95

			sd.play(audio, samplerate=24000)
			sd.wait()

		except Exception as e:
			print(f"Speech error: {e}", file=sys.stderr)
		finally:
			_speak_queue.task_done()


def _ensure_worker():
	"""Start the background speech worker thread (once)."""
	global _worker_started
	if not _worker_started:
		threading.Thread(target=_speak_worker, daemon=True).start()
		_worker_started = True


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
    if not text or not text.strip():
        return "Error: No text provided."

    if voice not in ALL_VOICE_IDS:
        return f"Error: Unknown voice '{voice}'. Use list_voices() to see available voices."

    speed = max(0.5, min(2.0, speed))

    _ensure_worker()
    _speak_queue.put((text, voice, speed, _generation))
    return f"Successfully queued {len(text)} chars via '{voice}'. User will hear the message shortly."


@mcp.tool()
def stop() -> str:
	"""Stop any currently playing speech and clear the speech queue.
	Only use when the user explicitly asks to stop speech.
	"""
	global _generation
	_generation += 1
	sd.stop()

	while not _speak_queue.empty():
		try:
			_speak_queue.get_nowait()
			_speak_queue.task_done()
		except queue.Empty:
			break

	return "Stopped."


@mcp.tool()
def list_voices() -> dict:
    """List all available Kokoro TTS voices organized by language and gender.

    Returns a dictionary mapping language/gender categories to lists of voice IDs.
    The default voice is af_nicole (American English female).
    """
    return VOICES


if __name__ == "__main__":
    mcp.run()
