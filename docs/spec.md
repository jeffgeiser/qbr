# Zenlayer QBR Tracker - Technical Specification

## Overview

The Zenlayer QBR (Quarterly Business Review) Tracker is an internal web application used to manage customer account engagement, track QBR lifecycle progress, and generate AI-powered executive briefings. It is designed for account teams to plan, prepare for, and follow up on quarterly business reviews with key customers.

## Architecture

The application is a server-side rendered monolith with a single Python process, a SQLite database, and a modern interactive frontend layer.

```
┌──────────────────────────────────────────────────────┐
│                   Browser (Client)                    │
│    Alpine.js (reactivity) + Tailwind CSS (styling)   │
└───────────────────────┬──────────────────────────────┘
                        │  HTTP / SSE
┌───────────────────────▼──────────────────────────────┐
│                  FastAPI (Python)                      │
│   Jinja2 Templates · REST + SSE endpoints             │
├───────────────┬───────────────────────────────────────┤
│   SQLite DB   │   Services Layer                      │
│  (accounts,   │  ┌─────────────────────────────────┐  │
│   briefings)  │  │ briefing_generator.py            │  │
│               │  │  Claude AI tool-use orchestrator │  │
│               │  ├─────────────────────────────────┤  │
│               │  │ salesforce_mcp.py                │  │
│               │  │  Salesforce MCP client (stdio)   │  │
│               │  └─────────────────────────────────┘  │
└───────────────┴───────────────────────────────────────┘
```

## Stack

### Backend

| Component | Technology | Purpose |
|-----------|------------|---------|
| Web Framework | **FastAPI** | Async Python web framework. Serves HTML pages and API endpoints. |
| Template Engine | **Jinja2** | Server-side HTML rendering with template inheritance (`base.html` layout). |
| Database | **SQLite** | Lightweight embedded database. Schema migrations applied on startup. |
| AI Integration | **Anthropic Claude API** | Claude tool-use for agentic briefing generation. |
| Data Source | **Salesforce MCP** | Model Context Protocol client connecting to `@tsmztech/mcp-server-salesforce` via stdio transport. |
| Runtime | **Python 3.10** | Base runtime in Docker. |
| MCP Runtime | **Node.js 20** | Required for the Salesforce MCP server process (spawned as a child process). |

### Frontend

| Component | Technology | Purpose |
|-----------|------------|---------|
| Reactivity | **Alpine.js** (via CDN) | Lightweight JavaScript framework for client-side interactivity (expand/collapse, modals, forms, filters). |
| Styling | **Tailwind CSS** (via CDN) | Utility-first CSS framework. SaaS-modern design with rounded corners, soft shadows, gradients. |
| Streaming | **Server-Sent Events (SSE)** | Real-time updates during briefing generation (tool activity indicators, progress). |

### Infrastructure

| Component | Technology | Purpose |
|-----------|------------|---------|
| Containerization | **Docker** + **docker-compose** | Single-container deployment with volume-mounted SQLite. |
| ASGI Server | **Uvicorn** | Production ASGI server for FastAPI. |

## Project Structure

```
qbr/
├── main.py                          # FastAPI app, routes, DB logic
├── requirements.txt                 # Python dependencies
├── Dockerfile                       # Python 3.10 + Node.js 20
├── docker-compose.yml               # Container config with env vars
├── templates/
│   ├── base.html                    # Layout: auto-collapsing sidebar, nav
│   ├── dashboard.html               # Portfolio dashboard with expandable rows
│   ├── account_detail.html          # Account view + multi-section edit form
│   ├── briefings.html               # Chat-driven briefing generator
│   ├── briefing_internal.html       # Internal Health Brief result view
│   └── briefing_customer.html       # Customer QBR result view
├── services/
│   ├── __init__.py
│   ├── salesforce_mcp.py            # Salesforce MCP client
│   └── briefing_generator.py        # Claude AI tool-use orchestrator
├── docs/
│   ├── spec.md                      # This file
│   └── progress.md                  # Development progress log
└── DESIGN_PLAN.md                   # Original design mockups and plan
```

## Database Schema

### `accounts` Table

| Column | Type | Description |
|--------|------|-------------|
| `id` | TEXT PK | UUID |
| `name` | TEXT | Account name (max 35 chars) |
| `tier` | TEXT | Tier 1 / Tier 2 / Tier 3 |
| `owner` | TEXT | Account owner name |
| `health_sentiment` | TEXT | `green`, `yellow`, or `red` |
| `engagement_stage` | TEXT | Current QBR lifecycle stage (Scheduling, Content Prep, etc.) |
| `next_qbr_date` | TEXT | ISO date string |
| `qbr_q1` through `qbr_q4` | INTEGER | Legacy boolean completion flags (0/1) |
| `qbr_milestones` | TEXT | JSON: `{"q1": {"status": "completed", "date": "2026-01-15"}, ...}` |
| `key_learnings` | TEXT | Multi-line text |
| `next_steps` | TEXT | Multi-line text |
| `latest_update` | TEXT | Short status headline (max 50 chars) |
| `action_items` | TEXT | JSON array of strings |
| `contacts` | TEXT | JSON array: `[{"name", "email", "title", "linkedin"}]` |

### `briefing_results` Table

| Column | Type | Description |
|--------|------|-------------|
| `id` | TEXT PK | UUID |
| `account_id` | TEXT | Foreign key to accounts |
| `briefing_type` | TEXT | `internal` or `customer` |
| `time_range_days` | INTEGER | Lookback window (default 90) |
| `result_json` | TEXT | Full briefing output as JSON |
| `created_at` | TEXT | ISO timestamp |

## API Routes

| Method | Path | Description |
|--------|------|-------------|
| GET | `/` | Portfolio dashboard |
| GET | `/account/{id}` | Account detail/edit page |
| POST | `/save` | Create or update account (JSON or form data) |
| POST | `/delete/{id}` | Delete account |
| GET | `/briefings` | Briefing generator page |
| POST | `/api/briefings/generate` | SSE streaming endpoint for briefing generation |
| GET | `/briefings/{account_id}/{type}` | View a generated briefing result |

## Key Design Decisions

1. **Monolithic architecture**: Single `main.py` with Jinja2 templates — simple to deploy, no build step for frontend.
2. **Alpine.js over React**: Lightweight reactivity without a build pipeline. All interactivity is inline in templates.
3. **CSS-only sidebar collapse**: Uses Tailwind `group-hover/sidebar:` classes instead of JavaScript state for the auto-collapsing sidebar.
4. **Claude tool-use for briefings**: Claude autonomously decides which Salesforce queries to run via an agentic loop, rather than hardcoded query sequences.
5. **SSE streaming**: Provides real-time feedback during briefing generation (tool calls, progress indicators).
6. **JSON save endpoint**: The edit form uses `fetch()` with JSON body for structured data (milestones, contacts with multiple fields).

## Environment Variables

| Variable | Description |
|----------|-------------|
| `DB_PATH` | SQLite database file path (default: `/app/data/accounts.db`) |
| `ANTHROPIC_API_KEY` | API key for Claude AI |
| `SALESFORCE_CLIENT_ID` | Salesforce OAuth client ID |
| `SALESFORCE_CLIENT_SECRET` | Salesforce OAuth client secret |
| `SALESFORCE_INSTANCE_URL` | Salesforce instance URL |
