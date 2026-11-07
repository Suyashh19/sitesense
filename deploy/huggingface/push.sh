#!/usr/bin/env bash
# Deploy the committed HEAD of this repo to a Hugging Face Docker Space (creates the Space if needed).
#   deploy/huggingface/push.sh <hf-username>/<space-name>
# Auth: a write token (https://huggingface.co/settings/tokens) from HF_TOKEN, or else the login saved by
#   deploy/huggingface/.venv/bin/hf auth login
# Only committed files are deployed; .env and anything outside git are never included.
set -euo pipefail

SPACE="${1:?usage: $0 <user>/<space>}"
HERE="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(git -C "$HERE" rev-parse --show-toplevel)"
WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT

# Snapshot committed files; the Space needs its Dockerfile + README (with Space settings) at the root.
git -C "$ROOT" archive HEAD | tar -x -C "$WORK"
rm -rf "$WORK/docs" "$WORK/docker-compose.yml" "$WORK"/*.bat
cp "$HERE/Dockerfile" "$HERE/README.md" "$WORK/"

# huggingface_hub uploads binaries (models, parquet, images) through LFS/Xet automatically.
VENV="$HERE/.venv"
[ -x "$VENV/bin/python" ] || { python3 -m venv "$VENV" && "$VENV/bin/pip" install -q huggingface_hub; }

SPACE="$SPACE" WORK="$WORK" COMMIT="$(git -C "$ROOT" rev-parse --short HEAD)" "$VENV/bin/python" - <<'PY'
import os
from huggingface_hub import HfApi

api, space = HfApi(token=os.environ.get("HF_TOKEN") or None), os.environ["SPACE"]  # None = saved login
api.create_repo(space, repo_type="space", space_sdk="docker", exist_ok=True)
api.upload_folder(repo_id=space, repo_type="space", folder_path=os.environ["WORK"],
                  commit_message=f"Deploy {os.environ['COMMIT']}", delete_patterns=["*"])
print(f"Pushed. Build logs and app: https://huggingface.co/spaces/{space}")
print(f"Direct URL once built:      https://{space.replace('/', '-').replace('_', '-').lower()}.hf.space")
PY
