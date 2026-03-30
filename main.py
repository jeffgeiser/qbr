
from fastapi import FastAPI, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse, StreamingResponse
from jinja2 import Environment, FileSystemLoader, select_autoescape
from typing import List, Optional, Dict
from contextlib import asynccontextmanager
import json
import uuid
import sqlite3
import os
import logging

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


@app.get("/api/briefings/search-account")
async def search_account(q: str = ""):
    """Search Salesforce for accounts matching the query string."""
    q = q.strip()
    if not q:
        return JSONResponse({"accounts": []})

    try:
        from services.salesforce_mcp import salesforce_client
        if not salesforce_client.is_connected:
            return JSONResponse({"accounts": [], "error": "Salesforce not connected"})

        raw = await salesforce_client._query(
            "Account", ["Name"],
            where=f"Name LIKE '%{q}%'",
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


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
