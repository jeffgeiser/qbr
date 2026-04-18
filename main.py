
from fastapi import FastAPI, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse, StreamingResponse
from jinja2 import Environment, FileSystemLoader, select_autoescape
from typing import List, Optional, Dict
from contextlib import asynccontextmanager
from datetime import datetime
import json
import uuid
import sqlite3
import os
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

from core.models import (
    AgentContext, InsightCard, Priority, InsightStatus, PRIORITY_RANK,
)
from core.agent_runtime import registry, AgentInstance, AgentBlueprint
from auth import get_current_user, set_user_cookie, clear_user_cookie, require_login

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
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=5000")
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

    # --- Agent platform tables ---
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS agent_instances (
            id TEXT PRIMARY KEY,
            user_id TEXT DEFAULT 'default',
            blueprint_id TEXT NOT NULL,
            name TEXT NOT NULL,
            config TEXT DEFAULT '{}',
            scope TEXT DEFAULT '{}',
            schedule TEXT DEFAULT 'manual',
            status TEXT DEFAULT 'active',
            last_run_at TEXT DEFAULT '',
            next_run_at TEXT DEFAULT '',
            created_at TEXT NOT NULL
        )
    ''')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS insights (
            id TEXT PRIMARY KEY,
            agent_instance_id TEXT DEFAULT '',
            agent_blueprint_id TEXT DEFAULT '',
            account_id TEXT DEFAULT '',
            account_name TEXT DEFAULT '',
            priority TEXT DEFAULT 'info',
            title TEXT DEFAULT '',
            summary TEXT DEFAULT '',
            detail_json TEXT DEFAULT '{}',
            sources_json TEXT DEFAULT '[]',
            actions_json TEXT DEFAULT '[]',
            status TEXT DEFAULT 'unread',
            created_at TEXT NOT NULL,
            expires_at TEXT DEFAULT ''
        )
    ''')
    conn.commit()

    # Account table migrations for agent platform
    agent_migrations = [
        "ALTER TABLE accounts ADD COLUMN must_win INTEGER DEFAULT 0",
        "ALTER TABLE accounts ADD COLUMN priority_boost INTEGER DEFAULT 0",
        "ALTER TABLE accounts ADD COLUMN salesforce_ids TEXT DEFAULT '[]'",
    ]
    for m in agent_migrations:
        try:
            cursor.execute(m)
            conn.commit()
        except Exception:
            pass

    # --- Users table ---
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            email TEXT DEFAULT '',
            role TEXT DEFAULT 'rep',
            team TEXT DEFAULT '',
            color TEXT DEFAULT '#6366f1',
            created_at TEXT NOT NULL
        )
    ''')

    # Per-user account preferences (must_win, priority_boost are per-user)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS user_account_prefs (
            user_id TEXT NOT NULL,
            account_id TEXT NOT NULL,
            must_win INTEGER DEFAULT 0,
            priority_boost INTEGER DEFAULT 0,
            PRIMARY KEY (user_id, account_id)
        )
    ''')

    # Add user_id columns to tables that need per-user scoping
    user_scope_migrations = [
        "ALTER TABLE insights ADD COLUMN user_id TEXT DEFAULT 'default'",
        "ALTER TABLE briefing_results ADD COLUMN user_id TEXT DEFAULT 'default'",
        "ALTER TABLE insights ADD COLUMN logic_explanation TEXT DEFAULT ''",
    ]
    for m in user_scope_migrations:
        try:
            cursor.execute(m)
            conn.commit()
        except Exception:
            pass

    conn.commit()

    # Seed team members if users table is empty
    cursor.execute("SELECT COUNT(*) FROM users")
    if cursor.fetchone()[0] == 0:
        team_members = [
            ("u1", "Jeff Geiser", "jeff.geiser@zenlayer.com", "manager", "SE", "#6366f1"),
            ("u2", "Carlos Morell", "carlos.morell@zenlayer.com", "rep", "Sales", "#0ea5e9"),
            ("u3", "Wade Chen", "wade.chen@zenlayer.com", "rep", "Sales", "#10b981"),
            ("u4", "Josh Lipold", "josh.lipold@zenlayer.com", "rep", "Sales", "#f59e0b"),
            ("u5", "Eric Rodriguez", "eric.rodriguez@zenlayer.com", "rep", "Sales", "#ef4444"),
            ("u6", "Sean Washak", "sean.washak@zenlayer.com", "rep", "Sales", "#8b5cf6"),
            ("u7", "Rebecca Yang", "rebecca.yang@zenlayer.com", "rep", "Sales", "#ec4899"),
        ]
        now = datetime.utcnow().isoformat()
        cursor.executemany(
            "INSERT INTO users (id, name, email, role, team, color, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
            [(uid, n, e, r, t, c, now) for uid, n, e, r, t, c in team_members],
        )
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
        "salesforceIds": _safe_json(_safe_col(row, "salesforce_ids", "[]"), []),
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
            key_learnings, next_steps, latest_update, action_items, salesforce_ids, contacts)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
        json.dumps(account_data.get("salesforceIds", [])),
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


# --- Agent Instance DB Helpers ---

def get_all_agent_instances(user_id: str = "default") -> list[dict]:
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM agent_instances WHERE user_id = ? ORDER BY created_at DESC", (user_id,))
    rows = cursor.fetchall()
    conn.close()
    return [_row_to_instance(r) for r in rows]


def get_agent_instance(instance_id: str) -> dict | None:
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM agent_instances WHERE id = ?", (instance_id,))
    row = cursor.fetchone()
    conn.close()
    return _row_to_instance(row) if row else None


def save_agent_instance(inst: dict):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('''
        INSERT OR REPLACE INTO agent_instances (id, user_id, blueprint_id, name, config, scope, schedule, status, last_run_at, next_run_at, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', (
        inst["id"], inst.get("user_id", "default"), inst["blueprint_id"], inst["name"],
        json.dumps(inst.get("config", {})), json.dumps(inst.get("scope", {})),
        inst.get("schedule", "manual"), inst.get("status", "active"),
        inst.get("last_run_at", ""), inst.get("next_run_at", ""),
        inst.get("created_at", datetime.utcnow().isoformat()),
    ))
    conn.commit()
    conn.close()


def delete_agent_instance(instance_id: str):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM agent_instances WHERE id = ?", (instance_id,))
    conn.commit()
    conn.close()


def _row_to_instance(row) -> dict:
    return {
        "id": row["id"],
        "user_id": row["user_id"],
        "blueprint_id": row["blueprint_id"],
        "name": row["name"],
        "config": _safe_json(row["config"], {}),
        "scope": _safe_json(row["scope"], {}),
        "schedule": row["schedule"],
        "status": row["status"],
        "last_run_at": row["last_run_at"],
        "next_run_at": row["next_run_at"],
        "created_at": row["created_at"],
    }


# --- Insights DB Helpers ---

def save_insight(card: InsightCard, user_id: str = "default"):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('''
        INSERT OR REPLACE INTO insights (id, agent_instance_id, agent_blueprint_id, account_id, account_name,
            priority, title, summary, detail_json, sources_json, actions_json, logic_explanation, status, created_at, expires_at, user_id)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', (
        card.id, card.agent_instance_id, card.agent_blueprint_id,
        card.account_id, card.account_name,
        card.priority.value if isinstance(card.priority, Priority) else card.priority,
        card.title, card.summary,
        json.dumps(card.detail), json.dumps([s.to_dict() for s in card.sources]),
        json.dumps(card.actions), card.logic_explanation,
        card.status.value if isinstance(card.status, InsightStatus) else card.status,
        card.created_at, card.expires_at, user_id,
    ))
    conn.commit()
    conn.close()


def get_insights(user_id: str = "default", limit: int = 50, status_filter: str = "") -> list[dict]:
    conn = get_db()
    cursor = conn.cursor()
    if status_filter:
        cursor.execute(
            "SELECT * FROM insights WHERE user_id = ? AND status = ? ORDER BY created_at DESC LIMIT ?",
            (user_id, status_filter, limit))
    else:
        cursor.execute(
            "SELECT * FROM insights WHERE user_id = ? AND status != 'dismissed' ORDER BY created_at DESC LIMIT ?",
            (user_id, limit))
    rows = cursor.fetchall()
    conn.close()
    return [_row_to_insight(r) for r in rows]


def update_insight_status(insight_id: str, status: str):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("UPDATE insights SET status = ? WHERE id = ?", (status, insight_id))
    conn.commit()
    conn.close()


def _row_to_insight(row) -> dict:
    return {
        "id": row["id"],
        "agent_instance_id": row["agent_instance_id"],
        "agent_blueprint_id": row["agent_blueprint_id"],
        "account_id": row["account_id"],
        "account_name": row["account_name"],
        "priority": row["priority"],
        "title": row["title"],
        "summary": row["summary"],
        "detail": _safe_json(row["detail_json"], {}),
        "sources": _safe_json(row["sources_json"], []),
        "actions": _safe_json(row["actions_json"], []),
        "logic_explanation": _safe_col(row, "logic_explanation", ""),
        "status": row["status"],
        "created_at": row["created_at"],
        "expires_at": row["expires_at"],
    }


def get_salesforce_ids_for_account(account_name: str) -> list[str]:
    """Look up mapped Salesforce Account IDs for a tracker account."""
    conn = get_db()
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT salesforce_ids FROM accounts WHERE name = ?", (account_name,))
        row = cursor.fetchone()
        if row:
            ids = _safe_json(_safe_col(row, "salesforce_ids", "[]"), [])
            return [i for i in ids if i]
    except Exception:
        pass
    finally:
        conn.close()
    return []


def get_must_win_accounts(user_id: str = "default") -> list[str]:
    conn = get_db()
    cursor = conn.cursor()
    try:
        cursor.execute("""
            SELECT a.name FROM accounts a
            JOIN user_account_prefs p ON a.id = p.account_id
            WHERE p.user_id = ? AND p.must_win = 1
        """, (user_id,))
        names = [r["name"] for r in cursor.fetchall()]
    except Exception:
        names = []
    conn.close()
    return names


# --- User DB Helpers ---

def get_all_users() -> list[dict]:
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM users ORDER BY name")
    rows = cursor.fetchall()
    conn.close()
    return [_row_to_user(r) for r in rows]


def get_user_by_id(user_id: str) -> dict | None:
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM users WHERE id = ?", (user_id,))
    row = cursor.fetchone()
    conn.close()
    return _row_to_user(row) if row else None


def _row_to_user(row) -> dict:
    name = row["name"]
    parts = name.split()
    initials = (parts[0][0] + parts[-1][0]).upper() if len(parts) >= 2 else name[:2].upper()
    role_labels = {"rep": "Sales Rep", "se": "Solutions Engineer", "manager": "Manager"}
    return {
        "id": row["id"],
        "name": name,
        "email": row["email"],
        "role": row["role"],
        "team": row["team"],
        "color": row["color"],
        "initials": initials,
        "role_label": role_labels.get(row["role"], row["role"]),
    }


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

def _register_agents_and_connectors():
    """Register all agent blueprints and integration connectors."""
    from agents.account_pulse import AccountPulseAgent
    from agents.qbr_composer import QBRComposerAgent
    from agents.meeting_prep import MeetingPrepAgent
    from agents.deal_strategist import DealStrategistAgent
    from agents.customer_voice import CustomerVoiceAgent
    from agents.news_monitor import NewsMonitorAgent
    from agents.account_digest import AccountDigestAgent
    from agents.executive_pulse import ExecutivePulseAgent
    registry.register(AccountPulseAgent)
    registry.register(QBRComposerAgent)
    registry.register(MeetingPrepAgent)
    registry.register(DealStrategistAgent)
    registry.register(CustomerVoiceAgent)
    registry.register(NewsMonitorAgent)
    registry.register(AccountDigestAgent)
    registry.register(ExecutivePulseAgent)

    from integrations.hub import hub
    from integrations.salesforce import SalesforceMCPConnector
    hub.register(SalesforceMCPConnector())
    logger.info("Agents and connectors registered.")


@asynccontextmanager
async def lifespan(app):
    # Startup
    init_db()
    _register_agents_and_connectors()
    await try_connect_salesforce()
    try:
        from services.scheduler import start_scheduler
        await start_scheduler()
    except Exception as e:
        logger.warning(f"Scheduler not started: {e}")
    yield
    # Shutdown
    try:
        from services.scheduler import stop_scheduler
        await stop_scheduler()
    except Exception:
        pass
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


# --- Routes: Login / Logout ---

@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    user = get_current_user(request)
    if user:
        return RedirectResponse(url="/qbr/workbench", status_code=303)
    users = get_all_users()
    return render_template("login.html", users=users, active_nav="")


@app.post("/login")
async def login_submit(request: Request, user_id: str = Form(...)):
    user = get_user_by_id(user_id)
    if not user:
        return RedirectResponse(url="/qbr/login", status_code=303)
    response = RedirectResponse(url="/qbr/workbench", status_code=303)
    set_user_cookie(response, user)
    return response


@app.get("/logout")
async def logout(request: Request):
    response = RedirectResponse(url="/qbr/login", status_code=303)
    clear_user_cookie(response)
    return response


# --- Routes: Portfolio Dashboard ---

@app.get("/", response_class=HTMLResponse)
@app.get("", response_class=HTMLResponse)
@app.get("/tracker", response_class=HTMLResponse)
async def dashboard(request: Request):
    redirect = require_login(request)
    if redirect:
        return redirect
    user = get_current_user(request)
    accounts = get_all_accounts()
    accounts_json = json.dumps(accounts)
    return render_template(
        "dashboard.html",
        accounts_json=accounts_json,
        active_nav="portfolio",
        current_user=user,
    )


# --- Routes: Account Details ---

@app.get("/account/{account_id}", response_class=HTMLResponse)
async def account_details(request: Request, account_id: str):
    redirect = require_login(request)
    if redirect:
        return redirect
    user = get_current_user(request)
    account = get_account_by_id(account_id)
    if not account:
        return RedirectResponse(url="/qbr/", status_code=303)
    account_json = json.dumps(account)
    return render_template(
        "account_detail.html",
        account=account,
        account_json=account_json,
        active_nav="portfolio",
        current_user=user,
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


@app.get("/workbench", response_class=HTMLResponse)
async def workbench_page(request: Request):
    redirect = require_login(request)
    if redirect:
        return redirect
    user = get_current_user(request)
    return render_template("workbench.html", active_nav="workbench", current_user=user)


@app.get("/briefings", response_class=HTMLResponse)
async def briefings_page(request: Request, type: Optional[str] = None):
    redirect = require_login(request)
    if redirect:
        return redirect
    user = get_current_user(request)
    return render_template("workbench.html", active_nav="workbench", current_user=user)


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
async def briefing_result_page(request: Request, account_id: str, briefing_type: str, result_id: Optional[str] = None):
    """Display a generated briefing result."""
    redirect = require_login(request)
    if redirect:
        return redirect
    user = get_current_user(request)

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
        current_user=user,
    )


# =============================================================================
# Agent Platform API Routes (all scoped by current user)
# =============================================================================

def _api_user(request: Request) -> dict | None:
    """Extract user from request for API routes. Returns None if not logged in."""
    return get_current_user(request)


@app.get("/api/agents/blueprints")
async def list_blueprints():
    return JSONResponse([bp.to_dict() for bp in registry.get_all_blueprints()])


@app.get("/api/agents/instances")
async def list_instances(request: Request):
    user = _api_user(request)
    uid = user["id"] if user else "default"
    return JSONResponse(get_all_agent_instances(user_id=uid))


@app.post("/api/agents/activate")
async def activate_agent(request: Request):
    user = _api_user(request)
    uid = user["id"] if user else "default"
    body = await request.json()
    blueprint_id = body.get("blueprint_id", "")
    bp = registry.get_blueprint(blueprint_id)
    if not bp:
        return JSONResponse({"error": f"Unknown blueprint: {blueprint_id}"}, status_code=404)

    existing = get_all_agent_instances(user_id=uid)
    for inst in existing:
        if inst["blueprint_id"] == blueprint_id:
            return JSONResponse({"error": "Already activated", "instance": inst}, status_code=409)

    instance = {
        "id": str(uuid.uuid4()),
        "user_id": uid,
        "blueprint_id": blueprint_id,
        "name": bp.name,
        "config": bp.default_config,
        "scope": body.get("scope", {}),
        "schedule": body.get("schedule", "manual"),
        "status": "active",
        "last_run_at": "",
        "next_run_at": "",
        "created_at": datetime.utcnow().isoformat(),
    }
    save_agent_instance(instance)
    return JSONResponse(instance)


@app.post("/api/agents/{instance_id}/run")
async def run_agent_instance(request: Request, instance_id: str):
    user = _api_user(request)
    uid = user["id"] if user else "default"
    inst = get_agent_instance(instance_id)
    if not inst or inst["user_id"] != uid:
        return JSONResponse({"error": "Instance not found"}, status_code=404)

    agent = registry.create_agent(inst["blueprint_id"])
    if not agent:
        return JSONResponse({"error": "Agent implementation not found"}, status_code=500)

    accounts = get_all_accounts()
    scope = inst.get("scope", {})
    scope_ids = scope.get("account_ids", [])
    scope_tiers = scope.get("tiers", [])

    if scope_ids:
        target_accounts = [a for a in accounts if a["id"] in scope_ids]
    elif scope_tiers:
        target_accounts = [a for a in accounts if a["tier"] in scope_tiers]
    else:
        target_accounts = accounts

    must_win = get_must_win_accounts(user_id=uid)
    context = AgentContext(
        account_ids=[a["id"] for a in target_accounts],
        account_names=[a["name"] for a in target_accounts],
        config=inst.get("config", {}),
        time_range_days=inst.get("config", {}).get("days", 90),
        must_win_accounts=must_win,
        instance_id=instance_id,
    )

    inst["status"] = "running"
    save_agent_instance(inst)

    try:
        result = await agent.run(context)
        for card in result.insights:
            card.agent_instance_id = instance_id
            save_insight(card, user_id=uid)

        inst["status"] = "active"
        inst["last_run_at"] = datetime.utcnow().isoformat()
        save_agent_instance(inst)

        return JSONResponse({
            "success": result.success,
            "insight_count": len(result.insights),
            "errors": result.errors,
        })
    except Exception as e:
        inst["status"] = "error"
        save_agent_instance(inst)
        logger.error(f"Agent run failed: {e}", exc_info=True)
        return JSONResponse({"error": str(e)}, status_code=500)


@app.post("/api/agents/{instance_id}/toggle")
async def toggle_agent_instance(request: Request, instance_id: str):
    user = _api_user(request)
    uid = user["id"] if user else "default"
    inst = get_agent_instance(instance_id)
    if not inst or inst["user_id"] != uid:
        return JSONResponse({"error": "Instance not found"}, status_code=404)

    new_status = "paused" if inst["status"] == "active" else "active"
    inst["status"] = new_status
    save_agent_instance(inst)
    return JSONResponse({"status": new_status})


@app.patch("/api/agents/{instance_id}/config")
async def update_agent_config(request: Request, instance_id: str):
    user = _api_user(request)
    uid = user["id"] if user else "default"
    inst = get_agent_instance(instance_id)
    if not inst or inst["user_id"] != uid:
        return JSONResponse({"error": "Instance not found"}, status_code=404)

    body = await request.json()
    if "config" in body:
        inst["config"] = {**inst.get("config", {}), **body["config"]}
    if "schedule" in body:
        inst["schedule"] = body["schedule"]
    save_agent_instance(inst)
    return JSONResponse({"updated": True, "config": inst["config"], "schedule": inst["schedule"]})


@app.delete("/api/agents/{instance_id}")
async def deactivate_agent(request: Request, instance_id: str):
    user = _api_user(request)
    uid = user["id"] if user else "default"
    inst = get_agent_instance(instance_id)
    if not inst or inst["user_id"] != uid:
        return JSONResponse({"error": "Instance not found"}, status_code=404)
    delete_agent_instance(instance_id)
    try:
        from services.scheduler import unschedule_agent_instance
        unschedule_agent_instance(instance_id)
    except Exception:
        pass
    return JSONResponse({"deleted": True})


# --- Intelligence Feed API (per-user) ---

@app.get("/api/feed")
async def get_feed(request: Request):
    user = _api_user(request)
    uid = user["id"] if user else "default"
    raw = get_insights(user_id=uid, limit=100)
    priority_order = {"critical": 0, "high": 1, "medium": 2, "low": 3, "info": 4}
    raw.sort(key=lambda i: (priority_order.get(i["priority"], 4), i["created_at"]))
    return JSONResponse(raw)


@app.post("/api/feed/{insight_id}/dismiss")
async def dismiss_insight(insight_id: str):
    update_insight_status(insight_id, "dismissed")
    return JSONResponse({"dismissed": True})


@app.post("/api/feed/{insight_id}/read")
async def mark_insight_read(insight_id: str):
    update_insight_status(insight_id, "read")
    return JSONResponse({"read": True})


# --- Command Bar API (per-user) ---

@app.post("/api/command")
async def command_endpoint(request: Request):
    """The universal command bar. Parses natural language, routes to the right agent, streams results."""
    user = _api_user(request)
    uid = user["id"] if user else "default"
    body = await request.json()
    user_message = body.get("message", "").strip()
    if not user_message:
        return JSONResponse({"error": "Empty message"}, status_code=400)

    from agents.command_router import parse_command

    async def command_stream():
        try:
            intent = await parse_command(user_message)
            yield _sse({"type": "status", "message": f"Routing to {intent.agent_id.replace('_', ' ').title()}..."})

            if intent.agent_id == "qbr_composer":
                briefing_type = intent.params.get("briefing_type", "internal")
                acct = intent.account_names[0] if intent.account_names else user_message
                user_msg = f"{acct} for the last {intent.params.get('days', 90)} days"

                from services.briefing_generator import generate_briefing_stream
                async for event in generate_briefing_stream(briefing_type, user_msg):
                    yield event
                    if "briefing_ready" in event:
                        try:
                            data = json.loads(event.split("data: ", 1)[1].strip())
                            data["briefing_type"] = briefing_type
                            yield _sse(data)
                        except Exception:
                            pass
            else:
                agent = registry.create_agent(intent.agent_id)
                if not agent:
                    yield _sse({"type": "error", "message": f"Agent '{intent.agent_id}' not available"})
                    return

                if not intent.account_names:
                    accounts = get_all_accounts()
                    intent.account_names = [a["name"] for a in accounts[:5]]

                must_win = get_must_win_accounts(user_id=uid)
                context = AgentContext(
                    account_names=intent.account_names,
                    config=intent.params,
                    time_range_days=intent.params.get("days", 90),
                    user_message=user_message,
                    must_win_accounts=must_win,
                )

                async for evt in agent.stream(context):
                    yield _sse(evt)
                    if evt.get("type") == "insight":
                        card_data = evt["data"]
                        card = InsightCard(
                            id=card_data.get("id", str(uuid.uuid4())),
                            agent_blueprint_id=card_data.get("agent_blueprint_id", intent.agent_id),
                            account_name=card_data.get("account_name", ""),
                            priority=Priority(card_data.get("priority", "info")),
                            title=card_data.get("title", ""),
                            summary=card_data.get("summary", ""),
                            detail=card_data.get("detail", {}),
                            actions=card_data.get("actions", []),
                            created_at=card_data.get("created_at", datetime.utcnow().isoformat()),
                        )
                        save_insight(card, user_id=uid)

                yield _sse({"type": "insights_ready"})

        except Exception as e:
            logger.error(f"Command error: {e}", exc_info=True)
            yield _sse({"type": "error", "message": f"Command failed: {str(e)}"})
        yield "data: [DONE]\n\n"

    return StreamingResponse(
        command_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive", "X-Accel-Buffering": "no"},
    )


# --- User Management API ---

@app.get("/api/users")
async def list_users():
    return JSONResponse(get_all_users())


@app.get("/api/users/me")
async def get_me(request: Request):
    user = _api_user(request)
    if not user:
        return JSONResponse({"error": "Not logged in"}, status_code=401)
    return JSONResponse(user)


def _sse(data: dict) -> str:
    return f"data: {json.dumps(data)}\n\n"


# --- Integration Status ---

@app.get("/api/integrations/status")
async def integrations_status():
    from integrations.hub import hub
    return JSONResponse(hub.get_all_statuses())


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
