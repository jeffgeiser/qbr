"""
Briefing Generator Service

Uses Claude AI with tool-use to orchestrate Salesforce queries and generate
structured briefing documents. Claude decides which queries to run based on
the user's request, calls the Salesforce MCP tools, and synthesizes results.
"""

import os
import json
import logging
from datetime import datetime
from typing import AsyncGenerator

import anthropic

logger = logging.getLogger(__name__)


# --- Tool Definitions for Claude ---

SALESFORCE_TOOLS = [
    {
        "name": "query_salesforce_cases",
        "description": "Query Salesforce cases (support tickets) for a customer account. Returns case number, subject, status, priority, created/closed dates, and descriptions.",
        "input_schema": {
            "type": "object",
            "properties": {
                "account_name": {
                    "type": "string",
                    "description": "The customer account name to search for in Salesforce"
                },
                "days": {
                    "type": "integer",
                    "description": "Number of days to look back from today. Default 90.",
                    "default": 90
                }
            },
            "required": ["account_name"]
        }
    },
    {
        "name": "query_salesforce_opportunities",
        "description": "Query Salesforce opportunities (deals/pipeline) for a customer account. Can filter by open, won, or lost. Returns opportunity name, stage, amount, close date, probability, and description.",
        "input_schema": {
            "type": "object",
            "properties": {
                "account_name": {
                    "type": "string",
                    "description": "The customer account name"
                },
                "status": {
                    "type": "string",
                    "enum": ["open", "won", "lost", "all"],
                    "description": "Filter by opportunity status. 'open' = not yet closed, 'won' = closed-won, 'lost' = closed-lost, 'all' = everything.",
                    "default": "all"
                },
                "days": {
                    "type": "integer",
                    "description": "For won/lost opportunities, how many days back to look. Default 90.",
                    "default": 90
                }
            },
            "required": ["account_name"]
        }
    },
    {
        "name": "query_salesforce_contacts",
        "description": "Query Salesforce contacts for a customer account. Returns name, email, phone, title, and department.",
        "input_schema": {
            "type": "object",
            "properties": {
                "account_name": {
                    "type": "string",
                    "description": "The customer account name"
                }
            },
            "required": ["account_name"]
        }
    },
    {
        "name": "query_salesforce_activities",
        "description": "Query Salesforce tasks/activities for a customer account. Returns subject, status, date, priority, and description of recent interactions.",
        "input_schema": {
            "type": "object",
            "properties": {
                "account_name": {
                    "type": "string",
                    "description": "The customer account name"
                },
                "days": {
                    "type": "integer",
                    "description": "Number of days to look back. Default 90.",
                    "default": 90
                }
            },
            "required": ["account_name"]
        }
    },
    {
        "name": "query_salesforce_account",
        "description": "Query the Salesforce account record itself. Returns account name, type, industry, annual revenue, owner, and description.",
        "input_schema": {
            "type": "object",
            "properties": {
                "account_name": {
                    "type": "string",
                    "description": "The customer account name"
                }
            },
            "required": ["account_name"]
        }
    },
]


# --- System Prompts ---

INTERNAL_SYSTEM = """You are an expert account strategist at Zenlayer, a global edge cloud and connectivity provider.

You are helping generate an INTERNAL Executive Health Brief for leadership. This document is CONFIDENTIAL and should be brutally candid, risk-focused, action-oriented, and data-driven.

IMPORTANT: You MUST call the Salesforce tools to gather real data. Do NOT describe what you would do — actually call the tools. Start by calling multiple tools in parallel (account info, cases, opportunities, contacts, activities).

Your workflow:
1. IMMEDIATELY call the Salesforce tools to gather data about the customer account — do not ask for confirmation
2. Analyze the data for risks, friction points, and revenue exposure
3. Generate a structured briefing

When you have enough data, output the briefing as a JSON block wrapped in ```json``` fences with this EXACT structure:
{
  "scorecard": [
    {"label": "Business Outlook", "score": <1-5>},
    {"label": "Support Health", "score": <1-5>},
    {"label": "Engagement Cadence", "score": <1-5>},
    {"label": "Pipeline Momentum", "score": <1-5>},
    {"label": "Relationship Depth", "score": <1-5>}
  ],
  "overall_assessment": "<1-2 sentence overall health assessment>",
  "friction_points": [
    {
      "severity": "critical|warning|info",
      "title": "<short title>",
      "description": "<detailed description>",
      "evidence": ["<specific case/data reference>"]
    }
  ],
  "revenue_at_risk_total": "<formatted amount like 220K+>",
  "revenue_items": [
    {
      "name": "<deal name>",
      "amount": "<formatted amount>",
      "status": "at_risk|won|lost|open",
      "detail": "<why it's notable>"
    }
  ],
  "red_flags": [
    {
      "title": "<flag title>",
      "description": "<what's wrong>"
    }
  ],
  "action_directives": [
    {
      "directive": "<what needs to happen>",
      "detail": "<additional context>",
      "priority": "urgent|high|normal"
    }
  ]
}

Be specific — reference actual case numbers, dollar amounts, and dates. If data is limited (e.g. tool results say "source: local_tracker"), still produce a meaningful assessment using whatever data is available. Do NOT tell the user that Salesforce is disconnected — just work with what you have."""

CUSTOMER_SYSTEM = """You are an expert account strategist at Zenlayer, a global edge cloud and connectivity provider.

You are helping generate a CUSTOMER-FACING Quarterly Business Review. This will be presented to the customer. It should be professional, proactive, transparent but diplomatic, and forward-looking.

IMPORTANT: You MUST call the Salesforce tools to gather real data. Do NOT describe what you would do — actually call the tools. Start by calling multiple tools in parallel (account info, cases, opportunities, contacts, activities).

Your workflow:
1. IMMEDIATELY call the Salesforce tools — do not ask for confirmation
2. Analyze the data for highlights, improvement areas, and growth opportunities
3. Generate a structured briefing

When you have enough data, output the briefing as a JSON block wrapped in ```json``` fences with this EXACT structure:
{
  "executive_summary": "<2-3 paragraph partnership narrative>",
  "key_stats": [
    {"label": "<metric name>", "value": "<metric value>"},
    {"label": "<metric name>", "value": "<metric value>"},
    {"label": "<metric name>", "value": "<metric value>"},
    {"label": "<metric name>", "value": "<metric value>"}
  ],
  "performance_metrics": [
    {"label": "<metric>", "value": "<value>"},
    {"label": "<metric>", "value": "<value>"},
    {"label": "<metric>", "value": "<value>"}
  ],
  "performance_highlights": [
    {
      "title": "<highlight category>",
      "detail": "<specific achievement>"
    }
  ],
  "improvement_plan": [
    {
      "title": "<initiative name>",
      "description": "<what we're doing>",
      "items": ["<specific action>"]
    }
  ],
  "expansion_initiatives": [
    {
      "name": "<initiative name>",
      "status": "live|in_progress|planning",
      "status_label": "Live|In Progress|Planning",
      "detail": "<description>"
    }
  ],
  "joint_actions": [
    {
      "action": "<collaborative next step>",
      "target_date": "<target date or null>"
    }
  ]
}

Frame problems as improvement opportunities. Highlight wins. Be specific with data. If data is limited (e.g. tool results say "source: local_tracker"), still produce a meaningful review using whatever data is available. Do NOT tell the user that Salesforce is disconnected — just work with what you have."""


def _get_tracker_account(account_name: str) -> dict | None:
    """Look up an account in the local tracker DB by name (fuzzy match)."""
    try:
        from main import get_all_accounts
        accounts = get_all_accounts()
        name_lower = account_name.lower()
        for account in accounts:
            if account["name"].lower() == name_lower or name_lower in account["name"].lower():
                return account
        return None
    except Exception as e:
        logger.warning(f"Could not look up tracker account: {e}")
        return None


def _tracker_fallback(tool_name: str, tool_input: dict) -> str:
    """Return local tracker data when Salesforce is not connected."""
    account_name = tool_input.get("account_name", "")
    account = _get_tracker_account(account_name)

    if not account:
        return json.dumps({
            "source": "local_tracker",
            "note": f"No account named '{account_name}' found in the tracker.",
            "data": []
        })

    if tool_name == "query_salesforce_account":
        return json.dumps({
            "source": "local_tracker",
            "data": [{
                "Name": account["name"],
                "Type": account["tier"],
                "Owner": {"Name": account["owner"]},
                "HealthSentiment": account["healthSentiment"],
                "EngagementStage": account["engagementStage"],
                "NextQbrDate": account["nextQbrDate"],
                "QbrCompletion": account["qbrCompletion"],
                "KeyLearnings": account["keyLearnings"],
                "NextSteps": account["nextSteps"],
                "LatestUpdate": account["latestUpdate"],
            }]
        })
    elif tool_name == "query_salesforce_contacts":
        return json.dumps({
            "source": "local_tracker",
            "data": account.get("contacts", [])
        })
    elif tool_name == "query_salesforce_activities":
        # Synthesize activity-like data from action items and latest update
        activities = []
        for item in account.get("actionItems", []):
            activities.append({
                "Subject": item.get("text", "Action item"),
                "Status": "Completed" if item.get("completed") else "Open",
            })
        if account.get("latestUpdate"):
            activities.append({
                "Subject": "Latest update",
                "Description": account["latestUpdate"],
                "Status": "Completed",
            })
        return json.dumps({"source": "local_tracker", "data": activities})
    else:
        # Cases and opportunities have no local equivalent
        return json.dumps({
            "source": "local_tracker",
            "note": f"No {tool_name.replace('query_salesforce_', '')} data available without Salesforce. Use other available account data to inform the briefing.",
            "data": []
        })


async def execute_salesforce_tool(tool_name: str, tool_input: dict) -> str:
    """Execute a Salesforce tool call via the MCP client, falling back to local tracker data."""
    try:
        from services.salesforce_mcp import salesforce_client

        if not salesforce_client.is_connected:
            logger.info(f"Salesforce not connected, using tracker fallback for {tool_name}")
            return _tracker_fallback(tool_name, tool_input)

        account_name = tool_input.get("account_name", "")
        days = tool_input.get("days", 90)

        if tool_name == "query_salesforce_cases":
            result = await salesforce_client.get_account_cases(account_name, days)
        elif tool_name == "query_salesforce_opportunities":
            status = tool_input.get("status", "all")
            if status == "open":
                result = await salesforce_client.get_open_opportunities(account_name)
            elif status in ("won", "lost"):
                result = await salesforce_client.get_closed_opportunities(account_name, days)
                if status == "won":
                    result = [r for r in result if r.get("IsWon", False)]
                else:
                    result = [r for r in result if not r.get("IsWon", True)]
            else:
                open_ops = await salesforce_client.get_open_opportunities(account_name)
                closed_ops = await salesforce_client.get_closed_opportunities(account_name, days)
                result = open_ops + closed_ops
        elif tool_name == "query_salesforce_contacts":
            result = await salesforce_client.get_contacts(account_name)
        elif tool_name == "query_salesforce_activities":
            result = await salesforce_client.get_activities(account_name, days)
        elif tool_name == "query_salesforce_account":
            result = await salesforce_client.get_account_info(account_name)
        else:
            return json.dumps({"error": f"Unknown tool: {tool_name}"})

        return json.dumps(result, default=str)

    except Exception as e:
        logger.error(f"Salesforce tool error ({tool_name}): {e}")
        # Fall back to tracker data on any Salesforce error
        return _tracker_fallback(tool_name, tool_input)


async def generate_briefing_stream(
    briefing_type: str,
    user_message: str,
) -> AsyncGenerator[str, None]:
    """
    Stream briefing generation using Claude with tool use.

    Yields Server-Sent Events (SSE) with these event types:
    - tool_start: Claude is calling a Salesforce tool
    - tool_done: Tool call completed
    - assistant_message: Claude has a text message
    - briefing_ready: Final briefing JSON is ready
    - error: Something went wrong
    """
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        yield _sse({"type": "error", "message": "ANTHROPIC_API_KEY not configured"})
        return

    # Send an immediate heartbeat so the SSE connection stays alive
    yield _sse({"type": "status", "message": "Starting briefing generation..."})

    try:
        client = anthropic.AsyncAnthropic(api_key=api_key)

        system = INTERNAL_SYSTEM if briefing_type == "internal" else CUSTOMER_SYSTEM
        messages = [{"role": "user", "content": user_message}]

        # Agentic loop — Claude calls tools, we execute them, feed results back
        max_iterations = 10
        for iteration in range(max_iterations):
            logger.info(f"Briefing generation iteration {iteration + 1}")

            # Force tool use on the first iteration so Claude gathers data
            # instead of just describing what it would do
            api_kwargs = dict(
                model="claude-haiku-4-5-20251001",
                max_tokens=4096,
                system=system,
                tools=SALESFORCE_TOOLS,
                messages=messages,
            )
            if iteration == 0:
                api_kwargs["tool_choice"] = {"type": "any"}

            response = await client.messages.create(**api_kwargs)

            # Process response content blocks and collect tool results
            has_tool_use = False
            tool_results = []
            briefing_found = False

            for block in response.content:
                if block.type == "text":
                    # Check if this text contains the final briefing JSON
                    briefing_json = _extract_briefing_json(block.text)
                    if briefing_json:
                        # Save and signal completion
                        from main import save_briefing_result
                        import uuid

                        account_id = _find_account_id(briefing_json, user_message)
                        result_id = str(uuid.uuid4())
                        save_briefing_result(
                            result_id, account_id, briefing_type, 90, briefing_json
                        )

                        yield _sse({
                            "type": "briefing_ready",
                            "result_id": result_id,
                            "account_id": account_id,
                        })
                        briefing_found = True
                        break
                    else:
                        yield _sse({"type": "assistant_message", "message": block.text})

                elif block.type == "tool_use":
                    has_tool_use = True

                    # Signal tool start
                    tool_label = _tool_display_name(block.name, block.input)
                    yield _sse({"type": "tool_start", "message": tool_label})

                    # Execute the tool
                    result = await execute_salesforce_tool(block.name, block.input)

                    yield _sse({"type": "tool_done", "message": f"{tool_label} - done"})

                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": result,
                    })

            if briefing_found:
                return

            # Add assistant message to conversation
            messages.append({"role": "assistant", "content": response.content})

            # If there were tool calls, add tool results
            if has_tool_use:
                messages.append({"role": "user", "content": tool_results})
            else:
                # No tool use and no briefing JSON found — we're done
                break

            # Stop if Claude signals end of turn
            if response.stop_reason == "end_turn" and not has_tool_use:
                break

        if not briefing_found:
            yield _sse({"type": "error", "message": "Generation completed but no structured briefing was produced. Please try again."})

    except anthropic.AuthenticationError:
        yield _sse({"type": "error", "message": "Invalid Anthropic API key. Please check your ANTHROPIC_API_KEY."})
    except Exception as e:
        logger.error(f"Briefing generation error: {e}")
        yield _sse({"type": "error", "message": f"Generation failed: {str(e)}"})


def _extract_briefing_json(text: str) -> dict | None:
    """Try to extract a briefing JSON from Claude's response text."""
    if "```json" in text:
        try:
            json_str = text.split("```json")[1].split("```")[0]
            return json.loads(json_str.strip())
        except (json.JSONDecodeError, IndexError):
            pass
    elif "```" in text:
        try:
            json_str = text.split("```")[1].split("```")[0]
            return json.loads(json_str.strip())
        except (json.JSONDecodeError, IndexError):
            pass

    # Try parsing the whole text as JSON
    try:
        return json.loads(text.strip())
    except json.JSONDecodeError:
        pass

    return None


def _find_account_id(briefing_json: dict, user_message: str) -> str:
    """Try to match the account from the briefing to a local account ID."""
    try:
        from main import get_all_accounts
        accounts = get_all_accounts()

        # Check the user message for account name matches
        user_lower = user_message.lower()
        for account in accounts:
            if account["name"].lower() in user_lower:
                return account["id"]

        # Fallback — return first account or "unknown"
        return accounts[0]["id"] if accounts else "unknown"
    except Exception:
        return "unknown"


def _tool_display_name(tool_name: str, tool_input: dict) -> str:
    """Create a user-friendly display name for a tool call."""
    account = tool_input.get("account_name", "")
    names = {
        "query_salesforce_cases": f"Fetching support cases for {account}",
        "query_salesforce_opportunities": f"Pulling pipeline data for {account}",
        "query_salesforce_contacts": f"Loading contacts for {account}",
        "query_salesforce_activities": f"Checking recent activity for {account}",
        "query_salesforce_account": f"Looking up account info for {account}",
    }
    return names.get(tool_name, f"Calling {tool_name}")


def _sse(data: dict) -> str:
    """Format a dict as a Server-Sent Event line."""
    return f"data: {json.dumps(data)}\n\n"
