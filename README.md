# CAD AI Checker

A browser-first prototype for checking whether a 2D DXF engineering drawing agrees with a 3D STEP/STP CAD model. Development runs entirely in GitHub Codespaces.

## Milestone 1 status

The repository foundation is complete:

- GitHub Codespaces development container with Python 3.11, CadQuery/OpenCASCADE, NumPy, Streamlit, ezdxf, and pytest.
- A minimal Streamlit application.
- A pytest smoke test.
- GitHub Actions continuous integration.
- Git ignore rules that prevent CAD uploads and common proprietary formats being committed.

STEP/STP upload and geometry extraction are deliberately not included yet; they are Milestone 2 work.

## Repository layout

```text
cad-ai-checker/
├── .devcontainer/             # Codespaces configuration
├── .github/workflows/         # Automated test workflow
├── app/                       # Streamlit application package
├── test_data/                 # Only deliberately created synthetic data
├── tests/                     # Automated tests
├── uploads/                   # Runtime uploads; ignored by Git
├── Dockerfile                 # Shared Codespaces image definition
├── environment.yml            # Reproducible Conda CAD environment
└── requirements.txt           # Pip packages used inside that environment
```

## Start in GitHub Codespaces

1. Create a private GitHub repository named `cad-ai-checker`.
2. Add these files to the repository and push them to the `main` branch.
3. On GitHub, select **Code → Codespaces → Create codespace on main**.
4. Wait for the development container build to finish. The first build installs CAD libraries and can take several minutes.
5. In the Codespaces terminal, run:

```bash
pytest -q
streamlit run app/main.py
```

Codespaces forwards port `8501`. Open the forwarded port in the browser when prompted.

## Expected Milestone 1 result

- `pytest -q` reports `1 passed`.
- Streamlit starts at `http://localhost:8501` inside the container and the Codespaces forwarded-port page displays **CAD AI Checker**.
- The page states that STEP/STP model reading is the next capability.

## If setup fails

Run these commands in the Codespaces terminal:

```bash
which python
python --version
python -c "import cadquery, ezdxf, streamlit; print('imports successful')"
```

Expected Python path: `/opt/conda/envs/cad-ai-checker/bin/python`.

If CadQuery cannot be imported, use the Codespaces Command Palette and select **Codespaces: Rebuild Container**. A container rebuild is required after changing `Dockerfile`, `environment.yml`, or `.devcontainer/devcontainer.json`.

If port 8501 does not open automatically, open the **Ports** tab in Codespaces, find port `8501`, and select the globe icon.
