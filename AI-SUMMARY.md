# Optional inspection summary

Run the CAD check first. Under **AI summary (optional)**, open **AI summary settings**, choose a provider, enter an accessible model ID and API key, then click **Generate AI Summary**. No request runs on upload, inspection, widget changes or download. No model is selected automatically.

The generated explanation appears in English and Japanese beneath the measured results. Both languages are included in subsequent PDF and JSON downloads, and the bilingual summary can be downloaded separately. Without a generated summary, existing reports work unchanged. A changed inspection invalidates the previous summary.

## Provider configuration

Session input can supply model/key. Alternatively, configure these environment variables on the server before starting Streamlit:

| Provider | API key | Model | Base URL |
|---|---|---|---|
| Gemini | `GEMINI_API_KEY` | `GEMINI_MODEL` | Fixed Google generateContent endpoint |
| OpenAI | `OPENAI_API_KEY` | `OPENAI_MODEL` | Fixed OpenAI Chat Completions endpoint |
| Open-source / compatible API | `CAD_SUMMARY_API_KEY` (optional for local servers) | `CAD_SUMMARY_MODEL` | `CAD_SUMMARY_BASE_URL`, including `/v1` where required |

Compatible endpoints must support Chat Completions JSON object output. Use HTTPS for remote servers. HTTP is supported only on localhost/loopback. A model running on your laptop is not the Codespace's localhost. The endpoint is administrator-configured rather than accepting arbitrary request destinations from dashboard visitors.

API keys belong in server secrets/environment or the password input, never Git or uploaded CAD files. Keys entered in the UI are held in the current Streamlit session. They are not included in reports. The optional request sends dimension values, result flags, reasons, selected figure IDs, scope and comparison basis. It excludes CAD file bytes, filenames and hashes. Reason text may contain engineering details; review provider suitability before submitting non-public inspections.

The CAD engine remains authoritative. Structured overall/per-dimension judgement conflicts are rejected; model text is still advisory and must be reviewed. Invalid responses, timeouts and unavailable providers produce a warning and do not suppress report downloads. The committed runtime limit permits two attempted requests per report/session and a 45-second request timeout. There is no automatic fallback or retry to another provider.

No real provider generation has been verified until a valid model/key or reachable local model is configured. Automated tests use simulated responses rather than actual paid requests.
