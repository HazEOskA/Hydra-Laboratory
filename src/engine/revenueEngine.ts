import { AuditItem, DraftItem, FollowupItem, Lead, LeadState } from '../types';

const URGENCY_SCORE: Record<string, number> = {
  immediate: 30,
  high: 24,
  medium: 15,
  low: 6,
  '': 0,
};

const TEAM_SCORE: Record<string, number> = {
  '1-9': 6,
  '10-49': 16,
  '50-199': 24,
  '200+': 20,
  '': 0,
};

export function scoreLead(lead: Partial<Lead>): number {
  let score = URGENCY_SCORE[(lead.urgency || '').toLowerCase()] || 0;
  score += TEAM_SCORE[lead.team_size || ''] || 0;
  if (lead.problem && lead.problem.trim().length > 0) score += 12;
  if (lead.website && lead.website.trim().length > 0) score += 8;
  if (lead.current_tools && lead.current_tools.length > 0) {
    score += Math.min(10, 3 * lead.current_tools.length);
  }
  if (lead.consent) score += 10;
  if (lead.email && lead.email.trim().length > 0) score += 4;
  return Math.max(0, Math.min(100, score));
}

export function estimateValue(lead: Partial<Lead>, score: number): number {
  const base: Record<string, number> = {
    '1-9': 1500,
    '10-49': 6000,
    '50-199': 15000,
    '200+': 30000,
  };
  const baseVal = base[lead.team_size || ''] || 2000;
  return Math.round(baseVal * (0.5 + score / 100));
}

export function generateAudit(lead: Lead, score: number, findings: string[] = []): string {
  const now = new Date().toISOString();
  const findingLines =
    findings.length > 0 ? findings.map((f) => `- ${f}`).join('\n') : '- No manual findings recorded yet.';

  return `# AI Operations & Automation Audit — ${lead.company}

- Prepared: ${now}
- Industry: ${lead.industry || 'not stated'}
- Team size: ${lead.team_size || 'not stated'}
- Stated problem: ${lead.problem || 'not stated'}
- Opportunity score: ${score}/100

## Observed problem map

${findingLines}

## Automation opportunities

- Candidate workflows are derived from the stated problem and current tools.
- Current tools on record: ${lead.current_tools.length > 0 ? lead.current_tools.join(', ') : 'none recorded'}

## Risk assessment

- Estimates in this document are forecasts, not commitments.
- No system was accessed to produce this audit; it uses supplied and public data only.

## Next step

- A scoped diagnostic sprint, quoted after a short technical discovery call.`;
}

export function generateOutreachDraft(lead: Lead, auditSummary: string): { subject: string; body: string } {
  const subject = `${lead.company}: automation findings from a short operations review`;
  const body = `Hello ${lead.contact_name || 'there'},

I looked at ${lead.company} from public information and put together a short operations review focused on where automation would actually pay for itself.

${auditSummary}

If it is useful I can walk through it in 20 minutes and leave you the written version either way.

— Bartosz Osiński, OsaTechGPT

[DRAFT — not sent. Sending requires scoped OSA approval.]`;

  return { subject, body };
}

export class RevenueLedgerEngine {
  private leads: Map<string, Lead> = new Map();
  private audits: Map<string, AuditItem> = new Map();
  private drafts: Map<string, DraftItem> = new Map();
  private followups: Map<string, FollowupItem> = new Map();

  constructor(initialLeads?: Lead[]) {
    if (initialLeads) {
      for (const l of initialLeads) {
        this.leads.set(l.lead_id, { ...l });
      }
    }
  }

  public getLeads(): Lead[] {
    return Array.from(this.leads.values()).sort(
      (a, b) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime()
    );
  }

  public getLead(leadId: string): Lead | undefined {
    return this.leads.get(leadId);
  }

  public getAudits(): AuditItem[] {
    return Array.from(this.audits.values());
  }

  public getDrafts(): DraftItem[] {
    return Array.from(this.drafts.values());
  }

  public getFollowups(): FollowupItem[] {
    return Array.from(this.followups.values());
  }

  public addLead(leadData: Omit<Lead, 'score' | 'estimated_value' | 'state' | 'created_at' | 'updated_at'>): Lead {
    const score = scoreLead(leadData);
    const estimated = estimateValue(leadData, score);
    const now = new Date().toISOString();

    const lead: Lead = {
      ...leadData,
      score,
      estimated_value: estimated,
      state: 'new',
      created_at: now,
      updated_at: now,
    };

    this.leads.set(lead.lead_id, lead);
    return lead;
  }

  public setState(leadId: string, newState: LeadState, approvalRef = ''): Lead {
    const lead = this.leads.get(leadId);
    if (!lead) throw new Error(`Lead '${leadId}' not found`);

    if (['approved_to_send', 'sent'].includes(newState) && !approvalRef) {
      throw new Error(`State '${newState}' implies external contact and strictly requires a scoped OSA approval`);
    }

    lead.state = newState;
    lead.updated_at = new Date().toISOString();
    return { ...lead };
  }

  public createAuditAndDraft(
    leadId: string,
    opts: {
      auditId: string;
      draftId: string;
      followupId: string;
      track?: string;
      findings?: string[];
      followupDays?: number;
    }
  ): { lead: Lead; audit: AuditItem; draft: DraftItem; followup: FollowupItem } {
    const lead = this.leads.get(leadId);
    if (!lead) throw new Error(`Lead '${leadId}' not found`);

    const score = scoreLead(lead);
    const auditBody = generateAudit(lead, score, opts.findings || []);
    const { subject, body: draftBody } = generateOutreachDraft(lead, `Opportunity score: ${score}/100`);

    const now = new Date().toISOString();
    const followupDue = new Date(Date.now() + (opts.followupDays || 4) * 86400000)
      .toISOString()
      .split('T')[0];

    const audit: AuditItem = {
      audit_id: opts.auditId,
      lead_id: leadId,
      track: opts.track || 'TRACK_1_AI_SYSTEM_AUDITS',
      body: auditBody,
      opportunity_score: score,
      created_at: now,
    };
    this.audits.set(audit.audit_id, audit);

    const draft: DraftItem = {
      draft_id: opts.draftId,
      lead_id: leadId,
      kind: 'outreach',
      subject,
      body: draftBody,
      sent: false,
      created_at: now,
    };
    this.drafts.set(draft.draft_id, draft);

    const followup: FollowupItem = {
      followup_id: opts.followupId,
      lead_id: leadId,
      due_date: followupDue,
      body: 'Check lead outreach response or send gentle nudge if approved',
      done: false,
      created_at: now,
    };
    this.followups.set(followup.followup_id, followup);

    lead.state = 'draft_ready';
    lead.updated_at = now;

    return { lead: { ...lead }, audit, draft, followup };
  }

  public getTotals(): {
    estimated_value: number;
    pipeline_value: number;
    contracted_value: number;
    invoiced_value: number;
    received_value: number;
  } {
    let estimated = 0;
    let pipeline = 0;
    for (const lead of this.leads.values()) {
      estimated += lead.estimated_value;
      if (['audit_ready', 'draft_ready', 'approved_to_send', 'sent', 'replied', 'qualified'].includes(lead.state)) {
        pipeline += lead.estimated_value * 0.4;
      } else if (lead.state === 'proposal') {
        pipeline += lead.estimated_value * 0.75;
      } else if (lead.state === 'won') {
        pipeline += lead.estimated_value;
      }
    }
    return {
      estimated_value: Math.round(estimated),
      pipeline_value: Math.round(pipeline),
      contracted_value: 0,
      invoiced_value: 0,
      received_value: 0,
    };
  }

  public getCounts(): {
    leads: number;
    audits: number;
    drafts: number;
    drafts_sent: number;
    followups_due: number;
  } {
    const today = new Date().toISOString().split('T')[0];
    let sentCount = 0;
    for (const d of this.drafts.values()) {
      if (d.sent) sentCount++;
    }
    let followupsDue = 0;
    for (const f of this.followups.values()) {
      if (!f.done && f.due_date <= today) followupsDue++;
    }

    return {
      leads: this.leads.size,
      audits: this.audits.size,
      drafts: this.drafts.size,
      drafts_sent: sentCount,
      followups_due: followupsDue,
    };
  }
}
