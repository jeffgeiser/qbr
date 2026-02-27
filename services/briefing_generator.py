"""
Briefing Generator Service

Uses Claude AI to synthesize Salesforce data into structured briefing documents.
Produces two types:
  1. Internal Executive Health Brief (candid, risk-focused)
  2. Customer-Facing QBR (professional, forward-looking)
"""

import os
import json
import logging
from datetime import datetime

import anthropic

logger = logging.getLogger(__name__)


INTERNAL_BRIEF_SYSTEM_PROMPT = """You are an expert account strategist at Zenlayer, a global edge cloud and connectivity provider.
You are generating an INTERNAL Executive Health Brief for leadership. This document is CONFIDENTIAL and should be:
- Brutally candid — no sugar-coating
- Risk-focused — surface every concern
- Action-oriented — every problem needs a directive
- Data-driven — cite specific case numbers, amounts, dates

Your tone is direct, urgent, and "no-fluff." Internal leadership needs to know WHERE we are failing and WHAT to do about it."""

INTERNAL_BRIEF_USER_PROMPT = """Based on the following Salesforce data for account "{account_name}", generate an Internal Executive Health Brief.

SALESFORCE DATA:
{salesforce_data}

INTERNAL TRACKER DATA:
- Tier: {tier}
- Owner: {owner}
- Health Sentiment: {health}
- Latest Update: {latest_update}
- Key Learnings: {key_learnings}

Generate a JSON response with this EXACT structure:
{{
  "scorecard": [
    {{"label": "Business Outlook", "score": <1-5>}},
    {{"label": "Support Health", "score": <1-5>}},
    {{"label": "Engagement Cadence", "score": <1-5>}},
    {{"label": "Pipeline Momentum", "score": <1-5>}},
    {{"label": "Relationship Depth", "score": <1-5>}}
  ],
  "overall_assessment": "<1-2 sentence overall health assessment>",
  "friction_points": [
    {{
      "severity": "critical|warning|info",
      "title": "<short title>",
      "description": "<detailed description>",
      "evidence": ["<specific case/data reference>", "..."]
    }}
  ],
  "revenue_at_risk_total": "<formatted amount like 220K+>",
  "revenue_items": [
    {{
      "name": "<deal name>",
      "amount": "<formatted amount>",
      "status": "at_risk|won|lost|open",
      "detail": "<why it's at risk or notable>"
    }}
  ],
  "red_flags": [
    {{
      "title": "<flag title>",
      "description": "<what's wrong and why it matters>"
    }}
  ],
  "action_directives": [
    {{
      "directive": "<what needs to happen>",
      "detail": "<additional context>",
      "priority": "urgent|high|normal"
    }}
  ]
}}

If data is limited, still generate a meaningful brief based on what's available. Infer risks from patterns in the case data. Be specific — reference actual case numbers, dollar amounts, and dates from the data."""


CUSTOMER_QBR_SYSTEM_PROMPT = """You are an expert account strategist at Zenlayer, a global edge cloud and connectivity provider.
You are generating a CUSTOMER-FACING Quarterly Business Review document. This will be presented to the customer and should be:
- Professional and polished
- Proactive — show we're on top of things
- Transparent but diplomatic — acknowledge issues as "improvement areas"
- Forward-looking — emphasize growth and roadmap
- Collaborative — frame everything as a partnership

Your tone is consultative, committed to excellence, and focused on demonstrating value."""

CUSTOMER_QBR_USER_PROMPT = """Based on the following Salesforce data for account "{account_name}", generate a Customer-Facing QBR document.

SALESFORCE DATA:
{salesforce_data}

INTERNAL TRACKER DATA:
- Tier: {tier}
- Owner: {owner}
- Latest Update: {latest_update}

Generate a JSON response with this EXACT structure:
{{
  "executive_summary": "<2-3 paragraph partnership narrative — acknowledge the customer as strategically important, summarize the period, highlight positives, address improvement areas diplomatically>",
  "key_stats": [
    {{"label": "<metric name>", "value": "<metric value>"}},
    {{"label": "<metric name>", "value": "<metric value>"}},
    {{"label": "<metric name>", "value": "<metric value>"}},
    {{"label": "<metric name>", "value": "<metric value>"}}
  ],
  "performance_metrics": [
    {{"label": "<metric>", "value": "<value>"}},
    {{"label": "<metric>", "value": "<value>"}},
    {{"label": "<metric>", "value": "<value>"}}
  ],
  "performance_highlights": [
    {{
      "title": "<highlight category>",
      "detail": "<specific achievement — cite resolution times, wins>"
    }}
  ],
  "improvement_plan": [
    {{
      "title": "<initiative name — positive framing>",
      "description": "<what we're doing to improve>",
      "items": ["<specific action>", "..."]
    }}
  ],
  "expansion_initiatives": [
    {{
      "name": "<initiative name>",
      "status": "live|in_progress|planning",
      "status_label": "Live|In Progress|Planning",
      "detail": "<description>"
    }}
  ],
  "joint_actions": [
    {{
      "action": "<collaborative next step>",
      "target_date": "<target date or null>"
    }}
  ]
}}

Frame problems as improvement opportunities. Highlight wins prominently. Be specific with numbers from the data. If data is limited, still produce a professional document based on what's available."""


async def generate_briefing(
    briefing_type: str,
    account_name: str,
    salesforce_data: dict,
    tracker_data: dict,
    time_range_days: int = 90,
) -> dict:
    """
    Generate a briefing using Claude AI.

    Args:
        briefing_type: "internal" or "customer"
        account_name: Name of the account
        salesforce_data: Dict from SalesforceMCPClient.fetch_all_briefing_data()
        tracker_data: Dict with internal tracker fields (tier, owner, health, etc.)
        time_range_days: Number of days of data

    Returns:
        Parsed briefing dict matching the template structure.
    """
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise RuntimeError("ANTHROPIC_API_KEY environment variable is required")

    client = anthropic.Anthropic(api_key=api_key)

    # Format Salesforce data as readable text
    sf_text = _format_salesforce_data(salesforce_data)

    if briefing_type == "internal":
        system_prompt = INTERNAL_BRIEF_SYSTEM_PROMPT
        user_prompt = INTERNAL_BRIEF_USER_PROMPT.format(
            account_name=account_name,
            salesforce_data=sf_text,
            tier=tracker_data.get("tier", "Unknown"),
            owner=tracker_data.get("owner", "Unknown"),
            health=tracker_data.get("healthSentiment", "Unknown"),
            latest_update=tracker_data.get("latestUpdate", "None"),
            key_learnings=tracker_data.get("keyLearnings", "None"),
        )
    else:
        system_prompt = CUSTOMER_QBR_SYSTEM_PROMPT
        user_prompt = CUSTOMER_QBR_USER_PROMPT.format(
            account_name=account_name,
            salesforce_data=sf_text,
            tier=tracker_data.get("tier", "Unknown"),
            owner=tracker_data.get("owner", "Unknown"),
            latest_update=tracker_data.get("latestUpdate", "None"),
        )

    logger.info(f"Generating {briefing_type} briefing for {account_name}")

    message = client.messages.create(
        model="claude-sonnet-4-5-20250514",
        max_tokens=4096,
        system=system_prompt,
        messages=[{"role": "user", "content": user_prompt}],
    )

    # Extract JSON from response
    response_text = message.content[0].text

    # Try to parse JSON from the response (it may be wrapped in markdown code fences)
    json_str = response_text
    if "```json" in json_str:
        json_str = json_str.split("```json")[1].split("```")[0]
    elif "```" in json_str:
        json_str = json_str.split("```")[1].split("```")[0]

    try:
        briefing = json.loads(json_str.strip())
    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse Claude response as JSON: {e}")
        logger.error(f"Response was: {response_text[:500]}")
        raise RuntimeError("Failed to generate briefing — invalid response format")

    # Add metadata
    briefing["_meta"] = {
        "account_name": account_name,
        "briefing_type": briefing_type,
        "generated_at": datetime.utcnow().isoformat(),
        "time_range_days": time_range_days,
    }

    return briefing


def _format_salesforce_data(data: dict) -> str:
    """Format Salesforce data dict into readable text for the AI prompt."""
    sections = []

    if data.get("account_info"):
        sections.append("=== ACCOUNT INFO ===")
        sections.append(json.dumps(data["account_info"], indent=2, default=str))

    if data.get("cases"):
        sections.append(f"\n=== CASES ({len(data['cases'])} records) ===")
        sections.append(json.dumps(data["cases"], indent=2, default=str))

    if data.get("open_opportunities"):
        sections.append(f"\n=== OPEN OPPORTUNITIES ({len(data['open_opportunities'])} records) ===")
        sections.append(json.dumps(data["open_opportunities"], indent=2, default=str))

    if data.get("closed_opportunities"):
        sections.append(f"\n=== CLOSED OPPORTUNITIES ({len(data['closed_opportunities'])} records) ===")
        sections.append(json.dumps(data["closed_opportunities"], indent=2, default=str))

    if data.get("contacts"):
        sections.append(f"\n=== CONTACTS ({len(data['contacts'])} records) ===")
        sections.append(json.dumps(data["contacts"], indent=2, default=str))

    if data.get("activities"):
        sections.append(f"\n=== ACTIVITIES ({len(data['activities'])} records) ===")
        sections.append(json.dumps(data["activities"], indent=2, default=str))

    if not sections:
        return "No Salesforce data available. Generate briefing based on internal tracker data only."

    return "\n".join(sections)
