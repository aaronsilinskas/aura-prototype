#!/usr/bin/env bash
# Download the CircuitPython mpy-cross binary for the current platform.
# The PyPI `mpy-cross` package is MicroPython's and produces incompatible .mpy files.
# Run once after checkout, and again whenever CircuitPython is upgraded.
#
# Usage: scripts/setup_mpy_cross.sh [version]
#   version defaults to the value in CIRCUITPYTHON_VERSION below.

set -euo pipefail

CIRCUITPYTHON_VERSION="${1:-10.2.1}"
DEST="$(cd "$(dirname "$0")/.." && pwd)/tools/mpy-cross"
BASE_URL="https://adafruit-circuit-python.s3.amazonaws.com/bin/mpy-cross"

OS="$(uname -s)"
ARCH="$(uname -m)"

case "$OS" in
  Darwin)
    PLATFORM="macos"
    case "$ARCH" in
      arm64)  SUFFIX="arm64" ;;
      x86_64) SUFFIX="x64"   ;;
      *)      echo "Unsupported macOS arch: $ARCH"; exit 1 ;;
    esac
    URL="$BASE_URL/macos/mpy-cross-${PLATFORM}-${CIRCUITPYTHON_VERSION}-${SUFFIX}"
    ;;
  Linux)
    case "$ARCH" in
      x86_64)  URL="$BASE_URL/linux-amd64/mpy-cross-linux-amd64-${CIRCUITPYTHON_VERSION}.static-amd64" ;;
      aarch64) URL="$BASE_URL/linux-aarch64/mpy-cross-linux-aarch64-${CIRCUITPYTHON_VERSION}.static-aarch64" ;;
      *)        echo "Unsupported Linux arch: $ARCH"; exit 1 ;;
    esac
    ;;
  *)
    echo "Unsupported OS: $OS"; exit 1 ;;
esac

mkdir -p "$(dirname "$DEST")"
echo "Downloading CircuitPython $CIRCUITPYTHON_VERSION mpy-cross..."
curl -fL "$URL" -o "$DEST"
chmod +x "$DEST"

VERSION="$("$DEST" --version 2>&1)"
echo "Installed: $VERSION"
echo "Binary: $DEST"
