"""
Meeting Prep Agent - Auto-generates pre-call briefing documents.

Pulls account context from Salesforce (cases, pipeline, contacts,
activities) AND recent news about the company to produce a concise
brief with talking points, landmines, and recommended asks.
"""

import os
import json
import logging
from typing import AsyncGenerator

from core.agent_runtime import BaseAgent, AgentBlueprint
from core.models import AgentContext, AgentResult, InsightCard, Priority, SourceObject
from integrations.hub import hub

logger = logging.getLogger(__name__)

MEETING_PREP_PROMPT = """You are a senior sales strategist at Zenlayer, preparing a pre-call briefing for an upcoming customer meeting.

Given the Salesforce data and recent news below, generate a concise meeting prep brief as a JSON object.

ACCOUNT DATA:
{account_data}

RECENT NEWS:
{news_data}

Generate this exact JSON structure:
```json
{{
  "account_summary": "<1-2 sentences: who this customer is, relationship status, strategic importance>",
  "recent_news": [
    {{"headline": "<article title>", "source": "<publication>", "relevance": "<why this matters for the meeting>"}}
  ],
  "recent_activity": [
    {{"date": "<date>", "type": "<meeting|call|email|support>", "summary": "<what happened>"}}
  ],
  "open_issues": [
    {{"id": "<case/opp id>", "title": "<subject>", "severity": "critical|high|medium|low", "summary": "<brief context>", "action_needed": "<what we need to do>"}}
  ],
  "pipeline_status": {{
    "total_pipeline": "<formatted dollar amount>",
    "deals": [
      {{"name": "<deal name>", "amount": "<formatted>", "stage": "<stage>", "next_step": "<what's needed>"}}
    ]
  }},
  "key_contacts": [
    {{"name": "<name>", "title": "<title>", "engagement": "active|passive|unknown", "note": "<context about this person>"}}
  ],
  "talking_points": [
    "<specific talking point with context — not generic. Reference news or data where relevant.>"
  ],
  "landmines": [
    "<issue to avoid or handle carefully, with specific context>"
  ],
  "recommended_asks": [
    "<specific ask for this meeting, based on the data>"
  ]
}}
```

IMPORTANT: If there is relevant news, weave it into talking points. For example, if the company announced an expansion, suggest discussing how Zenlayer can support it. Be specific — reference actual data. Do NOT mention data limitations to the user."""


class MeetingPrepAgent(BaseAgent):

    blueprint = AgentBlueprint(
        id="meeting_prep",
        name="Meeting Prep",
        description="Auto-generates pre-call briefing documents with talking points, landmines, and recommended asks based on live Salesforce data and recent company news.",
        category="preparation",
        icon="clipboard",
        color="blue",
        required_integrations=["salesforce"],
        default_config={
            "include_pipeline": True,
            "include_contacts": True,
            "include_cases": True,
            "include_news": True,
            "max_news_articles": 5,
        },
        capabilities=["meeting_preparation", "talking_points", "risk_awareness"],
        schedule_options=["manual"],
        data_sources=[
            "Salesforce Cases (open issues to address)",
            "Salesforce Opportunities (pipeline context)",
            "Salesforce Contacts (who you're meeting with)",
            "Salesforce Activities (recent interaction history)",
            "Salesforce Account Info (company context)",
            "Google News RSS (recent public news about the company)",
        ],
        logic_steps=[
            "Fetches 5 data types from Salesforce in parallel",
            "Fetches recent news articles via Google News RSS",
            "LLM synthesizes all sources into structured meeting brief",
            "News is woven into talking points where relevant",
            "Identifies landmines (open critical cases, lost deals, gaps)",
            "Recommends specific asks based on pipeline, relationship, and news",
            "Falls back to structured data summary if LLM unavailable",
        ],
        output_types=["Pre-call briefing with talking points, landmines, news context, and asks"],
    )

    async def run(self, context: AgentContext) -> AgentResult:
        insights: list[InsightCard] = []
        errors: list[str] = []

        for account_name in context.account_names:
            try:
                brief, news_sources = await self._prepare_brief(account_name, context)
                if brief:
                    all_sources = news_sources or []
                    news_count = len(brief.get("recent_news", []))
                    insights.append(InsightCard(
                        agent_instance_id=context.instance_id,
                        agent_blueprint_id=self.blueprint.id,
                        account_name=account_name,
                        priority=Priority.MEDIUM,
                        title=f"Meeting prep ready for {account_name}",
                        summary=brief.get("account_summary", f"Pre-call briefing prepared for {account_name}."),
                        detail=brief,
                        sources=all_sources,
                        actions=[
                            {"label": "View Full Brief", "action_type": "expand", "params": {}},
                            {"label": "Generate QBR", "action_type": "generate_briefing",
                             "params": {"account_name": account_name, "type": "customer"}},
                        ],
                        logic_explanation=f"Fetched 6 data sources for {account_name}: Salesforce Cases, Opportunities, Contacts, Activities, and Account Info (last {context.time_range_days} days), plus Google News RSS (up to {context.config.get('max_news_articles', 5)} recent articles). {news_count} news article{'s' if news_count != 1 else ''} found and included. All data was sent to an LLM which synthesized it into a meeting brief with news-informed talking points. Falls back to rule-based extraction if LLM unavailable.",
                    ))
                else:
                    errors.append(f"Could not generate prep for {account_name}")
            except Exception as e:
                errors.append(f"Meeting prep failed for {account_name}: {e}")
                logger.error(f"MeetingPrep error: {e}", exc_info=True)

        return AgentResult(success=len(errors) == 0, insights=insights, errors=errors)

    async def _prepare_brief(self, account_name: str, context: AgentContext) -> tuple[dict | None, list[SourceObject]]:
        days = context.time_range_days
        params = {"account_name": account_name, "days": days}

        cases = await hub.query("cases", params, "salesforce")
        opps = await hub.query("opportunities", params, "salesforce")
        contacts = await hub.query("contacts", params, "salesforce")
        activities = await hub.query("activities", params, "salesforce")
        account_info = await hub.query("account_info", params, "salesforce")

        account_data = {
            "account_info": account_info.records[:5],
            "recent_cases": cases.records[:10],
            "opportunities": opps.records[:10],
            "contacts": contacts.records[:10],
            "recent_activities": activities.records[:10],
        }

        news_articles = []
        news_sources: list[SourceObject] = []
        if context.config.get("include_news", True):
            try:
                from integrations.news import fetch_company_news
                max_articles = context.config.get("max_news_articles", 5)
                articles = await fetch_company_news(account_name, max_results=max_articles)
                for a in articles:
                    news_articles.append({
                        "title": a.title,
                        "source": a.source,
                        "published": a.published,
                        "snippet": a.snippet,
                    })
                    news_sources.append(SourceObject(
                        source_type="news",
                        object_type="article",
                        object_id=a.url,
                        display_name=a.source or "News",
                        deep_link=a.url,
                        snippet=a.title,
                        retrieved_at=a.published,
                    ))
            except Exception as e:
                logger.warning(f"News fetch for meeting prep failed: {e}")

        news_text = json.dumps(news_articles, default=str, indent=2) if news_articles else "No recent news found."

        try:
            from openai import AsyncOpenAI
            llm_url = os.environ.get("LOCAL_LLM_URL", "http://10.1.0.251:18010/v1/")
            llm_model = os.environ.get("LOCAL_LLM_MODEL", "Qwen/Qwen3.5-35B-A3B")
            client = AsyncOpenAI(base_url=llm_url, api_key="not-needed")

            prompt = MEETING_PREP_PROMPT.format(
                account_data=json.dumps(account_data, default=str, indent=2)[:5000],
                news_data=news_text[:2000],
            )

            response = await client.chat.completions.create(
                model=llm_model,
                max_tokens=4096,
                messages=[
                    {"role": "system", "content": prompt},
                    {"role": "user", "content": f"Prepare a meeting brief for {account_name}."},
                ],
            )

            text = response.choices[0].message.content.strip()
            result = self._extract_json(text)
            return result, news_sources
        except Exception as e:
            logger.error(f"LLM meeting prep failed: {e}")
            fallback = self._fallback_brief(account_name, account_data, news_articles)
            return fallback, news_sources

    def _fallback_brief(self, account_name: str, data: dict, news: list[dict]) -> dict:
        """Generate a basic brief without LLM when it's unavailable."""
        cases = data.get("recent_cases", [])
        opps = data.get("opportunities", [])
        contacts = data.get("contacts", [])

        open_cases = [c for c in cases if c.get("Status", "").lower() not in ("closed", "resolved")]
        critical = [c for c in open_cases if c.get("Priority", "").lower() in ("critical", "high")]

        talking_points = []
        if open_cases:
            talking_points.append(f"Review {len(open_cases)} open support cases")
        else:
            talking_points.append("Discuss current satisfaction")
        if opps:
            talking_points.append(f"Discuss {len(opps)} pipeline opportunities")
        else:
            talking_points.append("Explore expansion opportunities")
        for article in news[:2]:
            talking_points.append(f"Reference recent news: \"{article.get('title', '')}\" ({article.get('source', 'News')})")

        return {
            "account_summary": f"Briefing for {account_name} based on Salesforce data and {len(news)} recent news articles.",
            "recent_news": [
                {"headline": a.get("title", ""), "source": a.get("source", ""),
                 "relevance": "Discuss how this may impact the partnership"}
                for a in news[:5]
            ],
            "recent_activity": [],
            "open_issues": [
                {"id": c.get("CaseNumber", ""), "title": c.get("Subject", "Unknown"),
                 "severity": c.get("Priority", "medium").lower(),
                 "summary": c.get("Description", "")[:200] if c.get("Description") else "",
                 "action_needed": "Review and discuss status"}
                for c in critical[:5]
            ],
            "pipeline_status": {
                "total_pipeline": f"{len(opps)} open opportunities",
                "deals": [
                    {"name": o.get("Name", ""), "amount": o.get("Amount", "N/A"),
                     "stage": o.get("StageName", ""), "next_step": o.get("NextStep", "TBD")}
                    for o in opps[:5]
                ],
            },
            "key_contacts": [
                {"name": c.get("Name", ""), "title": c.get("Title", ""),
                 "engagement": "unknown", "note": ""}
                for c in contacts[:5]
            ],
            "talking_points": talking_points,
            "landmines": [
                f"{len(critical)} critical/high priority cases need acknowledgment" if critical else "No critical issues identified"
            ],
            "recommended_asks": [
                "Confirm key stakeholders for next quarter",
                "Align on expansion timeline",
            ],
        }

    def _extract_json(self, text: str) -> dict | None:
        if "```json" in text:
            text = text.split("```json")[1].split("```")[0]
        elif "```" in text:
            text = text.split("```")[1].split("```")[0]
        try:
            return json.loads(text.strip())
        except json.JSONDecodeError:
            brace_start = text.find('{')
            if brace_start >= 0:
                depth = 0
                for i in range(brace_start, len(text)):
                    if text[i] == '{': depth += 1
                    elif text[i] == '}':
                        depth -= 1
                        if depth == 0:
                            try:
                                return json.loads(text[brace_start:i+1])
                            except json.JSONDecodeError:
                                break
        return None
