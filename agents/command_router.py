"""
Command Router - interprets natural language from the command bar
and routes to the appropriate agent(s).

This replaces the old "pick a template" flow with fluid, natural
language interaction. The router uses the LLM to understand intent,
extract parameters, and dispatch to one or more agents.
"""

import os
import json
import logging
from dataclasses import dataclass
from typing import Optional

from core.agent_runtime import registry
from core.models import AgentContext

logger = logging.getLogger(__name__)


@dataclass
class CommandIntent:
    agent_id: str
    account_names: list[str]
    params: dict
    raw_query: str
    confidence: float = 1.0


ROUTING_PROMPT = """You are a command router for a sales intelligence platform. Given a user's natural language query, determine which agent to invoke and extract the parameters.

Available agents:
- account_pulse: Health monitoring, risk detection, account status checks. Use for questions about account health, risks, what's happening with an account, general status.
- qbr_composer: Generate formal briefing documents (internal health briefs or customer-facing QBRs). Use when user wants to generate/create a briefing, document, or QBR.
- meeting_prep: Pre-call briefing with talking points, landmines, and recommended asks. Use when user mentions meeting, call, prep, or preparing for a conversation.
- deal_strategist: Pipeline analysis, deal coaching, competitive positioning. Use when user asks about deals, pipeline, strategy, win plan, or competitive situation.
- customer_voice: Support ticket analysis, escalation prediction, recurring issue detection. Use when user asks about support, cases, tickets, customer satisfaction, or escalation risk.
- news_monitor: Industry news about customer companies. Use when user asks about news, press, industry updates, or what's happening publicly with a company.
- account_digest: Summary of changes across accounts. Use when user asks for a digest, weekly summary, recap, or wants to send a Teams notification.
- executive_pulse: Portfolio-wide health for leadership. Use when user asks about overall portfolio, all accounts, team performance, or executive summary.

Extract the following as JSON:
{
  "agent_id": "<agent_id from list above>",
  "account_names": ["<company/account name(s) mentioned>"],
  "params": {
    "briefing_type": "internal|customer",  // only for qbr_composer
    "days": <number of days, default 90>
  },
  "confidence": <0.0-1.0 how confident you are in the routing>
}

If the query mentions multiple accounts, include all. If no specific account, use an empty list.
Default to account_pulse for general/ambiguous questions.

Respond with ONLY the JSON object."""


async def parse_command(user_message: str) -> CommandIntent:
    """Parse a natural language command into a structured intent."""
    try:
        from openai import AsyncOpenAI
        llm_url = os.environ.get("LOCAL_LLM_URL", "http://10.1.0.251:18010/v1/")
        llm_model = os.environ.get("LOCAL_LLM_MODEL", "Qwen/Qwen3.5-35B-A3B")
        client = AsyncOpenAI(base_url=llm_url, api_key="not-needed")

        response = await client.chat.completions.create(
            model=llm_model,
            max_tokens=200,
            messages=[
                {"role": "system", "content": ROUTING_PROMPT},
                {"role": "user", "content": user_message},
            ],
        )

        text = response.choices[0].message.content.strip()
        if "```" in text:
            text = text.split("```")[1].split("```")[0]
            if text.startswith("json"):
                text = text[4:]

        parsed = json.loads(text.strip())
        return CommandIntent(
            agent_id=parsed.get("agent_id", "account_pulse"),
            account_names=parsed.get("account_names", []),
            params=parsed.get("params", {}),
            raw_query=user_message,
            confidence=parsed.get("confidence", 0.5),
        )
    except Exception as e:
        logger.warning(f"Command parsing failed: {e}, falling back to heuristic")
        return _heuristic_parse(user_message)


def _heuristic_parse(user_message: str) -> CommandIntent:
    """Fast fallback routing without LLM."""
    msg = user_message.lower()

    if any(w in msg for w in ("brief", "qbr", "document", "generate", "compose", "draft", "create")):
        agent_id = "qbr_composer"
    elif any(w in msg for w in ("meeting", "call", "prep", "prepare", "pre-call", "talking points")):
        agent_id = "meeting_prep"
    elif any(w in msg for w in ("deal", "pipeline", "strategy", "win plan", "competitive", "forecast")):
        agent_id = "deal_strategist"
    elif any(w in msg for w in ("support", "cases", "tickets", "escalat", "satisfaction", "voice")):
        agent_id = "customer_voice"
    elif any(w in msg for w in ("news", "press", "article", "industry", "headline", "announce")):
        agent_id = "news_monitor"
    elif any(w in msg for w in ("digest", "summary", "recap", "weekly", "teams notification")):
        agent_id = "account_digest"
    elif any(w in msg for w in ("portfolio", "all accounts", "executive", "leadership", "overview", "aggregate")):
        agent_id = "executive_pulse"
    else:
        agent_id = "account_pulse"

    briefing_type = "customer" if any(w in msg for w in ("customer", "external", "qbr")) else "internal"

    account_names = _extract_account_names(user_message)

    days = 90
    for token in msg.split():
        if token.isdigit() and 1 <= int(token) <= 365:
            days = int(token)
            break
    if "6 month" in msg or "180" in msg:
        days = 180
    elif "30 day" in msg or "month" in msg:
        days = 30

    return CommandIntent(
        agent_id=agent_id,
        account_names=account_names,
        params={"briefing_type": briefing_type, "days": days},
        raw_query=user_message,
        confidence=0.6,
    )


def _extract_account_names(text: str) -> list[str]:
    """Try to extract account names from the user's text by matching against known accounts."""
    try:
        from main import get_all_accounts
        accounts = get_all_accounts()
        found = []
        text_lower = text.lower()
        for a in accounts:
            if a["name"].lower() in text_lower:
                found.append(a["name"])
        return found
    except Exception:
        return []
