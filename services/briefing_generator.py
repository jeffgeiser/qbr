"""
Briefing Generator Service

Uses a local LLM (OpenAI-compatible API) with tool-use to orchestrate
Salesforce queries and generate structured briefing documents. The model
decides which queries to run based on the user's request, calls the
Salesforce MCP tools, and synthesizes results.
"""

import os
import json
import logging
from datetime import datetime
from typing import AsyncGenerator

from openai import AsyncOpenAI

logger = logging.getLogger(__name__)


# --- Tool Definitions for Claude ---

SALESFORCE_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "query_salesforce_cases",
            "description": "Query Salesforce cases (support tickets) for a customer account. Returns case number, subject, status, priority, created/closed dates, and descriptions.",
            "parameters": {
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
        }
    },
    {
        "type": "function",
        "function": {
            "name": "query_salesforce_opportunities",
            "description": "Query Salesforce opportunities (deals/pipeline) for a customer account. Can filter by open, won, or lost. Returns opportunity name, stage, amount, close date, probability, and description.",
            "parameters": {
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
        }
    },
    {
        "type": "function",
        "function": {
            "name": "query_salesforce_contacts",
            "description": "Query Salesforce contacts for a customer account. Returns name, email, phone, title, and department.",
            "parameters": {
                "type": "object",
                "properties": {
                    "account_name": {
                        "type": "string",
                        "description": "The customer account name"
                    }
                },
                "required": ["account_name"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "query_salesforce_activities",
            "description": "Query Salesforce tasks/activities for a customer account. Returns subject, status, date, priority, and description of recent interactions.",
            "parameters": {
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
        }
    },
    {
        "type": "function",
        "function": {
            "name": "query_salesforce_account",
            "description": "Query the Salesforce account record itself. Returns account name, type, industry, annual revenue, owner, and description.",
            "parameters": {
                "type": "object",
                "properties": {
                    "account_name": {
                        "type": "string",
                        "description": "The customer account name"
                    }
                },
                "required": ["account_name"]
            }
        }
    },
]


# --- System Prompts ---

INTERNAL_SYSTEM = """You are an expert account strategist at Zenlayer, a global edge cloud and connectivity provider.

You are helping generate an INTERNAL Executive Health Brief for leadership. This document is CONFIDENTIAL and should be candid, evidence-based, and action-oriented. Lead with the narrative, support with data.

IMPORTANT: You MUST call the Salesforce tools to gather real data. Do NOT describe what you would do — actually call the tools. Start by calling multiple tools in parallel (account info, cases, opportunities, contacts, activities).

Your workflow:
1. IMMEDIATELY call the Salesforce tools to gather data about the customer account — do not ask for confirmation
2. Analyze the data across all dimensions
3. Generate a structured briefing following the pyramid principle: conclusion first, then evidence

When you have enough data, output the briefing as a JSON block wrapped in ```json``` fences with this EXACT structure:
{
  "executive_snapshot": "<2-4 sentence narrative assessment. A VP should be able to read just this and understand the account situation. Be specific — reference dollar amounts, trends, and timeframes.>",
  "revenue_picture": {
    "summary": "<1 sentence revenue overview>",
    "closed_won": [
      {
        "name": "<deal name>",
        "amount": "<formatted amount like $50K>",
        "close_date": "<date or timeframe>",
        "detail": "<brief context>"
      }
    ],
    "closed_lost": [
      {
        "name": "<deal name>",
        "amount": "<formatted amount>",
        "close_date": "<date>",
        "detail": "<why it was lost if known>"
      }
    ],
    "active_pipeline": [
      {
        "name": "<opportunity name>",
        "amount": "<formatted amount>",
        "stage": "<current stage>",
        "probability": "<percentage or null>",
        "detail": "<context>"
      }
    ],
    "total_pipeline_value": "<formatted total like $1.2M>",
    "revenue_at_risk": "<formatted amount or null>"
  },
  "engagement_activity": {
    "summary": "<1-2 sentence engagement overview>",
    "support_tickets": {
      "open_count": <number>,
      "closed_count": <number>,
      "critical_tickets": [
        {
          "case_number": "<case #>",
          "subject": "<subject>",
          "status": "<status>",
          "priority": "<priority>",
          "age_days": "<days open or null>"
        }
      ],
      "trend": "<improving|stable|degrading|no data>"
    },
    "recent_interactions": [
      {
        "date": "<date or timeframe>",
        "type": "<meeting|email|call|task>",
        "summary": "<brief description>"
      }
    ],
    "key_contacts": [
      {
        "name": "<contact name>",
        "title": "<title>",
        "engagement_level": "<active|passive|disengaged|unknown>"
      }
    ]
  },
  "strategic_risks": [
    {
      "severity": "critical|warning|info",
      "title": "<short title>",
      "description": "<detailed description with specific evidence>",
      "evidence": ["<specific data point>"]
    }
  ],
  "recommended_actions": [
    {
      "priority": "urgent|high|normal",
      "action": "<what needs to happen>",
      "rationale": "<why this matters>",
      "owner_suggestion": "<suggested owner or team>"
    }
  ],
  "health_scorecard": [
    {"label": "Revenue Health", "score": <1-5>, "detail": "<1 sentence why>"},
    {"label": "Support Health", "score": <1-5>, "detail": "<1 sentence why>"},
    {"label": "Engagement Depth", "score": <1-5>, "detail": "<1 sentence why>"},
    {"label": "Pipeline Momentum", "score": <1-5>, "detail": "<1 sentence why>"},
    {"label": "Relationship Strength", "score": <1-5>, "detail": "<1 sentence why>"}
  ]
}

Be specific — reference actual case numbers, dollar amounts, contact names, and dates. If data is limited (e.g. tool results say "source: local_tracker"), still produce a meaningful assessment using whatever data is available. Do NOT tell the user that Salesforce is disconnected — just work with what you have."""

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


# Cache resolved account names to avoid repeated lookups within a session
_resolved_names: dict[str, str] = {}


async def _resolve_account(account_name: str) -> str:
    """Resolve a partial account name to the exact Salesforce name, with caching."""
    if account_name in _resolved_names:
        return _resolved_names[account_name]
    try:
        from services.salesforce_mcp import salesforce_client
        if salesforce_client.is_connected:
            resolved = await salesforce_client.resolve_account_name(account_name)
            _resolved_names[account_name] = resolved
            return resolved
    except Exception as e:
        logger.warning(f"Account name resolution failed: {e}")
    return account_name


def _truncate_result(result_json: str, max_bytes: int = 8000) -> str:
    """Truncate large tool results to stay within the model's context window."""
    if len(result_json) <= max_bytes:
        return result_json
    try:
        data = json.loads(result_json)
        if isinstance(data, list) and len(data) > 5:
            truncated = data[:5]
            truncated.append({"_note": f"Truncated: showing 5 of {len(data)} records"})
            return json.dumps(truncated, default=str)
    except (json.JSONDecodeError, TypeError):
        pass
    return result_json[:max_bytes] + '..."}'


async def execute_salesforce_tool(tool_name: str, tool_input: dict) -> str:
    """Execute a Salesforce tool call via the MCP client, falling back to local tracker data."""
    try:
        from services.salesforce_mcp import salesforce_client

        if not salesforce_client.is_connected:
            logger.warning(f"[SF] Not connected — falling back to tracker for {tool_name}({tool_input})")
            return _tracker_fallback(tool_name, tool_input)

        account_name = tool_input.get("account_name", "")
        days = tool_input.get("days", 90)

        # Resolve partial account names to exact Salesforce names
        account_name = await _resolve_account(account_name)

        logger.info(f"[SF] Calling {tool_name} for account='{account_name}' days={days}")

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

        result_json = json.dumps(result, default=str)
        logger.info(f"[SF] {tool_name} returned {len(result)} records ({len(result_json)} bytes)")
        if len(result) == 0:
            logger.warning(f"[SF] {tool_name} returned EMPTY results for '{account_name}'")
        return _truncate_result(result_json)

    except Exception as e:
        logger.error(f"[SF] {tool_name} FAILED for {tool_input}: {type(e).__name__}: {e}", exc_info=True)
        # Fall back to tracker data on any Salesforce error
        return _tracker_fallback(tool_name, tool_input)


async def generate_briefing_stream(
    briefing_type: str,
    user_message: str,
) -> AsyncGenerator[str, None]:
    """
    Stream briefing generation using a local LLM (OpenAI-compatible API) with tool use.

    Yields Server-Sent Events (SSE) with these event types:
    - tool_start: Model is calling a Salesforce tool
    - tool_done: Tool call completed
    - assistant_message: Model has a text message
    - briefing_ready: Final briefing JSON is ready
    - error: Something went wrong
    """
    llm_url = os.environ.get("LOCAL_LLM_URL", "http://10.1.0.251:18010/v1/")
    llm_model = os.environ.get("LOCAL_LLM_MODEL", "Qwen/Qwen3.5-35B-A3B")

    # Send an immediate heartbeat so the SSE connection stays alive
    yield _sse({"type": "status", "message": "Starting briefing generation..."})

    try:
        client = AsyncOpenAI(base_url=llm_url, api_key="not-needed")

        system = INTERNAL_SYSTEM if briefing_type == "internal" else CUSTOMER_SYSTEM
        messages = [
            {"role": "system", "content": system},
            {"role": "user", "content": user_message},
        ]

        # Agentic loop — model calls tools, we execute them, feed results back
        max_iterations = 10
        for iteration in range(max_iterations):
            logger.info(f"Briefing generation iteration {iteration + 1}")

            api_kwargs = dict(
                model=llm_model,
                max_tokens=4096,
                tools=SALESFORCE_TOOLS,
                messages=messages,
            )
            # Force tool use on the first iteration so the model gathers data
            if iteration == 0:
                api_kwargs["tool_choice"] = "required"

            response = await client.chat.completions.create(**api_kwargs)

            choice = response.choices[0]
            message = choice.message

            # Process response and collect tool results
            has_tool_use = False
            briefing_found = False

            # Check text content for briefing JSON
            if message.content:
                briefing_json = _extract_briefing_json(message.content)
                if briefing_json:
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
                else:
                    yield _sse({"type": "assistant_message", "message": message.content})

            if briefing_found:
                return

            # Process tool calls
            if message.tool_calls:
                has_tool_use = True

                # Add assistant message (with tool_calls) to conversation
                messages.append(message)

                for tool_call in message.tool_calls:
                    tool_name = tool_call.function.name
                    tool_input = json.loads(tool_call.function.arguments)

                    tool_label = _tool_display_name(tool_name, tool_input)
                    yield _sse({"type": "tool_start", "message": tool_label})

                    result = await execute_salesforce_tool(tool_name, tool_input)

                    # Count records for the frontend — parse MCP text format
                    import re
                    count = None
                    try:
                        parsed = json.loads(result)
                        if isinstance(parsed, list):
                            for item in parsed:
                                if isinstance(item, dict) and "text" in item:
                                    text = item["text"]
                                    # Try "Query returned N records:" header
                                    m = re.search(r'(?:returned|found)\s+(\d+)\s+records?', text, re.IGNORECASE)
                                    if m:
                                        count = int(m.group(1))
                                        break
                                    # Fallback: count "Record N:" occurrences
                                    record_matches = re.findall(r'Record \d+:', text)
                                    if record_matches:
                                        count = len(record_matches)
                                        break
                            if count is None and len(parsed) > 0:
                                # Check if the items themselves are records
                                if not any(isinstance(p, dict) and "text" in p for p in parsed):
                                    count = len(parsed)
                        elif isinstance(parsed, dict) and "data" in parsed:
                            count = len(parsed["data"])
                    except (json.JSONDecodeError, TypeError):
                        pass

                    done_msg = f"{tool_label} — {count} record{'s' if count != 1 else ''} found" if count is not None else f"{tool_label} — done"
                    yield _sse({"type": "tool_done", "message": done_msg})

                    messages.append({
                        "role": "tool",
                        "tool_call_id": tool_call.id,
                        "content": result,
                    })
            else:
                # No tool calls — add message to conversation and stop
                messages.append(message)
                break

            # Stop if model signals end of turn with no tool calls
            if choice.finish_reason == "stop" and not has_tool_use:
                break

        if not briefing_found:
            yield _sse({"type": "error", "message": "Generation completed but no structured briefing was produced. Please try again."})

    except Exception as e:
        logger.error(f"Briefing generation error: {e}")
        yield _sse({"type": "error", "message": f"Generation failed: {str(e)}"})


def _repair_json(json_str: str) -> str:
    """Attempt to fix common JSON issues from LLM output."""
    import re

    s = json_str.strip()

    # Remove trailing commas before } or ]
    s = re.sub(r',\s*([}\]])', r'\1', s)

    # Fix bare key:value pairs in arrays that should be objects
    # e.g. "Key": value  ->  {"label": "Key", "score": value} when inside scorecard array
    # More general: fix "key": value lines that aren't wrapped in {}
    # This handles the specific Qwen issue: "Relationship Depth": 2 in an array of objects
    def fix_bare_kv_in_array(match):
        key = match.group(1)
        value = match.group(2).strip().rstrip(',')
        # Try to guess the object shape from context
        try:
            v = json.loads(value)
            if isinstance(v, (int, float)):
                return f'{{"label": "{key}", "score": {value}}}'
            else:
                return f'{{"label": "{key}", "value": {value}}}'
        except (json.JSONDecodeError, ValueError):
            return f'{{"label": "{key}", "value": {value}}}'

    # Match array elements that are bare "key": value (not wrapped in {})
    # Look for pattern: after [ or , followed by "key": value (not starting with {)
    s = re.sub(
        r'(?<=[\[,])\s*"([^"]+)"\s*:\s*([^,\]\{][^,\]]*)',
        fix_bare_kv_in_array,
        s
    )

    return s


def _extract_briefing_json(text: str) -> dict | None:
    """Try to extract a briefing JSON from the model's response text."""
    json_str = None

    if "```json" in text:
        try:
            json_str = text.split("```json")[1].split("```")[0]
        except IndexError:
            pass
    elif "```" in text:
        try:
            json_str = text.split("```")[1].split("```")[0]
        except IndexError:
            pass

    candidates = []
    if json_str:
        candidates.append(json_str.strip())
    candidates.append(text.strip())

    for candidate in candidates:
        # Try parsing as-is first
        try:
            result = json.loads(candidate)
            if isinstance(result, dict):
                return result
        except json.JSONDecodeError:
            pass

        # Try with repairs
        try:
            repaired = _repair_json(candidate)
            result = json.loads(repaired)
            if isinstance(result, dict):
                logger.info("Briefing JSON parsed successfully after repair")
                return result
        except json.JSONDecodeError as e:
            logger.debug(f"JSON repair attempt failed: {e}")

    # Last resort: find the outermost { } block and try to parse that
    brace_start = text.find('{')
    if brace_start >= 0:
        depth = 0
        for i in range(brace_start, len(text)):
            if text[i] == '{':
                depth += 1
            elif text[i] == '}':
                depth -= 1
                if depth == 0:
                    raw = text[brace_start:i + 1]
                    for attempt in [raw, _repair_json(raw)]:
                        try:
                            result = json.loads(attempt)
                            if isinstance(result, dict):
                                logger.info("Briefing JSON extracted from brace matching")
                                return result
                        except json.JSONDecodeError:
                            continue
                    break

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
