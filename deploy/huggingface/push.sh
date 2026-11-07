#!/usr/bin/env bash
# Deploy the committed HEAD of this repo to a Hugging Face Docker Space (creates the Space if needed).
#   HF_TOKEN=hf_xxx deploy/huggingface/push.sh <hf-username>/<space-name>
# The token needs write access (https://huggingface.co/settings/tokens).
# Only committed files are deployed; .env and anything outside git are never included.
set -euo pipefail

SPACE="${1:?usage: HF_TOKEN=... $0 <user>/<space>}"
: "${HF_TOKEN:?set HF_TOKEN to a Hugging Face write token}"
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

api, space = HfApi(token=os.environ["HF_TOKEN"]), os.environ["SPACE"]
api.create_repo(space, repo_type="space", space_sdk="docker", exist_ok=True)
api.upload_folder(repo_id=space, repo_type="space", folder_path=os.environ["WORK"],
                  commit_message=f"Deploy {os.environ['COMMIT']}", delete_patterns=["*"])
print(f"Pushed. Build logs and app: https://huggingface.co/spaces/{space}")
print(f"Direct URL once built:      https://{space.replace('/', '-').replace('_', '-').lower()}.hf.space")
PY
