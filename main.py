
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
            next_qbr_date TEXT DEFAULT '',
            qbr_q1 INTEGER DEFAULT 0,
            qbr_q2 INTEGER DEFAULT 0,
            qbr_q3 INTEGER DEFAULT 0,
            qbr_q4 INTEGER DEFAULT 0,
            key_learnings TEXT DEFAULT '',
            next_steps TEXT DEFAULT '',
            latest_update TEXT DEFAULT '',
            action_items TEXT DEFAULT '[]',
            contacts TEXT DEFAULT '[]'
        )
    ''')
    conn.commit()

    # Migration for existing databases
    try:
        cursor.execute("ALTER TABLE accounts ADD COLUMN next_steps TEXT DEFAULT ''")
        conn.commit()
    except:
        pass
    try:
        cursor.execute("ALTER TABLE accounts ADD COLUMN latest_update TEXT DEFAULT ''")
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

def row_to_account(row):
    return {
        "id": row["id"],
        "name": row["name"],
        "tier": row["tier"],
        "owner": row["owner"],
        "healthSentiment": row["health_sentiment"],
        "nextQbrDate": row["next_qbr_date"],
        "qbrCompletion": {
            "q1": bool(row["qbr_q1"]),
            "q2": bool(row["qbr_q2"]),
            "q3": bool(row["qbr_q3"]),
            "q4": bool(row["qbr_q4"])
        },
        "keyLearnings": row["key_learnings"] or "",
        "nextSteps": row["next_steps"] if "next_steps" in row.keys() else "",
        "latestUpdate": row["latest_update"] if "latest_update" in row.keys() else "",
        "actionItems": json.loads(row["action_items"]),
        "contacts": json.loads(row["contacts"])
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
    cursor.execute('''
        INSERT OR REPLACE INTO accounts (id, name, tier, owner, health_sentiment, next_qbr_date, qbr_q1, qbr_q2, qbr_q3, qbr_q4, key_learnings, next_steps, latest_update, action_items, contacts)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', (
        account_data["id"],
        account_data["name"],
        account_data["tier"],
        account_data["owner"],
        account_data["healthSentiment"],
        account_data["nextQbrDate"],
        1 if account_data["qbrCompletion"]["q1"] else 0,
        1 if account_data["qbrCompletion"]["q2"] else 0,
        1 if account_data["qbrCompletion"]["q3"] else 0,
        1 if account_data["qbrCompletion"]["q4"] else 0,
        account_data["keyLearnings"],
        account_data.get("nextSteps", ""),
        account_data.get("latestUpdate", ""),
        json.dumps(account_data["actionItems"]),
        json.dumps(account_data["contacts"])
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
async def save_account_endpoint(
    id: Optional[str] = Form(None),
    name: str = Form(...),
    tier: str = Form(...),
    owner: str = Form(""),
    health_sentiment: Optional[str] = Form("green"),
    next_qbr_date: Optional[str] = Form(""),
    key_learnings: Optional[str] = Form(""),
    next_steps: Optional[str] = Form(""),
    latest_update: Optional[str] = Form(""),
    contacts_json: Optional[str] = Form("[]"),
    action_items_json: Optional[str] = Form("[]"),
    q1: Optional[str] = Form(None),
    q2: Optional[str] = Form(None),
    q3: Optional[str] = Form(None),
    q4: Optional[str] = Form(None)
):
    qbr = {
        "q1": q1 == "on",
        "q2": q2 == "on",
        "q3": q3 == "on",
        "q4": q4 == "on"
    }

    try:
        contacts = json.loads(contacts_json) if contacts_json else []
        contacts = [c for c in contacts if c.get('name') or c.get('email')]
    except:
        contacts = []

    try:
        action_items = json.loads(action_items_json) if action_items_json else []
        action_items = [item for item in action_items if item.strip()]
    except:
        action_items = []

    account_id = id if id else str(uuid.uuid4())
    account_data = {
        "id": account_id,
        "name": name,
        "tier": tier,
        "owner": owner,
        "healthSentiment": health_sentiment or "green",
        "nextQbrDate": next_qbr_date or "",
        "keyLearnings": key_learnings or "",
        "nextSteps": next_steps or "",
        "latestUpdate": latest_update or "",
        "contacts": contacts,
        "actionItems": action_items,
        "qbrCompletion": qbr
    }
    save_account(account_data)

    if id:
        return RedirectResponse(url=f"/qbr/account/{id}", status_code=303)
    else:
        return RedirectResponse(url="/qbr/", status_code=303)

@app.post("/delete/{account_id}")
async def delete_account(account_id: str):
    delete_account_by_id(account_id)
    return RedirectResponse(url="/qbr/", status_code=303)


# --- Routes: Briefing Generator ---

@app.get("/briefings", response_class=HTMLResponse)
async def briefings_page(type: Optional[str] = None):
    return render_template(
        "briefings.html",
        preselected_type=type or "",
        active_nav="briefings",
    )


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

    from services.briefing_generator import generate_briefing_stream

    async def event_stream():
        async for event in generate_briefing_stream(briefing_type, user_message):
            yield event
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
