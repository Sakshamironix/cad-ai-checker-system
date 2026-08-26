# CAD AI Checker

## Milestone 16 — End-to-end validation and pilot hardening

The checker accepts DXF plus STEP/STP only. DXF drawing regions are segmented before
comparison so geometry from separate drawing views never combines. Unitless DXF values
are treated as millimetres; recorded unit metadata is retained and unsupported metadata
raises a warning. The deterministic engine selects orthographic STEP projections for
standard views and centre-plane candidates for full sections. A view that cannot be
classified or compared produces NG, never REVIEW. AI assistance can explain evidence
only and cannot change the deterministic OK/NG judgement.

Milestone 16 validates and hardens the completed deterministic workflow for pilot trials.
It adds configurable runtime limits, controlled bilingual errors, temporary-file cleanup,
safe diagnostics, report validation, an offline health check, and a restartable container.
Permanent public hosting remains Milestone 17.

Permanent hosting is scheduled for Milestone 17; the Codespaces Streamlit URL is only
available while its Codespace and process are running.

A browser-first engineering prototype that compares a 2D DXF drawing with a 3D STEP/STP model. Development and trials run in GitHub Codespaces through a Streamlit dashboard.

## Current milestone

Milestone 16 adds pilot validation and hardening. The implemented workflow now provides:

- STEP/STP topology, dimensions, physical properties, planar/cylindrical geometry, and likely-hole detection.
- DXF units, layers, extents, dimensions, text, circles, arcs, and normalized drawing requirements.
- Deterministic 2D-to-3D dimension and cylindrical-feature matching.
- Projected outer-profile and internal circular-profile comparison.
- Deterministic **OK** or **NG (Not Good)** judgement; there is no REVIEW state.
- Vector DXF/STEP overlay with red mismatch highlighting when an applicable tolerance exists.
- English/Japanese predefined dashboard text.
- A single operator choice for **General tolerance: Applied / Not applied**.
- Numerical general-tolerance values maintained only in the background rule set.
- Explicit drawing tolerances taking priority over background general-tolerance rules.
- Deterministic NG when no explicit limit exists and general tolerance is not applied.
- Ordered, downloadable JSON and PDF final reports.
- A bilingual local explanation for every completed check, including possible causes and recommended verification steps.
- Optional Gemini-primary explanations with automatic Groq fallback, based only on normalized comparison evidence and drawing text.
- A hard boundary that prevents the explanation layer from changing deterministic OK/NG or evidence identity.
- Split-arc reconstruction, concentric annular profile detection, and STEP torus extraction.
- Normalized `DIM-###` requirements with explicit, limit, symmetric, asymmetric, and unilateral tolerance parsing.
- STEP-geometry measurements for extents and likely through-hole diameters.
- Deterministic unique feature mapping; missing or ambiguous feature mappings are NG.
- Versioned `config/general_tolerances.json` validation and tolerance-priority resolution.
- Versioned `config/runtime_limits.json` for upload, topology, time and report limits.
- Container startup with a non-root user, health check and restart policy.
- Controlled bilingual DXF/STEP error messages with safe recovery guidance.
- Offline health checks that verify dependencies, configuration and temporary storage without calling AI providers.

## Final report order

1. Overall OK/NG judgement.
2. File identification.
3. General-tolerance application state.
4. Dimension summary.
5. Profile summary.
6. NG findings.
7. Assisted explanation and its safety notice.
8. Detailed dimension and profile evidence.
9. Visual-overlay evidence metadata.
10. Warnings and known limitations.

The report is a prototype engineering aid and is not production release approval.

## Repository layout

```text
cad-ai-checker-system/
├── .devcontainer/             # GitHub Codespaces configuration
├── .github/workflows/         # Automated pytest workflow
├── app/
│   ├── main.py                # Streamlit dashboard
│   ├── step_reader.py         # STEP/STP analysis
│   ├── dxf_reader.py          # DXF analysis
│   ├── drawing_interpreter.py # Drawing requirement normalization
│   ├── feature_matcher.py     # Dimension/feature matching
│   ├── dimension_mapping.py   # View-aware DXF-to-STEP mapping evidence
│   ├── step_measurements.py   # Geometry-derived STEP measurements
│   ├── tolerance_resolver.py  # Explicit/general tolerance priority
│   ├── tolerance_validation.py# Background-rule configuration validation
│   ├── runtime_limits.py      # Pilot processing-limit validation
│   ├── diagnostics.py         # Safe timing diagnostics
│   ├── error_catalog.py       # Bilingual controlled errors
│   └── health.py              # Offline readiness check
│   ├── profile_comparison.py  # Projected-shape comparison
│   ├── overlay.py             # SVG comparison overlay
│   ├── general_tolerances.py  # Background tolerance rule set
│   ├── ai_assistant.py        # Guarded bilingual discrepancy assistance
│   └── reporting.py           # JSON/PDF final reports
├── config/general_tolerances.json # Versioned background tolerance rules
├── tests/                     # Automated synthetic CAD tests
├── environment.yml            # Conda CAD environment
└── requirements.txt           # Pip dependencies
```

## Launch in GitHub Codespaces

Open the repository Codespace and run:

```bash
/opt/conda/envs/cad-ai-checker/bin/pytest -q
/opt/conda/envs/cad-ai-checker/bin/streamlit run app/main.py
```

Open forwarded port `8501`, select **Run CAD Check / CAD照合**, upload one DXF and one STEP/STP file, select the STEP projection and general-tolerance application state, and press **Run CAD Check / CAD照合を実行**.

After calculation, the dashboard displays:

- Overall OK/NG judgement.
- Dimension and profile summary.
- Combined vector overlay.
- Bilingual discrepancy explanation with possible causes and recommended checks.
- Detailed comparison evidence.
- JSON and PDF report download buttons.

## Milestone 16 pilot container

Build and start the restartable pilot container locally:

```bash
docker compose up --build
```

The dashboard is then available on `http://localhost:8501`. Store `GEMINI_API_KEY` and
`GROQ_API_KEY` only in the host or deployment secret store; never add them to files or
images. Verify the container without calling AI providers:

```bash
docker compose exec cad-ai-checker python scripts/healthcheck.py
```

For rollback, deploy the previously verified image tag, run the health check above, and
record the restored Git commit plus the runtime and tolerance-rule versions. Do not include
uploads or secrets in images, logs, reports or backups. Permanent HTTPS hosting is Milestone 17.

## Optional dual-provider AI enhancement

The local deterministic explanation works without credentials. To enable enhanced explanations, add encrypted GitHub Codespaces secrets named `GEMINI_API_KEY` and `GROQ_API_KEY`, then rebuild or restart the Codespace. Gemini is tried first; Groq is used automatically if Gemini fails. Optional `GEMINI_MODEL` and `GROQ_MODEL` environment variables can override the defaults.

The optional request contains normalized judgement evidence, summaries, NG findings, drawing text, and known limitations. Raw DXF and STEP/STP file bytes and API keys are never included in the request evidence or reports. Provider API usage may be billed separately.

## Expected test output

`pytest -q` should finish with all tests passing. Dependency deprecation warnings from CadQuery/pyparsing may still be displayed.

## Current known limitations

- Profile registration centers geometry and tests rotations only in 90-degree steps.
- Hole matching currently uses diameter/radius; complete hole-axis and center-position comparison is not implemented.
- Linear dimension matching currently relies on STEP bounding-box axes.
- Angular dimensions, GD&T, datums, threads, surface finish, and full positional requirements are not complete.
- The background general-tolerance table is provisional until the approved project rules are supplied.
- The PDF includes comparison evidence and overlay metadata, but not the rendered SVG graphic itself.
- AI-generated possible causes are hypotheses and require engineering verification; they never change OK/NG.

## Diagnose setup errors

Run:

```bash
which python
/opt/conda/envs/cad-ai-checker/bin/python --version
/opt/conda/envs/cad-ai-checker/bin/python -c "import cadquery, ezdxf, reportlab, streamlit; print('imports successful')"
```

Expected Python environment:

```text
/opt/conda/envs/cad-ai-checker
```

If imports fail after dependency changes, rebuild the Codespace container from the Codespaces command palette. If the dashboard does not open, check that port `8501` is running and set to the required visibility in the **Ports** panel.
