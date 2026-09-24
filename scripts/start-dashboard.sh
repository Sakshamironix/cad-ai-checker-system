#!/usr/bin/env bash
# Idempotent Codespaces startup on one stable port.
set -euo pipefail
cd "$(dirname "$0")/.."
mkdir -p .logs
exec 9>.logs/dashboard.lock
flock -n 9 || exit 0
PYTHON_BIN="${CAD_PYTHON:-python}"
if [[ -x /opt/conda/envs/cad-ai-checker/bin/python ]]; then
  PYTHON_BIN=/opt/conda/envs/cad-ai-checker/bin/python
fi
"$PYTHON_BIN" -m py_compile app/main.py app/geometry_check.py app/step_section.py
if curl --fail --silent http://127.0.0.1:8501/_stcore/health | grep -q '^ok$'; then
  echo 'Dashboard already responds on port 8501.'
  exit 0
fi
nohup "$PYTHON_BIN" -m streamlit run app/main.py --server.address=0.0.0.0 --server.port=8501 --server.headless=true >.logs/dashboard.log 2>&1 < /dev/null 9>&- &
for attempt in {1..20}; do
  if curl --fail --silent http://127.0.0.1:8501/_stcore/health | grep -q '^ok$'; then
    echo 'Dashboard responds on port 8501. Open its Codespaces Ports link.'
    exit 0
  fi
  sleep 1
done
echo 'Dashboard failed to start. See .logs/dashboard.log.' >&2
exit 1
