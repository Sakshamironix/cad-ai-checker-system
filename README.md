# CAD AI Checker — geometry-based dimension verification

This initial release compares native DXF dimensions with spatially corresponding
features in an explicitly selected STEP projection or an actual solid section.
It is a dimension checker, not full-shape, GD&T, or manufacturing release approval.

## Run

The repository's Conda environment supplies CadQuery/OpenCASCADE and the UI dependencies:

```bash
conda env create -f environment.yml
conda activate cad-ai-checker
python -m streamlit run app/main.py --server.address=0.0.0.0 --server.port=8501
```

In an existing configured Codespace:

```bash
git pull --ff-only origin main
bash scripts/start-dashboard.sh
```

The devcontainer post-start hook runs this idempotent startup script. It uses one
fixed port (8501), verifies Streamlit's health endpoint, and writes startup errors
to `.logs/dashboard.log`. A health endpoint alone does not prove a CAD check works.
Open the URL actually shown in the Codespace **Ports** tab; old Codespace URLs are
not permanent hosting. Port sharing remains controlled by GitHub/Codespaces.

## Checking a drawing

1. Upload millimetre DXF and STEP/STP files. Unitless DXF requires explicit mm confirmation.
2. Exclude centreline, construction, title, and border layers where needed. Inspect view
   separation; adjust the gap when disconnected geometry belongs to one figure.
3. Assign every native DIMENSION to exactly one figure. Dimensions outside the figure
   can be assigned manually. Unassigned/duplicate dimensions return NG, never a pass.
4. Choose a named STEP projection (visible outlines; hidden edges optional), or select
   an X/Y/Z plane and its **absolute STEP coordinate** for a true cross-section.
5. Inspect the grey DXF and amber STEP overlay. Set quarter-turn rotation and translation
   if necessary, then confirm the correspondence. The model is never scaled to fit.
6. Enable an explicit project fallback tolerance only if appropriate. Text tolerances and
   native DXF dimension-style tolerances take precedence. No implicit ±0.1 mm approval.
7. Run the check. Export the same authoritative result as CSV, JSON, or PDF.

### How measurements work

Linear/aligned dimensions reference the DXF extension-line origins. Those anchors
must correspond to drawing geometry, then uniquely associate spatially with
STEP projected vertices or circle centres/extrema. Linear distances are measured
along the dimension direction; aligned dimensions use endpoint distance.

Radius/diameter dimensions identify the drawn circle/arc by centre and radial anchor,
then require a unique spatially corresponding projected circle. Nominal dimension
text is used only in tolerance evaluation, never to select the STEP feature.

The association distance is a geometric search radius, not a pass tolerance.
Unresolved and ambiguous correspondences return `NG — Cannot verify`; numerical
out-of-limit measurements return `NG — Measured geometry is outside dimension limits`.
An OK means every assigned native dimension was verified, not that undimensioned
geometry or all manufacturing requirements were checked.

OpenCASCADE hidden-line projection includes curved silhouettes. Circular torus
silhouettes represented approximately by HLR are recovered from their corresponding
analytic STEP surface; there is no blanket torus pass. Sections use actual
plane/solid intersections, including blind-hole depth effects.

## Supported initial scope and limitations

- Native linear, aligned, diameter, and radius DXF dimensions in millimetres.
- Six orthographic views and axis-normal sections at user-selected offsets.
- Explicit symmetric/asymmetric text limits, native dimension-style limits, and an
  optional user-defined uniform fallback tolerance.
- Equal-size features are disambiguated by geometry, not numerical coincidence.
- Every view selection/alignment is operator-confirmed; automatic interpretation of
  arbitrary drawing cutting-plane labels is not claimed.
- Angular, ordinate, quantity/reference callouts, exploded dimensions, complex
  formatted tolerance text, GD&T, oblique/stepped cuts, arbitrary-angle alignment,
  and drawing detail-scale normalization are not verified in this release.
- Annotation geometry on the same layer as part geometry may require DXF cleanup.
- Radius dimensions on partially visible arcs without a unique circular projection
  require an appropriate section/view or return cannot verify.
- Preview and landmark sampling do not constitute a certified profile-tolerance test.

## Changes from the previous prototype

The active dashboard no longer calls the global nearest-number feature matcher,
legacy dimension mapper, generic profile-width/deviation tests, or the torus
semantic override. It has one dimension-result path shared by screen and exports.
Legacy modules are retained for compatibility tests and historical development;
they do not decide the new dashboard's result. AI explanations and unrelated
engineering summary panels were removed from the active checking flow.

## Validation

```bash
python -m pytest -q
python -m py_compile app/*.py
```

The geometry regression suite creates real STEP solids and DXF dimensions. It covers
matching/mismatching width, misleading dimension text, displaced holes, circular
measurements, actual blind-hole and torus sections, partial arcs, ambiguous anchors,
missing limits, file import through PDF export, and dashboard stale-result clearing.
Original user CAD files must still be validated before production use.
