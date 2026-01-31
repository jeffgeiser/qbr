
from fastapi import FastAPI, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from jinja2 import Template
from typing import List, Optional, Dict
import json
import uuid

app = FastAPI(root_path="/qbr")

# --- Initial Data ---
ACCOUNTS = [
    {
        "id": "1",
        "name": "Zoom Video Communications Inc.",
        "tier": "Tier 1",
        "owner": "Carlos",
        "healthSentiment": "green",
        "nextQbrDate": "",
        "qbrCompletion": {"q1": False, "q2": False, "q3": False, "q4": False},
        "keyLearnings": "",
        "actionItems": [],
        "contacts": [{"name": "Eric Yuan", "email": "eric@zoom.com"}, {"name": "Kelly Steckelberg", "email": "kelly@zoom.com"}]
    },
    {
        "id": "2",
        "name": "Nvidia Corporation",
        "tier": "Tier 1",
        "owner": "Wade",
        "healthSentiment": "yellow",
        "nextQbrDate": "",
        "qbrCompletion": {"q1": True, "q2": False, "q3": False, "q4": False},
        "keyLearnings": "Strong interest in expanding GPU allocation for AI workloads.",
        "actionItems": ["Follow up on pricing proposal", "Schedule technical deep-dive"],
        "contacts": [{"name": "Jensen Huang", "email": "jensen@nvidia.com"}]
    },
    {
        "id": "3",
        "name": "Cisco - Jasper",
        "tier": "Tier 1",
        "owner": "Josh L.",
        "healthSentiment": "red",
        "nextQbrDate": "2026-03-15",
        "qbrCompletion": {"q1": True, "q2": True, "q3": False, "q4": False},
        "keyLearnings": "Concerns about latency in APAC region. Need to address before renewal.",
        "actionItems": ["Review APAC latency metrics", "Prepare renewal proposal", "Schedule exec alignment call"],
        "contacts": [{"name": "Mike Hayes", "email": "mhayes@cisco.com"}, {"name": "Chuck Robbins", "email": "crobbins@cisco.com"}]
    }
]

# --- HTML Template for Main Dashboard ---
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
        <div class="grid grid-cols-1 sm:grid-cols-3 gap-4 mb-10">
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
                        <th class="px-6 py-4 border-b border-slate-100">
                            <div class="text-[11px] font-bold text-slate-400 uppercase tracking-widest mb-1">QBR Tracking</div>
                            <div class="flex">
                                <span class="w-6 text-[9px] font-semibold text-slate-300 text-center">Q1</span>
                                <span class="w-6 text-[9px] font-semibold text-slate-300 text-center">Q2</span>
                                <span class="w-6 text-[9px] font-semibold text-slate-300 text-center">Q3</span>
                                <span class="w-6 text-[9px] font-semibold text-slate-300 text-center">Q4</span>
                            </div>
                        </th>
                        <th class="px-6 py-4 text-[11px] font-bold text-slate-400 uppercase tracking-widest border-b border-slate-100">Next QBR</th>
                        <th class="px-6 py-4 text-[11px] font-bold text-slate-400 uppercase tracking-widest border-b border-slate-100">Tier</th>
                        <th class="px-6 py-4 text-[11px] font-bold text-slate-400 uppercase tracking-widest border-b border-slate-100">Owner</th>
                    </tr>
                </thead>
                <tbody class="divide-y divide-slate-50">
                    <template x-for="account in filteredAccounts()" :key="account.id">
                        <tr @click="goToAccount(account.id)" class="hover:bg-slate-50/50 transition-colors cursor-pointer">
                            <td class="px-6 py-4">
                                <div class="flex items-center space-x-3">
                                    <div class="w-2.5 h-2.5 rounded-full flex-shrink-0"
                                         :class="{
                                             'bg-emerald-500': account.healthSentiment === 'green',
                                             'bg-amber-400': account.healthSentiment === 'yellow',
                                             'bg-rose-500': account.healthSentiment === 'red'
                                         }"></div>
                                    <span class="font-semibold text-slate-900 text-sm" x-text="account.name"></span>
                                </div>
                            </td>
                            <td class="px-6 py-4">
                                <div class="flex">
                                    <template x-for="q in ['q1', 'q2', 'q3', 'q4']">
                                        <div class="w-6 flex justify-center">
                                            <div :class="account.qbrCompletion[q] ? 'bg-emerald-500' : 'bg-slate-200'"
                                                 class="w-2.5 h-2.5 rounded-full transition-all"></div>
                                        </div>
                                    </template>
                                </div>
                            </td>
                            <td class="px-6 py-4">
                                <span class="text-sm" :class="account.nextQbrDate ? 'text-slate-600' : 'text-slate-400'"
                                      x-text="account.nextQbrDate ? formatDate(account.nextQbrDate) : 'TBD'"></span>
                            </td>
                            <td class="px-6 py-4">
                                <span x-text="account.tier" class="px-2 py-0.5 rounded-md text-[10px] font-bold border border-slate-100 text-slate-600 bg-slate-50/30"></span>
                            </td>
                            <td class="px-6 py-4 text-sm text-slate-600" x-text="account.owner"></td>
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
                    <input name="name" x-model="newAccount.name" class="w-full bg-slate-50 border-none rounded-xl px-4 py-3 text-sm focus:ring-1 focus:ring-blue-400" required>
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
                showModal: false,
                newAccount: { name: '', tier: 'Tier 2', owner: '' },

                filteredAccounts() {
                    return this.accounts.filter(acc => {
                        const matchesSearch = acc.name.toLowerCase().includes(this.search.toLowerCase());
                        const matchesTier = this.tierFilter === 'All' || acc.tier === this.tierFilter;
                        return matchesSearch && matchesTier;
                    });
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
            <div class="flex items-center space-x-2.5">
                <div class="relative w-8 h-8 flex items-center justify-center">
                    <div class="absolute inset-0 rounded-full border-[5px] border-transparent donut-logo"></div>
                </div>
                <div class="flex flex-col">
                    <span class="text-[22px] font-medium text-[#2d3b45] tracking-tight leading-none">zenlayer</span>
                    <span class="text-[9px] font-bold text-slate-400 uppercase tracking-[0.2em] mt-0.5 leading-none">Engagement Plan</span>
                </div>
            </div>
            <a href="/qbr/" class="flex items-center space-x-2 text-slate-500 hover:text-slate-900 transition-colors">
                <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M10 19l-7-7m0 0l7-7m-7 7h18"/></svg>
                <span class="text-sm font-medium">Back to Portfolio</span>
            </a>
        </div>
    </nav>

    <main class="max-w-4xl mx-auto px-6 py-8">
        <!-- Account Header -->
        <div class="bg-white rounded-2xl border border-slate-100 shadow-sm p-8 mb-6">
            <div class="flex items-start justify-between">
                <div class="flex items-center space-x-4">
                    <div class="w-4 h-4 rounded-full"
                         :class="{
                             'bg-emerald-500': account.healthSentiment === 'green',
                             'bg-amber-400': account.healthSentiment === 'yellow',
                             'bg-rose-500': account.healthSentiment === 'red'
                         }"></div>
                    <div>
                        <h1 class="text-2xl font-bold text-slate-900" x-text="account.name"></h1>
                        <div class="flex items-center space-x-3 mt-1">
                            <span class="text-sm text-slate-500">Owner: <span class="font-medium text-slate-700" x-text="account.owner || 'Unassigned'"></span></span>
                            <span class="text-slate-300">|</span>
                            <span class="px-2 py-0.5 rounded-md text-[10px] font-bold border border-slate-100 text-slate-600 bg-slate-50/30" x-text="account.tier"></span>
                        </div>
                    </div>
                </div>
                <button x-show="!isEditing" @click="isEditing = true" class="bg-slate-900 hover:bg-slate-800 text-white px-5 py-2 rounded-xl text-sm font-semibold transition-all">
                    Edit Account
                </button>
            </div>
        </div>

        <!-- View Mode -->
        <div x-show="!isEditing" class="space-y-6">
            <!-- Basic Info Card -->
            <div class="bg-white rounded-2xl border border-slate-100 shadow-sm p-8 space-y-6">
                <div class="grid grid-cols-2 gap-6">
                    <div>
                        <label class="block text-[10px] font-black text-slate-400 uppercase tracking-widest mb-2">Account Name</label>
                        <p class="text-sm text-slate-900" x-text="account.name"></p>
                    </div>
                    <div>
                        <label class="block text-[10px] font-black text-slate-400 uppercase tracking-widest mb-2">Owner</label>
                        <p class="text-sm text-slate-900" x-text="account.owner || 'Unassigned'"></p>
                    </div>
                </div>

                <div class="grid grid-cols-2 gap-6">
                    <div>
                        <label class="block text-[10px] font-black text-slate-400 uppercase tracking-widest mb-2">Tier</label>
                        <p class="text-sm text-slate-900" x-text="account.tier"></p>
                    </div>
                    <div>
                        <label class="block text-[10px] font-black text-slate-400 uppercase tracking-widest mb-2">Next Scheduled QBR</label>
                        <p class="text-sm" :class="account.nextQbrDate ? 'text-slate-900' : 'text-slate-400'" x-text="account.nextQbrDate ? formatDate(account.nextQbrDate) : 'TBD'"></p>
                    </div>
                </div>

                <div>
                    <label class="block text-[10px] font-black text-slate-400 uppercase tracking-widest mb-2">Health Sentiment</label>
                    <div class="flex items-center space-x-2">
                        <div class="w-3 h-3 rounded-full"
                             :class="{
                                 'bg-emerald-500': account.healthSentiment === 'green',
                                 'bg-amber-400': account.healthSentiment === 'yellow',
                                 'bg-rose-500': account.healthSentiment === 'red'
                             }"></div>
                        <span class="text-sm text-slate-900" x-text="account.healthSentiment === 'green' ? 'Healthy' : (account.healthSentiment === 'yellow' ? 'Concern' : 'At Risk')"></span>
                    </div>
                </div>

                <div>
                    <label class="block text-[10px] font-black text-slate-400 uppercase tracking-widest mb-2">QBR Completion Tracker</label>
                    <div class="flex space-x-2">
                        <template x-for="q in ['q1', 'q2', 'q3', 'q4']">
                            <div :class="account.qbrCompletion[q] ? 'bg-emerald-500 text-white' : 'bg-slate-100 text-slate-400'"
                                 class="w-10 h-10 rounded-xl flex items-center justify-center text-xs font-bold uppercase"
                                 x-text="q"></div>
                        </template>
                    </div>
                </div>
            </div>

            <!-- Primary Contacts Card -->
            <div class="bg-white rounded-2xl border border-slate-100 shadow-sm p-8">
                <label class="block text-[10px] font-black text-slate-400 uppercase tracking-widest mb-4">Primary Contacts</label>
                <div x-show="account.contacts && account.contacts.length > 0" class="space-y-3">
                    <template x-for="(contact, index) in account.contacts" :key="index">
                        <div class="flex items-center space-x-3 p-3 bg-slate-50 rounded-xl">
                            <div class="w-8 h-8 bg-slate-200 rounded-full flex items-center justify-center">
                                <svg class="w-4 h-4 text-slate-500" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M16 7a4 4 0 11-8 0 4 4 0 018 0zM12 14a7 7 0 00-7 7h14a7 7 0 00-7-7z"/></svg>
                            </div>
                            <div>
                                <p class="text-sm font-medium text-slate-900" x-text="contact.name"></p>
                                <p class="text-xs text-slate-500" x-text="contact.email"></p>
                            </div>
                        </div>
                    </template>
                </div>
                <p x-show="!account.contacts || account.contacts.length === 0" class="text-sm text-slate-400">No contacts added yet.</p>
            </div>

            <!-- Key Learnings Card -->
            <div class="bg-white rounded-2xl border border-slate-100 shadow-sm p-8">
                <label class="block text-[10px] font-black text-slate-400 uppercase tracking-widest mb-4">Key Learnings from Last QBR</label>
                <p x-show="account.keyLearnings" class="text-sm text-slate-700 whitespace-pre-wrap" x-text="account.keyLearnings"></p>
                <p x-show="!account.keyLearnings" class="text-sm text-slate-400">No key learnings recorded yet.</p>
            </div>

            <!-- Action Items Card -->
            <div class="bg-white rounded-2xl border border-slate-100 shadow-sm p-8">
                <label class="block text-[10px] font-black text-slate-400 uppercase tracking-widest mb-4">Next Steps / Action Items</label>
                <div x-show="account.actionItems && account.actionItems.length > 0" class="space-y-2">
                    <template x-for="(item, index) in account.actionItems" :key="index">
                        <div class="flex items-start space-x-3 p-3 bg-slate-50 rounded-xl">
                            <div class="w-5 h-5 bg-blue-100 rounded-full flex items-center justify-center flex-shrink-0 mt-0.5">
                                <span class="text-[10px] font-bold text-blue-600" x-text="index + 1"></span>
                            </div>
                            <p class="text-sm text-slate-700" x-text="item"></p>
                        </div>
                    </template>
                </div>
                <p x-show="!account.actionItems || account.actionItems.length === 0" class="text-sm text-slate-400">No action items recorded yet.</p>
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
                        <input name="name" x-model="account.name" class="w-full bg-slate-50 border-none rounded-xl px-4 py-3 text-sm focus:ring-1 focus:ring-blue-400" required>
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
                        <label class="block text-[10px] font-black text-slate-400 uppercase tracking-widest mb-2">Next Scheduled QBR</label>
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

            <!-- Key Learnings Card -->
            <div class="bg-white rounded-2xl border border-slate-100 shadow-sm p-8">
                <label class="block text-[10px] font-black text-slate-400 uppercase tracking-widest mb-4">Key Learnings from Last QBR</label>
                <textarea x-model="account.keyLearnings" rows="4" placeholder="Record insights and learnings from the last QBR..."
                          class="w-full bg-slate-50 border-none rounded-xl px-4 py-3 text-sm focus:ring-1 focus:ring-blue-400 resize-none"></textarea>
            </div>

            <!-- Action Items Card -->
            <div class="bg-white rounded-2xl border border-slate-100 shadow-sm p-8">
                <div class="flex items-center justify-between mb-4">
                    <label class="block text-[10px] font-black text-slate-400 uppercase tracking-widest">Next Steps / Action Items</label>
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
                    // Ensure arrays exist
                    if (!this.account.contacts) this.account.contacts = [];
                    if (!this.account.actionItems) this.account.actionItems = [];
                    if (!this.account.keyLearnings) this.account.keyLearnings = '';
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
    accounts_json = json.dumps(ACCOUNTS)
    return Template(HTML_TEMPLATE).render(accounts_json=accounts_json)

@app.get("/account/{account_id}", response_class=HTMLResponse)
async def account_details(account_id: str):
    account = next((acc for acc in ACCOUNTS if acc["id"] == account_id), None)
    if not account:
        return RedirectResponse(url="/qbr/", status_code=303)
    account_json = json.dumps(account)
    return Template(ACCOUNT_DETAILS_TEMPLATE).render(account=account, account_json=account_json)

@app.post("/save")
async def save_account(
    id: Optional[str] = Form(None),
    name: str = Form(...),
    tier: str = Form(...),
    owner: str = Form(""),
    health_sentiment: Optional[str] = Form("green"),
    next_qbr_date: Optional[str] = Form(""),
    key_learnings: Optional[str] = Form(""),
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

    if id:
        for acc in ACCOUNTS:
            if acc["id"] == id:
                acc.update({
                    "name": name,
                    "tier": tier,
                    "owner": owner,
                    "healthSentiment": health_sentiment or "green",
                    "nextQbrDate": next_qbr_date or "",
                    "keyLearnings": key_learnings or "",
                    "contacts": contacts,
                    "actionItems": action_items,
                    "qbrCompletion": qbr
                })
                break
        return RedirectResponse(url=f"/qbr/account/{id}", status_code=303)
    else:
        new_id = str(uuid.uuid4())
        new_acc = {
            "id": new_id,
            "name": name,
            "tier": tier,
            "owner": owner,
            "healthSentiment": health_sentiment or "green",
            "nextQbrDate": next_qbr_date or "",
            "keyLearnings": key_learnings or "",
            "contacts": contacts,
            "actionItems": action_items,
            "qbrCompletion": qbr
        }
        ACCOUNTS.append(new_acc)
        return RedirectResponse(url="/qbr/", status_code=303)

@app.post("/delete/{account_id}")
async def delete_account(account_id: str):
    global ACCOUNTS
    ACCOUNTS = [acc for acc in ACCOUNTS if acc["id"] != account_id]
    return RedirectResponse(url="/qbr/", status_code=303)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
