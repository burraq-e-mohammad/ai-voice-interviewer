"""Download a Piper TTS voice into the `models/` folder.

Usage:
    python scripts/download_voice.py                     # default voice
    python scripts/download_voice.py en_GB-alan-medium   # another voice

Browse voices (and listen to samples) at:
    https://rhasspy.github.io/piper-samples/

Each voice needs two files: the model (`.onnx`) and its config (`.onnx.json`).
They are hosted on Hugging Face in the official `rhasspy/piper-voices` repo.
"""

import sys
import urllib.request
from pathlib import Path

DEFAULT_VOICE = "en_US-lessac-medium"
BASE_URL = "https://huggingface.co/rhasspy/piper-voices/resolve/v1.0.0"
MODELS_DIR = Path(__file__).resolve().parent.parent / "models"


def voice_url(voice_name: str, extension: str) -> str:
    """Build the download URL from a name like 'en_US-lessac-medium'.

    The repo is organised as: <lang>/<lang_REGION>/<speaker>/<quality>/<file>
    e.g. en/en_US/lessac/medium/en_US-lessac-medium.onnx
    """
    locale, speaker, quality = voice_name.split("-")
    language = locale.split("_")[0]
    return f"{BASE_URL}/{language}/{locale}/{speaker}/{quality}/{voice_name}{extension}"


def download(voice_name: str) -> None:
    MODELS_DIR.mkdir(exist_ok=True)
    for extension in (".onnx", ".onnx.json"):
        target = MODELS_DIR / f"{voice_name}{extension}"
        if target.exists():
            print(f"Already downloaded: {target.name}")
            continue
        url = voice_url(voice_name, extension)
        print(f"Downloading {url} ...")
        # Download to a temporary name first, so an interrupted download
        # never leaves a half-written file that looks complete.
        partial = target.with_suffix(target.suffix + ".part")
        urllib.request.urlretrieve(url, partial)
        partial.replace(target)
        print(f"Saved {target}")


if __name__ == "__main__":
    name = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_VOICE
    if name.count("-") != 2:
        sys.exit(f"Voice names look like 'en_US-lessac-medium', got '{name}'.")
    download(name)
    print("Done. Set PIPER_VOICE_PATH in .env if you chose a non-default voice.")
