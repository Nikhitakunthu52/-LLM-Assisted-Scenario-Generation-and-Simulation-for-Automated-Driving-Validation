#!/usr/bin/env bash
# Downloads the latest esmini release binaries into ./tools/esmini (Linux / macOS).
# Windows: download esmini-bin_Windows.zip from https://github.com/esmini/esmini/releases
# and set ESMINI_BIN to its bin folder.
set -euo pipefail
cd "$(dirname "$0")/.."
case "$(uname -s)" in
  Linux)  asset=esmini-bin_Linux.zip ;;
  Darwin) asset=esmini-bin_macOS.zip ;;
  *) echo "unsupported OS - download manually"; exit 1 ;;
esac
mkdir -p tools
curl -L -o tools/esmini.zip "https://github.com/esmini/esmini/releases/latest/download/$asset"
unzip -q -o tools/esmini.zip -d tools && rm tools/esmini.zip
echo "esmini installed. Add to .env:  ESMINI_BIN=$(pwd)/tools/esmini/bin"
