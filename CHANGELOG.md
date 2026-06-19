# Changelog

All notable changes to the Yucatan Slang Jailbreak Benchmark are documented here.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- Docker infrastructure: `compose.yml` orchestrating three services — MongoDB,
  n8n, and Grafana — on a shared `slang_net` bridge network.
- Per-service Dockerfiles under `docker/`:
  - `docker/mongodb/Dockerfile` — `mongo:7.0` with a first-boot init hook
    (`init/` mounted into `/docker-entrypoint-initdb.d/`).
  - `docker/n8n/Dockerfile` — `n8nio/n8n` plus the `n8n-nodes-mongodb` community node.
  - `docker/grafana/Dockerfile` — Grafana with the `haohanyang-mongodb-datasource`
    community plugin installed at build time.
- Grafana provisioning: MongoDB datasource and dashboard provider wired via
  `docker/grafana/provisioning/`.
- `.env.example` template documenting all configuration variables.

### Changed
- Switched results/corpus storage from PostgreSQL + pgvector to MongoDB.
- Restricted all LLM calls (attacker, targets, judge) to NVIDIA NIM only.
  Removed Gemini, Anthropic, Groq, and local Ollama configuration.
- Trimmed the `AGENTS.md` Supported Targets table to the four NVIDIA NIM models
  and updated the "Adding a New Target LLM" guide accordingly.
- Grafana dashboard mount now points at the `./grafana` directory instead of a
  single (possibly missing) JSON file.

[Unreleased]: https://example.com/compare/HEAD
