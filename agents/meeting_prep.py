"""
Meeting Prep Agent - Auto-generates pre-call briefing documents.

Pulls account context, recent activity, open issues, pipeline status,
and key contacts to produce a concise 1-page brief with talking points,
landmines to avoid, and recommended asks.
"""

import os
import json
import logging
from typing import AsyncGenerator

from core.agent_runtime import BaseAgent, AgentBlueprint
from core.models import AgentContext, AgentResult, InsightCard, Priority
from integrations.hub import hub

logger = logging.getLogger(__name__)

MEETING_PREP_PROMPT = """You are a senior sales strategist at Zenlayer, preparing a pre-call briefing for an upcoming customer meeting.

Given the Salesforce data below, generate a concise meeting prep brief as a JSON object.

ACCOUNT DATA:
{account_data}

Generate this exact JSON structure:
```json
{{
  "account_summary": "<1-2 sentences: who this customer is, relationship status, strategic importance>",
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
    "<specific talking point with context — not generic>"
  ],
  "landmines": [
    "<issue to avoid or handle carefully, with specific context>"
  ],
  "recommended_asks": [
    "<specific ask for this meeting, based on the data>"
  ]
}}
```

Be specific — reference actual data. If data is limited, still produce useful guidance based on what's available. Do NOT mention data limitations to the user."""


class MeetingPrepAgent(BaseAgent):

    blueprint = AgentBlueprint(
        id="meeting_prep",
        name="Meeting Prep",
        description="Auto-generates pre-call briefing documents with talking points, landmines, and recommended asks based on live account data.",
        category="preparation",
        icon="clipboard",
        color="blue",
        required_integrations=["salesforce"],
        default_config={
            "include_pipeline": True,
            "include_contacts": True,
            "include_cases": True,
        },
        capabilities=["meeting_preparation", "talking_points", "risk_awareness"],
        schedule_options=["manual"],
        data_sources=[
            "Salesforce Cases (open issues to address)",
            "Salesforce Opportunities (pipeline context)",
            "Salesforce Contacts (who you're meeting with)",
            "Salesforce Activities (recent interaction history)",
            "Salesforce Account Info (company context)",
        ],
        logic_steps=[
            "Fetches all 5 data types from Salesforce in parallel",
            "LLM synthesizes into structured meeting brief",
            "Generates talking points based on actual account data",
            "Identifies landmines (open critical cases, lost deals, gaps)",
            "Recommends specific asks based on pipeline and relationship state",
            "Falls back to structured data summary if LLM unavailable",
        ],
        output_types=["Pre-call briefing with talking points, landmines, and asks"],
    )

    async def run(self, context: AgentContext) -> AgentResult:
        insights: list[InsightCard] = []
        errors: list[str] = []

        for account_name in context.account_names:
            try:
                brief = await self._prepare_brief(account_name, context)
                if brief:
                    insights.append(InsightCard(
                        agent_instance_id=context.instance_id,
                        agent_blueprint_id=self.blueprint.id,
                        account_name=account_name,
                        priority=Priority.MEDIUM,
                        title=f"Meeting prep ready for {account_name}",
                        summary=brief.get("account_summary", f"Pre-call briefing prepared for {account_name}."),
                        detail=brief,
                        sources=[],
                        actions=[
                            {"label": "View Full Brief", "action_type": "expand", "params": {}},
                            {"label": "Generate QBR", "action_type": "generate_briefing",
                             "params": {"account_name": account_name, "type": "customer"}},
                        ],
                        logic_explanation=f"Fetched 5 Salesforce data types for {account_name} over the last {context.time_range_days} days: Cases (up to 10), Opportunities (up to 10), Contacts (up to 10), Activities (up to 10), and Account Info (up to 5 records). This data was sent to an LLM which synthesized it into a structured meeting brief with talking points, landmines to avoid, and recommended asks. If the LLM was unavailable, a rule-based fallback was used to extract key data points directly.",
                    ))
                else:
                    errors.append(f"Could not generate prep for {account_name}")
            except Exception as e:
                errors.append(f"Meeting prep failed for {account_name}: {e}")
                logger.error(f"MeetingPrep error: {e}", exc_info=True)

        return AgentResult(success=len(errors) == 0, insights=insights, errors=errors)

    async def _prepare_brief(self, account_name: str, context: AgentContext) -> dict | None:
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

        try:
            from openai import AsyncOpenAI
            llm_url = os.environ.get("LOCAL_LLM_URL", "http://10.1.0.251:18010/v1/")
            llm_model = os.environ.get("LOCAL_LLM_MODEL", "Qwen/Qwen3.5-35B-A3B")
            client = AsyncOpenAI(base_url=llm_url, api_key="not-needed")

            prompt = MEETING_PREP_PROMPT.format(
                account_data=json.dumps(account_data, default=str, indent=2)[:6000]
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
            return self._extract_json(text)
        except Exception as e:
            logger.error(f"LLM meeting prep failed: {e}")
            return self._fallback_brief(account_name, account_data)

    def _fallback_brief(self, account_name: str, data: dict) -> dict:
        """Generate a basic brief without LLM when it's unavailable."""
        cases = data.get("recent_cases", [])
        opps = data.get("opportunities", [])
        contacts = data.get("contacts", [])

        open_cases = [c for c in cases if c.get("Status", "").lower() not in ("closed", "resolved")]
        critical = [c for c in open_cases if c.get("Priority", "").lower() in ("critical", "high")]

        return {
            "account_summary": f"Briefing for {account_name} based on available Salesforce data.",
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
            "talking_points": [
                f"Review {len(open_cases)} open support cases" if open_cases else "Discuss current satisfaction",
                f"Discuss {len(opps)} pipeline opportunities" if opps else "Explore expansion opportunities",
            ],
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
