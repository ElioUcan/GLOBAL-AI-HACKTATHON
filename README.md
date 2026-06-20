# Yucatan Slang Jailbreak Benchmark

## Technologies

![PostgreSQL](https://img.shields.io/badge/PostgreSQL-316192?style=for-the-badge&logo=postgresql&logoColor=white)
![Grafana](https://img.shields.io/badge/Grafana-F46800?style=for-the-badge&logo=grafana&logoColor=white)
![n8n](https://img.shields.io/badge/n8n-EA4B71?style=for-the-badge&logo=n8n&logoColor=white)
![Docker](https://img.shields.io/badge/Docker-2CA5E0?style=for-the-badge&logo=docker&logoColor=white)
![Python](https://img.shields.io/badge/Python-3776AB?style=for-the-badge&logo=python&logoColor=white)
![NVIDIA NIM](https://img.shields.io/badge/NVIDIA%20NIM-76B900?style=for-the-badge&logo=nvidia&logoColor=white)

## Features

- **Attacker Agent** — generates adversarial prompts by embedding Yucatan/Mexican slang into harmful-intent requests using seven distinct attack techniques (translation transfer, semantic obfuscation, roleplay wrap, and more)
- **Target Agent** — swappable LLM under test; supports four NVIDIA NIM models out of the box with no code changes required
- **Judge Agent** — evaluates each response with a deterministic LLM call, returning a structured verdict (`jailbreak_success`, `confidence`, `severity`, `reasoning`)
- **PAIR Loop** — iterative multi-turn attack: the attacker refines its prompt based on judge feedback for up to five iterations, stopping early on a confirmed jailbreak
- **Regex Pre-filter** — short-circuits the Judge call when obvious harm keywords are detected, saving tokens and latency
- **PostgreSQL Storage** — every attack attempt, response, and verdict is persisted in a structured schema queryable across models, techniques, and harm categories
- **Grafana Dashboards** — live visualization of jailbreak success rates broken down by model, attack technique, and harm category

## Uses

This benchmark is used by AI safety researchers and hackathon teams to measure how well LLM safety filters resist adversarial prompts written in regional Mexican and Yucatecan slang. The goal is to surface alignment blind spots caused by underrepresented languages and dialects, producing quantifiable results that can inform model fine-tuning and safety evaluation pipelines.

## Process

The system is orchestrated entirely through n8n workflows: the Attacker Agent reads slang terms from PostgreSQL, calls an NVIDIA NIM LLM via API key to generate an adversarial prompt, forwards it to the Target LLM, then passes both prompt and response to the Judge Agent for scoring. All structured results are written back to PostgreSQL. Grafana connects directly to PostgreSQL to render live dashboards — no intermediate data pipeline needed. The entire stack runs locally in Docker Compose, making it reproducible across team members without any cloud infrastructure dependency.

## Running the project

**1. Configure environment**
```bash
cp .env.example .env
# Open .env and set NVIDIA_API_KEY to your NVIDIA NIM API key
```

**2. Start all services**
```bash
docker compose up -d --build
```

**3. Access the services**
```
n8n (workflow editor)  →  http://localhost:5678
Grafana (dashboards)   →  http://localhost:3000   (user: admin / pass: admin)
PostgreSQL             →  localhost:5432           (user: admin / db: slang_bench)
```

**Stopping the stack**
```bash
docker compose down
```

> All data is persisted in Docker volumes. To wipe and start fresh: `docker compose down -v`
