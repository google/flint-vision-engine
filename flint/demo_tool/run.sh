#!/usr/bin/env bash
# Copyright 2026 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     https://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

set -e

# Change directory to the folder containing this script
cd "$(dirname "$0")"
SCRIPT_DIR="$(pwd -P 2>/dev/null || pwd)"

# Safety guard: Prevent accidental execution from inside Trash
if [[ "$SCRIPT_DIR" == *"Trash"* ]]; then
  echo "=================================================="
  echo "❌ Error: You are executing run.sh from inside Trash!"
  echo "Directory: $SCRIPT_DIR"
  echo ""
  echo "Please move or extract FVMv1 into your Documents directory and cd there:"
  echo "   cd ~/Documents/FVMv1"
  echo "   ./run.sh"
  echo "=================================================="
  exit 1
fi

echo "=================================================="
echo "⚡ Launching FLINT Vision Engine..."
echo "=================================================="

# 1. Clean up any foreign virtualenvs or Trash paths from PATH and environment
if [ -n "$VIRTUAL_ENV" ]; then
  CURRENT_VENV="$SCRIPT_DIR/.venv"
  if [ "$VIRTUAL_ENV" != "$CURRENT_VENV" ]; then
    echo "🔄 Detaching external virtual environment ($VIRTUAL_ENV)..."
    unset VIRTUAL_ENV
    if type deactivate &>/dev/null; then
      deactivate 2>/dev/null || true
    fi
  fi
fi

# Strip any paths containing 'Trash' or foreign '.venv' from PATH so stale binaries are ignored
CLEANED_PATH=""
IFS=':' read -ra ADDR <<< "$PATH"
for p in "${ADDR[@]}"; do
  if [[ "$p" != *"Trash"* ]] && [[ "$p" != *".venv"* ]]; then
    if [ -z "$CLEANED_PATH" ]; then
      CLEANED_PATH="$p"
    else
      CLEANED_PATH="$CLEANED_PATH:$p"
    fi
  fi
done
export PATH="$CLEANED_PATH"

# 2. Verify Python 3 exists
if ! command -v python3 &>/dev/null; then
  echo "❌ Error: python3 is not installed on this system."
  echo "Please install Python 3.8 or higher."
  exit 1
fi

PY_VERSION=$(python3 -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')" 2>/dev/null || echo "3")

# 3. On Linux, automatically install system packages if needed
OS="$(uname -s)"
if [ "$OS" = "Linux" ]; then
  if command -v apt-get &>/dev/null; then
    if ! dpkg -s python3-venv &>/dev/null || ! dpkg -s "python${PY_VERSION}-venv" &>/dev/null || ! python3 -m pip --version &>/dev/null; then
      echo "⚡ Attempting automatic system package install (python3-venv, python3-pip)..."
      APT_PKGS="python3-pip python3-venv python${PY_VERSION}-venv python3-full"
      if command -v sudo &>/dev/null; then
        sudo apt-get install -y $APT_PKGS 2>/dev/null || (sudo apt-get update -y && sudo apt-get install -y $APT_PKGS) 2>/dev/null || true
      else
        apt-get install -y $APT_PKGS 2>/dev/null || (apt-get update -y && apt-get install -y $APT_PKGS) 2>/dev/null || true
      fi
    fi
  fi
fi

# 4. Clean up any invalid or outdated local .venv
if [ -d ".venv" ]; then
  if [ ! -f ".venv/bin/python3" ] || [ ! -f ".venv/bin/activate" ] || ! grep -q "$SCRIPT_DIR" .venv/bin/activate 2>/dev/null; then
    echo "🧹 Removing broken or outdated local .venv..."
    rm -rf .venv
  fi
fi

# 5. Set up and activate local virtual environment (.venv)
if [ ! -f ".venv/bin/activate" ]; then
  echo "📦 Initializing local virtual environment (.venv)..."
  rm -rf .venv 2>/dev/null || true

  # Try standard venv first (redirect stdout and stderr to avoid Debian warning banner)
  if ! python3 -m venv .venv >/dev/null 2>&1; then
    # Fallback to --without-pip (always succeeds on Debian/Ubuntu/gLinux without python3-venv)
    rm -rf .venv 2>/dev/null || true
    python3 -m venv --without-pip .venv >/dev/null 2>&1 || true
  fi
fi

# Activate local .venv if available
if [ -f ".venv/bin/activate" ]; then
  source .venv/bin/activate
  echo "🔄 Activated local virtual environment (.venv)"
fi

# 6. Ensure pip is installed and functioning inside .venv
if ! python3 -m pip --version >/dev/null 2>&1; then
  echo "⚡ Installing pip into virtual environment..."
  
  # Try ensurepip
  python3 -m ensurepip --default-pip >/dev/null 2>&1 || true

  # If still no pip, bootstrap via bundled get-pip.py
  if ! python3 -m pip --version >/dev/null 2>&1; then
    GET_PIP_CMD=""
    if [ -f "get-pip.py" ]; then
      GET_PIP_CMD="get-pip.py"
    elif [ -f "$(dirname "$0")/get-pip.py" ]; then
      GET_PIP_CMD="$(dirname "$0")/get-pip.py"
    fi

    if [ -n "$GET_PIP_CMD" ]; then
      python3 "$GET_PIP_CMD" --no-warn-script-location >/dev/null 2>&1 ||       python3 "$GET_PIP_CMD" --break-system-packages --no-warn-script-location >/dev/null 2>&1 ||       python3 "$GET_PIP_CMD" --user --break-system-packages --no-warn-script-location >/dev/null 2>&1 ||       python3 "$GET_PIP_CMD" >/dev/null 2>&1 || true
    fi
  fi
fi

# 7. Check and install PyTorch and dependencies safely
# Note: Installing torch/torchvision separately avoids index issues where torch declares
# a dependency on cuda-toolkit, which can return 403 Forbidden on internal proxy mirrors.
if ! python3 -c "import torch, torchvision" >/dev/null 2>&1; then
  echo "📦 Installing PyTorch and torchvision..."
  python3 -m pip install --retries 5 --timeout 60 torch torchvision --extra-index-url https://download.pytorch.org/whl/cpu >/dev/null 2>&1 ||   python3 -m pip install --retries 5 --timeout 60 --no-deps torch torchvision ||   python3 -m pip install --retries 5 --timeout 60 torch torchvision || true
fi

# Install remaining dependencies from requirements.txt
if ! python3 -c "import transformers, huggingface_hub, PIL, cv2, sklearn" >/dev/null 2>&1; then
  echo "📦 Installing remaining dependencies via pip..."
  if [ -n "$VIRTUAL_ENV" ]; then
    python3 -m pip install --retries 5 --timeout 60 -r requirements.txt ||     python3 -m pip install --retries 5 --timeout 60 -r requirements.txt --break-system-packages || true
  else
    python3 -m pip install --retries 5 --timeout 60 -r requirements.txt --break-system-packages ||     python3 -m pip install --retries 5 --timeout 60 -r requirements.txt --user --break-system-packages ||     python3 -m pip install --retries 5 --timeout 60 -r requirements.txt --user ||     python3 -m pip install --retries 5 --timeout 60 -r requirements.txt || true
  fi
fi

# 8. Start FLINT Vision Engine
python3 app.py "$@"
