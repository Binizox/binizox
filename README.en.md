# Binizox

Binizox is a local-first personal knowledge and automation agent. It evolves from a pinned Yuxi source baseline while using an independent Binizox product, Python package, CLI, container, and configuration namespace.

The shipping flow is:

```text
document upload → PDF/DOCX parsing → server-side visibility filtering → Evidence
→ cited Agent answer → user-confirmed tool call → personal Markdown note
→ persisted Run/result/citations → Vue and SSE presentation
```

The runtime keeps Vue, FastAPI, PostgreSQL, Redis, MinIO, ARQ, LangGraph checkpoints, SSE, Skills, MCP, and an isolated parser sidecar. The former AsterDesk VPN approval prototype is no longer registered in the API, worker, UI, Skills, services, or schema bootstrap. Existing migrated database rows are not deleted.

## Local development

```powershell
Set-Location D:\Download\Binizox
.\scripts\conda-bootstrap.ps1 -InstallPlatform
Copy-Item .env.binizox.example .env.binizox.local
.\scripts\dev-infra-up.ps1
.\scripts\dev-parser.ps1
.\scripts\dev-tool-runner.ps1
.\scripts\dev-api.ps1
.\scripts\dev-worker.ps1
.\scripts\dev-web.ps1
```

See [the Chinese README](README.md), [design](docs/BINIZOX_DESIGN.md), [acceptance record](docs/BINIZOX_ACCEPTANCE.md), and [upstream inventory](docs/BINIZOX_UPSTREAMS.md).

## Attribution

Yuxi remains the MIT-licensed historical engineering baseline. RAGFlow parsing and DeerFlow frontmatter adaptations retain their respective notices. WeKnora, LibreChat, and DeepSeek Harness are research candidates or architecture references, not bundled runtimes. Exact commits and reuse boundaries are documented in `docs/`; the root [LICENSE](LICENSE) identifies Binizox, while required upstream copyright and MIT terms remain in [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).
