# Reproducible product demo

The portfolio video and screenshots are recorded from the real React/FastAPI/SQLite application.
No production account, personal document or pre-existing local database is read.

## Requirements

- Python 3.12 virtual environment at `.venv` with `requirements-dev.lock` installed
- Node.js 24 LTS and `npm ci --prefix frontend`
- Playwright Chromium, Google Chrome or Microsoft Edge

Install Playwright's preferred local browser once:

```powershell
npm --prefix frontend run demo:install
```

On platforms where the bundled browser is unavailable, the recorder falls back to an installed
Chrome or Edge browser.

## Record

```powershell
npm --prefix frontend run demo:record
```

The command performs the complete workflow:

1. Creates an operating-system temporary directory and disposable SQLite vault.
2. Applies every Alembic migration to that vault.
3. Starts FastAPI and Vite on dynamically allocated loopback ports.
4. Seeds the fictional `ada_demo` workspace through the public loopback API.
5. Opens a 1600×900 browser viewport and records a 1280×720 tour.
6. Visits the daily workspace, Career Vault, Resume Studio and application pipeline.
7. Fails on visible alerts, page exceptions, console errors or API responses with status 400+.
8. Produces the WebM, poster, animated preview and screenshots in `docs/assets/`.
9. Stops only the processes it started and deletes the verified temporary directory.

The final `careeros-demo.webm` must remain below 10 MiB. The committed tour is approximately
34 seconds and intentionally has no synthetic voice-over: short English chapter overlays make it
understandable while muted. A hackathon submission should still use the separate narrated
under-three-minute plan in `docs/devpost.md`.

## Outputs

| File | Purpose |
| --- | --- |
| `careeros-demo.webm` | Full GitHub product tour |
| `careeros-demo-poster.jpg` | Clickable README preview |
| `careeros-demo.gif` | Lightweight animated preview |
| `careeros-workspace.png` | Daily workspace capture |
| `careeros-vault.png` | Career Vault capture |
| `careeros-resume-studio.png` | Resume Studio capture |
| `careeros-applications.png` | Full application pipeline capture |

Set `CAREEROS_DEMO_HEADED=1` to watch the automated tour while developing it. Set
`CAREEROS_DEMO_PYTHON` only when the project virtual environment lives at a non-standard path.
