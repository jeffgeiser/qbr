
from fastapi import FastAPI, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from jinja2 import Template
from typing import List, Optional, Dict
import json
import uuid

app = FastAPI(rooth_path="/qbr"))

# --- Initial Data ---
ACCOUNTS = [
    {
        "id": "1",
        "name": "Zoom Video Communications Inc.",
        "tier": "Tier 1",
        "owner": "Carlos",
        "primaryContact": "Lagos Project",
        "keyContacts": "Eric Yuan (CEO), Kelly Steckelberg (CFO)",
        "email": "contact@zoom.com",
        "location": "Global",
        "annualRevenue": 8807991,
        "status": "Active",
        "notes": "In person.. Dinner preferable Jasper: Lagos project active ($100k MRR)",
        "qbrCompletion": {"q1": False, "q2": False, "q3": False, "q4": False}
    },
    {
        "id": "2",
        "name": "Nvidia Corporation",
        "tier": "Tier 1",
        "owner": "Wade",
        "primaryContact": "Wade's Contact",
        "keyContacts": "Jensen Huang (CEO), Colette Kress (CFO)",
        "email": "info@nvidia.com",
        "location": "Global",
        "annualRevenue": 3288080,
        "status": "Active",
        "notes": "Strategic hardware alignment",
        "qbrCompletion": {"q1": False, "q2": False, "q3": False, "q4": False}
    },
    {
        "id": "3",
        "name": "Cisco - Jasper",
        "tier": "Tier 1",
        "owner": "Josh L.",
        "primaryContact": "Mike Hayes",
        "keyContacts": "Chuck Robbins, Maria Martinez (COO)",
        "email": "mhayes@cisco.com",
        "location": "NoCal",
        "annualRevenue": 3210445,
        "status": "Active",
        "notes": "Project active; Umbrella/Webex integration",
        "qbrCompletion": {"q1": False, "q2": False, "q3": False, "q4": False}
    }
]

# --- HTML Template ---
HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Zenlayer Account Engagement</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <script defer src="https://unpkg.com/alpinejs@3.x.x/dist/cdn.min.js"></script>
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap" rel="stylesheet">
    <style>
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
            <h1 class="text-3xl font-bold text-slate-900 mb-1">Account Portfolio</h1>
            <p class="text-slate-500 text-sm font-medium">Strategic roadmap and quarterly QBR tracking dashboard.</p>
        </div>

        <!-- Stats -->
        <div class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4 mb-10">
            <div class="bg-white p-5 rounded-2xl border border-slate-100 shadow-sm">
                <span class="text-[11px] font-bold text-slate-400 uppercase tracking-widest block mb-2">Total Accounts</span>
                <span class="text-2xl font-semibold text-slate-900" x-text="accounts.length"></span>
            </div>
            <div class="bg-white p-5 rounded-2xl border border-slate-100 shadow-sm">
                <span class="text-[11px] font-bold text-slate-400 uppercase tracking-widest block mb-2">Q1 Completion</span>
                <span class="text-2xl font-semibold text-slate-900" x-text="q1Count() + '%'"></span>
            </div>
            <div class="bg-white p-5 rounded-2xl border border-slate-100 shadow-sm">
                <span class="text-[11px] font-bold text-slate-400 uppercase tracking-widest block mb-2">Tier 1 Strategic</span>
                <span class="text-2xl font-semibold text-slate-900" x-text="tier1Count()"></span>
            </div>
            <div class="bg-white p-5 rounded-2xl border border-slate-100 shadow-sm">
                <span class="text-[11px] font-bold text-slate-400 uppercase tracking-widest block mb-2">At Risk Status</span>
                <span class="text-2xl font-semibold text-rose-500" x-text="riskCount()"></span>
            </div>
        </div>

        <!-- Tier Filters -->
        <div class="flex items-center space-x-2 mb-6">
            <template x-for="t in ['All', 'Tier 1', 'Tier 2', 'Tier 3']">
                <button @click="tierFilter = t" 
                        :class="tierFilter === t ? 'bg-white shadow-sm text-slate-900 border-slate-200' : 'text-slate-500 border-transparent'"
                        class="px-4 py-1.5 rounded-lg text-xs font-semibold transition-all border"
                        x-text="t"></button>
            </template>
        </div>

        <!-- Account Table -->
        <div class="bg-white rounded-2xl border border-slate-100 shadow-sm overflow-hidden">
            <table class="w-full text-left">
                <thead>
                    <tr class="bg-slate-50/30">
                        <th class="px-6 py-4 text-[11px] font-bold text-slate-400 uppercase tracking-widest border-b border-slate-100">Account</th>
                        <th class="px-6 py-4 text-[11px] font-bold text-slate-400 uppercase tracking-widest border-b border-slate-100">QBR Tracking</th>
                        <th class="px-6 py-4 text-[11px] font-bold text-slate-400 uppercase tracking-widest border-b border-slate-100">Tier</th>
                        <th class="px-6 py-4 text-[11px] font-bold text-slate-400 uppercase tracking-widest border-b border-slate-100">Owner</th>
                        <th class="px-6 py-4 text-[11px] font-bold text-slate-400 uppercase tracking-widest border-b border-slate-100 text-right">Settings</th>
                    </tr>
                </thead>
                <tbody class="divide-y divide-slate-50">
                    <template x-for="account in filteredAccounts()" :key="account.id">
                        <tr class="hover:bg-slate-50/50 transition-colors">
                            <td class="px-6 py-4">
                                <span class="font-semibold text-slate-900 text-sm" x-text="account.name"></span>
                            </td>
                            <td class="px-6 py-4">
                                <div class="flex space-x-1.5">
                                    <template x-for="q in ['q1', 'q2', 'q3', 'q4']">
                                        <div :class="account.qbrCompletion[q] ? 'bg-emerald-500 text-white' : 'bg-slate-100 text-slate-400'"
                                             class="w-7 h-7 rounded-md flex items-center justify-center text-[10px] font-bold uppercase transition-all shadow-sm"
                                             x-text="q"></div>
                                    </template>
                                </div>
                            </td>
                            <td class="px-6 py-4">
                                <span x-text="account.tier" class="px-2 py-0.5 rounded-md text-[10px] font-bold border border-slate-100 text-slate-600 bg-slate-50/30"></span>
                            </td>
                            <td class="px-6 py-4 text-sm text-slate-600" x-text="account.owner"></td>
                            <td class="px-6 py-4 text-right">
                                <button @click="openModal(account)" class="p-1.5 text-slate-400 hover:text-blue-500 transition-colors">
                                    <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.065 2.572c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.572 1.065c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.065-2.572c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 001.066-2.573c-.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 2.572-1.065z"/><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15 12a3 3 0 11-6 0 3 3 0 016 0z"/></svg>
                                </button>
                            </td>
                        </tr>
                    </template>
                </tbody>
            </table>
        </div>
    </main>

    <!-- Modal -->
    <div x-show="showModal" class="fixed inset-0 bg-slate-900/40 backdrop-blur-sm z-50 flex items-center justify-center p-4" x-cloak>
        <div class="bg-white rounded-[2rem] w-full max-w-xl max-h-[90vh] overflow-hidden shadow-2xl flex flex-col" @click.away="showModal = false">
            <div class="p-6 border-b flex justify-between items-center bg-slate-50/50">
                <h2 class="text-lg font-bold text-slate-900" x-text="editingAccount.id ? 'Edit Account' : 'New Account'"></h2>
                <button @click="showModal = false" class="p-1 hover:bg-slate-100 rounded-full"><svg class="w-5 h-5 text-slate-400" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path d="M6 18L18 6M6 6l12 12" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/></svg></button>
            </div>
            <form action="save" method="POST" class="overflow-y-auto p-8 space-y-6">
                <input type="hidden" name="id" :value="editingAccount.id">
                <div>
                    <label class="block text-[10px] font-black text-slate-400 uppercase tracking-widest mb-2">Account Name</label>
                    <input name="name" x-model="editingAccount.name" class="w-full bg-slate-50 border-none rounded-xl px-4 py-3 text-sm focus:ring-1 focus:ring-blue-400" required>
                </div>
                <div class="grid grid-cols-2 gap-4">
                    <div>
                        <label class="block text-[10px] font-black text-slate-400 uppercase tracking-widest mb-2">Tier</label>
                        <select name="tier" x-model="editingAccount.tier" class="w-full bg-slate-50 border-none rounded-xl px-4 py-3 text-sm focus:ring-1 focus:ring-blue-400">
                            <option>Tier 1</option><option>Tier 2</option><option>Tier 3</option>
                        </select>
                    </div>
                    <div>
                        <label class="block text-[10px] font-black text-slate-400 uppercase tracking-widest mb-2">Owner</label>
                        <input name="owner" x-model="editingAccount.owner" class="w-full bg-slate-50 border-none rounded-xl px-4 py-3 text-sm focus:ring-1 focus:ring-blue-400">
                    </div>
                </div>
                <div>
                    <label class="block text-[10px] font-black text-slate-400 uppercase tracking-widest mb-2">Account Status</label>
                    <label class="cursor-pointer inline-flex items-center space-x-3">
                        <input type="checkbox" name="at_risk" x-model="editingAccount.status" true-value="At Risk" false-value="Active" class="hidden">
                        <div :class="editingAccount.status === 'At Risk' ? 'bg-rose-500 text-white' : 'bg-slate-100 text-slate-400'"
                             class="px-4 py-2 rounded-lg text-xs font-bold uppercase transition-all border border-transparent">
                            At Risk
                        </div>
                        <span class="text-sm text-slate-500" x-text="editingAccount.status === 'At Risk' ? 'This account is marked as at risk' : 'Click to mark as at risk'"></span>
                    </label>
                </div>
                <div>
                    <label class="block text-[10px] font-black text-slate-400 uppercase tracking-widest mb-2">QBR Completion Tracker</label>
                    <div class="grid grid-cols-4 gap-2">
                        <template x-for="q in ['q1', 'q2', 'q3', 'q4']">
                            <label class="cursor-pointer">
                                <input type="checkbox" :name="q" x-model="editingAccount.qbrCompletion[q]" class="hidden">
                                <div :class="editingAccount.qbrCompletion[q] ? 'bg-emerald-500 text-white' : 'bg-slate-100 text-slate-400'"
                                     class="px-3 py-2 rounded-lg text-center text-xs font-bold uppercase transition-all border border-transparent"
                                     x-text="q"></div>
                            </label>
                        </template>
                    </div>
                </div>
                <div class="flex space-x-3 pt-4">
                    <button type="submit" class="flex-1 bg-slate-900 text-white font-bold py-3 rounded-xl hover:bg-black transition-all">Save Changes</button>
                    <template x-if="editingAccount.id">
                         <button type="button" @click="deleteAccount()" class="bg-rose-50 text-rose-500 px-4 py-3 rounded-xl hover:bg-rose-100 transition-all"><svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/></svg></button>
                    </template>
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
                showModal: false,
                editingAccount: { id: '', name: '', tier: 'Tier 2', owner: '', status: 'Active', qbrCompletion: {q1: false, q2: false, q3: false, q4: false} },
                
                filteredAccounts() {
                    return this.accounts.filter(acc => {
                        const matchesSearch = acc.name.toLowerCase().includes(this.search.toLowerCase());
                        const matchesTier = this.tierFilter === 'All' || acc.tier === this.tierFilter;
                        return matchesSearch && matchesTier;
                    });
                },
                openModal(acc = null) {
                    if (acc) {
                        this.editingAccount = JSON.parse(JSON.stringify(acc));
                    } else {
                        this.editingAccount = { id: '', name: '', tier: 'Tier 2', owner: '', status: 'Active', qbrCompletion: {q1: false, q2: false, q3: false, q4: false} };
                    }
                    this.showModal = true;
                },
                q1Count() {
                    if (!this.accounts.length) return 0;
                    return Math.round((this.accounts.filter(a => a.qbrCompletion.q1).length / this.accounts.length) * 100);
                },
                tier1Count() {
                    return this.accounts.filter(a => a.tier === 'Tier 1').length;
                },
                riskCount() {
                    return this.accounts.filter(a => a.status === 'At Risk').length;
                },
                deleteAccount() {
                    if (confirm('Delete this account permanently?')) {
                        const form = document.createElement('form');
                        form.method = 'POST';
                        form.action = 'delete/' + this.editingAccount.id;
                        document.body.appendChild(form);
                        form.submit();
                    }
                }
            }
        }
    </script>
</body>
</html>
"""

@app.get("/", response_class=HTMLResponse)
@app.get("", response_class=HTMLResponse) # 3. ADD EMPTY ROUTE
async def dashboard(request: Request):
    accounts_json = json.dumps(ACCOUNTS)
    return Template(HTML_TEMPLATE).render(accounts_json=accounts_json)

@app.post("/save")
async def save_account(
    id: Optional[str] = Form(None),
    name: str = Form(...),
    tier: str = Form(...),
    owner: str = Form(""),
    at_risk: Optional[str] = Form(None),
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
    status = "At Risk" if at_risk == "on" else "Active"

    if id:
        for acc in ACCOUNTS:
            if acc["id"] == id:
                acc.update({"name": name, "tier": tier, "owner": owner, "status": status, "qbrCompletion": qbr})
                break
    else:
        new_acc = {
            "id": str(uuid.uuid4()),
            "name": name,
            "tier": tier,
            "owner": owner,
            "status": status,
            "qbrCompletion": qbr
        }
        ACCOUNTS.append(new_acc)
    
    return RedirectResponse(url="/", status_code=303)

@app.post("/delete/{account_id}")
async def delete_account(account_id: str):
    global ACCOUNTS
    ACCOUNTS = [acc for acc in ACCOUNTS if acc["id"] != account_id]
    return RedirectResponse(url="/", status_code=303)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
