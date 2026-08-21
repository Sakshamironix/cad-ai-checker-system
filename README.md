# CAD AI Checker

A browser-first engineering prototype that compares a 2D DXF drawing with a 3D STEP/STP model. Development and trials run in GitHub Codespaces through a Streamlit dashboard.

## Current milestone

Milestone 11 adds guarded AI-assisted discrepancy explanations. The implemented workflow now provides:

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
- Optional OpenAI-enhanced explanations based only on normalized comparison evidence and drawing text.
- A hard boundary that prevents the explanation layer from changing deterministic OK/NG or evidence identity.

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
│   ├── profile_comparison.py  # Projected-shape comparison
│   ├── overlay.py             # SVG comparison overlay
│   ├── general_tolerances.py  # Background tolerance rule set
│   ├── ai_assistant.py        # Guarded bilingual discrepancy assistance
│   └── reporting.py           # JSON/PDF final reports
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

## Optional OpenAI enhancement

The local deterministic explanation works without credentials. To enable the optional enhanced explanation button, add an encrypted GitHub Codespaces secret named `OPENAI_API_KEY`, then rebuild or restart the Codespace. The OpenAI Python SDK reads this environment variable automatically. An optional `OPENAI_MODEL` environment variable can override the default model.

The optional request contains normalized judgement evidence, summaries, NG findings, drawing text, and known limitations. Raw DXF and STEP/STP file bytes are not sent by this feature. OpenAI API usage is billed separately from a ChatGPT subscription.

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
/opt/conda/envs/cad-ai-checker/bin/python -c "import cadquery, ezdxf, openai, reportlab, streamlit; print('imports successful')"
```

Expected Python environment:

```text
/opt/conda/envs/cad-ai-checker
```

If imports fail after dependency changes, rebuild the Codespace container from the Codespaces command palette. If the dashboard does not open, check that port `8501` is running and set to the required visibility in the **Ports** panel.
