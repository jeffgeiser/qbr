
export enum AccountTier {
  TIER1 = 'Tier 1',
  TIER2 = 'Tier 2',
  TIER3 = 'Tier 3'
}

export enum AccountStatus {
  ACTIVE = 'Active',
  AT_RISK = 'At Risk',
  CHURNED = 'Churned',
  NEW = 'New'
}

export interface QBRCompletion {
  q1: boolean;
  q2: boolean;
  q3: boolean;
  q4: boolean;
}

export interface Account {
  id: string;
  name: string;
  tier: AccountTier;
  owner: string;
  primaryContact: string;
  keyContacts: string;
  email: string;
  location: string;
  annualRevenue: number;
  engagementFocus: string;
  qbrFrequency: string;
  lastQbrDate: string;
  nextQbrDate: string;
  status: AccountStatus;
  notes: string;
  qbrCompletion: QBRCompletion;
}
