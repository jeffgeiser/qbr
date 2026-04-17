"""
Industry News Monitor - Watches for news about customer companies.

Runs on a schedule, fetches Google News RSS for each account in scope,
and surfaces relevant articles as info-level InsightCards. Zero setup
for reps — just activate the agent and news appears in the feed.
"""

import logging
from core.agent_runtime import BaseAgent, AgentBlueprint
from core.models import AgentContext, AgentResult, InsightCard, Priority, SourceObject

logger = logging.getLogger(__name__)


class NewsMonitorAgent(BaseAgent):

    blueprint = AgentBlueprint(
        id="news_monitor",
        name="Industry News",
        description="Monitors news for your customer companies automatically. Surfaces relevant articles in your feed — no setup required.",
        category="intelligence",
        icon="newspaper",
        color="sky",
        required_integrations=[],
        default_config={
            "max_articles_per_account": 3,
        },
        capabilities=["news_monitoring", "competitive_intelligence", "industry_awareness"],
        schedule_options=["manual", "daily", "weekly"],
        data_sources=[
            "Google News RSS (public news articles matching account name)",
        ],
        logic_steps=[
            "Searches Google News RSS for each account in scope",
            "Extracts title, source, publish date, and snippet",
            "Creates one insight card per article, tagged to the account",
            "Boosts priority from low to medium for must-win accounts",
            "No API key required — uses public RSS feeds",
        ],
        output_types=["News article alerts with source links"],
    )

    async def run(self, context: AgentContext) -> AgentResult:
        from integrations.news import fetch_company_news

        insights: list[InsightCard] = []
        errors: list[str] = []
        max_per = context.config.get("max_articles_per_account", 3)

        for account_name in context.account_names:
            try:
                articles = await fetch_company_news(account_name, max_results=max_per)
                if not articles:
                    continue

                for article in articles:
                    is_must_win = account_name.lower() in [n.lower() for n in context.must_win_accounts]
                    insights.append(InsightCard(
                        agent_instance_id=context.instance_id,
                        agent_blueprint_id=self.blueprint.id,
                        account_name=account_name,
                        priority=Priority.LOW if not is_must_win else Priority.MEDIUM,
                        title=article.title[:120],
                        summary=f"{article.source}: {article.snippet}" if article.source else article.snippet,
                        detail=article.to_dict(),
                        sources=[SourceObject(
                            source_type="news",
                            object_type="article",
                            object_id=article.url,
                            display_name=article.source or "News",
                            deep_link=article.url,
                            snippet=article.title,
                            retrieved_at=article.published,
                        )],
                        actions=[
                            {"label": "Read Article", "action_type": "external_link",
                             "params": {"url": article.url}},
                        ],
                    ))

            except Exception as e:
                errors.append(f"News fetch failed for {account_name}: {e}")
                logger.error(f"NewsMonitor error for {account_name}: {e}", exc_info=True)

        return AgentResult(
            success=len(errors) == 0,
            insights=insights,
            errors=errors,
            metadata={"articles_found": len(insights)},
        )
