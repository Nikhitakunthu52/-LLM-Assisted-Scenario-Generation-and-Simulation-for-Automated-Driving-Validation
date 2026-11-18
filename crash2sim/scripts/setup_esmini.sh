#!/usr/bin/env bash
# Downloads the latest esmini DEMO package (binaries + 3D car/road models) into ./tools/esmini-demo
# (Linux / macOS). Windows: download esmini-demo_Windows.zip from https://github.com/esmini/esmini/releases,
# unzip into tools/, and set ESMINI_BIN=tools\esmini-demo\bin in .env.
set -euo pipefail
cd "$(dirname "$0")/.."
case "$(uname -s)" in
  Linux)  asset=esmini-demo_Linux.zip ;;
  Darwin) asset=esmini-demo_macOS.zip ;;
  *) echo "unsupported OS - download manually"; exit 1 ;;
esac
mkdir -p tools
curl -L -o tools/esmini.zip "https://github.com/esmini/esmini/releases/latest/download/$asset"
unzip -q -o tools/esmini.zip -d tools && rm tools/esmini.zip
echo "esmini installed (with 3D models). Add to .env:  ESMINI_BIN=$(pwd)/tools/esmini-demo/bin"
