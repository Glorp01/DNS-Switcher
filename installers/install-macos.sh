#!/usr/bin/env bash
set -euo pipefail

REPO="${DNS_SWITCHER_REPO:-Glorp01/DNS-Switcher}"
API_URL="https://api.github.com/repos/${REPO}/releases/latest"
APP_NAME="DNS Switcher.app"

case "$(uname -m)" in
  arm64|aarch64)
    ASSET_NAME="DNS-Switcher-macos-apple-silicon.zip"
    ;;
  x86_64)
    ASSET_NAME="DNS-Switcher-macos-intel.zip"
    ;;
  *)
    echo "Unsupported macOS architecture: $(uname -m)" >&2
    exit 1
    ;;
esac

TEMP_DIR="$(mktemp -d)"
cleanup() {
  rm -rf "${TEMP_DIR}"
}
trap cleanup EXIT

DOWNLOAD_URL="$(
  curl -fsSL "${API_URL}" | python3 - "${ASSET_NAME}" <<'PY'
import json
import sys

asset_name = sys.argv[1]
release = json.load(sys.stdin)

for asset in release.get("assets", []):
    if asset.get("name") == asset_name:
        print(asset["browser_download_url"])
        break
else:
    raise SystemExit(f"Could not find release asset: {asset_name}")
PY
)"

INSTALL_DIR="${INSTALL_DIR:-/Applications}"
if [[ ! -w "${INSTALL_DIR}" ]]; then
  INSTALL_DIR="${HOME}/Applications"
fi
mkdir -p "${INSTALL_DIR}"

ARCHIVE_PATH="${TEMP_DIR}/${ASSET_NAME}"
EXTRACT_DIR="${TEMP_DIR}/extracted"

echo "Downloading ${ASSET_NAME} from ${REPO}..."
curl -fL "${DOWNLOAD_URL}" -o "${ARCHIVE_PATH}"

mkdir -p "${EXTRACT_DIR}"
ditto -x -k "${ARCHIVE_PATH}" "${EXTRACT_DIR}"

APP_PATH="$(find "${EXTRACT_DIR}" -maxdepth 1 -name "*.app" -print -quit)"
if [[ -z "${APP_PATH}" ]]; then
  echo "The downloaded archive did not contain a macOS app bundle." >&2
  exit 1
fi

TARGET_PATH="${INSTALL_DIR}/${APP_NAME}"
rm -rf "${TARGET_PATH}"
cp -R "${APP_PATH}" "${TARGET_PATH}"
xattr -dr com.apple.quarantine "${TARGET_PATH}" 2>/dev/null || true

echo "Installed ${APP_NAME} to ${TARGET_PATH}"
open "${TARGET_PATH}"
