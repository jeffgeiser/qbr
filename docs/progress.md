# Zenlayer QBR Tracker - Development Progress

## Phase 0: Foundation (Initial Build)

The application started as a basic account tracking tool built with FastAPI and inline HTML.

- **Initial scaffolding**: FastAPI app with inline HTML templates, Docker + docker-compose deployment
- **Account CRUD**: Create, read, update, delete accounts with name, tier, owner, health sentiment
- **QBR tracking**: Simple boolean checkboxes for Q1-Q4 completion
- **SQLite persistence**: Volume-mounted database with seed data (22 Zenlayer customer accounts)
- **Basic UI**: Table layout with health dot indicators, search, tier filters, expandable row details
- **Iterative UI refinements**:
  - Added sortable columns (Name, Tier, Owner)
  - Added health sentiment filters (green/yellow/red)
  - Accordion-style expandable rows with key learnings, contacts, action items
  - Account detail page with view/edit modes
  - Fixed column widths, wrapping, and responsive layout
  - Styled delete confirmation modal
  - Latest Update column and Next QBR date display

## Phase 1: Design Planning

Designed the architecture for adding AI-powered briefing generation alongside the existing portfolio tracker.

- **Created `DESIGN_PLAN.md`** with comprehensive ASCII mockups and architecture diagrams
- **Two-page architecture**: Portfolio dashboard + Briefing Generator, connected by a collapsible sidebar
- **Defined two briefing types**:
  - **Internal Executive Health Brief** — candid, risk-focused, for internal leadership (health scorecard, friction points, revenue protection signals, red flags, action directives)
  - **Customer-Facing QBR** — professional, diplomatic, for customer presentation (executive summary, performance metrics, improvement plan, roadmap alignment, joint action items)
- **Data source**: Salesforce MCP as the sole external data source (cases, contacts, pipeline, deals, activities)

## Phase 2: Briefing Generator Implementation

Built the full briefing generation system with Salesforce MCP integration and Claude AI orchestration.

### Sidebar Navigation
- **Auto-collapsing left sidebar** replacing top tab navigation
- CSS-only collapse using Tailwind `group-hover/sidebar:` classes (no JavaScript state)
- Two nav items: Portfolio and Briefings (flat, no sub-menus)
- Collapses to icon-only (56px) when mouse leaves, expands to full width (224px) on hover

### Jinja2 Template System
- **Extracted all inline HTML** from `main.py` into file-based Jinja2 templates
- `base.html` — shared layout with sidebar, Alpine.js + Tailwind CDN imports
- `dashboard.html` — portfolio table with filters, sorting, expandable rows
- `account_detail.html` — account view and edit form
- `briefings.html` — chat-driven briefing generator
- `briefing_internal.html` — internal health brief result view
- `briefing_customer.html` — customer QBR result view

### Chat-Driven Briefing Interface
- Two-step flow: user picks a briefing type card, then types customer name and timeframe in a chat field
- Natural language input (e.g., "Cisco for the last 90 days") rather than rigid dropdowns
- SSE streaming for real-time feedback:
  - `tool_start` / `tool_done` events show which Salesforce queries are running
  - `assistant_message` events stream Claude's thinking
  - `briefing_ready` event delivers the final structured result

### Salesforce MCP Client (`services/salesforce_mcp.py`)
- Uses the Python `mcp` SDK with `StdioServerParameters`
- Connects to `@tsmztech/mcp-server-salesforce` via stdio transport (requires Node.js)
- Methods: `get_account_cases()`, `get_open_opportunities()`, `get_closed_opportunities()`, `get_contacts()`, `get_activities()`, `get_account_info()`, `fetch_all_briefing_data()`

### Claude AI Tool-Use Orchestrator (`services/briefing_generator.py`)
- Defines 5 Salesforce tools for Claude (get cases, open opps, closed opps, contacts, activities)
- Distinct system prompts for internal vs. customer briefings
- Agentic loop: Claude autonomously decides which tools to call, receives results, iterates, then produces structured JSON output
- Streams SSE events throughout the process

### Docker Updates
- Added Node.js 20 to the Dockerfile (required for MCP server)
- Added environment variables for Anthropic API key and Salesforce credentials

## Phase 3: UI Component Rebuild (Current)

Major redesign of the dashboard expanded row and account edit form with SaaS-modern design patterns.

### Dashboard Expanded Row
- **Summary row**: Health dot + Account Name + Engagement Stage status badge (color-coded) + 3-state QBR tracker dots (green=completed, blue=scheduled, grey=not started)
- **QBR Status Timeline**: Horizontal stepper UI showing Q1-Q4 with circle icons (checkmark for completed, clock for scheduled), connector lines, status labels, and dates
- **Two-column grid**: Latest Update + Key Learnings (bulleted) on left; Primary Contact cards on right with avatar initials, name, job title, email link, and LinkedIn icon
- **Actions**: Gradient "Generate Briefing" button (blue-to-indigo) + bordered "Edit" button
- **Row-level quick action**: Lightning bolt icon on hover to jump to briefing generator

### Account Detail Edit Form
- **Multi-section modal-style layout** with section headers (Account Information, QBR Lifecycle Management, Stakeholders, Intelligence Inputs)
- **QBR Lifecycle Management**: Per-quarter cards with status dropdown (Not Started / Scheduled / Completed) and date picker
- **Enhanced Stakeholders**: 4-field grid per contact — Name, Email, Job Title, LinkedIn URL — with hover-reveal delete button
- **Engagement Stage**: Dedicated dropdown (Not Started, Scheduling, Content Prep, Deck Review, QBR Delivered, Follow-up Sent)
- **Health Sentiment**: Visual radio buttons with color-coded pill selectors
- **Intelligence Inputs**: Separate text areas for Latest Update (50 char max), Key Learnings, and Next Steps
- **JSON save**: Uses `fetch()` API with JSON body instead of legacy form submission

### Backend Data Model Updates
- Added `engagement_stage` column (TEXT)
- Added `qbr_milestones` column (JSON) — `{"q1": {"status": "completed", "date": "2026-01-15"}, ...}`
- Enhanced contacts model: each contact now has `name`, `email`, `title`, `linkedin`
- `row_to_account()` backfills milestones from legacy boolean QBR columns
- Save endpoint accepts both JSON body and legacy form data

## What's Next

- **End-to-end testing** of the briefing generation flow with live Salesforce credentials
- **PDF export** for generated briefings
- **Briefing history** — list of previously generated briefings per account
- **UI polish** — responsive design, loading states, error handling
