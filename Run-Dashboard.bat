@echo off
cd /d "%~dp0"
where conda >nul 2>&1
if errorlevel 1 (
  echo Open Miniforge Prompt, change to this extracted folder, and run Run-Dashboard.bat.
  pause
  exit /b 1
)
conda run -n cad-ai-checker python -c "import cadquery, streamlit, ezdxf, reportlab"
if errorlevel 1 (
  conda env update -f environment.yml
  if errorlevel 1 (
    pause
    exit /b 1
  )
)
conda run --no-capture-output -n cad-ai-checker python -m streamlit run app/main.py --server.address=127.0.0.1 --server.port=8501
pause
