# Agent Inventory — Sources, Logic & Decision Thresholds

Last updated: 2026-04-18

---

## 1. Account Pulse

**Purpose:** Continuous health monitoring per account

### Data Sources

| Source | Salesforce Object | Query |
|--------|-------------------|-------|
| Cases | `Case` | `Account.Name = X AND CreatedDate >= {90d ago}`, ordered by CreatedDate DESC |
| Open Pipeline | `Opportunity` | `Account.Name = X AND IsClosed = false`, ordered by Amount DESC |
| Closed-Won | `Opportunity` | `Account.Name = X AND IsClosed = true AND CloseDate >= {90d ago}`, filtered IsWon = true |
| Closed-Lost | `Opportunity` | `Account.Name = X AND IsClosed = true AND CloseDate >= {90d ago}`, filtered IsWon = false |
| Activities | `Task` | `Account.Name = X AND CreatedDate >= {90d ago}`, ordered by ActivityDate DESC, limit 50 |

### Decisions & Thresholds

| Insight | Threshold | Priority |
|---------|-----------|----------|
| Critical cases open | Priority = Critical/High AND Status != Closed/Resolved | HIGH |
| High case volume | > 5 open cases | MEDIUM |
| Closed-won momentum | Any won deals in time range | INFO |
| Lost deals | Any lost deals in time range | HIGH |
| Stalled deals | Open opps with no NextStep field | MEDIUM |
| Low engagement | < 2 activities in time range | MEDIUM |
| Stable (all clear) | None of the above triggered | INFO |
| Must-win boost | Account flagged must-win: MEDIUM becomes HIGH, HIGH becomes CRITICAL | — |

---

## 2. QBR Composer

**Purpose:** Generate formal Internal Health Briefs or Customer-Facing QBRs

### Data Sources

| Source | Salesforce Object | Query |
|--------|-------------------|-------|
| Account Info | `Account` | `Name = X`, fields: Type, Industry, Revenue, Owner |
| Cases | `Case` | Same as Account Pulse |
| Opportunities | `Opportunity` | Open + Closed, same queries |
| Contacts | `Contact` | `Account.Name = X`, fields: Name, Email, Title, Department |
| Activities | `Task` | Same as Account Pulse |

### Decisions

| Decision | Logic | Output |
|----------|-------|--------|
| Route to LLM | Sends all data + system prompt (Internal or Customer template) | Structured JSON briefing |
| Tool-use loop | LLM chooses which Salesforce queries to run, up to 10 iterations | — |
| Force tool call | Iteration 0: `tool_choice = "required"` to ensure data gathering | — |
| Fallback | If Salesforce down, uses local tracker DB data | Same JSON structure |

### Output Types
- **Internal Brief:** Executive snapshot, revenue picture, engagement activity, strategic risks, recommended actions, health scorecard (5 dimensions, 1-5 scale)
- **Customer QBR:** Executive summary, key stats, performance metrics, highlights, improvement plan, expansion initiatives, joint action plan

---

## 3. Meeting Prep

**Purpose:** Pre-call briefing with talking points, landmines, and recommended asks

### Data Sources

| Source | Object/API | Query |
|--------|-----------|-------|
| Cases | `Case` | Same as Account Pulse, limit 10 records |
| Opportunities | `Opportunity` | All (open + closed), limit 10 |
| Contacts | `Contact` | All for account, limit 10 |
| Activities | `Task` | Same as Account Pulse, limit 10 |
| Account Info | `Account` | Same as QBR Composer, limit 5 |
| **News** | **Google News RSS** | `https://news.google.com/rss/search?q={company_name}`, up to 5 articles |

### Decisions

| Decision | Logic | Output |
|----------|-------|--------|
| LLM synthesis | All 6 sources sent to LLM with structured prompt | JSON brief |
| News into talking points | LLM instructed to weave news into talking points | e.g. "Reference their $2B expansion announcement" |
| Fallback | If LLM down, extract key fields directly + news headlines as talking points | Same JSON structure |

### Output Sections
Account summary, recent news, recent activity, open issues, pipeline status, key contacts, talking points, landmines, recommended asks

---

## 4. Deal Strategist

**Purpose:** Pipeline analysis, deal coaching, competitive signals

### Data Sources

| Source | Salesforce Object | Query |
|--------|-------------------|-------|
| Opportunities | `Opportunity` | All (open + closed), up to 15 records |
| Contacts | `Contact` | All for account, up to 10 |
| Account Info | `Account` | Same fields as QBR Composer, up to 3 |

### Decisions & Thresholds

| Insight | Logic | Priority |
|---------|-------|----------|
| No pipeline | Zero open opportunities returned | INFO |
| Deals at risk | LLM scores each deal risk_level as high or critical | HIGH |
| Pipeline healthy | LLM finds no high/critical risk deals | INFO |
| Quick wins | LLM identifies low-effort actionable opportunities | MEDIUM |
| Stalled deals (fallback) | If LLM down: open opps with no NextStep field | MEDIUM |
| Must-win boost | MEDIUM becomes HIGH for must-win accounts | — |

### LLM Analysis Dimensions
Per-deal: risk level, risk factors, recommended actions, stakeholder gaps, win strategy. Portfolio: risks, quick wins, competitive signals.

---

## 5. Customer Voice

**Purpose:** Support pattern analysis, escalation prediction

### Data Sources

| Source | Salesforce Object | Query |
|--------|-------------------|-------|
| Cases | `Case` | `Account.Name = X AND CreatedDate >= {90d ago}` — Subject, Status, Priority |

### Decisions & Thresholds

| Insight | Threshold | Priority |
|---------|-----------|----------|
| Escalation risk | Open cases with Priority Critical/High >= 3 (configurable) | CRITICAL |
| Backlog growing | Total cases > 10 AND open ratio > 40% | MEDIUM |
| Recurring themes | Keyword clustering on case Subjects, 3+ occurrences per keyword | MEDIUM |
| Support health normal | None of the above triggered | INFO |
| Must-win boost | MEDIUM becomes HIGH for must-win accounts | — |

### Keyword Clustering Method
Splits each case Subject into words, filters noise words (common English words plus "case", "issue", "request", "ticket", "support", "help", etc.), counts frequency of remaining significant words (length > 2 characters). Themes with 3+ occurrences are reported.

---

## 6. Industry News

**Purpose:** Monitor public news about customer companies

### Data Sources

| Source | API | Query |
|--------|-----|-------|
| Google News RSS | `https://news.google.com/rss/search?q={company_name}&hl=en-US&gl=US&ceid=US:en` | Up to 3 articles per account (configurable) |

### Decisions

| Insight | Logic | Priority |
|---------|-------|----------|
| News found | Each article becomes one InsightCard | LOW |
| Must-win boost | LOW becomes MEDIUM for must-win accounts | — |
| No news | No card generated (silent skip) | — |

### Data Extracted Per Article
Title, source publication, publish date, snippet (first 200 chars of description, HTML stripped)

---

## 7. Account Digest

**Purpose:** Periodic summary of account changes, pushed to Microsoft Teams

### Data Sources

| Source | Salesforce Object | Query |
|--------|-------------------|-------|
| Cases | `Case` | Same as Account Pulse — counts new and open |
| Open Opps | `Opportunity` | `IsClosed = false` — counts deals |
| Activities | `Task` | Same as Account Pulse — counts volume |

### Decisions

| Decision | Logic | Output |
|----------|-------|--------|
| Has changes | Account has any cases, opps, or activities in time range | Included in digest |
| Critical alert | Cases with Priority Critical/High and Status not Closed/Resolved | Flagged in digest |
| Teams push | If `teams_webhook_url` configured in agent config | MessageCard to Teams channel |
| No webhook | Digest still appears as in-app InsightCard | Feed only |

### Teams MessageCard Format
Per-account sections with: New Cases count, Open Cases count, Pipeline Deals count, Activities count, Alert text (if critical cases exist)

---

## 8. Executive Pulse

**Purpose:** Portfolio-wide health summary for VP/EVP of Sales

### Data Sources

| Source | Object | Query |
|--------|--------|-------|
| Accounts DB | Local `accounts` table | All accounts in focus tiers (default: Tier 1 + Tier 2) |
| Cases | `Case` per account | Same query, filtered for Critical/High open |
| Open Opps | `Opportunity` per account | `IsClosed = false` — count per account |
| Closed-Lost | `Opportunity` per account | `IsClosed = true, CloseDate >= {90d ago}`, IsWon = false |
| Activities | `Task` per account | Same query — flags accounts with < 2 |

### Decisions & Thresholds

| Insight | Threshold | Priority |
|---------|-----------|----------|
| Portfolio overview | Aggregates health (green/yellow/red) across all focus-tier accounts | INFO (or HIGH if any red) |
| Critical case concentration | Accounts with any open Critical/High cases | HIGH |
| Tier 1 no engagement | Tier 1 accounts with < 2 activities in time range | HIGH |
| General low engagement | Non-Tier 1 accounts with < 2 activities | MEDIUM |
| Lost deal trend | Any accounts with closed-lost deals in time range | MEDIUM |
| Teams push | If `teams_webhook_url` configured | Executive MessageCard |

### Scope
Default focus tiers: Tier 1 + Tier 2 (configurable). Tier 3 accounts excluded unless focus_tiers config is changed. Currently tracks 20 accounts (12 Tier 1 + 8 Tier 2).

---

## Cross-Cutting Behaviors

| Behavior | Applies To | Logic |
|----------|-----------|-------|
| **Must-win boost** | Account Pulse, Customer Voice, Deal Strategist | If account is in user's must-win list: MEDIUM→HIGH, HIGH→CRITICAL |
| **Account name resolution** | All Salesforce queries | Fuzzy match: exact first, then LIKE `%name%`, prefer startsWith match |
| **Salesforce fallback** | QBR Composer, Account Pulse | If Salesforce disconnected, uses local tracker DB (limited data) |
| **LLM fallback** | Meeting Prep, Deal Strategist, QBR Composer | If Qwen LLM unavailable, rule-based extraction from raw data |
| **Result truncation** | All Salesforce queries | Tool results capped at 4KB to stay within LLM context window |
| **Per-user scoping** | All agents | Insights saved per user_id, feed filtered per user |
| **Per-insight explanation** | All agents | Every InsightCard includes a `logic_explanation` describing exactly what was queried and what threshold triggered it, visible via (i) tooltip in the UI |

---

## Integration Connectors

| Connector | Protocol | Auth | Capabilities |
|-----------|----------|------|-------------|
| **Salesforce** | MCP via stdio (Node.js subprocess) | OAuth 2.0 Client Credentials | cases, opportunities, contacts, activities, account_info |
| **Google News** | HTTP GET (RSS/XML) | None (public) | news articles by company name search |
| **Microsoft Teams** | HTTP POST (Incoming Webhook) | Webhook URL per user | MessageCard notifications |

---

## LLM Configuration

| Setting | Default | Used By |
|---------|---------|---------|
| `LOCAL_LLM_URL` | `http://10.1.0.251:18010/v1/` | QBR Composer, Meeting Prep, Deal Strategist, Command Router |
| `LOCAL_LLM_MODEL` | `Qwen/Qwen3.5-35B-A3B` | Same |
| API format | OpenAI-compatible | All LLM calls use `openai.AsyncOpenAI` |
| Max tokens | 4096 (agents), 8192 (QBR Composer) | — |
| Tool-use | QBR Composer only (up to 10 iterations) | — |
