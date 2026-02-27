# QBR Site Redesign: Unified Platform with Dual Briefing Generator

## Current State

**Zenlayer Account Engagement Tracker** — FastAPI + Alpine.js + Tailwind CSS + SQLite.
Single workflow: Dashboard table → Account detail → Edit. Flat top-nav, no sidebar.

---

## What's Changing

1. **Collapsible left sidebar** replaces the flat top-nav as the primary navigation
2. **Briefing Generator** — a new first-class feature that produces two distinct document types from Salesforce data:
   - **Internal Executive Health Brief** — Candid, risk-focused, for internal leadership
   - **Customer-Facing QBR** — Professional, proactive, for presenting to the customer
3. **Salesforce MCP** is the data source: cases, contacts, pipeline/opportunities, deals won/lost, solution details
4. **PDF export** for both briefing types

---

## Navigation: Collapsible Left Sidebar

The current top navbar (logo + search + new account button) transforms into a sidebar-driven layout. The sidebar collapses to icons-only for maximum content space.

### Expanded Sidebar
```
┌──────────────────┬──────────────────────────────────────────────────┐
│                  │                                                  │
│  🔵 zenlayer     │                                                  │
│     Engagement   │           [main content area]                    │
│                  │                                                  │
│  ─────────────── │                                                  │
│                  │                                                  │
│  📊 Portfolio    │                                                  │
│                  │                                                  │
│  📄 Briefings    │                                                  │
│     ├ Internal   │                                                  │
│     └ Customer   │                                                  │
│                  │                                                  │
│  ─────────────── │                                                  │
│                  │                                                  │
│                  │                                                  │
│                  │                                                  │
│                  │                                                  │
│                  │                                                  │
│                  │                                                  │
│  « Collapse      │                                                  │
│                  │                                                  │
└──────────────────┴──────────────────────────────────────────────────┘
  ~200px wide                    remaining width
```

### Collapsed Sidebar
```
┌──────┬──────────────────────────────────────────────────────────────┐
│      │                                                              │
│  🔵  │                                                              │
│      │              [main content area — wider]                     │
│ ──── │                                                              │
│      │                                                              │
│  📊  │                                                              │
│      │                                                              │
│  📄  │                                                              │
│      │                                                              │
│      │                                                              │
│      │                                                              │
│      │                                                              │
│      │                                                              │
│  »   │                                                              │
│      │                                                              │
└──────┴──────────────────────────────────────────────────────────────┘
 ~56px                       remaining width
```

### Sidebar Navigation Items

| Icon | Label | Destination |
|------|-------|-------------|
| 📊 | Portfolio | Existing dashboard (account table, filters, stats) |
| 📄 | Briefings | Briefing generator with sub-items: |
| | ├ Internal Brief | Internal Executive Health Brief generator |
| | └ Customer QBR | Customer-Facing QBR generator |

The **Search bar** and **+ New Account** button move into the main content area header (contextual to the Portfolio view), keeping the sidebar clean and navigation-focused.

---

## Full Page Layouts

### 1. Portfolio View (Dashboard — Enhanced)

The existing dashboard, now framed within the sidebar layout. Search and New Account live in the content header.

```
┌──────────────────┬──────────────────────────────────────────────────────┐
│                  │                                                      │
│  🔵 zenlayer     │  Key Account Engagement         [Search] [+ New]    │
│     Engagement   │  Quarterly QBR tracking dashboard                    │
│                  │                                                      │
│  ─────────────── │  [All] [Tier 1] [Tier 2] [Tier 3]  Health: ● ● ●   │
│                  │                                                      │
│  📊 Portfolio  ← │  ┌────────────────────────────────────────────────┐  │
│                  │  │ Account  │ Update │ QBR    │ Next  │ Tier│Owner│  │
│  📄 Briefings    │  ├────────────────────────────────────────────────┤  │
│     ├ Internal   │  │ ● Zoom   │ ...    │ ○○○○   │ Mar15 │ T1  │ CM │  │
│     └ Customer   │  │ ● SpaceX │ ...    │ ●○○○   │ Apr02 │ T1  │ JL │  │
│                  │  │ ● Cisco  │ Will.. │ ○○○○   │ --    │ T1  │ JL │  │
│                  │  │ ● Zscaler│ ...    │ ○○○○   │ --    │ T1  │ CM │  │
│                  │  │   ...    │        │        │       │     │    │  │
│                  │  └────────────────────────────────────────────────┘  │
│                  │                                                      │
│  « Collapse      │                                                      │
│                  │                                                      │
└──────────────────┴──────────────────────────────────────────────────────┘
```

---

### 2. Briefing Generator — Landing / Account Selection

When the user clicks "Briefings" (or either sub-item) they land on the briefing generator. The first step is always: **pick an account, pick a briefing type**.

```
┌──────────────────┬──────────────────────────────────────────────────────┐
│                  │                                                      │
│  🔵 zenlayer     │  Account Briefing Generator                          │
│     Engagement   │  Generate executive briefings powered by Salesforce  │
│                  │                                                      │
│  ─────────────── │  ┌────────────────────────────────────────────────┐  │
│                  │  │                                                │  │
│  📊 Portfolio    │  │  Select Account                                │  │
│                  │  │  [ Zoom                                    ▾ ] │  │
│  📄 Briefings  ← │  │                                                │  │
│     ├ Internal   │  │  Time Range                                    │  │
│     └ Customer   │  │  [ Last 90 days                            ▾ ] │  │
│                  │  │                                                │  │
│                  │  └────────────────────────────────────────────────┘  │
│                  │                                                      │
│                  │  Choose Briefing Type                                 │
│                  │                                                      │
│                  │  ┌──────────────────────┐ ┌──────────────────────┐   │
│                  │  │                      │ │                      │   │
│                  │  │  🔒 INTERNAL         │ │  🤝 CUSTOMER         │   │
│                  │  │  Executive Health    │ │  Facing QBR          │   │
│                  │  │  Brief               │ │                      │   │
│                  │  │                      │ │                      │   │
│                  │  │  Candid risk         │ │  Professional        │   │
│                  │  │  assessment for      │ │  partnership review  │   │
│                  │  │  internal leadership │ │  for the customer    │   │
│                  │  │                      │ │                      │   │
│                  │  │  • At-risk scorecard │ │  • Partnership       │   │
│                  │  │  • Friction points   │ │    summary           │   │
│                  │  │  • Revenue at risk   │ │  • Performance       │   │
│                  │  │  • Internal red flags│ │    highlights        │   │
│                  │  │  • Action directives │ │  • Improvement plan  │   │
│                  │  │                      │ │  • Growth roadmap    │   │
│                  │  │  [ Generate Brief ]  │ │  • Joint action plan │   │
│                  │  │                      │ │                      │   │
│                  │  └──────────────────────┘ │  [ Generate QBR ]    │   │
│                  │                           │                      │   │
│  « Collapse      │                           └──────────────────────┘   │
│                  │                                                      │
└──────────────────┴──────────────────────────────────────────────────────┘
```

The two cards make the choice obvious and visual. Each card lists exactly what sections will be generated, setting expectations before the user clicks.

---

### 3. Internal Executive Health Brief — Results View

After generating, the user sees the candid, no-fluff internal assessment.

```
┌──────────────────┬──────────────────────────────────────────────────────┐
│                  │                                                      │
│  🔵 zenlayer     │  Internal Executive Health Brief     [PDF] [Edit]   │
│     Engagement   │  Zoom · Generated Feb 27, 2026 · Last 90 days       │
│                  │  ← Back to Briefings                                 │
│  ─────────────── │                                                      │
│                  │  ┌─ At-Risk Scorecard ──────────────────────────┐    │
│  📊 Portfolio    │  │                                              │    │
│                  │  │  BUSINESS OUTLOOK        ████░  4/5          │    │
│  📄 Briefings    │  │  SUPPORT HEALTH          ██░░░  2/5  ⚠      │    │
│   ▸ Internal   ← │  │  ENGAGEMENT CADENCE      ███░░  3/5          │    │
│     └ Customer   │  │  PIPELINE MOMENTUM       ████░  4/5          │    │
│                  │  │  RELATIONSHIP DEPTH       ███░░  3/5          │    │
│                  │  │                                              │    │
│                  │  │  Overall Health: CAUTION — Support risk is   │    │
│                  │  │  undermining an otherwise strong account     │    │
│                  │  │                                              │    │
│                  │  └──────────────────────────────────────────────┘    │
│                  │                                                      │
│                  │  ┌─ Friction Points & Escalations ─────────────┐    │
│                  │  │                                              │    │
│                  │  │  ⚠ Post-Maintenance Link-Down Pattern        │    │
│                  │  │    5 instances identified:                    │    │
│                  │  │    • Case #01734201 — MEX2/NYC1 down 4hrs   │    │
│                  │  │    • Case #01734387 — LAX POP post-maint    │    │
│                  │  │    • Case #01734512 — SIN1 link flap        │    │
│                  │  │    • Case #01734601 — FRA2 circuit drop     │    │
│                  │  │    • Case #01734733 — NYC1 recurring        │    │
│                  │  │                                              │    │
│                  │  │  🔴 Direct Customer Outburst                 │    │
│                  │  │    Joel Burt: "WHY? STILL DOWN" on case      │    │
│                  │  │    #01734733 — indicates eroding patience    │    │
│                  │  │                                              │    │
│                  │  └──────────────────────────────────────────────┘    │
│                  │                                                      │
│                  │  ┌─ Revenue Protection ─────┐ ┌─ Internal Red ────┐ │
│                  │  │                           │ │  Flags             │ │
│                  │  │  Pipeline at Risk: $220K+ │ │                    │ │
│                  │  │                           │ │  ⚠ Case #01734733 │ │
│                  │  │  • KSA IPT Expansion      │ │    stalled 12+    │ │
│                  │  │    $160K — at risk if      │ │    days — no      │ │
│                  │  │    reliability unsolved    │ │    escalation      │ │
│                  │  │                           │ │    workflow         │ │
│                  │  │  • DDoS Pro Add-on        │ │                    │ │
│                  │  │    $60K — champion         │ │  ⚠ Salesforce     │ │
│                  │  │    losing confidence       │ │    close dates     │ │
│                  │  │                           │ │    stale on 3      │ │
│                  │  │  Deals Won (period):      │ │    opportunities   │ │
│                  │  │  • APAC Edge ($95K) ✓     │ │                    │ │
│                  │  │                           │ │  ⚠ No standardized │ │
│                  │  │  Deals Lost: None         │ │    P1 escalation   │ │
│                  │  │                           │ │    protocol exists  │ │
│                  │  └───────────────────────────┘ └────────────────────┘ │
│                  │                                                      │
│                  │  ┌─ Internal Action Directives ────────────────┐    │
│                  │  │                                              │    │
│                  │  │  1. ⬜ Audit maintenance verification        │    │
│                  │  │        process for all Zoom circuits         │    │
│                  │  │  2. ⬜ Establish dedicated P1 escalation     │    │
│                  │  │        workflow for Tier 1 accounts          │    │
│                  │  │  3. ⬜ Unstall Case #01734733 — assign       │    │
│                  │  │        senior engineer, update customer      │    │
│                  │  │  4. ⬜ Refresh stale Salesforce close dates  │    │
│                  │  │        on KSA IPT, DDoS Pro, Bandwidth opps │    │
│                  │  │  5. ⬜ Schedule executive touchpoint with    │    │
│                  │  │        Zoom NOC leadership (damage control)  │    │
│                  │  │                                              │    │
│                  │  └──────────────────────────────────────────────┘    │
│                  │                                                      │
│                  │     [ Regenerate ]   [ Export PDF ]   [ Save ]       │
│                  │                                                      │
│  « Collapse      │                                                      │
│                  │                                                      │
└──────────────────┴──────────────────────────────────────────────────────┘
```

---

### 4. Customer-Facing QBR — Results View

The same underlying data, reframed as a professional, forward-looking partnership review.

```
┌──────────────────┬──────────────────────────────────────────────────────┐
│                  │                                                      │
│  🔵 zenlayer     │  Quarterly Business Review             [PDF] [Edit] │
│     Engagement   │  Zoom · Q1 2026 · Prepared Feb 27, 2026             │
│                  │  ← Back to Briefings                                 │
│  ─────────────── │                                                      │
│                  │  ┌─ Executive Summary of Partnership ──────────┐    │
│  📊 Portfolio    │  │                                              │    │
│                  │  │  Zoom is a strategically important account   │    │
│  📄 Briefings    │  │  with a global service portfolio spanning    │    │
│     ├ Internal   │  │  North America, Europe, Asia, and the       │    │
│   ▸ Customer   ← │  │  Middle East. This quarter has seen         │    │
│                  │  │  continued expansion into APAC markets and   │    │
│                  │  │  proactive investment in network resilience. │    │
│                  │  │  Zenlayer remains committed to delivering    │    │
│                  │  │  the performance and reliability that Zoom's │    │
│                  │  │  global operations demand.                   │    │
│                  │  │                                              │    │
│                  │  └──────────────────────────────────────────────┘    │
│                  │                                                      │
│                  │  ┌─ Operational Performance ───────────────────┐    │
│                  │  │                                              │    │
│                  │  │  Cases Handled This Period: 35               │    │
│                  │  │                                              │    │
│                  │  │  Resolution Highlights:                      │    │
│                  │  │  ✦ 12-minute resolution — LAX routing fix    │    │
│                  │  │  ✦ 4-hour turnaround — SIN1 failover        │    │
│                  │  │  ✦ 92% of cases resolved within SLA         │    │
│                  │  │                                              │    │
│                  │  │  Average Response Time: 18 minutes           │    │
│                  │  │  Customer Satisfaction: Excellent / 4.2★     │    │
│                  │  │                                              │    │
│                  │  └──────────────────────────────────────────────┘    │
│                  │                                                      │
│                  │  ┌─ Service Improvement Plan ──────────────────┐    │
│                  │  │  "We Hear You"                               │    │
│                  │  │                                              │    │
│                  │  │  Circuit Optimization                        │    │
│                  │  │  Formal RCA and carrier-level review for     │    │
│                  │  │  MEX2/NYC1 route to ensure future uptime.    │    │
│                  │  │  Target: 99.99% availability by Q2.         │    │
│                  │  │                                              │    │
│                  │  │  Named Account Support Protocol              │    │
│                  │  │  • Dedicated case queue for Zoom             │    │
│                  │  │  • Weekly case reviews with your team        │    │
│                  │  │  • Named senior engineer assignment          │    │
│                  │  │  • Priority P1 escalation path               │    │
│                  │  │                                              │    │
│                  │  └──────────────────────────────────────────────┘    │
│                  │                                                      │
│                  │  ┌─ Strategic Roadmap & Expansion ─────────────┐    │
│                  │  │                                              │    │
│                  │  │  Active Growth Initiatives:                  │    │
│                  │  │  • Global SDN — Phase 2 rollout in progress  │    │
│                  │  │  • DDoS Protection — Enhanced edge defense   │    │
│                  │  │  • Colocation — New builds in KSA region     │    │
│                  │  │                                              │    │
│                  │  │  Multi-Region Expansion:                     │    │
│                  │  │  ✓ APAC edge nodes — live                    │    │
│                  │  │  ◐ Middle East (KSA) — in progress           │    │
│                  │  │  ○ LATAM expansion — planning phase          │    │
│                  │  │                                              │    │
│                  │  └──────────────────────────────────────────────┘    │
│                  │                                                      │
│                  │  ┌─ Joint Action Plan ─────────────────────────┐    │
│                  │  │                                              │    │
│                  │  │  1. Executive touchpoint: Zenlayer VP Ops    │    │
│                  │  │     ↔ Zoom NOC Leadership (March)            │    │
│                  │  │  2. MEX2/NYC1 RCA delivery — target Mar 15  │    │
│                  │  │  3. Named support protocol kickoff — Mar 1   │    │
│                  │  │  4. KSA IPT expansion design review — Mar 20│    │
│                  │  │  5. Q2 QBR scheduled — June 2026             │    │
│                  │  │                                              │    │
│                  │  └──────────────────────────────────────────────┘    │
│                  │                                                      │
│                  │     [ Regenerate ]   [ Export PDF ]   [ Save ]       │
│                  │                                                      │
│  « Collapse      │                                                      │
│                  │                                                      │
└──────────────────┴──────────────────────────────────────────────────────┘
```

---

## The Two Briefing Types — Side by Side

### Internal Executive Health Brief

| Attribute | Detail |
|-----------|--------|
| **Goal** | Risk mitigation, internal accountability, resource allocation |
| **Tone** | Candid, urgent, no-fluff |
| **Audience** | Internal leadership, account team |
| **PDF Header** | "CONFIDENTIAL — Internal Use Only" |

**Sections:**
1. **At-Risk Scorecard** — 5-dimension radar: Business Outlook, Support Health, Engagement Cadence, Pipeline Momentum, Relationship Depth. Each scored 1-5 with visual bar.
2. **Friction Points & Escalations** — Raw case data surfacing patterns (e.g., post-maintenance link-down pattern with 5 specific instances). Includes direct customer quotes/outbursts.
3. **Revenue Protection** — Pipeline dollars tied to stability. Which deals are at risk and why.
4. **Internal Red Flags** — Process gaps: stalled cases, missing escalation workflows, stale Salesforce data.
5. **Internal Action Directives** — Concrete to-do list with checkboxes. Immediate, assignable, accountable.

### Customer-Facing QBR

| Attribute | Detail |
|-----------|--------|
| **Goal** | Demonstrate transparency, prove ROI, roadmap the future |
| **Tone** | Professional, proactive, committed to excellence |
| **Audience** | Customer stakeholders, decision makers |
| **PDF Header** | "Quarterly Business Review — Prepared for [Customer]" |

**Sections:**
1. **Executive Summary of Partnership** — High-level narrative acknowledging the customer as strategically important. Global portfolio scope.
2. **Operational Performance Transparency** — Volume metrics (cases handled), success highlights (best resolution times), SLA adherence. Honest but framed positively.
3. **Service Improvement Plan ("We Hear You")** — Reframes problems as improvement initiatives. "Circuit Optimization" not "circuit failures." Proposes Named Account Support Protocol.
4. **Strategic Roadmap & Expansion** — Aligns Zenlayer growth with customer expansion. SDN, DDoS, Colocation, multi-region.
5. **Joint Action Plan** — Collaborative next steps with dates and owners. Executive touchpoints, RCA deliveries, protocol kickoffs.

### Comparison Matrix

| Feature | Internal Brief | Customer QBR |
|---------|---------------|--------------|
| **Primary Focus** | Where are we failing? | How are we improving? |
| **Case Detail** | Stalled & poor resolutions | Exceptional wins & remediation |
| **Financials** | Pipeline at risk, stale dates | Expansion opportunities & roadmap |
| **Tone** | Critical & direct | Consultative & collaborative |
| **Contacts** | Internal owners & gaps | Joint stakeholder map |
| **Actions** | Internal directives (fix it) | Joint action plan (partner on it) |

---

## Salesforce MCP Data Requirements

All data comes from Salesforce MCP queries. No M365 for now.

| Salesforce Object | Used For | Internal Brief | Customer QBR |
|-------------------|----------|:-:|:-:|
| **Cases** | Support volume, P1s, resolution times, escalations, customer comments | ✓ | ✓ |
| **Contacts** | Key stakeholders, engagement mapping | ✓ | ✓ |
| **Opportunities** (open) | Pipeline, deal stages, amounts, close dates | ✓ | ✓ |
| **Opportunities** (won) | Recent wins, revenue validation | ✓ | ✓ |
| **Opportunities** (lost) | Churn signals, competitive pressure | ✓ | — |
| **Opportunity Products / Solutions** | What's deployed, expansion areas | ✓ | ✓ |
| **Activities / Tasks** | Engagement cadence, last touchpoints | ✓ | — |
| **Account** | Tier, owner, metadata | ✓ | ✓ |

---

## Navigation Architecture

### Routes

```
/qbr/                           → Portfolio Dashboard
/qbr/account/{id}               → Account Detail
/qbr/account/{id}?edit=true     → Account Edit
/qbr/briefings                  → Briefing Generator (account + type selection)
/qbr/briefings/{id}/internal    → Generate / View Internal Health Brief
/qbr/briefings/{id}/customer    → Generate / View Customer-Facing QBR
```

### Sidebar State

The sidebar remembers its collapsed/expanded state via localStorage. On mobile, it becomes a hamburger overlay.

```
Sidebar Items:
  📊  Portfolio          → /qbr/
  📄  Briefings          → /qbr/briefings
       ├ Internal Brief  → /qbr/briefings (pre-selects "Internal")
       └ Customer QBR    → /qbr/briefings (pre-selects "Customer")
```

### Entry Points to Generate a Briefing

1. **Sidebar → Briefings** — Full selection flow (pick account, pick type)
2. **Sidebar → Internal / Customer** — Pre-selects type, just pick account
3. **Account Detail Page** — New "Generate Briefing" button → pre-selects account
4. **Dashboard row** — Quick-action icon on hover → pre-selects account

---

## PDF Export Designs

### Internal Brief PDF

```
┌─────────────────────────────────────────┐
│                                         │
│  ZENLAYER — CONFIDENTIAL                │
│  Internal Executive Health Brief        │
│                                         │
│  Account: Zoom                          │
│  Period: Dec 2025 — Feb 2026 (90 days)  │
│  Prepared: February 27, 2026            │
│  Owner: Carlos Morell                   │
│                                         │
│  ═══════════════════════════════════════ │
│                                         │
│  AT-RISK SCORECARD                      │
│  Business Outlook     ████░  4/5        │
│  Support Health       ██░░░  2/5  ⚠     │
│  Engagement Cadence   ███░░  3/5        │
│  Pipeline Momentum    ████░  4/5        │
│  Relationship Depth   ███░░  3/5        │
│                                         │
│  FRICTION POINTS & ESCALATIONS          │
│  [Detailed case patterns + quotes]      │
│                                         │
│  REVENUE PROTECTION                     │
│  Pipeline at risk: $220K+               │
│  [Deal-by-deal breakdown]               │
│                                         │
│  INTERNAL RED FLAGS                     │
│  [Process gaps and stalled items]       │
│                                         │
│  ACTION DIRECTIVES                      │
│  ☐ [Numbered, assignable action items]  │
│                                         │
│  ─────────────────────────────────────  │
│  Confidential — Zenlayer Internal Only  │
│                                         │
└─────────────────────────────────────────┘
```

### Customer QBR PDF

```
┌─────────────────────────────────────────┐
│                                         │
│  ZENLAYER                               │
│  Quarterly Business Review              │
│  Prepared for Zoom                      │
│                                         │
│  Q1 2026                                │
│  February 27, 2026                      │
│  Account Team: Carlos Morell            │
│                                         │
│  ═══════════════════════════════════════ │
│                                         │
│  EXECUTIVE SUMMARY                      │
│  [Partnership narrative]                │
│                                         │
│  OPERATIONAL PERFORMANCE                │
│  Cases: 35 | Avg Response: 18 min       │
│  SLA Adherence: 92%                     │
│  [Highlight wins table]                 │
│                                         │
│  SERVICE IMPROVEMENT PLAN               │
│  [Circuit optimization details]         │
│  [Named Account Support Protocol]       │
│                                         │
│  STRATEGIC ROADMAP                      │
│  [Expansion initiatives + timeline]     │
│                                         │
│  JOINT ACTION PLAN                      │
│  [Numbered collaborative next steps]    │
│                                         │
│  ─────────────────────────────────────  │
│  Zenlayer — Your Edge in Global         │
│  Connectivity                           │
│                                         │
└─────────────────────────────────────────┘
```

---

## Loading / Generation State

Salesforce MCP calls + AI summarization will take 15-30 seconds. The loading state should be informative, not just a spinner.

```
┌──────────────────────────────────────────────────────────────┐
│                                                              │
│  Generating Internal Health Brief for Zoom...                │
│                                                              │
│  ✅ Fetching cases and support history...          Done      │
│  ✅ Pulling pipeline and opportunities...          Done      │
│  ⏳ Analyzing contacts and engagement...           Working   │
│  ○  Generating executive narrative...              Queued    │
│  ○  Building risk assessment...                    Queued    │
│                                                              │
│  ████████████░░░░░░░░  60%                                   │
│                                                              │
└──────────────────────────────────────────────────────────────┘
```

---

## Technical Data Flow

```
User selects account + briefing type
        │
        ▼
FastAPI /qbr/briefings/{id}/{type} (POST)
        │
        ├──→ Salesforce MCP: query Cases (by account, date range)
        ├──→ Salesforce MCP: query Opportunities (open, won, lost)
        ├──→ Salesforce MCP: query Contacts (by account)
        ├──→ Salesforce MCP: query Activities/Tasks
        ├──→ Salesforce MCP: query Opportunity Products/Solutions
        └──→ SQLite: fetch internal QBR tracker data
                │
                ▼
        Merge all data into unified context object
                │
                ▼
        AI Summarization (Claude API)
        ├──→ If type=internal: Use "internal health brief" prompt
        └──→ If type=customer: Use "customer QBR" prompt
                │
                ▼
        Return structured JSON with all sections
                │
                ▼
        Render results page (Jinja2 + Alpine.js)
                │
        User reviews / edits sections inline
                │
                ▼
        [ Export PDF ]  →  weasyprint renders HTML → PDF
        [ Save ]        →  Store to SQLite for later retrieval
        [ Regenerate ]  →  Re-run with same parameters
```

---

## Design Principles

1. **Same visual language** — Sidebar uses the same Inter font, slate palette, subtle borders. No design system clash.
2. **Two lenses, one truth** — Both briefings draw from the same Salesforce data. The AI prompt is what changes the lens, not the data.
3. **Candor vs. diplomacy** — The internal brief is deliberately uncomfortable. The customer QBR is deliberately reassuring. This contrast is the product's core value.
4. **Editable before export** — Every section supports inline editing. The AI gets you 80%; the account manager owns the final 20%.
5. **Progressive loading** — Show data as it arrives. Don't make users stare at a blank screen for 30 seconds.
6. **Sidebar scales** — The collapsible sidebar pattern accommodates future features (analytics, reports, settings) without redesigning navigation.
