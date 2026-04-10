# AI Content Engine

A local AI content workflow that turns a rough idea into a researched outline and source-grounded draft. Built on [Olostep](https://www.olostep.com/) for web research and page extraction, with a FastAPI backend, React frontend, and OpenAI-driven orchestration.

If you want to see how web research and page extraction fit into a real application flow, not just isolated scraping scripts, this repo is a small, composable reference you can run, read, and adapt.

![Blog Writer thumbnail](blog_writer.png)

---

## What this repo is

An open-source AI content engine with:

- a **FastAPI backend** for orchestration and WebSocket streaming
- a **React frontend** for chat-style interaction and live updates
- **OpenAI** for workflow orchestration and drafting
- **Olostep search** for natural-language web research and source discovery
- **[Olostep Scrapes](https://docs.olostep.com/api-reference/scrapes/create)** for clean page-level content extraction

It is designed as a reference implementation, not a polished product. The goal is a small, readable architecture that developers can plug into their own research, writing, or content automation pipelines.

---

## What the app does

For each content workflow, the app:

1. Collects the brief through a chat-style interaction
2. Turns the brief into a structured outline
3. Lets the user review or approve the outline before continuing
4. Researches the topic when source grounding is needed
5. Scrapes relevant pages for cleaner source material
6. Drafts the article grounded in collected sources
7. Supports revision cycles for both outline and draft
8. Streams live workflow updates to the frontend

---

## Which Olostep services this repo uses

### Search

The backend runs web research through Olostep's search capability and, in the current implementation, sends that research task to `POST /v1/answers`. This is how the app surfaces relevant sources and keeps research attached to the writing flow.

Use search when you want structured result discovery from a topic or question, without pre-knowing which URLs to target.

### Scrapes

The backend calls the [Olostep Scrapes API](https://docs.olostep.com/api-reference/scrapes/create) to extract clean content from URLs surfaced during research. Source material is converted to markdown and passed into downstream drafting steps.

Use Scrapes when you already have a URL and need clean, AI-ready content from that page.

> Olostep supports broader web scraping and crawling workflows across its platform. This repo uses only the parts needed for research and page-level extraction in a content workflow.

---

## How it works under the hood

The integration is straightforward to follow:

| File | What it does |
|---|---|
| `blog_agent/tools/search.py` | Calls Olostep `POST /v1/answers` for web research |
| `blog_agent/tools/scrape.py` | Calls Olostep `POST /v1/scrapes` for page extraction |
| `blog_agent/tools/tools.py` | Wraps both calls behind a shared tool provider |
| `blog_agent/agent/source_registry.py` | Stores source metadata so results can be reused across steps |
| `blog_agent/agent/blog_agent.py` | Orchestrates the brief -> outline -> draft -> revision flow |

---

## Quick Start

### Prerequisites

- Python 3.11+
- Node.js 18+
- npm
- Docker and Docker Compose (optional, for containerized setup)
- An `OPENAI_API_KEY`
- An `OLOSTEP_API_KEY` (required for web research and page extraction)

### 1. Create a `.env` file

```env
OPENAI_API_KEY=your_openai_api_key_here
OLOSTEP_API_KEY=your_olostep_api_key_here
OPENAI_MODEL=gpt-4.1-mini
LOG_LEVEL=INFO
```

### 2. Install backend dependencies

```bash
pip install -r requirements.txt
```

### 3. Start the backend

```bash
uvicorn blog_agent.main:app --reload --host 0.0.0.0 --port 8000
```

### 4. Install frontend dependencies

```bash
cd frontend
npm install
```

### 5. Start the frontend

```bash
npm run dev
```

Open the local URL printed by Vite, usually `http://localhost:5173`.

### 6. Run the full stack with Docker Compose

```bash
docker compose up --build
```

When running with Docker Compose:

- Frontend: `http://localhost:3000`
- Backend health check: `http://localhost:8000/health`
- Environment variables are read from the root `.env` file

---

## Project structure

```text
blog_agent/        Backend workflow, prompts, models, tools, and WebSocket server
frontend/          React + Vite frontend
Dockerfile         Backend container image
docker-compose.yml Local multi-service setup
```

---

## FAQ

**What is this repo for?**  
It is an open-source reference implementation of a source-grounded AI content workflow. It demonstrates how to combine web research and page-level data extraction inside a complete application, from brief to outline to draft.

**Can I reuse this for other agentic content extraction workflows?**  
Yes. The same orchestration, tool-wrapper, and source-registry patterns apply to research automation, report generation, lead enrichment, and other source-grounded AI systems.

---

## Related resources

- [Olostep homepage](https://www.olostep.com/)
- [Welcome to Olostep docs](https://docs.olostep.com/get-started/welcome)
- [Olostep Scrapes API - page-level data extraction](https://docs.olostep.com/api-reference/scrapes/create)
- [Olostep blog](https://www.olostep.com/blog)
- [Olostep Web Data API for AI Agents & RAG Pipelines](https://www.olostep.com/blog/olostep-web-data-api-for-ai-agents)
- [Web Scraping vs Web Crawling: What's the Difference](https://www.olostep.com/blog/web-scraping-vs-web-crawling)
- [How to Extract Table Data From a Website Without Breakage](https://www.olostep.com/blog/extract-table-data-from-website)

---