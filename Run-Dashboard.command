#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
if ! command -v conda >/dev/null 2>&1; then
  echo "Install Miniforge, then run this launcher from its terminal."
  read -r -p "Press Enter to close. "
  exit 1
fi
if ! conda run -n cad-ai-checker python -c "import cadquery, streamlit, ezdxf, reportlab"; then
  conda env update -f environment.yml
fi
exec conda run --no-capture-output -n cad-ai-checker python -m streamlit run app/main.py --server.address=127.0.0.1 --server.port=8501
