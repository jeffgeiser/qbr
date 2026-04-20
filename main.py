
from fastapi import FastAPI, Request, Form, BackgroundTasks
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse, StreamingResponse
from jinja2 import Environment, FileSystemLoader, select_autoescape
from typing import List, Optional, Dict
from contextlib import asynccontextmanager
import json
import uuid
import sqlite3
import os
import logging
import asyncio
import hmac
import hashlib
import base64

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# --- Jinja2 Template Setup ---
templates_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "templates")
jinja_env = Environment(
    loader=FileSystemLoader(templates_dir),
    autoescape=select_autoescape(["html"]),
)

# --- Database Setup ---
DB_PATH = os.environ.get("DB_PATH", "/app/data/accounts.db")

def get_db():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS accounts (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            tier TEXT NOT NULL,
            owner TEXT DEFAULT '',
            health_sentiment TEXT DEFAULT 'green',
            engagement_stage TEXT DEFAULT '',
            next_qbr_date TEXT DEFAULT '',
            qbr_q1 INTEGER DEFAULT 0,
            qbr_q2 INTEGER DEFAULT 0,
            qbr_q3 INTEGER DEFAULT 0,
            qbr_q4 INTEGER DEFAULT 0,
            qbr_milestones TEXT DEFAULT '{}',
            key_learnings TEXT DEFAULT '',
            next_steps TEXT DEFAULT '',
            latest_update TEXT DEFAULT '',
            action_items TEXT DEFAULT '[]',
            contacts TEXT DEFAULT '[]'
        )
    ''')
    conn.commit()

    # Migrations for existing databases
    migrations = [
        "ALTER TABLE accounts ADD COLUMN next_steps TEXT DEFAULT ''",
        "ALTER TABLE accounts ADD COLUMN latest_update TEXT DEFAULT ''",
        "ALTER TABLE accounts ADD COLUMN engagement_stage TEXT DEFAULT ''",
        "ALTER TABLE accounts ADD COLUMN qbr_milestones TEXT DEFAULT '{}'",
    ]
    for migration in migrations:
        try:
            cursor.execute(migration)
            conn.commit()
        except:
            pass

    # Briefing results table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS briefing_results (
            id TEXT PRIMARY KEY,
            account_id TEXT NOT NULL,
            briefing_type TEXT NOT NULL,
            time_range_days INTEGER DEFAULT 90,
            result_json TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
    ''')
    conn.commit()

    # Seed with sample data if table is empty
    cursor.execute("SELECT COUNT(*) FROM accounts")
    if cursor.fetchone()[0] == 0:
        sample_accounts = [
            # Tier 1 accounts (12)
            ("1", "Zoom", "Tier 1", "Carlos Morell", "green", "", 0, 0, 0, 0, "", "", "", "[]", "[]"),
            ("2", "Nvidia", "Tier 1", "Wade Chen", "green", "", 0, 0, 0, 0, "", "", "", "[]", "[]"),
            ("3", "Cisco - Jasper", "Tier 1", "Josh Lipold", "green", "", 0, 0, 0, 0, "", "", "Will target in person dinner", "[]", '[{"name": "Mike Hayes", "email": ""}, {"name": "Stef", "email": ""}]'),
            ("4", "Cisco - Webex", "Tier 1", "Josh Lepold", "green", "", 0, 0, 0, 0, "", "", "Will target in person dinner", "[]", '[{"name": "Gabe", "email": ""}]'),
            ("5", "Zscaler", "Tier 1", "Carlos Morell", "green", "", 0, 0, 0, 0, "", "", "", "[]", "[]"),
            ("6", "McAfee", "Tier 1", "Eric Rodriguez", "green", "", 0, 0, 0, 0, "", "", "Eric to schedule - main sponsor in dallas", "[]", "[]"),
            ("7", "Basis", "Tier 1", "Sean Washak", "green", "", 0, 0, 0, 0, "", "", "", "[]", "[]"),
            ("8", "DXC Technology", "Tier 1", "Carlos Morell", "green", "", 0, 0, 0, 0, "", "", "", "[]", "[]"),
            ("9", "SpaceX", "Tier 1", "Josh Lipold", "green", "", 0, 0, 0, 0, "", "", "Geiser sent email 2/27 - In person Seattle..", "[]", '[{"name": "Jonathan Harrison", "email": ""}]'),
            ("10", "Valve", "Tier 1", "Carlos Morell", "green", "", 0, 0, 0, 0, "", "", "", "[]", "[]"),
            ("11", "Maersk", "Tier 1", "Sean Washak", "green", "", 0, 0, 0, 0, "", "", "", "[]", "[]"),
            ("12", "Netskope", "Tier 1", "Josh Lepold", "green", "", 0, 0, 0, 0, "", "", "Dinner focused - try to get to Vegas.. Technically oriented", "[]", '[{"name": "Jason Hoffman", "email": ""}]'),
            # Tier 2 accounts (8)
            ("13", "Proofpoint", "Tier 2", "Josh Lepold", "green", "", 0, 0, 0, 0, "", "", "Early January completed a QBR.. Target April..", "[]", '[{"name": "Brian Adams", "email": ""}]'),
            ("14", "Catchpoint", "Tier 2", "Rebecca Yang", "green", "", 0, 0, 0, 0, "", "", "", "[]", "[]"),
            ("15", "Corning", "Tier 2", "Carlos Morell", "green", "", 0, 0, 0, 0, "", "", "", "[]", "[]"),
            ("16", "TPUSA", "Tier 2", "Eric Rodriguez", "green", "", 0, 0, 0, 0, "", "", "Eric to schedule", "[]", "[]"),
            ("17", "Multiplay", "Tier 2", "Wade Chen", "green", "", 0, 0, 0, 0, "", "", "", "[]", "[]"),
            ("18", "Menlo Security", "Tier 2", "Josh Lepold", "green", "", 0, 0, 0, 0, "", "", "Target in person (confirm with Kap whether we want to go in person)...", "[]", '[{"name": "Chris Maxwell", "email": ""}]'),
            ("19", "Cook Medical", "Tier 2", "Josh Lepold", "green", "", 0, 0, 0, 0, "", "", "Virtual -", "[]", '[{"name": "Gareth Orley", "email": ""}]'),
            ("20", "Threatlocker", "Tier 2", "Josh Lepold", "green", "", 0, 0, 0, 0, "", "", "Project kickoff with Qingli, strategic meeting in Florida", "[]", '[{"name": "Martin Olivo", "email": ""}]'),
            # Tier 3 accounts (2)
            ("21", "Mullvad", "Tier 3", "Wade Chen", "green", "", 0, 0, 0, 0, "", "", "", "[]", "[]"),
            ("22", "NSFOCUS", "Tier 3", "Rebecca Yang", "green", "", 0, 0, 0, 0, "", "", "", "[]", "[]"),
        ]
        cursor.executemany('''
            INSERT INTO accounts (id, name, tier, owner, health_sentiment, next_qbr_date, qbr_q1, qbr_q2, qbr_q3, qbr_q4, key_learnings, next_steps, latest_update, action_items, contacts)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', sample_accounts)
        conn.commit()
    conn.close()

def _safe_json(val, default):
    if not val:
        return default
    try:
        return json.loads(val)
    except (json.JSONDecodeError, TypeError):
        return default

def _safe_col(row, col, default=""):
    return row[col] if col in row.keys() else default

def row_to_account(row):
    # Parse QBR milestones — {q1: {status, date}, q2: ...}
    milestones_raw = _safe_json(_safe_col(row, "qbr_milestones", "{}"), {})
    default_milestone = {"status": "not_started", "date": ""}

    # Backfill from legacy boolean columns
    qbr_milestones = {}
    for q in ["q1", "q2", "q3", "q4"]:
        if q in milestones_raw and milestones_raw[q].get("status"):
            qbr_milestones[q] = milestones_raw[q]
        else:
            is_done = bool(row[f"qbr_{q}"]) if f"qbr_{q}" in row.keys() else False
            qbr_milestones[q] = {"status": "completed" if is_done else "not_started", "date": ""}

    # Enhanced contacts: each contact now has name, email, title, linkedin
    contacts_raw = _safe_json(row["contacts"], [])
    contacts = []
    for c in contacts_raw:
        contacts.append({
            "name": c.get("name", ""),
            "email": c.get("email", ""),
            "title": c.get("title", ""),
            "linkedin": c.get("linkedin", ""),
        })

    return {
        "id": row["id"],
        "name": row["name"],
        "tier": row["tier"],
        "owner": row["owner"],
        "healthSentiment": row["health_sentiment"],
        "engagementStage": _safe_col(row, "engagement_stage", ""),
        "nextQbrDate": row["next_qbr_date"],
        "qbrCompletion": {
            "q1": qbr_milestones["q1"]["status"] == "completed",
            "q2": qbr_milestones["q2"]["status"] == "completed",
            "q3": qbr_milestones["q3"]["status"] == "completed",
            "q4": qbr_milestones["q4"]["status"] == "completed",
        },
        "qbrMilestones": qbr_milestones,
        "keyLearnings": row["key_learnings"] or "",
        "nextSteps": _safe_col(row, "next_steps", ""),
        "latestUpdate": _safe_col(row, "latest_update", ""),
        "actionItems": _safe_json(row["action_items"], []),
        "contacts": contacts,
    }

def get_all_accounts():
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM accounts ORDER BY name")
    rows = cursor.fetchall()
    conn.close()
    return [row_to_account(row) for row in rows]

def get_account_by_id(account_id: str):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM accounts WHERE id = ?", (account_id,))
    row = cursor.fetchone()
    conn.close()
    return row_to_account(row) if row else None

def save_account(account_data: dict):
    conn = get_db()
    cursor = conn.cursor()
    milestones = account_data.get("qbrMilestones", {})
    cursor.execute('''
        INSERT OR REPLACE INTO accounts (id, name, tier, owner, health_sentiment, engagement_stage, next_qbr_date,
            qbr_q1, qbr_q2, qbr_q3, qbr_q4, qbr_milestones,
            key_learnings, next_steps, latest_update, action_items, contacts)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', (
        account_data["id"],
        account_data["name"],
        account_data["tier"],
        account_data["owner"],
        account_data["healthSentiment"],
        account_data.get("engagementStage", ""),
        account_data.get("nextQbrDate", ""),
        1 if milestones.get("q1", {}).get("status") == "completed" else 0,
        1 if milestones.get("q2", {}).get("status") == "completed" else 0,
        1 if milestones.get("q3", {}).get("status") == "completed" else 0,
        1 if milestones.get("q4", {}).get("status") == "completed" else 0,
        json.dumps(milestones),
        account_data.get("keyLearnings", ""),
        account_data.get("nextSteps", ""),
        account_data.get("latestUpdate", ""),
        json.dumps(account_data.get("actionItems", [])),
        json.dumps(account_data.get("contacts", []))
    ))
    conn.commit()
    conn.close()

def delete_account_by_id(account_id: str):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM accounts WHERE id = ?", (account_id,))
    conn.commit()
    conn.close()

def save_briefing_result(result_id: str, account_id: str, briefing_type: str, time_range_days: int, result: dict):
    conn = get_db()
    cursor = conn.cursor()
    from datetime import datetime
    cursor.execute('''
        INSERT OR REPLACE INTO briefing_results (id, account_id, briefing_type, time_range_days, result_json, created_at)
        VALUES (?, ?, ?, ?, ?, ?)
    ''', (result_id, account_id, briefing_type, time_range_days, json.dumps(result), datetime.utcnow().isoformat()))
    conn.commit()
    conn.close()

def get_briefing_result(result_id: str):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM briefing_results WHERE id = ?", (result_id,))
    row = cursor.fetchone()
    conn.close()
    if row:
        return {
            "id": row["id"],
            "account_id": row["account_id"],
            "briefing_type": row["briefing_type"],
            "time_range_days": row["time_range_days"],
            "result": json.loads(row["result_json"]),
            "created_at": row["created_at"],
        }
    return None


# --- App Lifespan ---

async def try_connect_salesforce():
    """Attempt to connect to Salesforce MCP. Non-fatal if it fails."""
    try:
        from services.salesforce_mcp import salesforce_client
        if os.environ.get("SALESFORCE_CLIENT_ID"):
            await salesforce_client.connect()
            logger.info("Salesforce MCP connected successfully.")
        else:
            logger.warning("Salesforce credentials not configured. Briefing generator will use mock data.")
    except Exception as e:
        logger.warning(f"Could not connect to Salesforce MCP: {e}. Briefing generator will use mock data.")

@asynccontextmanager
async def lifespan(app):
    # Startup
    init_db()
    await try_connect_salesforce()
    yield
    # Shutdown
    try:
        from services.salesforce_mcp import salesforce_client
        await salesforce_client.disconnect()
    except Exception:
        pass


app = FastAPI(root_path="/qbr", lifespan=lifespan)


# --- Template Rendering Helper ---

def render_template(template_name: str, **kwargs) -> HTMLResponse:
    template = jinja_env.get_template(template_name)
    html = template.render(**kwargs)
    return HTMLResponse(content=html)


# --- Routes: Portfolio Dashboard ---

@app.get("/", response_class=HTMLResponse)
@app.get("", response_class=HTMLResponse)
async def dashboard(request: Request):
    accounts = get_all_accounts()
    accounts_json = json.dumps(accounts)
    return render_template(
        "dashboard.html",
        accounts_json=accounts_json,
        active_nav="portfolio",
    )


# --- Routes: Account Details ---

@app.get("/account/{account_id}", response_class=HTMLResponse)
async def account_details(account_id: str):
    account = get_account_by_id(account_id)
    if not account:
        return RedirectResponse(url="/qbr/", status_code=303)
    account_json = json.dumps(account)
    return render_template(
        "account_detail.html",
        account=account,
        account_json=account_json,
        active_nav="portfolio",
    )


# --- Routes: Save / Delete Account ---

@app.post("/save")
async def save_account_endpoint(request: Request):
    """Accept either JSON body or form data for saving accounts."""
    content_type = request.headers.get("content-type", "")

    if "application/json" in content_type:
        body = await request.json()
        account_id = body.get("id") or str(uuid.uuid4())
        contacts = [c for c in body.get("contacts", []) if c.get("name") or c.get("email")]
        action_items = [item for item in body.get("actionItems", []) if item and item.strip()]
        account_data = {
            "id": account_id,
            "name": body.get("name", ""),
            "tier": body.get("tier", "Tier 2"),
            "owner": body.get("owner", ""),
            "healthSentiment": body.get("healthSentiment", "green"),
            "engagementStage": body.get("engagementStage", ""),
            "nextQbrDate": body.get("nextQbrDate", ""),
            "keyLearnings": body.get("keyLearnings", ""),
            "nextSteps": body.get("nextSteps", ""),
            "latestUpdate": body.get("latestUpdate", ""),
            "contacts": contacts,
            "actionItems": action_items,
            "qbrMilestones": body.get("qbrMilestones", {}),
        }
        save_account(account_data)
        if body.get("id"):
            return JSONResponse({"success": True, "redirect": f"/qbr/account/{account_id}"})
        else:
            return JSONResponse({"success": True, "redirect": "/qbr/"})

    # Legacy form submission support
    form = await request.form()
    account_id = form.get("id") or str(uuid.uuid4())
    try:
        contacts = json.loads(form.get("contacts_json", "[]"))
        contacts = [c for c in contacts if c.get("name") or c.get("email")]
    except:
        contacts = []
    try:
        action_items = json.loads(form.get("action_items_json", "[]"))
        action_items = [item for item in action_items if item.strip()]
    except:
        action_items = []

    milestones = {}
    for q in ["q1", "q2", "q3", "q4"]:
        milestones[q] = {
            "status": "completed" if form.get(q) == "on" else "not_started",
            "date": "",
        }

    account_data = {
        "id": account_id,
        "name": form.get("name", ""),
        "tier": form.get("tier", "Tier 2"),
        "owner": form.get("owner", ""),
        "healthSentiment": form.get("health_sentiment", "green"),
        "engagementStage": form.get("engagement_stage", ""),
        "nextQbrDate": form.get("next_qbr_date", ""),
        "keyLearnings": form.get("key_learnings", ""),
        "nextSteps": form.get("next_steps", ""),
        "latestUpdate": form.get("latest_update", ""),
        "contacts": contacts,
        "actionItems": action_items,
        "qbrMilestones": milestones,
    }
    save_account(account_data)

    if form.get("id"):
        return RedirectResponse(url=f"/qbr/account/{account_id}", status_code=303)
    else:
        return RedirectResponse(url="/qbr/", status_code=303)

@app.post("/delete/{account_id}")
async def delete_account(account_id: str):
    delete_account_by_id(account_id)
    return RedirectResponse(url="/qbr/", status_code=303)


# --- Routes: Briefing Generator ---

@app.get("/api/briefings/health")
async def briefings_health():
    """Health check for briefing dependencies."""
    checks = {}
    try:
        import openai
        checks["openai_sdk"] = "ok"
    except ImportError as e:
        checks["openai_sdk"] = f"missing: {e}"

    llm_url = os.environ.get("LOCAL_LLM_URL", "http://10.1.0.251:18010/v1/")
    llm_model = os.environ.get("LOCAL_LLM_MODEL", "Qwen/Qwen3.5-35B-A3B")
    checks["llm_url"] = llm_url
    checks["llm_model"] = llm_model

    try:
        from services.briefing_generator import generate_briefing_stream
        checks["briefing_generator"] = "ok"
    except ImportError as e:
        checks["briefing_generator"] = f"import error: {e}"

    return JSONResponse(checks)


@app.get("/briefings", response_class=HTMLResponse)
async def briefings_page(type: Optional[str] = None):
    return render_template(
        "briefings.html",
        preselected_type=type or "",
        active_nav="briefings",
    )


@app.post("/api/briefings/parse-input")
async def parse_briefing_input(request: Request):
    """Use the local LLM to extract account name and timeframe from natural language."""
    body = await request.json()
    user_input = body.get("input", "").strip()
    if not user_input:
        return JSONResponse({"account_name": "", "days": 90})

    try:
        from openai import AsyncOpenAI
        llm_url = os.environ.get("LOCAL_LLM_URL", "http://10.1.0.251:18010/v1/")
        llm_model = os.environ.get("LOCAL_LLM_MODEL", "Qwen/Qwen3.5-35B-A3B")
        client = AsyncOpenAI(base_url=llm_url, api_key="not-needed")

        response = await client.chat.completions.create(
            model=llm_model,
            max_tokens=100,
            messages=[
                {"role": "system", "content": (
                    "Extract the customer/company name and timeframe from the user's request. "
                    "Respond with ONLY a JSON object, no other text: "
                    '{"account_name": "<company name>", "days": <number of days, default 90>}\n'
                    "Examples:\n"
                    '"analyze Zoom for last 30 days" -> {"account_name": "Zoom", "days": 30}\n'
                    '"SpaceX quarterly review" -> {"account_name": "SpaceX", "days": 90}\n'
                    '"briefing on Nvidia last 6 months" -> {"account_name": "Nvidia", "days": 180}'
                )},
                {"role": "user", "content": user_input},
            ],
        )

        text = response.choices[0].message.content.strip()
        # Extract JSON from response (handle markdown fences)
        if "```" in text:
            text = text.split("```")[1].split("```")[0]
            if text.startswith("json"):
                text = text[4:]
        import json as json_mod
        parsed = json_mod.loads(text.strip())
        return JSONResponse({
            "account_name": parsed.get("account_name", ""),
            "days": parsed.get("days", 90),
        })
    except Exception as e:
        logger.warning(f"LLM input parsing failed: {e}, falling back to raw input")
        # Fallback: use the whole input as account name
        return JSONResponse({"account_name": user_input, "days": 90})


@app.get("/api/briefings/search-account")
async def search_account(q: str = ""):
    """Search Salesforce for accounts matching the query string."""
    q = q.strip()
    if not q:
        return JSONResponse({"accounts": []})

    try:
        from services.salesforce_mcp import salesforce_client, _escape
        if not salesforce_client.is_connected:
            return JSONResponse({"accounts": [], "error": "Salesforce not connected"})

        raw = await salesforce_client._query(
            "Account", ["Name"],
            where=f"Name LIKE '%{_escape(q)}%'",
            limit=10,
        )
        records = salesforce_client._parse_text_records(raw)
        names = [r["Name"] for r in records if "Name" in r]
        return JSONResponse({"accounts": names})
    except Exception as e:
        logger.error(f"Account search failed: {e}")
        return JSONResponse({"accounts": [], "error": str(e)})


@app.post("/api/briefings/generate")
async def generate_briefing_endpoint(request: Request):
    """Streaming API endpoint. Claude orchestrates Salesforce tool calls and generates the briefing."""
    body = await request.json()
    briefing_type = body.get("briefing_type")
    user_message = body.get("user_message", "")

    if not briefing_type or briefing_type not in ("internal", "customer"):
        return JSONResponse({"detail": "briefing_type must be 'internal' or 'customer'"}, status_code=400)

    if not user_message.strip():
        return JSONResponse({"detail": "user_message is required"}, status_code=400)

    try:
        from services.briefing_generator import generate_briefing_stream
    except ImportError as e:
        logger.error(f"Failed to import briefing_generator: {e}")
        return JSONResponse({"detail": f"Briefing service unavailable: {e}"}, status_code=500)

    async def event_stream():
        try:
            async for event in generate_briefing_stream(briefing_type, user_message):
                yield event
        except Exception as e:
            logger.error(f"Stream error: {e}")
            yield f'data: {{"type": "error", "message": "Stream error: {str(e)}"}}\n\n'
        yield "data: [DONE]\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@app.get("/briefings/{account_id}/{briefing_type}", response_class=HTMLResponse)
async def briefing_result_page(account_id: str, briefing_type: str, result_id: Optional[str] = None):
    """Display a generated briefing result."""
    from datetime import datetime

    account = get_account_by_id(account_id)
    if not account:
        return RedirectResponse(url="/qbr/briefings", status_code=303)

    if not result_id:
        return RedirectResponse(url=f"/qbr/briefings?account_id={account_id}&type={briefing_type}", status_code=303)

    result = get_briefing_result(result_id)
    if not result:
        return RedirectResponse(url=f"/qbr/briefings?account_id={account_id}&type={briefing_type}", status_code=303)

    briefing = result["result"]

    # Format the generated date
    try:
        gen_dt = datetime.fromisoformat(result["created_at"])
        generated_date = gen_dt.strftime("%b %d, %Y")
    except:
        generated_date = "Unknown"

    active = "briefing_internal" if briefing_type == "internal" else "briefing_customer"
    template = "briefing_internal.html" if briefing_type == "internal" else "briefing_customer.html"

    return render_template(
        template,
        account=account,
        briefing=briefing,
        generated_date=generated_date,
        time_range_days=result["time_range_days"],
        active_nav=active,
    )


# --- Teams Webhook Integration ---

async def generate_briefing_sync(briefing_type: str, user_message: str) -> dict | None:
    """Run the briefing generator and collect the final result (non-streaming)."""
    try:
        from services.briefing_generator import generate_briefing_stream, _extract_briefing_json
        result_json = None
        async for sse_line in generate_briefing_stream(briefing_type, user_message):
            if "briefing_ready" in sse_line:
                data = json.loads(sse_line.replace("data: ", "").strip())
                return {
                    "result_id": data.get("result_id"),
                    "account_id": data.get("account_id"),
                }
        return None
    except Exception as e:
        logger.error(f"Sync briefing generation failed: {e}")
        return None


def format_adaptive_card(briefing: dict, account_name: str, briefing_type: str, result_url: str = "") -> dict:
    """Format a briefing as a Teams Adaptive Card."""
    card_body = []

    # Header
    card_body.append({
        "type": "TextBlock",
        "size": "Large",
        "weight": "Bolder",
        "text": f"{'Internal Health Brief' if briefing_type == 'internal' else 'Customer QBR'} — {account_name}",
    })

    # Executive snapshot / summary
    snapshot = briefing.get("executive_snapshot") or briefing.get("executive_summary", "")
    if snapshot:
        card_body.append({
            "type": "TextBlock",
            "text": snapshot,
            "wrap": True,
            "spacing": "Medium",
        })

    # Revenue picture
    rev = briefing.get("revenue_picture", {})
    if rev:
        pipeline = rev.get("total_pipeline_value", "N/A")
        at_risk = rev.get("revenue_at_risk", "N/A")
        card_body.append({
            "type": "ColumnSet",
            "spacing": "Medium",
            "columns": [
                {"type": "Column", "width": "stretch", "items": [
                    {"type": "TextBlock", "text": "PIPELINE", "size": "Small", "color": "Accent", "weight": "Bolder"},
                    {"type": "TextBlock", "text": str(pipeline), "size": "ExtraLarge", "weight": "Bolder"},
                ]},
                {"type": "Column", "width": "stretch", "items": [
                    {"type": "TextBlock", "text": "AT RISK", "size": "Small", "color": "Attention", "weight": "Bolder"},
                    {"type": "TextBlock", "text": str(at_risk) if at_risk else "None", "size": "ExtraLarge", "weight": "Bolder", "color": "Attention"},
                ]},
            ]
        })

        # Active pipeline deals
        for opp in rev.get("active_pipeline", [])[:5]:
            card_body.append({
                "type": "TextBlock",
                "text": f"**{opp.get('name', 'Deal')}** — {opp.get('amount', 'N/A')} ({opp.get('stage', '')})",
                "wrap": True,
                "spacing": "Small",
            })

    # Support tickets summary
    engagement = briefing.get("engagement_activity", {})
    tickets = engagement.get("support_tickets", {})
    if tickets:
        open_count = tickets.get("open_count", 0)
        closed_count = tickets.get("closed_count", 0)
        trend = tickets.get("trend", "unknown")
        card_body.append({
            "type": "TextBlock",
            "text": f"**Support:** {open_count} open / {closed_count} closed — Trend: {trend}",
            "wrap": True,
            "spacing": "Medium",
        })

    # Strategic risks
    risks = briefing.get("strategic_risks", [])
    if risks:
        card_body.append({
            "type": "TextBlock",
            "text": "RISKS & RED FLAGS",
            "size": "Small",
            "weight": "Bolder",
            "color": "Attention",
            "spacing": "Medium",
        })
        for risk in risks[:3]:
            severity = risk.get("severity", "info").upper()
            card_body.append({
                "type": "TextBlock",
                "text": f"[{severity}] **{risk.get('title', '')}** — {risk.get('description', '')}",
                "wrap": True,
                "spacing": "Small",
            })

    # Recommended actions
    actions = briefing.get("recommended_actions", [])
    if actions:
        card_body.append({
            "type": "TextBlock",
            "text": "RECOMMENDED ACTIONS",
            "size": "Small",
            "weight": "Bolder",
            "spacing": "Medium",
        })
        for i, action in enumerate(actions[:5], 1):
            priority = f"[{action.get('priority', 'normal').upper()}] " if action.get('priority') in ('urgent', 'high') else ""
            card_body.append({
                "type": "TextBlock",
                "text": f"{i}. {priority}**{action.get('action', '')}**",
                "wrap": True,
                "spacing": "Small",
            })

    # Health scorecard as compact line
    scorecard = briefing.get("health_scorecard", [])
    if scorecard:
        scores = " | ".join([f"{s.get('label', '')}: {s.get('score', '?')}/5" for s in scorecard])
        card_body.append({
            "type": "TextBlock",
            "text": f"**Scorecard:** {scores}",
            "wrap": True,
            "spacing": "Medium",
            "size": "Small",
        })

    card = {
        "type": "message",
        "attachments": [{
            "contentType": "application/vnd.microsoft.card.adaptive",
            "content": {
                "$schema": "http://adaptivecards.io/schemas/adaptive-card.json",
                "type": "AdaptiveCard",
                "version": "1.4",
                "body": card_body,
            }
        }]
    }

    # Add "View Full Report" button if URL provided
    if result_url:
        card["attachments"][0]["content"]["actions"] = [{
            "type": "Action.OpenUrl",
            "title": "View Full Report",
            "url": result_url,
        }]

    return card


async def process_teams_briefing(
    account_name: str, briefing_type: str, webhook_url: str, base_url: str
):
    """Background task: generate briefing and post result back to Teams."""
    import httpx

    result = await generate_briefing_sync(briefing_type, account_name)
    if not result:
        async with httpx.AsyncClient() as client:
            await client.post(webhook_url, json={
                "type": "message",
                "text": f"Failed to generate {briefing_type} briefing for {account_name}. Please try again.",
            })
        return

    # Fetch the saved briefing
    briefing_data = get_briefing_result(result["result_id"])
    if not briefing_data or not briefing_data.get("result"):
        async with httpx.AsyncClient() as client:
            await client.post(webhook_url, json={
                "type": "message",
                "text": f"Briefing generated but could not be retrieved. ID: {result['result_id']}",
            })
        return

    result_url = f"{base_url}/qbr/briefings/{result['account_id']}/{briefing_type}?result_id={result['result_id']}"
    card = format_adaptive_card(briefing_data["result"], account_name, briefing_type, result_url)

    async with httpx.AsyncClient() as client:
        resp = await client.post(webhook_url, json=card)
        logger.info(f"Teams webhook callback: {resp.status_code}")


@app.post("/api/webhook/teams")
async def teams_webhook(request: Request, background_tasks: BackgroundTasks):
    """
    Teams Outgoing Webhook handler.

    Expects messages like:
      @QBR zoom internal
      @QBR spacex customer 30 days
      @QBR nvidia

    Responds immediately with "Working on it..." then posts the briefing
    back to the channel via the replyToId webhook URL.
    """
    body = await request.json()
    text = body.get("text", "").strip()
    # Teams prepends the bot mention as HTML — strip it
    import re
    text = re.sub(r'<at>.*?</at>\s*', '', text).strip()

    if not text:
        return JSONResponse({"type": "message", "text": "Usage: @QBR <account name> [internal|customer] [N days]"})

    # Parse: account name, optional type, optional days
    parts = text.split()
    briefing_type = "internal"
    account_parts = []

    for part in parts:
        lower = part.lower()
        if lower in ("internal", "customer"):
            briefing_type = lower
        elif re.match(r'^\d+$', part):
            pass  # days number, handled by LLM
        elif lower == "days":
            pass
        else:
            account_parts.append(part)

    account_name = " ".join(account_parts) if account_parts else text

    # Get the webhook URL for posting back
    service_url = body.get("serviceUrl", "")
    conversation_id = body.get("conversation", {}).get("id", "")
    activity_id = body.get("id", "")
    webhook_url = os.environ.get("TEAMS_WEBHOOK_URL", "")
    base_url = os.environ.get("APP_BASE_URL", "http://localhost:8000")

    if webhook_url:
        background_tasks.add_task(
            process_teams_briefing, account_name, briefing_type, webhook_url, base_url
        )

    return JSONResponse({
        "type": "message",
        "text": f"Generating {briefing_type} briefing for **{account_name}**... I'll post the results here when ready.",
    })


@app.post("/api/webhook/generic")
async def generic_webhook(request: Request, background_tasks: BackgroundTasks):
    """
    Generic webhook for any integration (Slack, custom tools, etc).

    POST JSON:
    {
        "account_name": "Zoom",
        "briefing_type": "internal",
        "callback_url": "https://your-webhook-url",
        "base_url": "https://your-app-url"
    }

    Responds immediately with 202, then POSTs the Adaptive Card to callback_url.
    """
    body = await request.json()
    account_name = body.get("account_name", "").strip()
    briefing_type = body.get("briefing_type", "internal")
    callback_url = body.get("callback_url", "")
    base_url = body.get("base_url", os.environ.get("APP_BASE_URL", "http://localhost:8000"))

    if not account_name:
        return JSONResponse({"error": "account_name is required"}, status_code=400)
    if briefing_type not in ("internal", "customer"):
        return JSONResponse({"error": "briefing_type must be 'internal' or 'customer'"}, status_code=400)
    if not callback_url:
        return JSONResponse({"error": "callback_url is required"}, status_code=400)

    background_tasks.add_task(
        process_teams_briefing, account_name, briefing_type, callback_url, base_url
    )

    return JSONResponse(
        {"status": "accepted", "message": f"Generating {briefing_type} briefing for {account_name}"},
        status_code=202,
    )


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
