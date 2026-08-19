# CAD AI Checker

A browser-first prototype for checking whether a 2D DXF engineering drawing agrees with a 3D STEP/STP CAD model. Development runs entirely in GitHub Codespaces.

## Milestone status

Milestones 1–4 established the repository foundation, CAD readers, and DXF requirement interpretation. Milestone 5 adds basic 2D-to-3D feature matching:

- GitHub Codespaces development container with Python 3.11, CadQuery/OpenCASCADE, NumPy, Streamlit, ezdxf, and pytest.
- STEP/STP upload with a 25 MB prototype limit.
- Solid, shell, face, edge, and vertex counts.
- X/Y/Z bounding-box dimensions, volume, surface area, and center of mass.
- Planar face, cylindrical face, circular edge, outer-boundary, and likely-hole detection.
- DXF upload with the same 25 MB prototype limit.
- DXF version, drawing units, layer names, model-space entity counts, and drawing extents.
- Circle and arc geometry, TEXT/MTEXT annotations, and DIMENSION measurements.
- Separate Streamlit tabs for 3D STEP/STP and 2D DXF analysis.
- Normalized nominal dimensions with symmetric or asymmetric deviations.
- Supported tolerance formats including `±`, `+/-`, `+-`, and `+value/-value`.
- General-tolerance detection from DXF TEXT/MTEXT notes and application to dimensions without explicit tolerance.
- Calculated minimum and maximum dimensional limits.
- Diameter, radius, angle, ordinate, and linear dimension classification.
- Circle-based hole candidates with center coordinates and diameter.
- Clear warnings for unitless drawings, unresolved dimensions, missing tolerances, missing extents, and missing hole candidates.
- Paired DXF and STEP/STP upload in a dedicated matching dashboard tab.
- Unit conversion to millimetres for millimetres, centimetres, metres, inches, and feet.
- Low-confidence matching of DXF drawing extents to unique STEP bounding-box axes.
- Linear-dimension matching to unique STEP bounding-box axes.
- Diameter and radius matching to likely cylindrical STEP holes.
- Circle-candidate matching to likely STEP holes by diameter.
- Explicit matched, out-of-tolerance, missing-candidate, unsupported, and unmatched-3D statuses.
- Traceable differences, applied deviations, tolerance sources, confidence, and matching reasons.
- Synthetic STEP tests generated at runtime, so no CAD test files are committed.
- Synthetic DXF tests generated at runtime, including geometry, annotations, and a linear dimension.
- GitHub Actions continuous integration.
- Git ignore rules that prevent CAD uploads and common proprietary formats being committed.

Full pass/fail comparison rules and final engineering judgement are deliberately outside this milestone and begin in Milestone 6.

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

## Expected result

- `pytest -q` reports all project tests passing.
- Streamlit starts at `http://localhost:8501` inside the container and the Codespaces forwarded-port page displays **CAD AI Checker**.
- Uploading a valid small STEP/STP part displays its topology, dimensions, physical properties, and detected basic geometry.
- Uploading a valid small DXF drawing displays its layers, entity counts, extents, circles, arcs, dimensions, and text.
- The DXF dashboard also displays interpreted requirements, calculated limits, tolerance sources, drawing notes, and circle-based hole candidates.
- The matching dashboard accepts both files and displays basic size and hole matches with status, difference, tolerance, confidence, and reason.

## Milestone 5 limitations

- Hole matching uses diameter or radius only because STEP hole centers and axes are not yet retained.
- Drawing extents can include annotation geometry and therefore remain low-confidence matching inputs.
- Linear dimensions are matched only against overall STEP bounding-box axes in this milestone.
- Angular, ordinate, GD&T, datum, thread, surface-finish, and positional requirements remain unresolved.

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
