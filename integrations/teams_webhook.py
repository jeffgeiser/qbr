"""
Microsoft Teams Incoming Webhook integration.

Sends formatted message cards to a Teams channel via webhook URL.
Users configure the webhook URL per-agent-instance.
"""

import logging
from typing import Optional

logger = logging.getLogger(__name__)


async def send_teams_message(webhook_url: str, title: str, summary: str,
                             sections: list[dict] = None, theme_color: str = "0076D7") -> bool:
    """Send a MessageCard to a Teams incoming webhook."""
    import httpx

    if not webhook_url:
        logger.warning("No Teams webhook URL configured")
        return False

    card = {
        "@type": "MessageCard",
        "@context": "http://schema.org/extensions",
        "themeColor": theme_color,
        "summary": summary,
        "title": title,
        "sections": sections or [{"text": summary}],
    }

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(webhook_url, json=card)
            if resp.status_code == 200:
                logger.info(f"Teams message sent: {title}")
                return True
            else:
                logger.warning(f"Teams webhook returned {resp.status_code}: {resp.text}")
                return False
    except Exception as e:
        logger.error(f"Teams webhook failed: {e}")
        return False


def format_digest_card(user_name: str, period: str, account_summaries: list[dict]) -> tuple[str, str, list[dict]]:
    """Format an account digest as a Teams MessageCard."""
    title = f"Account Digest — {period}"
    summary = f"{len(account_summaries)} account{'s' if len(account_summaries) != 1 else ''} with updates"

    sections = []
    for acct in account_summaries[:10]:
        facts = []
        if acct.get("new_cases"):
            facts.append({"name": "New Cases", "value": str(acct["new_cases"])})
        if acct.get("open_cases"):
            facts.append({"name": "Open Cases", "value": str(acct["open_cases"])})
        if acct.get("pipeline_deals"):
            facts.append({"name": "Pipeline Deals", "value": str(acct["pipeline_deals"])})
        if acct.get("activities"):
            facts.append({"name": "Activities", "value": str(acct["activities"])})
        if acct.get("alert"):
            facts.append({"name": "Alert", "value": acct["alert"]})

        section = {
            "activityTitle": acct.get("name", "Unknown Account"),
            "activitySubtitle": acct.get("health", ""),
            "facts": facts,
            "markdown": True,
        }
        sections.append(section)

    if not sections:
        sections = [{"text": "No notable changes across your accounts this period."}]

    return title, summary, sections


def format_executive_card(title: str, metrics: dict, highlights: list[str],
                          risks: list[str]) -> tuple[str, str, list[dict]]:
    """Format an executive summary as a Teams MessageCard."""
    summary = f"{len(highlights)} highlights, {len(risks)} risks"

    sections = []

    if metrics:
        facts = [{"name": k, "value": str(v)} for k, v in metrics.items()]
        sections.append({
            "activityTitle": "Portfolio Metrics",
            "facts": facts,
            "markdown": True,
        })

    if highlights:
        sections.append({
            "activityTitle": "Highlights",
            "text": "\n\n".join(f"- {h}" for h in highlights[:5]),
            "markdown": True,
        })

    if risks:
        sections.append({
            "activityTitle": "Risks & Actions Needed",
            "text": "\n\n".join(f"- {r}" for r in risks[:5]),
            "markdown": True,
        })

    return title, summary, sections
