
from fastapi import FastAPI, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from jinja2 import Template
from typing import List, Optional, Dict
import json
import uuid
import sqlite3
import os

app = FastAPI(root_path="/qbr")

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

    # Add new columns if they don't exist (migration for existing databases)
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

# Initialize database on startup
init_db()

# --- HTML Template for Main Dashboard ---
HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Zenlayer Account Engagement</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <script defer src="https://unpkg.com/@alpinejs/collapse@3.x.x/dist/cdn.min.js"></script>
    <script defer src="https://unpkg.com/alpinejs@3.x.x/dist/cdn.min.js"></script>
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap" rel="stylesheet">
    <style>
        [x-cloak] { display: none !important; }
        body { font-family: 'Inter', sans-serif; background-color: #fcfcfd; }
        .donut-logo {
            background: linear-gradient(to right, #33d4ff, #0076ff) border-box;
            -webkit-mask: linear-gradient(#fff 0 0) padding-box, linear-gradient(#fff 0 0);
            -webkit-mask-composite: destination-out;
            mask-composite: exclude;
        }
    </style>
</head>
<body x-data="dashboard()">
    <nav class="sticky top-0 z-30 bg-white/80 backdrop-blur-md border-b border-slate-100">
        <div class="max-w-7xl mx-auto px-6 h-20 flex items-center justify-between">
            <div class="flex items-center space-x-2.5">
                <div class="relative w-8 h-8 flex items-center justify-center">
                    <div class="absolute inset-0 rounded-full border-[5px] border-transparent donut-logo"></div>
                </div>
                <div class="flex flex-col">
                    <span class="text-[22px] font-medium text-[#2d3b45] tracking-tight leading-none">zenlayer</span>
                    <span class="text-[9px] font-bold text-slate-400 uppercase tracking-[0.2em] mt-0.5 leading-none">Engagement Plan</span>
                </div>
            </div>
            <div class="flex items-center space-x-4">
                <input type="text" x-model="search" placeholder="Search accounts..."
                       class="bg-slate-50 border-none rounded-full py-2 px-5 text-sm focus:ring-1 focus:ring-blue-400 w-64 transition-all">
                <button @click="openModal()" class="bg-slate-900 hover:bg-slate-800 text-white px-5 py-2 rounded-full text-[13px] font-semibold flex items-center space-x-2 transition-all shadow-sm">
                    <span>+ New Account</span>
                </button>
            </div>
        </div>
    </nav>

    <main class="max-w-7xl mx-auto px-6 py-8">
        <div class="mb-10">
            <h1 class="text-3xl font-bold text-slate-900 mb-1">Key Account Engagement</h1>
            <p class="text-slate-500 text-sm font-medium">Quarterly QBR tracking dashboard.</p>
        </div>

        

        <!-- Tier & Health Filters -->
        <div class="flex items-center space-x-6 mb-6">
            <!-- Tier Filters -->
            <div class="flex items-center space-x-2">
                <template x-for="t in ['All', 'Tier 1', 'Tier 2', 'Tier 3']">
                    <button @click="tierFilter = t"
                            :class="tierFilter === t ? 'bg-white shadow-sm text-slate-900 border-slate-200' : 'text-slate-500 border-transparent'"
                            class="px-4 py-1.5 rounded-lg text-xs font-semibold transition-all border"
                            x-text="t"></button>
                </template>
            </div>
            <!-- Health Sentiment Filters -->
            <div class="flex items-center space-x-2">
                <span class="text-[10px] font-bold text-slate-400 uppercase tracking-wider mr-1">Health:</span>
                <button @click="healthFilter = 'All'"
                        :class="healthFilter === 'All' ? 'bg-slate-200 text-slate-700' : 'text-slate-500'"
                        class="px-3 py-1 rounded-lg text-xs font-semibold transition-all hover:bg-slate-100">All</button>
                <button @click="healthFilter = 'green'"
                        :class="healthFilter === 'green' ? 'ring-2 ring-emerald-500 ring-offset-1' : ''"
                        class="w-4 h-4 rounded-full bg-emerald-500 transition-all hover:scale-110"
                        title="Healthy"></button>
                <button @click="healthFilter = 'yellow'"
                        :class="healthFilter === 'yellow' ? 'ring-2 ring-amber-400 ring-offset-1' : ''"
                        class="w-4 h-4 rounded-full bg-amber-400 transition-all hover:scale-110"
                        title="Concern"></button>
                <button @click="healthFilter = 'red'"
                        :class="healthFilter === 'red' ? 'ring-2 ring-rose-500 ring-offset-1' : ''"
                        class="w-4 h-4 rounded-full bg-rose-500 transition-all hover:scale-110"
                        title="At Risk"></button>
            </div>
        </div>

        <!-- Account Table -->
        <div class="bg-white rounded-2xl border border-slate-100 shadow-sm overflow-hidden">
            <table class="w-full text-left table-fixed">
                <thead>
                    <tr class="bg-slate-50/30">
                        <th class="w-10 border-b border-slate-100 text-[11px] font-bold text-slate-400 uppercase tracking-widest"></th>
                        <th @click="toggleSort('name')" class="w-56 py-4 text-[11px] font-bold text-slate-400 uppercase tracking-widest border-b border-slate-100 cursor-pointer hover:text-slate-600 select-none">
                            <div class="flex items-center space-x-1">
                                <span>Account</span>
                                <svg class="w-3 h-3 transition-transform" :class="{ 'rotate-180': sortBy === 'name' && sortDir === 'desc', 'text-slate-600': sortBy === 'name', 'text-slate-300': sortBy !== 'name' }" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 15l7-7 7 7"/>
                                </svg>
                            </div>
                        </th>
                        <th class="px-6 py-4 text-[11px] font-bold text-slate-400 uppercase tracking-widest border-b border-slate-100">Latest Update</th>
                        <th class="w-28 px-4 py-4 border-b border-slate-100">
                            <div class="text-[11px] font-bold text-slate-400 uppercase tracking-widest mb-1">QBR Tracking</div>
                            <div class="flex">
                                <span class="w-6 text-[9px] font-semibold text-slate-300 text-center">Q1</span>
                                <span class="w-6 text-[9px] font-semibold text-slate-300 text-center">Q2</span>
                                <span class="w-6 text-[9px] font-semibold text-slate-300 text-center">Q3</span>
                                <span class="w-6 text-[9px] font-semibold text-slate-300 text-center">Q4</span>
                            </div>
                        </th>
                        <th class="w-28 px-4 py-4 text-[11px] font-bold text-slate-400 uppercase tracking-widest border-b border-slate-100">Next QBR</th>
                        <th @click="toggleSort('tier')" class="w-20 px-3 py-4 text-[11px] font-bold text-slate-400 uppercase tracking-widest border-b border-slate-100 cursor-pointer hover:text-slate-600 select-none">
                            <div class="flex items-center space-x-1">
                                <span>Tier</span>
                                <svg class="w-3 h-3 transition-transform" :class="{ 'rotate-180': sortBy === 'tier' && sortDir === 'desc', 'text-slate-600': sortBy === 'tier', 'text-slate-300': sortBy !== 'tier' }" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 15l7-7 7 7"/>
                                </svg>
                            </div>
                        </th>
                        <th @click="toggleSort('owner')" class="w-28 px-3 py-4 text-[11px] font-bold text-slate-400 uppercase tracking-widest border-b border-slate-100 cursor-pointer hover:text-slate-600 select-none">
                            <div class="flex items-center space-x-1">
                                <span>Owner</span>
                                <svg class="w-3 h-3 transition-transform" :class="{ 'rotate-180': sortBy === 'owner' && sortDir === 'desc', 'text-slate-600': sortBy === 'owner', 'text-slate-300': sortBy !== 'owner' }" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 15l7-7 7 7"/>
                                </svg>
                            </div>
                        </th>
                    </tr>
                </thead>
                <tbody class="divide-y divide-slate-50">
                    <template x-for="account in filteredAccounts()" :key="account.id">
                        <tr>
                            <td colspan="7" class="p-0">
                                <!-- Main Row -->
                                <div @click="toggleExpand(account.id)" class="flex hover:bg-slate-50/50 transition-colors items-center cursor-pointer">
                                    <!-- Chevron Toggle -->
                                    <div class="w-10 flex items-center justify-center flex-shrink-0">
                                        <div class="p-1 rounded transition-colors"
                                             :class="expandedAccountId === account.id ? 'text-slate-700' : 'text-slate-400'">
                                            <svg class="w-4 h-4 transition-transform duration-200"
                                                 :class="expandedAccountId === account.id ? 'rotate-90' : ''"
                                                 fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 5l7 7-7 7"/>
                                            </svg>
                                        </div>
                                    </div>
                                    <!-- Account Name (fixed width, truncated) -->
                                    <div class="w-56 py-4 flex-shrink-0">
                                        <div class="flex items-center space-x-3">
                                            <div class="w-2.5 h-2.5 rounded-full flex-shrink-0"
                                                 :class="{
                                                     'bg-emerald-500': account.healthSentiment === 'green',
                                                     'bg-amber-400': account.healthSentiment === 'yellow',
                                                     'bg-rose-500': account.healthSentiment === 'red'
                                                 }"></div>
                                            <span class="font-semibold text-slate-900 text-sm truncate" x-text="truncate(account.name, 35)"></span>
                                        </div>
                                    </div>
                                    <!-- Latest Update (flexible width, max 50 chars) -->
                                    <div class="flex-1 px-6 py-4">
                                        <span class="text-sm" :class="account.latestUpdate ? 'text-slate-600' : 'text-slate-400'"
                                              x-text="truncate(account.latestUpdate, 50) || '-'"></span>
                                    </div>
                                    <!-- QBR Tracking -->
                                    <div class="w-28 px-4 py-4 flex-shrink-0">
                                        <div class="flex">
                                            <template x-for="q in ['q1', 'q2', 'q3', 'q4']">
                                                <div class="w-6 flex justify-center">
                                                    <div :class="account.qbrCompletion[q] ? 'bg-emerald-500' : 'bg-slate-200'"
                                                         class="w-2.5 h-2.5 rounded-full transition-all"></div>
                                                </div>
                                            </template>
                                        </div>
                                    </div>
                                    <!-- Next QBR -->
                                    <div class="w-28 px-4 py-4 flex-shrink-0">
                                        <span class="text-sm" :class="account.nextQbrDate ? 'text-slate-600' : 'text-slate-400'"
                                              x-text="account.nextQbrDate ? formatDate(account.nextQbrDate) : 'TBD'"></span>
                                    </div>
                                    <!-- Tier -->
                                    <div class="w-20 px-3 py-4 flex-shrink-0">
                                        <span x-text="account.tier" class="px-2 py-0.5 rounded-md text-[10px] font-bold border border-slate-200 text-slate-600 bg-slate-50"></span>
                                    </div>
                                    <!-- Owner -->
                                    <div class="w-28 px-3 py-4 flex-shrink-0 text-sm text-slate-600" x-text="account.owner"></div>
                                </div>
                                <!-- Expandable Details Row -->
                                <div x-show="expandedAccountId === account.id" x-collapse
                                     class="border-t border-slate-100 bg-slate-50/50">
                                    <div class="py-6 px-10">
                                        <!-- Header with Edit Button -->
                                        <div class="flex items-center justify-between mb-5">
                                            <h3 class="text-sm font-bold text-slate-700" x-text="account.name + ' Details'"></h3>
                                            <a :href="'/qbr/account/' + account.id + '?edit=true'"
                                               @click.stop
                                               class="inline-flex items-center space-x-1.5 px-3 py-1.5 bg-slate-900 hover:bg-slate-800 text-white text-xs font-semibold rounded-lg transition-colors">
                                                <svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M11 5H6a2 2 0 00-2 2v11a2 2 0 002 2h11a2 2 0 002-2v-5m-1.414-9.414a2 2 0 112.828 2.828L11.828 15H9v-2.828l8.586-8.586z"/>
                                                </svg>
                                                <span>Edit</span>
                                            </a>
                                        </div>
                                        <!-- Content Grid -->
                                        <div class="grid grid-cols-2 gap-6">
                                            <!-- Left Column -->
                                            <div class="space-y-5">
                                                <!-- Latest Update -->
                                                <div>
                                                    <label class="block text-[10px] font-black text-slate-400 uppercase tracking-widest mb-2">Latest Update</label>
                                                    <p x-show="account.latestUpdate" class="text-sm text-slate-700" x-text="account.latestUpdate"></p>
                                                    <p x-show="!account.latestUpdate" class="text-sm text-slate-400 italic">No update recorded.</p>
                                                </div>
                                                <!-- Key Learnings -->
                                                <div>
                                                    <label class="block text-[10px] font-black text-slate-400 uppercase tracking-widest mb-2">Key Learnings</label>
                                                    <template x-if="account.keyLearnings">
                                                        <ul class="space-y-1">
                                                            <template x-for="line in account.keyLearnings.split('\\n').filter(l => l.trim())">
                                                                <li class="flex items-start space-x-2 text-sm text-slate-600">
                                                                    <span class="text-slate-400 mt-0.5">•</span>
                                                                    <span x-text="line.replace(/^[-•*]\\s*/, '')"></span>
                                                                </li>
                                                            </template>
                                                        </ul>
                                                    </template>
                                                    <p x-show="!account.keyLearnings" class="text-sm text-slate-400 italic">No learnings recorded.</p>
                                                </div>
                                            </div>
                                            <!-- Right Column -->
                                            <div class="space-y-5">
                                                <!-- Next Steps -->
                                                <div>
                                                    <label class="block text-[10px] font-black text-slate-400 uppercase tracking-widest mb-2">Next Steps</label>
                                                    <template x-if="account.nextSteps">
                                                        <ul class="space-y-1">
                                                            <template x-for="line in account.nextSteps.split('\\n').filter(l => l.trim())">
                                                                <li class="flex items-start space-x-2 text-sm text-slate-600">
                                                                    <span class="text-slate-400 mt-0.5">•</span>
                                                                    <span x-text="line.replace(/^[-•*]\\s*/, '')"></span>
                                                                </li>
                                                            </template>
                                                        </ul>
                                                    </template>
                                                    <p x-show="!account.nextSteps" class="text-sm text-slate-400 italic">No next steps defined.</p>
                                                </div>
                                                <!-- Contacts -->
                                                <div>
                                                    <label class="block text-[10px] font-black text-slate-400 uppercase tracking-widest mb-2">Contacts</label>
                                                    <div x-show="account.contacts && account.contacts.length > 0" class="space-y-2">
                                                        <template x-for="(contact, idx) in account.contacts" :key="idx">
                                                            <div class="flex items-center space-x-2">
                                                                <div class="w-6 h-6 rounded-full bg-slate-200 flex items-center justify-center flex-shrink-0">
                                                                    <svg class="w-3 h-3 text-slate-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                                                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M16 7a4 4 0 11-8 0 4 4 0 018 0zM12 14a7 7 0 00-7 7h14a7 7 0 00-7-7z"/>
                                                                    </svg>
                                                                </div>
                                                                <div>
                                                                    <p class="text-sm font-medium text-slate-700" x-text="contact.name"></p>
                                                                    <a x-show="contact.email" :href="'mailto:' + contact.email" class="text-xs text-blue-600 hover:underline" x-text="contact.email" @click.stop></a>
                                                                </div>
                                                            </div>
                                                        </template>
                                                    </div>
                                                    <p x-show="!account.contacts || account.contacts.length === 0" class="text-sm text-slate-400 italic">No contacts added.</p>
                                                </div>
                                            </div>
                                        </div>
                                    </div>
                                </div>
                            </td>
                        </tr>
                    </template>
                </tbody>
            </table>
        </div>
    </main>

    <!-- New Account Modal -->
    <div x-show="showModal" class="fixed inset-0 bg-slate-900/40 backdrop-blur-sm z-50 flex items-center justify-center p-4" x-cloak>
        <div class="bg-white rounded-[2rem] w-full max-w-xl max-h-[90vh] overflow-hidden shadow-2xl flex flex-col" @click.away="showModal = false">
            <div class="p-6 border-b flex justify-between items-center bg-slate-50/50">
                <h2 class="text-lg font-bold text-slate-900">New Account</h2>
                <button @click="showModal = false" class="p-1 hover:bg-slate-100 rounded-full"><svg class="w-5 h-5 text-slate-400" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path d="M6 18L18 6M6 6l12 12" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/></svg></button>
            </div>
            <form action="/qbr/save" method="POST" class="overflow-y-auto p-8 space-y-6">
                <div>
                    <label class="block text-[10px] font-black text-slate-400 uppercase tracking-widest mb-2">Account Name</label>
                    <input name="name" x-model="newAccount.name" maxlength="35" class="w-full bg-slate-50 border-none rounded-xl px-4 py-3 text-sm focus:ring-1 focus:ring-blue-400" required>
                    <p class="text-xs text-slate-400 mt-1">Max 35 characters</p>
                </div>
                <div class="grid grid-cols-2 gap-4">
                    <div>
                        <label class="block text-[10px] font-black text-slate-400 uppercase tracking-widest mb-2">Tier</label>
                        <select name="tier" x-model="newAccount.tier" class="w-full bg-slate-50 border-none rounded-xl px-4 py-3 text-sm focus:ring-1 focus:ring-blue-400">
                            <option>Tier 1</option><option>Tier 2</option><option>Tier 3</option>
                        </select>
                    </div>
                    <div>
                        <label class="block text-[10px] font-black text-slate-400 uppercase tracking-widest mb-2">Owner</label>
                        <input name="owner" x-model="newAccount.owner" class="w-full bg-slate-50 border-none rounded-xl px-4 py-3 text-sm focus:ring-1 focus:ring-blue-400">
                    </div>
                </div>
                <div class="flex space-x-3 pt-4">
                    <button type="submit" class="flex-1 bg-slate-900 text-white font-bold py-3 rounded-xl hover:bg-black transition-all">Create Account</button>
                </div>
            </form>
        </div>
    </div>

    <script>
        function dashboard() {
            return {
                accounts: {{ accounts_json | safe }},
                search: '',
                tierFilter: 'All',
                healthFilter: 'All',
                sortBy: 'name',
                sortDir: 'asc',
                showModal: false,
                expandedAccountId: null,
                newAccount: { name: '', tier: 'Tier 2', owner: '' },

                filteredAccounts() {
                    let results = this.accounts.filter(acc => {
                        const matchesSearch = acc.name.toLowerCase().includes(this.search.toLowerCase());
                        const matchesTier = this.tierFilter === 'All' || acc.tier === this.tierFilter;
                        const matchesHealth = this.healthFilter === 'All' || acc.healthSentiment === this.healthFilter;
                        return matchesSearch && matchesTier && matchesHealth;
                    });

                    // Apply sorting
                    results.sort((a, b) => {
                        let aVal, bVal;
                        if (this.sortBy === 'name') {
                            aVal = a.name.toLowerCase();
                            bVal = b.name.toLowerCase();
                        } else if (this.sortBy === 'tier') {
                            aVal = a.tier;
                            bVal = b.tier;
                        } else {
                            aVal = (a.owner || '').toLowerCase();
                            bVal = (b.owner || '').toLowerCase();
                        }
                        if (aVal < bVal) return this.sortDir === 'asc' ? -1 : 1;
                        if (aVal > bVal) return this.sortDir === 'asc' ? 1 : -1;
                        return 0;
                    });

                    return results;
                },
                toggleSort(column) {
                    if (this.sortBy === column) {
                        this.sortDir = this.sortDir === 'asc' ? 'desc' : 'asc';
                    } else {
                        this.sortBy = column;
                        this.sortDir = 'asc';
                    }
                },
                toggleExpand(id) {
                    this.expandedAccountId = this.expandedAccountId === id ? null : id;
                },
                truncate(text, length) {
                    if (!text) return '';
                    return text.length > length ? text.substring(0, length) + '...' : text;
                },
                openModal() {
                    this.newAccount = { name: '', tier: 'Tier 2', owner: '' };
                    this.showModal = true;
                },
                goToAccount(id) {
                    window.location.href = '/qbr/account/' + id;
                },
                formatDate(dateStr) {
                    if (!dateStr) return 'TBD';
                    const date = new Date(dateStr);
                    return date.toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' });
                },
                q1Count() {
                    if (!this.accounts.length) return 0;
                    return Math.round((this.accounts.filter(a => a.qbrCompletion.q1).length / this.accounts.length) * 100);
                },
                tier1Count() {
                    return this.accounts.filter(a => a.tier === 'Tier 1').length;
                }
            }
        }
    </script>
</body>
</html>
"""

# --- HTML Template for Account Details Page ---
ACCOUNT_DETAILS_TEMPLATE = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{{ account.name }} - Zenlayer</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <script defer src="https://unpkg.com/alpinejs@3.x.x/dist/cdn.min.js"></script>
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap" rel="stylesheet">
    <style>
        [x-cloak] { display: none !important; }
        body { font-family: 'Inter', sans-serif; background-color: #fcfcfd; }
        .donut-logo {
            background: linear-gradient(to right, #33d4ff, #0076ff) border-box;
            -webkit-mask: linear-gradient(#fff 0 0) padding-box, linear-gradient(#fff 0 0);
            -webkit-mask-composite: destination-out;
            mask-composite: exclude;
        }
    </style>
</head>
<body x-data="accountDetails()">
    <nav class="sticky top-0 z-30 bg-white/80 backdrop-blur-md border-b border-slate-100">
        <div class="max-w-7xl mx-auto px-6 h-20 flex items-center justify-between">
            <a href="/qbr/" class="flex items-center space-x-2.5 hover:opacity-80 transition-opacity">
                <div class="relative w-8 h-8 flex items-center justify-center">
                    <div class="absolute inset-0 rounded-full border-[5px] border-transparent donut-logo"></div>
                </div>
                <div class="flex flex-col">
                    <span class="text-[22px] font-medium text-[#2d3b45] tracking-tight leading-none">zenlayer</span>
                    <span class="text-[9px] font-bold text-slate-400 uppercase tracking-[0.2em] mt-0.5 leading-none">Engagement Plan</span>
                </div>
            </a>
            <a href="/qbr/" class="flex items-center space-x-2 text-slate-500 hover:text-slate-900 transition-colors">
                <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M10 19l-7-7m0 0l7-7m-7 7h18"/></svg>
                <span class="text-sm font-medium">Back to Portfolio</span>
            </a>
        </div>
    </nav>

    <main class="max-w-4xl mx-auto pl-6 pr-6 py-8">
        <!-- Account Header with Metadata Badges -->
        <div class="bg-white rounded-2xl border border-slate-100 shadow-sm p-8 mb-6">
            <div class="flex items-start justify-between">
                <div class="flex-1">
                    <div class="flex items-center space-x-3 mb-1">
                        <h1 class="text-2xl font-bold text-slate-900" x-text="account.name"></h1>
                        <span class="px-2.5 py-1 rounded-full text-[10px] font-bold border border-slate-200 text-slate-600 bg-slate-50" x-text="account.tier"></span>
                    </div>
                    <div class="flex items-center space-x-2 text-sm text-slate-500 mb-2">
                        <span>Owner: <span class="font-medium text-slate-700" x-text="account.owner || 'Unassigned'"></span></span>
                    </div>
                    <!-- Current Status Headline -->
                    <p x-show="account.latestUpdate" class="text-base font-semibold text-slate-700 mt-3" x-text="account.latestUpdate"></p>
                </div>
                <!-- Metadata Badges + Edit Button -->
                <div class="flex flex-col items-end space-y-3">
                    <button x-show="!isEditing" @click="isEditing = true" class="bg-slate-900 hover:bg-slate-800 text-white px-5 py-2 rounded-xl text-sm font-semibold transition-all">
                        Edit Account
                    </button>
                    <div class="flex items-center space-x-2">
                        <!-- Health Sentiment Badge -->
                        <div class="flex items-center space-x-1.5 px-3 py-1.5 rounded-full text-xs font-semibold"
                             :class="{
                                 'bg-emerald-50 text-emerald-700 border border-emerald-200': account.healthSentiment === 'green',
                                 'bg-amber-50 text-amber-700 border border-amber-200': account.healthSentiment === 'yellow',
                                 'bg-rose-50 text-rose-700 border border-rose-200': account.healthSentiment === 'red'
                             }">
                            <div class="w-2 h-2 rounded-full"
                                 :class="{
                                     'bg-emerald-500': account.healthSentiment === 'green',
                                     'bg-amber-500': account.healthSentiment === 'yellow',
                                     'bg-rose-500': account.healthSentiment === 'red'
                                 }"></div>
                            <span x-text="account.healthSentiment === 'green' ? 'Healthy' : (account.healthSentiment === 'yellow' ? 'Concern' : 'At Risk')"></span>
                        </div>
                        <!-- Next QBR Badge -->
                        <div class="flex items-center space-x-1.5 px-3 py-1.5 rounded-full text-xs font-semibold bg-slate-50 text-slate-600 border border-slate-200">
                            <svg class="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M8 7V3m8 4V3m-9 8h10M5 21h14a2 2 0 002-2V7a2 2 0 00-2-2H5a2 2 0 00-2 2v12a2 2 0 002 2z"/></svg>
                            <span x-text="'Next QBR: ' + (account.nextQbrDate ? formatDate(account.nextQbrDate) : 'TBD')"></span>
                        </div>
                    </div>
                </div>
            </div>
        </div>

        <!-- View Mode -->
        <div x-show="!isEditing" class="space-y-6">
            <!-- Hero Insights - Key Learnings & Action Items (Top Priority) -->
            <div class="bg-gradient-to-br from-slate-50 to-white rounded-2xl border border-slate-100 shadow-sm p-8">
                <div class="grid grid-cols-2 gap-8">
                    <div>
                        <label class="block text-[10px] font-black text-slate-400 uppercase tracking-widest mb-3">Key Learnings</label>
                        <template x-if="account.keyLearnings">
                            <ul class="space-y-2">
                                <template x-for="line in account.keyLearnings.split('\\n').filter(l => l.trim())">
                                    <li class="flex items-start space-x-2 text-sm text-slate-700">
                                        <span class="text-slate-400 mt-0.5">•</span>
                                        <span x-text="line.replace(/^[-•*]\\s*/, '')"></span>
                                    </li>
                                </template>
                            </ul>
                        </template>
                        <p x-show="!account.keyLearnings" class="text-sm text-slate-400 italic">No key learnings recorded yet.</p>
                    </div>
                    <div>
                        <label class="block text-[10px] font-black text-slate-400 uppercase tracking-widest mb-3">Action Items</label>
                        <template x-if="account.actionItems && account.actionItems.length > 0">
                            <ul class="space-y-2">
                                <template x-for="(item, index) in account.actionItems" :key="index">
                                    <li class="flex items-start space-x-2 text-sm text-slate-700">
                                        <span class="text-slate-400 mt-0.5">•</span>
                                        <span x-text="item"></span>
                                    </li>
                                </template>
                            </ul>
                        </template>
                        <p x-show="!account.actionItems || account.actionItems.length === 0" class="text-sm text-slate-400 italic">No action items defined yet.</p>
                    </div>
                </div>
            </div>

            <!-- Main Content + Sidebar Layout -->
            <div class="grid grid-cols-3 gap-6">
                <!-- Main Content (2 columns) -->
                <div class="col-span-2 space-y-6">
                    <!-- QBR Tracker Card -->
                    <div class="bg-white rounded-2xl border border-slate-100 shadow-sm p-8">
                        <label class="block text-[10px] font-black text-slate-400 uppercase tracking-widest mb-4">QBR Completion Tracker</label>
                        <div class="flex space-x-3">
                            <template x-for="q in ['q1', 'q2', 'q3', 'q4']">
                                <div :class="account.qbrCompletion[q] ? 'bg-emerald-500 text-white' : 'bg-slate-100 text-slate-400'"
                                     class="w-12 h-12 rounded-xl flex items-center justify-center text-sm font-bold uppercase"
                                     x-text="q"></div>
                            </template>
                        </div>
                    </div>
                </div>

                <!-- Contacts Sidebar (1 column) -->
                <div class="col-span-1">
                    <div class="bg-white rounded-2xl border border-slate-100 shadow-sm p-6 sticky top-28">
                        <div class="flex items-center space-x-2 mb-4">
                            <svg class="w-4 h-4 text-slate-400" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M17 20h5v-2a3 3 0 00-5.356-1.857M17 20H7m10 0v-2c0-.656-.126-1.283-.356-1.857M7 20H2v-2a3 3 0 015.356-1.857M7 20v-2c0-.656.126-1.283.356-1.857m0 0a5.002 5.002 0 019.288 0M15 7a3 3 0 11-6 0 3 3 0 016 0zm6 3a2 2 0 11-4 0 2 2 0 014 0zM7 10a2 2 0 11-4 0 2 2 0 014 0z"/></svg>
                            <label class="text-[10px] font-black text-slate-400 uppercase tracking-widest">Contacts</label>
                        </div>
                        <div x-show="account.contacts && account.contacts.length > 0" class="space-y-3">
                            <template x-for="(contact, index) in account.contacts" :key="index">
                                <div class="p-3 bg-slate-50 rounded-xl">
                                    <p class="text-sm font-medium text-slate-900" x-text="contact.name"></p>
                                    <a :href="'mailto:' + contact.email" class="text-xs text-blue-600 hover:text-blue-700" x-text="contact.email"></a>
                                </div>
                            </template>
                        </div>
                        <p x-show="!account.contacts || account.contacts.length === 0" class="text-sm text-slate-400">No contacts added yet.</p>
                    </div>
                </div>
            </div>
        </div>

        <!-- Edit Mode -->
        <form x-show="isEditing" @submit.prevent="submitForm()" class="space-y-6">
            <input type="hidden" name="id" :value="account.id">

            <!-- Basic Info Card -->
            <div class="bg-white rounded-2xl border border-slate-100 shadow-sm p-8 space-y-6">
                <div class="grid grid-cols-2 gap-6">
                    <div>
                        <label class="block text-[10px] font-black text-slate-400 uppercase tracking-widest mb-2">Account Name</label>
                        <input name="name" x-model="account.name" maxlength="35" class="w-full bg-slate-50 border-none rounded-xl px-4 py-3 text-sm focus:ring-1 focus:ring-blue-400" required>
                        <p class="text-xs text-slate-400 mt-1">Max 35 characters</p>
                    </div>
                    <div>
                        <label class="block text-[10px] font-black text-slate-400 uppercase tracking-widest mb-2">Owner</label>
                        <input name="owner" x-model="account.owner" class="w-full bg-slate-50 border-none rounded-xl px-4 py-3 text-sm focus:ring-1 focus:ring-blue-400">
                    </div>
                </div>

                <div class="grid grid-cols-2 gap-6">
                    <div>
                        <label class="block text-[10px] font-black text-slate-400 uppercase tracking-widest mb-2">Tier</label>
                        <select name="tier" x-model="account.tier" class="w-full bg-slate-50 border-none rounded-xl px-4 py-3 text-sm focus:ring-1 focus:ring-blue-400">
                            <option>Tier 1</option><option>Tier 2</option><option>Tier 3</option>
                        </select>
                    </div>
                    <div>
                        <label class="block text-[10px] font-black text-slate-400 uppercase tracking-widest mb-2">Next QBR</label>
                        <input type="date" name="next_qbr_date" x-model="account.nextQbrDate" class="w-full bg-slate-50 border-none rounded-xl px-4 py-3 text-sm focus:ring-1 focus:ring-blue-400">
                    </div>
                </div>

                <div>
                    <label class="block text-[10px] font-black text-slate-400 uppercase tracking-widest mb-2">Health Sentiment</label>
                    <div class="flex space-x-3">
                        <label class="cursor-pointer">
                            <input type="radio" name="health_sentiment" value="green" x-model="account.healthSentiment" class="hidden">
                            <div :class="account.healthSentiment === 'green' ? 'ring-2 ring-emerald-500 ring-offset-2' : ''"
                                 class="flex items-center space-x-2 px-4 py-2 rounded-xl bg-emerald-50 text-emerald-700 transition-all">
                                <div class="w-3 h-3 rounded-full bg-emerald-500"></div>
                                <span class="text-sm font-medium">Healthy</span>
                            </div>
                        </label>
                        <label class="cursor-pointer">
                            <input type="radio" name="health_sentiment" value="yellow" x-model="account.healthSentiment" class="hidden">
                            <div :class="account.healthSentiment === 'yellow' ? 'ring-2 ring-amber-400 ring-offset-2' : ''"
                                 class="flex items-center space-x-2 px-4 py-2 rounded-xl bg-amber-50 text-amber-700 transition-all">
                                <div class="w-3 h-3 rounded-full bg-amber-400"></div>
                                <span class="text-sm font-medium">Concern</span>
                            </div>
                        </label>
                        <label class="cursor-pointer">
                            <input type="radio" name="health_sentiment" value="red" x-model="account.healthSentiment" class="hidden">
                            <div :class="account.healthSentiment === 'red' ? 'ring-2 ring-rose-500 ring-offset-2' : ''"
                                 class="flex items-center space-x-2 px-4 py-2 rounded-xl bg-rose-50 text-rose-700 transition-all">
                                <div class="w-3 h-3 rounded-full bg-rose-500"></div>
                                <span class="text-sm font-medium">At Risk</span>
                            </div>
                        </label>
                    </div>
                </div>

                <div>
                    <label class="block text-[10px] font-black text-slate-400 uppercase tracking-widest mb-2">QBR Completion Tracker</label>
                    <div class="grid grid-cols-4 gap-3">
                        <template x-for="q in ['q1', 'q2', 'q3', 'q4']">
                            <label class="cursor-pointer">
                                <input type="checkbox" :name="q" x-model="account.qbrCompletion[q]" class="hidden">
                                <div :class="account.qbrCompletion[q] ? 'bg-emerald-500 text-white' : 'bg-slate-100 text-slate-400'"
                                     class="px-4 py-3 rounded-xl text-center text-sm font-bold uppercase transition-all"
                                     x-text="q"></div>
                            </label>
                        </template>
                    </div>
                </div>
            </div>

            <!-- Primary Contacts Card -->
            <div class="bg-white rounded-2xl border border-slate-100 shadow-sm p-8">
                <div class="flex items-center justify-between mb-4">
                    <label class="block text-[10px] font-black text-slate-400 uppercase tracking-widest">Primary Contacts</label>
                    <button type="button" @click="addContact()" class="text-xs font-semibold text-blue-600 hover:text-blue-700">+ Add Contact</button>
                </div>
                <div class="space-y-3">
                    <template x-for="(contact, index) in account.contacts" :key="index">
                        <div class="flex items-center space-x-3">
                            <input type="text" x-model="contact.name" placeholder="Name" class="flex-1 bg-slate-50 border-none rounded-xl px-4 py-3 text-sm focus:ring-1 focus:ring-blue-400">
                            <input type="email" x-model="contact.email" placeholder="Email" class="flex-1 bg-slate-50 border-none rounded-xl px-4 py-3 text-sm focus:ring-1 focus:ring-blue-400">
                            <button type="button" @click="removeContact(index)" class="p-2 text-slate-400 hover:text-rose-500 transition-colors">
                                <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16"/></svg>
                            </button>
                        </div>
                    </template>
                </div>
                <p x-show="account.contacts.length === 0" class="text-sm text-slate-400">No contacts added yet. Click "Add Contact" to add one.</p>
            </div>

            <!-- Latest Update Card -->
            <div class="bg-white rounded-2xl border border-slate-100 shadow-sm p-8">
                <label class="block text-[10px] font-black text-slate-400 uppercase tracking-widest mb-4">Latest Update</label>
                <input type="text" x-model="account.latestUpdate" maxlength="50" placeholder="Short headline for current status..."
                       class="w-full bg-slate-50 border-none rounded-xl px-4 py-3 text-sm focus:ring-1 focus:ring-blue-400">
                <p class="text-xs text-slate-400 mt-2">A brief status headline shown on the main dashboard. Max 50 characters.</p>
            </div>

            <!-- Key Learnings & Next Steps Card -->
            <div class="bg-white rounded-2xl border border-slate-100 shadow-sm p-8">
                <div class="grid grid-cols-2 gap-6">
                    <div>
                        <label class="block text-[10px] font-black text-slate-400 uppercase tracking-widest mb-4">Key Learnings</label>
                        <textarea x-model="account.keyLearnings" rows="5" placeholder="Record insights and learnings from the last QBR..."
                                  class="w-full bg-slate-50 border-none rounded-xl px-4 py-3 text-sm focus:ring-1 focus:ring-blue-400 resize-none"></textarea>
                    </div>
                    <div>
                        <label class="block text-[10px] font-black text-slate-400 uppercase tracking-widest mb-4">Next Steps</label>
                        <textarea x-model="account.nextSteps" rows="5" placeholder="Define the next steps and priorities..."
                                  class="w-full bg-slate-50 border-none rounded-xl px-4 py-3 text-sm focus:ring-1 focus:ring-blue-400 resize-none"></textarea>
                    </div>
                </div>
            </div>

            <!-- Action Items Card -->
            <div class="bg-white rounded-2xl border border-slate-100 shadow-sm p-8">
                <div class="flex items-center justify-between mb-4">
                    <label class="block text-[10px] font-black text-slate-400 uppercase tracking-widest">Action Items</label>
                    <button type="button" @click="addActionItem()" class="text-xs font-semibold text-blue-600 hover:text-blue-700">+ Add Item</button>
                </div>
                <div class="space-y-3">
                    <template x-for="(item, index) in account.actionItems" :key="index">
                        <div class="flex items-center space-x-3">
                            <div class="w-6 h-6 bg-blue-100 rounded-full flex items-center justify-center flex-shrink-0">
                                <span class="text-[10px] font-bold text-blue-600" x-text="index + 1"></span>
                            </div>
                            <input type="text" x-model="account.actionItems[index]" placeholder="Action item..." class="flex-1 bg-slate-50 border-none rounded-xl px-4 py-3 text-sm focus:ring-1 focus:ring-blue-400">
                            <button type="button" @click="removeActionItem(index)" class="p-2 text-slate-400 hover:text-rose-500 transition-colors">
                                <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16"/></svg>
                            </button>
                        </div>
                    </template>
                </div>
                <p x-show="account.actionItems.length === 0" class="text-sm text-slate-400">No action items yet. Click "Add Item" to add one.</p>
            </div>

            <!-- Action Buttons -->
            <div class="bg-white rounded-2xl border border-slate-100 shadow-sm p-8">
                <div class="flex space-x-3">
                    <button type="submit" class="flex-1 bg-slate-900 text-white font-bold py-3 rounded-xl hover:bg-black transition-all">Save Changes</button>
                    <button type="button" @click="isEditing = false; resetAccount()" class="bg-slate-100 text-slate-700 px-6 py-3 rounded-xl hover:bg-slate-200 transition-all font-semibold">Cancel</button>
                    <button type="button" @click="showDeleteConfirm = true" class="bg-rose-50 text-rose-500 px-6 py-3 rounded-xl hover:bg-rose-100 transition-all font-semibold">Delete</button>
                </div>
            </div>
        </form>
    </main>

    <!-- Delete Confirmation Modal -->
    <div x-show="showDeleteConfirm" class="fixed inset-0 bg-slate-900/40 backdrop-blur-sm z-[60] flex items-center justify-center p-4" x-cloak>
        <div class="bg-white rounded-2xl w-full max-w-sm overflow-hidden shadow-2xl" @click.away="showDeleteConfirm = false">
            <div class="p-6 text-center">
                <div class="w-12 h-12 rounded-full bg-rose-100 flex items-center justify-center mx-auto mb-4">
                    <svg class="w-6 h-6 text-rose-500" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/></svg>
                </div>
                <h3 class="text-lg font-bold text-slate-900 mb-2">Delete Account</h3>
                <p class="text-sm text-slate-500 mb-6">Are you sure you want to delete <span class="font-semibold text-slate-700" x-text="account.name"></span>? This action cannot be undone.</p>
                <div class="flex space-x-3">
                    <button @click="showDeleteConfirm = false" class="flex-1 bg-slate-100 text-slate-700 font-semibold py-2.5 rounded-xl hover:bg-slate-200 transition-all">Cancel</button>
                    <button @click="confirmDelete()" class="flex-1 bg-rose-500 text-white font-semibold py-2.5 rounded-xl hover:bg-rose-600 transition-all">Delete</button>
                </div>
            </div>
        </div>
    </div>

    <script>
        function accountDetails() {
            return {
                account: {{ account_json | safe }},
                originalAccount: JSON.parse('{{ account_json | safe }}'),
                isEditing: false,
                showDeleteConfirm: false,

                init() {
                    // Ensure arrays and fields exist
                    if (!this.account.contacts) this.account.contacts = [];
                    if (!this.account.actionItems) this.account.actionItems = [];
                    if (!this.account.keyLearnings) this.account.keyLearnings = '';
                    if (!this.account.nextSteps) this.account.nextSteps = '';
                    if (!this.account.latestUpdate) this.account.latestUpdate = '';
                    // Check for edit mode in URL
                    const urlParams = new URLSearchParams(window.location.search);
                    if (urlParams.get('edit') === 'true') {
                        this.isEditing = true;
                    }
                },
                formatDate(dateStr) {
                    if (!dateStr) return 'TBD';
                    const date = new Date(dateStr);
                    return date.toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' });
                },
                resetAccount() {
                    this.account = JSON.parse(JSON.stringify(this.originalAccount));
                    if (!this.account.contacts) this.account.contacts = [];
                    if (!this.account.actionItems) this.account.actionItems = [];
                    if (!this.account.keyLearnings) this.account.keyLearnings = '';
                    if (!this.account.nextSteps) this.account.nextSteps = '';
                    if (!this.account.latestUpdate) this.account.latestUpdate = '';
                },
                addContact() {
                    this.account.contacts.push({ name: '', email: '' });
                },
                removeContact(index) {
                    this.account.contacts.splice(index, 1);
                },
                addActionItem() {
                    this.account.actionItems.push('');
                },
                removeActionItem(index) {
                    this.account.actionItems.splice(index, 1);
                },
                submitForm() {
                    // Create form and submit with JSON data
                    const form = document.createElement('form');
                    form.method = 'POST';
                    form.action = '/qbr/save';

                    const fields = {
                        id: this.account.id,
                        name: this.account.name,
                        tier: this.account.tier,
                        owner: this.account.owner,
                        health_sentiment: this.account.healthSentiment,
                        next_qbr_date: this.account.nextQbrDate,
                        key_learnings: this.account.keyLearnings,
                        next_steps: this.account.nextSteps,
                        latest_update: this.account.latestUpdate,
                        contacts_json: JSON.stringify(this.account.contacts),
                        action_items_json: JSON.stringify(this.account.actionItems),
                        q1: this.account.qbrCompletion.q1 ? 'on' : '',
                        q2: this.account.qbrCompletion.q2 ? 'on' : '',
                        q3: this.account.qbrCompletion.q3 ? 'on' : '',
                        q4: this.account.qbrCompletion.q4 ? 'on' : ''
                    };

                    for (const [key, value] of Object.entries(fields)) {
                        const input = document.createElement('input');
                        input.type = 'hidden';
                        input.name = key;
                        input.value = value;
                        form.appendChild(input);
                    }

                    document.body.appendChild(form);
                    form.submit();
                },
                confirmDelete() {
                    const form = document.createElement('form');
                    form.method = 'POST';
                    form.action = '/qbr/delete/' + this.account.id;
                    document.body.appendChild(form);
                    form.submit();
                }
            }
        }
    </script>
</body>
</html>
"""

@app.get("/", response_class=HTMLResponse)
@app.get("", response_class=HTMLResponse)
async def dashboard(request: Request):
    accounts = get_all_accounts()
    accounts_json = json.dumps(accounts)
    return Template(HTML_TEMPLATE).render(accounts_json=accounts_json)

@app.get("/account/{account_id}", response_class=HTMLResponse)
async def account_details(account_id: str):
    account = get_account_by_id(account_id)
    if not account:
        return RedirectResponse(url="/qbr/", status_code=303)
    account_json = json.dumps(account)
    return Template(ACCOUNT_DETAILS_TEMPLATE).render(account=account, account_json=account_json)

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

    # Parse JSON fields
    try:
        contacts = json.loads(contacts_json) if contacts_json else []
        # Filter out empty contacts
        contacts = [c for c in contacts if c.get('name') or c.get('email')]
    except:
        contacts = []

    try:
        action_items = json.loads(action_items_json) if action_items_json else []
        # Filter out empty items
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

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
