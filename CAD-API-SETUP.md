# CAD processing for ChatGPT Sites

## What is included

The Sites dashboard connects to this authenticated Python/OpenCASCADE API. It supports actual STEP projections, actual X/Y/Z plane intersections, drawing view segmentation, manual dimension-to-view assignment, rigid alignment, confirmation, and dimension checks using explicit or optionally enabled project tolerance. AI summaries are separate and are not implemented by this API.

## Start without GitHub

Use this source directory on a Linux server with Docker:

```bash
docker build -f Dockerfile.api -t cad-checker-api .
```

Create a private environment file outside the source directory containing:

```text
CAD_API_KEY=<random secret of at least 32 characters>
CAD_ALLOWED_ORIGINS=https://cad-checker-workbench.capable-creator.chatgpt.site
PORT=8000
```

Generate a token locally with `python -c "import secrets; print(secrets.token_urlsafe(48))"`. Keep it private. Then run, replacing the environment file path:

```bash
docker run -d --restart unless-stopped --name cad-api --env-file /secure/path/cad-api.env -p 127.0.0.1:8000:8000 cad-checker-api
```

Place an HTTPS reverse proxy in front of port 8000. Use a supported Docker host; a container/server with 4 GB RAM is a reasonable initial allocation for two concurrent CAD subprocesses, but benchmark your own parts. Configure a 52 MB maximum request body, 180-second proxy timeout, no upload/body logging, and no cache. Do not use an unauthenticated public proxy to expose this service. The API rejects requests without a valid token and requires Content-Length for POSTs. Configure the public URL in Sites under **Connect CAD engine**, enter the token, and select **Test connection**.

There is no hosted server provisioned by this package. The Sites frontend alone cannot execute this container.

## Endpoints

All requests require `Authorization: Bearer <token>`.

- `GET /health`: verifies the protocol and available operations.
- `POST /v1/analyze`: multipart `dxf`, `step`, `settings` (JSON). Returns drawing views, dimensions, layers and STEP bounds.
- `POST /v1/preview`: same upload plus selected views in settings. Returns actual SVG overlays.
- `POST /v1/check`: same upload/settings, with per-view confirmation. Returns the report and measured overlays.

CAD bytes are uploaded again per operation; no server session or durable CAD storage is used. Temporary files are removed after the response. Each operation executes in a subprocess with a configured 120-second timeout. There are at most two active CAD subprocesses per API process; run only one API worker. No third-party AI receives the CAD files. The client stores neither token nor CAD files persistently.

Changing model, drawing, alignment, assignments or tolerance clears the displayed CAD result. Changing geometry selection requires previewing and confirming again. A report does not certify undimensioned geometry or GD&T.

## Validation

`python -m pip install -r requirements-api.txt`

`python -m pytest tests/test_cad_api.py tests/test_geometry_check.py -q`

The API test executes real CAD subprocesses with generated DXF/STEP fixtures and covers passing measurements, a nonmatching projection, absent confirmation, out-of-part cuts, invalid options, upload limits, authentication and allowed-origin behavior. It does not validate customer CAD parts or a production host. The Docker definition is supplied; its image still needs to be built on the selected host.

## Temporary GitHub Codespaces pilot

The devcontainer now installs API dependencies and starts the Streamlit dashboard on 8501 and CAD API on 8000. For an existing Codespace, pull main, run `python -m pip install -r requirements-api.txt`, then `python scripts/run-cad-api.py` with the cad-ai-checker interpreter. The script creates a private, ignored access token file at `.logs/cad-api-key` and refuses to replace an unrelated service on port 8000.

Open the Ports panel and use the generated port 8000 address. Sites needs to reach that route without GitHub's interactive sign-in, while the API itself continues to require its bearer token. Port visibility must be configured deliberately in the Codespaces UI. Enter the route and the token into the private Site's connection panel; never commit the token. This remains temporary hosting: Codespaces stopping or quota exhaustion makes processing unavailable.
