"""
Deal Strategist Agent - Active deal coaching and next-best-action.

Analyzes open pipeline, win/loss patterns, stakeholder coverage,
and competitive signals to recommend deal strategy.
"""

import os
import json
import logging

from core.agent_runtime import BaseAgent, AgentBlueprint
from core.models import AgentContext, AgentResult, InsightCard, Priority
from integrations.hub import hub

logger = logging.getLogger(__name__)

STRATEGY_PROMPT = """You are a senior sales strategist at Zenlayer analyzing deal pipeline for an account.

Given the Salesforce pipeline and account data below, generate strategic deal recommendations as JSON.

ACCOUNT DATA:
{account_data}

Generate this exact JSON structure:
```json
{{
  "pipeline_summary": "<1-2 sentences: overall pipeline health and trajectory>",
  "deals": [
    {{
      "name": "<opportunity name>",
      "amount": "<formatted amount>",
      "stage": "<current stage>",
      "risk_level": "low|medium|high|critical",
      "risk_factors": ["<specific risk>"],
      "recommended_actions": ["<specific next step>"],
      "stakeholder_gaps": ["<missing stakeholder access>"],
      "win_strategy": "<1-2 sentence strategy for this specific deal>"
    }}
  ],
  "portfolio_risks": [
    {{"risk": "<risk description>", "impact": "<what happens if unaddressed>", "mitigation": "<recommended action>"}}
  ],
  "quick_wins": [
    "<immediately actionable opportunity>"
  ],
  "competitive_signals": [
    "<any competitive intelligence from the data>"
  ]
}}
```

Be specific. Reference actual deal names, amounts, and stages. If a deal has no next step defined, flag it."""


class DealStrategistAgent(BaseAgent):

    blueprint = AgentBlueprint(
        id="deal_strategist",
        name="Deal Strategist",
        description="Analyzes your open pipeline, identifies risk factors, stakeholder gaps, and recommends next-best-actions for each deal.",
        category="strategy",
        icon="target",
        color="amber",
        required_integrations=["salesforce"],
        default_config={
            "risk_threshold": "medium",
            "include_closed_lost_patterns": True,
        },
        capabilities=["deal_coaching", "pipeline_analysis", "competitive_intelligence"],
        schedule_options=["manual", "daily", "weekly"],
        data_sources=[
            "Salesforce Open Opportunities (stage, amount, probability, next step)",
            "Salesforce Contacts (stakeholder coverage)",
            "Salesforce Account Info (company context)",
        ],
        logic_steps=[
            "Analyzes each open deal for risk factors and stakeholder gaps",
            "LLM scores risk level per deal (low/medium/high/critical)",
            "Identifies deals missing next steps as stalled",
            "Detects competitive signals from deal descriptions",
            "Recommends specific next-best-actions per deal",
            "Highlights quick wins (low-effort, high-impact moves)",
            "Falls back to rule-based stall detection if LLM unavailable",
        ],
        output_types=["Deal risk assessments", "Strategy recommendations", "Quick win identification"],
    )

    async def run(self, context: AgentContext) -> AgentResult:
        insights: list[InsightCard] = []
        errors: list[str] = []

        for account_name in context.account_names:
            try:
                cards = await self._analyze_deals(account_name, context)
                if account_name.lower() in [n.lower() for n in context.must_win_accounts]:
                    for c in cards:
                        if c.priority == Priority.MEDIUM:
                            c.priority = Priority.HIGH
                insights.extend(cards)
            except Exception as e:
                errors.append(f"Deal analysis failed for {account_name}: {e}")
                logger.error(f"DealStrategist error: {e}", exc_info=True)

        return AgentResult(success=len(errors) == 0, insights=insights, errors=errors)

    async def _analyze_deals(self, account_name: str, ctx: AgentContext) -> list[InsightCard]:
        insights: list[InsightCard] = []
        days = ctx.time_range_days
        params = {"account_name": account_name, "days": days}

        opps = await hub.query("opportunities", params, "salesforce")
        contacts = await hub.query("contacts", params, "salesforce")
        account_info = await hub.query("account_info", params, "salesforce")

        if not opps.records:
            insights.append(InsightCard(
                agent_instance_id=ctx.instance_id,
                agent_blueprint_id=self.blueprint.id,
                account_name=account_name,
                priority=Priority.INFO,
                title="No active pipeline",
                summary=f"{account_name} has no open opportunities. Consider prospecting for new deals.",
                actions=[{"label": "Prep Outreach", "action_type": "run_agent",
                          "params": {"agent": "meeting_prep", "account": account_name}}],
            ))
            return insights

        account_data = {
            "account_info": account_info.records[:3],
            "opportunities": opps.records[:15],
            "contacts": contacts.records[:10],
        }

        strategy = await self._generate_strategy(account_name, account_data)
        if strategy:
            deals = strategy.get("deals", [])
            high_risk = [d for d in deals if d.get("risk_level") in ("high", "critical")]
            if high_risk:
                insights.append(InsightCard(
                    agent_instance_id=ctx.instance_id,
                    agent_blueprint_id=self.blueprint.id,
                    account_name=account_name,
                    priority=Priority.HIGH,
                    title=f"{len(high_risk)} deal{'s' if len(high_risk) != 1 else ''} at risk",
                    summary=strategy.get("pipeline_summary", f"{len(high_risk)} deals need attention."),
                    detail=strategy,
                    sources=opps.sources[:5],
                    actions=[
                        {"label": "View Strategy", "action_type": "expand", "params": {}},
                        {"label": "Prep Meeting", "action_type": "run_agent",
                         "params": {"agent": "meeting_prep", "account": account_name}},
                    ],
                ))
            else:
                insights.append(InsightCard(
                    agent_instance_id=ctx.instance_id,
                    agent_blueprint_id=self.blueprint.id,
                    account_name=account_name,
                    priority=Priority.INFO,
                    title=f"Pipeline healthy: {len(deals)} active deal{'s' if len(deals) != 1 else ''}",
                    summary=strategy.get("pipeline_summary", "Pipeline on track."),
                    detail=strategy,
                    sources=opps.sources[:5],
                    actions=[{"label": "View Details", "action_type": "expand", "params": {}}],
                ))

            if strategy.get("quick_wins"):
                insights.append(InsightCard(
                    agent_instance_id=ctx.instance_id,
                    agent_blueprint_id=self.blueprint.id,
                    account_name=account_name,
                    priority=Priority.MEDIUM,
                    title=f"{len(strategy['quick_wins'])} quick win{'s' if len(strategy['quick_wins']) != 1 else ''} identified",
                    summary="; ".join(strategy["quick_wins"][:3]),
                    detail={"quick_wins": strategy["quick_wins"]},
                    actions=[],
                ))
        else:
            self._fallback_analysis(insights, account_name, opps, ctx)

        return insights

    def _fallback_analysis(self, insights, account_name, opps, ctx):
        """Basic analysis without LLM."""
        stalled = [o for o in opps.records
                   if not o.get("NextStep")
                   and o.get("StageName", "").lower() not in ("closed won", "closed lost")]
        if stalled:
            insights.append(InsightCard(
                agent_instance_id=ctx.instance_id,
                agent_blueprint_id=self.blueprint.id,
                account_name=account_name,
                priority=Priority.MEDIUM,
                title=f"{len(stalled)} deal{'s' if len(stalled) != 1 else ''} missing next steps",
                summary=f"{account_name} has {len(stalled)} open opportunities with no defined next step.",
                detail={"stalled_deals": stalled[:5]},
                sources=opps.sources[:5],
            ))

    async def _generate_strategy(self, account_name: str, data: dict) -> dict | None:
        try:
            from openai import AsyncOpenAI
            llm_url = os.environ.get("LOCAL_LLM_URL", "http://10.1.0.251:18010/v1/")
            llm_model = os.environ.get("LOCAL_LLM_MODEL", "Qwen/Qwen3.5-35B-A3B")
            client = AsyncOpenAI(base_url=llm_url, api_key="not-needed")

            prompt = STRATEGY_PROMPT.format(
                account_data=json.dumps(data, default=str, indent=2)[:6000]
            )

            response = await client.chat.completions.create(
                model=llm_model,
                max_tokens=4096,
                messages=[
                    {"role": "system", "content": prompt},
                    {"role": "user", "content": f"Analyze the pipeline for {account_name} and recommend strategy."},
                ],
            )

            text = response.choices[0].message.content.strip()
            if "```json" in text:
                text = text.split("```json")[1].split("```")[0]
            elif "```" in text:
                text = text.split("```")[1].split("```")[0]
            return json.loads(text.strip())
        except Exception as e:
            logger.warning(f"LLM deal strategy failed: {e}")
            return None
