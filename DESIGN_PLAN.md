# QBR Site Redesign: Unified Dashboard + Executive Summary Generator

## Current State

The app is a **Zenlayer Account Engagement Tracker** — a single-page dashboard listing accounts in a table with expandable rows, plus an account detail/edit page. It's built on FastAPI + Alpine.js + Tailwind CSS with SQLite storage.

**Current navigation is flat:** Dashboard → Account Detail → Edit Mode. That's it.

---

## The Design Challenge

We need to add a fundamentally different capability — an **AI-powered Executive Summary Generator** that pulls data from Salesforce (and possibly M365), synthesizes it, and produces a PDF — while keeping the existing account tracking dashboard intact. These are two related but distinct workflows:

1. **Track & Manage** (existing) — ongoing account hygiene, QBR scheduling, health monitoring
2. **Research & Generate** (new) — on-demand deep-dive into an account for meeting prep

---

## Proposed Approach: Unified App with Contextual Navigation

Rather than bolting on a separate page, we unify both workflows under a single cohesive experience. The key insight: **the account is the anchor**. Both workflows start from the same place — an account — and diverge from there.

### Option A: Account-Centric Hub (Recommended)

The account detail page becomes a **hub with tabs/sections**, and "Generate Summary" becomes a first-class action you can take on any account.

```
┌─────────────────────────────────────────────────────────────────────┐
│  🔵 zenlayer                                    [Search]  [+ New]  │
│     ENGAGEMENT PLAN          Portfolio | Summary Generator          │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│  ┌─ Portfolio View (current dashboard, unchanged) ──────────────┐  │
│  │                                                               │  │
│  │  Key Account Engagement                                       │  │
│  │  Quarterly QBR tracking dashboard                             │  │
│  │                                                               │  │
│  │  [All] [Tier 1] [Tier 2] [Tier 3]    Health: [●] [●] [●]    │  │
│  │                                                               │  │
│  │  ┌──────────────────────────────────────────────────────────┐ │  │
│  │  │ Account    │ Update  │ QBR Q1-Q4  │ Next QBR │ Tier │ ⚡│ │  │
│  │  ├──────────────────────────────────────────────────────────┤ │  │
│  │  │ ● Zoom     │ ...     │ ○ ○ ○ ○    │ Mar 15   │ T1   │ ▶│ │  │
│  │  │ ● SpaceX   │ ...     │ ● ○ ○ ○    │ Apr 02   │ T1   │ ▶│ │  │
│  │  └──────────────────────────────────────────────────────────┘ │  │
│  └───────────────────────────────────────────────────────────────┘  │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘

  ⚡ = New "Generate Summary" quick-action button per row
  ▶  = Existing expand/detail behavior
```

### The Summary Generator Page

Accessible from:
- The **⚡ button** on any account row (pre-selects that account)
- The **"Summary Generator"** nav tab (starts with account selector)
- The **account detail page** (new "Generate Summary" button)

```
┌─────────────────────────────────────────────────────────────────────┐
│  🔵 zenlayer                                    [Search]  [+ New]  │
│     ENGAGEMENT PLAN          Portfolio | Summary Generator          │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│  Executive Summary Generator                                        │
│  Build a comprehensive account brief for QBRs and meetings         │
│                                                                     │
│  ┌─── Configuration ───────────────────────────────────────────┐   │
│  │                                                              │   │
│  │  Account    [  SpaceX                              ▾ ]      │   │
│  │                                                              │   │
│  │  Time Range [  Last 90 days                        ▾ ]      │   │
│  │                                                              │   │
│  │  Data Sources                                                │   │
│  │  ☑ Salesforce — Opportunities, Cases, Activities             │   │
│  │  ☑ M365 — Emails, Calendar, Teams                            │   │
│  │  ☑ QBR Tracker — Internal notes, health, contacts            │   │
│  │                                                              │   │
│  │  Focus Areas (optional)                                      │   │
│  │  ☐ Revenue & Pipeline    ☐ Support & Escalations             │   │
│  │  ☐ Engagement Cadence    ☐ Risks & Concerns                  │   │
│  │  ☐ Key Contacts Map      ☐ Product Usage                     │   │
│  │                                                              │   │
│  │               [ ⚡ Generate Executive Summary ]               │   │
│  └──────────────────────────────────────────────────────────────┘   │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
```

### Summary Results View

After generation, a rich results page appears below the config panel (or replaces it):

```
┌─────────────────────────────────────────────────────────────────────┐
│  🔵 zenlayer                                    [Search]  [+ New]  │
│     ENGAGEMENT PLAN          Portfolio | Summary Generator          │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│  Executive Summary: SpaceX               [ 📄 Export PDF ] [Edit]  │
│  Generated Feb 27, 2026 · Last 90 days                              │
│                                                                     │
│  ┌─── Account Snapshot ────────────────────────────────────────┐   │
│  │                                                              │   │
│  │  SpaceX                              Tier 1 │ ● Healthy     │   │
│  │  Owner: Josh Lipold                                          │   │
│  │  ARR: $2.4M  │  Open Opps: 3  │  Open Cases: 1              │   │
│  │  Last QBR: Dec 2025  │  Next QBR: Mar 2026                   │   │
│  │                                                              │   │
│  └──────────────────────────────────────────────────────────────┘   │
│                                                                     │
│  ┌─── Executive Summary ───────────────────────────────────────┐   │
│  │                                                              │   │
│  │  SpaceX continues to be a high-value strategic account       │   │
│  │  with strong engagement momentum. Revenue grew 18% QoQ       │   │
│  │  driven by expansion into APAC edge nodes. The Q4 QBR        │   │
│  │  surfaced interest in additional DDoS protection services.    │   │
│  │  One open support case (P2) around latency in LAX POP        │   │
│  │  is being actively worked. Key risk: champion Jonathan        │   │
│  │  Harrison may be transitioning roles...                       │   │
│  │                                                              │   │
│  └──────────────────────────────────────────────────────────────┘   │
│                                                                     │
│  ┌─ Recent Activity ──────┐  ┌─ Pipeline & Revenue ───────────┐   │
│  │                         │  │                                 │   │
│  │  📧 14 emails (90d)    │  │  ┌─────────────────────────┐   │   │
│  │  📞  6 calls           │  │  │  $2.4M ARR              │   │   │
│  │  📅  3 meetings        │  │  │  ████████████░░  87%    │   │   │
│  │  📋  2 cases           │  │  │  renewal confidence     │   │   │
│  │                         │  │  └─────────────────────────┘   │   │
│  │  Last Contact:          │  │                                 │   │
│  │  Feb 22 — Email from    │  │  Open Opportunities:            │   │
│  │  J. Harrison re: APAC   │  │  • DDoS Pro ($180K) - Stage 3  │   │
│  │  expansion timeline     │  │  • Edge Compute ($95K) - S2    │   │
│  │                         │  │  • Bandwidth Upgrade ($40K) S4 │   │
│  └─────────────────────────┘  └─────────────────────────────────┘   │
│                                                                     │
│  ┌─ Key Contacts ─────────┐  ┌─ Risks & Action Items ────────┐   │
│  │                         │  │                                 │   │
│  │  Jonathan Harrison      │  │  ⚠ Champion may be changing    │   │
│  │  VP Infrastructure      │  │    roles — confirm status       │   │
│  │  Last: Feb 22 (email)   │  │                                 │   │
│  │  Engagement: ●●●●○      │  │  ⚠ P2 case open > 14 days     │   │
│  │                         │  │    Escalate to engineering lead │   │
│  │  Sarah Chen             │  │                                 │   │
│  │  Dir. Network Ops       │  │  ✅ Schedule in-person QBR     │   │
│  │  Last: Feb 10 (call)    │  │     in Seattle (March)          │   │
│  │  Engagement: ●●●○○      │  │                                 │   │
│  └─────────────────────────┘  └─────────────────────────────────┘   │
│                                                                     │
│  ┌─ Talking Points for Next Meeting ───────────────────────────┐   │
│  │                                                              │   │
│  │  1. Congratulate on APAC expansion — position Zenlayer's     │   │
│  │     regional edge presence as a natural fit                   │   │
│  │  2. Address LAX POP latency issue — bring resolution update  │   │
│  │  3. Introduce DDoS Pro opportunity — align with their        │   │
│  │     growing security posture concerns                         │   │
│  │  4. Confirm Jonathan's role/succession for relationship      │   │
│  │     continuity planning                                       │   │
│  │                                                              │   │
│  └──────────────────────────────────────────────────────────────┘   │
│                                                                     │
│         [ ⚡ Regenerate ]   [ 📄 Export PDF ]   [ 💾 Save ]        │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
```

---

## Navigation Architecture

### Current
```
Nav: [Logo + Title]                              [Search] [+ New]

Routes:
  /qbr/                    → Dashboard
  /qbr/account/{id}        → Account Detail
  /qbr/account/{id}?edit   → Account Edit
```

### Proposed
```
Nav: [Logo + Title]    [Portfolio] [Summary Generator]   [Search] [+ New]

Routes:
  /qbr/                    → Portfolio Dashboard (existing, enhanced)
  /qbr/account/{id}        → Account Detail (existing + "Generate Summary" CTA)
  /qbr/summary             → Summary Generator (account selector)
  /qbr/summary/{id}        → Summary Generator (pre-selected account)
  /qbr/summary/{id}/result → Generated Summary View
```

The top nav gets **two persistent tabs**: "Portfolio" (the existing dashboard) and "Summary Generator" (the new feature). Clean, simple, discoverable.

---

## Design Principles

1. **Same visual language** — Both features share the same card-based, Tailwind-styled, Inter-font aesthetic. No jarring transitions.

2. **Account as the anchor** — Everything ties back to an account. The summary generator isn't a separate world; it's a tool you use *on* an account.

3. **Progressive disclosure** — The summary generator starts simple (pick account, click generate) and reveals rich detail. Don't overwhelm upfront.

4. **Live data, static output** — The generator pulls live data from Salesforce/M365, but the resulting summary is a snapshot you can export, save, and share.

5. **Edit-friendly** — The generated summary should be editable before export. AI gets you 80% there; the account manager fine-tunes the last 20%.

---

## Quick-Action Integration on Dashboard

Add a subtle but powerful shortcut directly on the dashboard table rows:

```
Before:
┌──────────┬──────────┬────────┬──────────┬──────┬───────┐
│ Account  │ Update   │ QBR    │ Next QBR │ Tier │ Owner │
├──────────┼──────────┼────────┼──────────┼──────┼───────┤
│ ● SpaceX │ Geiser...│ ● ○ ○ ○│ Mar 15   │ T1   │ Josh  │
└──────────┴──────────┴────────┴──────────┴──────┴───────┘

After:
┌──────────┬──────────┬────────┬──────────┬──────┬───────┬────────┐
│ Account  │ Update   │ QBR    │ Next QBR │ Tier │ Owner │        │
├──────────┼──────────┼────────┼──────────┼──────┼───────┼────────┤
│ ● SpaceX │ Geiser...│ ● ○ ○ ○│ Mar 15   │ T1   │ Josh  │ [⚡📄] │
└──────────┴──────────┴────────┴──────────┴──────┴───────┴────────┘
                                                           ↑
                                                  Quick-generate button
                                                  (appears on hover)
```

---

## PDF Export Design

The PDF should be a polished, boardroom-ready document:

```
┌─────────────────────────────────────────┐
│                                         │
│  ZENLAYER                               │
│  Executive Account Summary              │
│                                         │
│  SpaceX                                 │
│  Prepared: February 27, 2026            │
│  Account Owner: Josh Lipold             │
│                                         │
│  ─────────────────────────────────────  │
│                                         │
│  EXECUTIVE SUMMARY                      │
│  [AI-generated narrative paragraph]     │
│                                         │
│  ACCOUNT OVERVIEW                       │
│  Tier: 1 — Strategic                    │
│  Health: Healthy                        │
│  ARR: $2.4M                             │
│  Renewal: Aug 2026                      │
│                                         │
│  RECENT ACTIVITY (90 DAYS)              │
│  • 14 email exchanges                   │
│  • 6 calls / 3 meetings                 │
│  • 2 support cases (1 resolved)         │
│                                         │
│  PIPELINE                               │
│  [Table of open opportunities]          │
│                                         │
│  KEY CONTACTS                           │
│  [Contact cards with engagement level]  │
│                                         │
│  RISKS & RECOMMENDATIONS               │
│  [Bulleted risk items + actions]        │
│                                         │
│  TALKING POINTS                         │
│  [Numbered conversation starters]       │
│                                         │
│  ─────────────────────────────────────  │
│  Confidential — Zenlayer Internal       │
│                                         │
└─────────────────────────────────────────┘
```

---

## Technical Approach (High Level)

### Backend
- New FastAPI routes for `/summary`, `/summary/{id}`, `/summary/generate`
- MCP client integration for Salesforce queries (opportunities, cases, activities, contacts)
- Optional M365 MCP for email/calendar data
- AI summarization endpoint (Claude API or via MCP) to synthesize raw data into narrative
- PDF generation via `weasyprint` or `reportlab`

### Frontend
- Same Alpine.js + Tailwind approach for consistency
- New Jinja2 templates for the summary generator and results pages
- Streaming/loading state while summary generates (could take 10-30s with MCP calls)
- Contenteditable sections for post-generation editing
- Client-side print stylesheet as PDF fallback

### Data Flow
```
User selects account + options
        │
        ▼
FastAPI receives request
        │
        ├──→ Salesforce MCP: fetch opportunities, cases, activities
        ├──→ M365 MCP: fetch emails, meetings (optional)
        └──→ SQLite: fetch internal QBR tracker data
                │
                ▼
        Merge all data into context object
                │
                ▼
        AI summarization (Claude) — generate narrative,
        extract risks, suggest talking points
                │
                ▼
        Return structured summary to frontend
                │
                ▼
        Render rich results page
                │
        User reviews / edits
                │
                ▼
        [ Export PDF ]  [ Save to DB ]
```

---

## Summary: Why This Design Works

| Concern | Solution |
|---------|----------|
| Feature creep / UI clutter | Two clean tabs — user picks their workflow |
| Discoverability | Quick-action button on every row + persistent nav tab |
| Consistency | Same visual language, components, and layout grid |
| Speed to value | One click from dashboard → generating a summary |
| Flexibility | Works for formal QBR prep OR quick meeting background |
| Shareability | PDF export produces a standalone, polished document |
| Editability | Generated content is editable before export |
