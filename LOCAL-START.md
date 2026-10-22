# CAD Checker: local dashboard

1. Extract the complete ZIP. Keep the app folder and launchers together.
2. Install Miniforge if Conda is not already installed.
3. Windows: open Miniforge Prompt in this folder and run `Run-Dashboard.bat`.
   macOS/Linux: open a Conda-enabled terminal here and run `bash Run-Dashboard.command`.
4. The first run installs the environment from environment.yml; it needs internet.
5. Open http://localhost:8501 on that same computer. Keep the terminal running.

After installation, checking does not require GitHub or an AI service. CAD uploads are processed on the computer running the dashboard. The launcher binds to loopback so it is accessible only on that computer.

## Checking workflow

Upload DXF and STEP, confirm millimetres where required, assign each drawing dimension to its figure, select the corresponding STEP projection or actual section, inspect alignment and confirm it, then check dimensions. Download CSV, JSON or PDF results.

Explicit drawing limits are used. Optional project tolerance applies only where enabled. Missing or ambiguous evidence is marked NG with a cannot-verify reason. The summary separates measured NG from cannot-verify rows. Undimensioned geometry and GD&T are not certified.

## Verification

The automated fixtures cover projections, actual sections, hole positions, radius/diameter checks, ambiguity, tolerance handling, report generation, and the dashboard workflow. Original customer parts still require validation.
