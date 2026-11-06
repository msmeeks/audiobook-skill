#!/usr/bin/env bash
# Idempotent setup for the audiobook skill: a Python venv with Kokoro + PyMuPDF, and the
# Kokoro v1.0 model files (sha256-verified). Safe to re-run; prints the python path last.
set -euo pipefail

HOME_DIR="${AUDIOBOOK_HOME:-$HOME/.cache/audiobook}"
VENV="$HOME_DIR/venv"
MODELS="$HOME_DIR/models"
RELEASE="https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0"
PACKAGES=(kokoro-onnx==0.6.1 onnxruntime soundfile numpy pymupdf pytest)

command -v ffmpeg >/dev/null || { echo "ffmpeg not found: brew install ffmpeg" >&2; exit 1; }

if [ ! -x "$VENV/bin/python" ]; then
  echo "creating venv at $VENV"
  if command -v uv >/dev/null; then uv venv -q --python 3.12 "$VENV"
  else python3 -m venv "$VENV"; fi
fi
if command -v uv >/dev/null; then uv pip install -q --python "$VENV/bin/python" "${PACKAGES[@]}"
else "$VENV/bin/pip" install -q "${PACKAGES[@]}"; fi

verified() { [ -f "$1" ] && echo "$2  $1" | shasum -a 256 -c --status; }

fetch_model() {
  local name=$1 sha=$2
  local target="$MODELS/$name"
  verified "$target" "$sha" && return
  echo "downloading $name"
  curl -fL --progress-bar -o "$target.part" "$RELEASE/$name"
  verified "$target.part" "$sha" || { rm -f "$target.part"; echo "checksum mismatch: $name" >&2; exit 1; }
  mv "$target.part" "$target"
}

mkdir -p "$MODELS"
fetch_model kokoro-v1.0.onnx 7d5df8ecf7d4b1878015a32686053fd0eebe2bc377234608764cc0ef3636a6c5
fetch_model voices-v1.0.bin bca610b8308e8d99f32e6fe4197e7ec01679264efed0cac9140fe9c29f1fbf7d

echo "ready: $VENV/bin/python"
