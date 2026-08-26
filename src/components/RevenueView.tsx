import React, { useState } from 'react';
import {
  DollarSign,
  TrendingUp,
  FileText,
  Mail,
  Send,
  Plus,
  ShieldAlert,
  CheckCircle2,
  Clock,
  Sparkles,
  Search,
  X,
  Lock,
} from 'lucide-react';
import { AuditItem, DraftItem, FollowupItem, Lead, LeadState } from '../types';
import { RevenueLedgerEngine } from '../engine/revenueEngine';

interface RevenueViewProps {
  revenueEngine: RevenueLedgerEngine;
  leads: Lead[];
  audits: AuditItem[];
  drafts: DraftItem[];
  followups: FollowupItem[];
  onAddLead: (lead: any) => void;
  onGenerateAuditAndDraft: (leadId: string) => void;
  onSetLeadState: (leadId: string, newState: LeadState, approvalRef?: string) => void;
}

export const RevenueView: React.FC<RevenueViewProps> = ({
  revenueEngine,
  leads,
  audits,
  drafts,
  followups,
  onAddLead,
  onGenerateAuditAndDraft,
  onSetLeadState,
}) => {
  const [showAddModal, setShowAddModal] = useState(false);
  const [showAuditViewer, setShowAuditViewer] = useState<AuditItem | null>(null);
  const [showDraftViewer, setShowDraftViewer] = useState<DraftItem | null>(null);
  const [showApprovalModal, setShowApprovalModal] = useState<{ lead: Lead; targetState: LeadState } | null>(null);
  const [approvalToken, setApprovalToken] = useState('OSA-APPROVAL-2026-REV');
  const [searchLead, setSearchLead] = useState('');

  // Form state
  const [newCompany, setNewCompany] = useState('');
  const [newContact, setNewContact] = useState('');
  const [newEmail, setNewEmail] = useState('');
  const [newIndustry, setNewIndustry] = useState('Enterprise Software');
  const [newProblem, setNewProblem] = useState('');
  const [newTeamSize, setNewTeamSize] = useState('10-49');
  const [newUrgency, setNewUrgency] = useState('high');
  const [newTools, setNewTools] = useState('PostgreSQL, Jira, Python');
  const [newConsent, setNewConsent] = useState(true);

  const totals = revenueEngine.getTotals();
  const counts = revenueEngine.getCounts();

  const handleAddSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    const toolsArray = newTools
      .split(',')
      .map((s) => s.trim())
      .filter(Boolean);
    const leadId = `lead-${newCompany.toLowerCase().replace(/[^a-z0-9]/g, '-').slice(0, 20)}-${Date.now().toString().slice(-4)}`;

    onAddLead({
      lead_id: leadId,
      company: newCompany,
      contact_name: newContact,
      email: newEmail,
      website: `https://${newCompany.toLowerCase().replace(/[^a-z0-9]/g, '')}.example`,
      industry: newIndustry,
      problem: newProblem,
      team_size: newTeamSize,
      current_tools: toolsArray,
      urgency: newUrgency,
      consent: newConsent,
      source: 'Direct research / intake',
    });

    setShowAddModal(false);
    setNewCompany('');
    setNewContact('');
    setNewEmail('');
    setNewProblem('');
  };

  const handleApprovalSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!showApprovalModal) return;
    try {
      onSetLeadState(showApprovalModal.lead.lead_id, showApprovalModal.targetState, approvalToken);
      setShowApprovalModal(null);
    } catch (err: any) {
      alert(`Approval error: ${err.message}`);
    }
  };

  const filteredLeads = leads.filter((l) =>
    l.company.toLowerCase().includes(searchLead.toLowerCase()) ||
    l.industry.toLowerCase().includes(searchLead.toLowerCase()) ||
    l.problem.toLowerCase().includes(searchLead.toLowerCase())
  );

  return (
    <div className="space-y-6">
      {/* Top Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 pb-2 border-b border-slate-800">
        <div>
          <h2 className="text-lg font-bold text-slate-100 flex items-center gap-2">
            <DollarSign className="w-5 h-5 text-emerald-400" />
            Revenue Operations & Monitored Ledger
          </h2>
          <p className="text-xs text-slate-400 mt-1">
            Ethical monetization engine. Outbound outreach drafts require explicit OSA review before sending.
          </p>
        </div>

        <div className="flex items-center gap-2">
          <button
            onClick={() => setShowAddModal(true)}
            className="flex items-center gap-1.5 px-3.5 py-1.5 bg-emerald-600 hover:bg-emerald-500 text-white font-mono text-xs rounded-lg transition cursor-pointer"
          >
            <Plus className="w-3.5 h-3.5" />
            <span>Intake Lead</span>
          </button>
        </div>
      </div>

      {/* Financial Pipeline KPI Metrics */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-5 gap-3">
        <div className="bg-slate-900/80 border border-slate-800 rounded-xl p-4">
          <div className="text-[11px] font-mono text-slate-400">ESTIMATED ADDRESSABLE</div>
          <div className="text-xl font-bold font-mono text-slate-100 mt-1">
            ${totals.estimated_value.toLocaleString()}
          </div>
          <div className="text-[10px] text-slate-500 mt-1">Sum of all lead potential</div>
        </div>

        <div className="bg-slate-900/80 border border-slate-800 rounded-xl p-4">
          <div className="text-[11px] font-mono text-emerald-400">WEIGHTED PIPELINE</div>
          <div className="text-xl font-bold font-mono text-emerald-300 mt-1">
            ${totals.pipeline_value.toLocaleString()}
          </div>
          <div className="text-[10px] text-slate-500 mt-1">Active audits & proposals</div>
        </div>

        <div className="bg-slate-900/80 border border-slate-800 rounded-xl p-4">
          <div className="text-[11px] font-mono text-slate-400">CONTRACTED CASH</div>
          <div className="text-xl font-bold font-mono text-slate-100 mt-1">$0</div>
          <div className="text-[10px] text-slate-500 mt-1">Signed engagements</div>
        </div>

        <div className="bg-slate-900/80 border border-slate-800 rounded-xl p-4">
          <div className="text-[11px] font-mono text-slate-400">INVOICED CASH</div>
          <div className="text-xl font-bold font-mono text-slate-100 mt-1">$0</div>
          <div className="text-[10px] text-slate-500 mt-1">Awaiting settlement</div>
        </div>

        <div className="bg-slate-900/80 border border-slate-800 rounded-xl p-4">
          <div className="text-[11px] font-mono text-slate-400">REALISED CASH</div>
          <div className="text-xl font-bold font-mono text-slate-100 mt-1">$0</div>
          <div className="text-[10px] text-slate-500 mt-1">Strict fact-based accounting</div>
        </div>
      </div>

      {/* Monetization Rules Banner */}
      <div className="bg-slate-900/60 border border-slate-800 rounded-xl p-4 text-xs font-mono text-slate-300 flex items-start gap-3">
        <Lock className="w-4 h-4 text-amber-400 shrink-0 mt-0.5" />
        <div>
          <span className="font-semibold text-slate-100">SOUL.md Monetization Principles: </span>
          Drafting audits and emails is <span className="text-emerald-400 font-bold">GREEN</span>. 
          Sending any external email, outreach, or charging cards is <span className="text-rose-400 font-bold">STRICT RED</span> and requires scoped OSA authorization.
        </div>
      </div>

      {/* Leads Table */}
      <div className="bg-slate-900/80 border border-slate-800 rounded-xl overflow-hidden shadow-sm">
        <div className="p-3.5 border-b border-slate-800 flex items-center justify-between">
          <div className="flex items-center gap-2 text-xs font-mono text-slate-300">
            <span>QUALIFIED LEADS ({filteredLeads.length})</span>
          </div>

          <div className="relative w-64">
            <Search className="w-3.5 h-3.5 text-slate-400 absolute left-3 top-2.5" />
            <input
              type="text"
              value={searchLead}
              onChange={(e) => setSearchLead(e.target.value)}
              placeholder="Search companies, problems..."
              className="w-full bg-slate-950 border border-slate-800 rounded-lg pl-8 pr-3 py-1.5 text-xs text-slate-200 focus:outline-none focus:border-sky-500 font-mono"
            />
          </div>
        </div>

        <div className="overflow-x-auto">
          <table className="w-full text-left text-xs font-mono">
            <thead className="bg-slate-950/80 text-slate-400 border-b border-slate-800">
              <tr>
                <th className="py-3 px-4">Score & Value</th>
                <th className="py-3 px-4">Company & Contact</th>
                <th className="py-3 px-4">Stated Problem & Tools</th>
                <th className="py-3 px-4">State</th>
                <th className="py-3 px-4 text-right">Operations</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-800/80 text-slate-300">
              {filteredLeads.map((lead) => {
                const leadAudits = audits.filter((a) => a.lead_id === lead.lead_id);
                const leadDrafts = drafts.filter((d) => d.lead_id === lead.lead_id);

                return (
                  <tr key={lead.lead_id} className="hover:bg-slate-850/50">
                    <td className="py-3 px-4">
                      <div className="flex items-center gap-2">
                        <div
                          className={`w-9 h-9 rounded-lg flex flex-col items-center justify-center font-bold ${
                            lead.score >= 75
                              ? 'bg-emerald-950 text-emerald-300 border border-emerald-800'
                              : lead.score >= 50
                              ? 'bg-sky-950 text-sky-300 border border-sky-800'
                              : 'bg-slate-800 text-slate-300'
                          }`}
                        >
                          <span className="text-xs">{lead.score}</span>
                          <span className="text-[8px] opacity-75">/100</span>
                        </div>
                        <div>
                          <div className="font-bold text-slate-100">${lead.estimated_value.toLocaleString()}</div>
                          <div className="text-[10px] text-slate-500">Urgency: {lead.urgency}</div>
                        </div>
                      </div>
                    </td>

                    <td className="py-3 px-4">
                      <div className="font-semibold text-slate-100">{lead.company}</div>
                      <div className="text-[11px] text-slate-400">
                        {lead.contact_name} &bull; <span className="text-slate-500">{lead.email}</span>
                      </div>
                      <div className="text-[10px] text-slate-500">{lead.industry} ({lead.team_size} team)</div>
                    </td>

                    <td className="py-3 px-4 max-w-xs">
                      <p className="text-slate-300 truncate" title={lead.problem}>
                        {lead.problem || 'No stated problem recorded'}
                      </p>
                      <div className="flex flex-wrap gap-1 mt-1">
                        {lead.current_tools.map((t, idx) => (
                          <span key={idx} className="text-[10px] bg-slate-950 text-slate-400 px-1 rounded border border-slate-850">
                            {t}
                          </span>
                        ))}
                      </div>
                    </td>

                    <td className="py-3 px-4">
                      <span
                        className={`inline-block px-2 py-0.5 rounded text-[11px] font-semibold ${
                          lead.state === 'draft_ready' || lead.state === 'audit_ready'
                            ? 'bg-purple-950 text-purple-300 border border-purple-800'
                            : lead.state === 'approved_to_send'
                            ? 'bg-amber-950 text-amber-300 border border-amber-800'
                            : lead.state === 'sent'
                            ? 'bg-sky-950 text-sky-300 border border-sky-800'
                            : 'bg-slate-800 text-slate-300'
                        }`}
                      >
                        {lead.state}
                      </span>
                    </td>

                    <td className="py-3 px-4 text-right">
                      <div className="flex items-center justify-end gap-1.5">
                        {/* 1-Click Generate Audit & Draft */}
                        <button
                          onClick={() => onGenerateAuditAndDraft(lead.lead_id)}
                          className="px-2.5 py-1 bg-sky-600 hover:bg-sky-500 text-white rounded text-[11px] flex items-center gap-1 cursor-pointer"
                          title="Generate mini-audit and draft email (GREEN)"
                        >
                          <Sparkles className="w-3 h-3" />
                          <span>Generate Audit</span>
                        </button>

                        {leadAudits.length > 0 && (
                          <button
                            onClick={() => setShowAuditViewer(leadAudits[0])}
                            className="px-2 py-1 bg-slate-800 hover:bg-slate-700 text-slate-300 rounded text-[11px] flex items-center gap-1 cursor-pointer"
                            title="View generated audit report"
                          >
                            <FileText className="w-3 h-3 text-purple-400" />
                            <span>Audit</span>
                          </button>
                        )}

                        {leadDrafts.length > 0 && (
                          <button
                            onClick={() => setShowDraftViewer(leadDrafts[0])}
                            className="px-2 py-1 bg-slate-800 hover:bg-slate-700 text-slate-300 rounded text-[11px] flex items-center gap-1 cursor-pointer"
                            title="View generated outreach draft"
                          >
                            <Mail className="w-3 h-3 text-sky-400" />
                            <span>Draft</span>
                          </button>
                        )}

                        {lead.state === 'draft_ready' && (
                          <button
                            onClick={() => setShowApprovalModal({ lead, targetState: 'approved_to_send' })}
                            className="px-2 py-1 bg-rose-900/80 hover:bg-rose-800 text-rose-200 rounded text-[11px] flex items-center gap-1 cursor-pointer"
                            title="Grant OSA approval to send email"
                          >
                            <Lock className="w-3 h-3 text-rose-400" />
                            <span>Approve Send</span>
                          </button>
                        )}
                      </div>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </div>

      {/* Add Lead Modal */}
      {showAddModal && (
        <div className="fixed inset-0 bg-black/70 backdrop-blur-sm z-50 flex items-center justify-center p-4">
          <div className="bg-slate-900 border border-slate-800 rounded-xl max-w-lg w-full p-5 space-y-4 shadow-2xl font-mono">
            <div className="flex items-center justify-between pb-2 border-b border-slate-800">
              <h3 className="text-sm font-semibold text-slate-100 flex items-center gap-2">
                <Plus className="w-4 h-4 text-emerald-400" />
                INTAKE QUALIFIED LEAD RECORD
              </h3>
              <button onClick={() => setShowAddModal(false)} className="text-slate-400 hover:text-slate-200">
                <X className="w-4 h-4" />
              </button>
            </div>

            <form onSubmit={handleAddSubmit} className="space-y-3 text-xs">
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="block text-slate-400 mb-1">Company</label>
                  <input
                    type="text"
                    required
                    value={newCompany}
                    onChange={(e) => setNewCompany(e.target.value)}
                    placeholder="e.g. Apex Health"
                    className="w-full bg-slate-950 border border-slate-800 rounded px-2.5 py-1.5 text-slate-200"
                  />
                </div>
                <div>
                  <label className="block text-slate-400 mb-1">Contact Name</label>
                  <input
                    type="text"
                    required
                    value={newContact}
                    onChange={(e) => setNewContact(e.target.value)}
                    placeholder="e.g. Sarah Connor"
                    className="w-full bg-slate-950 border border-slate-800 rounded px-2.5 py-1.5 text-slate-200"
                  />
                </div>
              </div>

              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="block text-slate-400 mb-1">Email</label>
                  <input
                    type="email"
                    required
                    value={newEmail}
                    onChange={(e) => setNewEmail(e.target.value)}
                    placeholder="sarah@apexhealth.example"
                    className="w-full bg-slate-950 border border-slate-800 rounded px-2.5 py-1.5 text-slate-200"
                  />
                </div>
                <div>
                  <label className="block text-slate-400 mb-1">Industry</label>
                  <input
                    type="text"
                    required
                    value={newIndustry}
                    onChange={(e) => setNewIndustry(e.target.value)}
                    className="w-full bg-slate-950 border border-slate-800 rounded px-2.5 py-1.5 text-slate-200"
                  />
                </div>
              </div>

              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="block text-slate-400 mb-1">Team Size</label>
                  <select
                    value={newTeamSize}
                    onChange={(e) => setNewTeamSize(e.target.value)}
                    className="w-full bg-slate-950 border border-slate-800 rounded px-2.5 py-1.5 text-slate-200"
                  >
                    <option value="1-9">1-9</option>
                    <option value="10-49">10-49</option>
                    <option value="50-199">50-199</option>
                    <option value="200+">200+</option>
                  </select>
                </div>
                <div>
                  <label className="block text-slate-400 mb-1">Urgency</label>
                  <select
                    value={newUrgency}
                    onChange={(e) => setNewUrgency(e.target.value)}
                    className="w-full bg-slate-950 border border-slate-800 rounded px-2.5 py-1.5 text-slate-200"
                  >
                    <option value="immediate">immediate (+30)</option>
                    <option value="high">high (+24)</option>
                    <option value="medium">medium (+15)</option>
                    <option value="low">low (+6)</option>
                  </select>
                </div>
              </div>

              <div>
                <label className="block text-slate-400 mb-1">Observed Workflow Problem</label>
                <textarea
                  rows={2}
                  required
                  value={newProblem}
                  onChange={(e) => setNewProblem(e.target.value)}
                  placeholder="e.g. 5 staff spending 20 hours/week copy-pasting insurance claims"
                  className="w-full bg-slate-950 border border-slate-800 rounded p-2 text-slate-200"
                />
              </div>

              <div>
                <label className="block text-slate-400 mb-1">Current Tools (comma-separated)</label>
                <input
                  type="text"
                  value={newTools}
                  onChange={(e) => setNewTools(e.target.value)}
                  className="w-full bg-slate-950 border border-slate-800 rounded px-2.5 py-1.5 text-slate-200"
                />
              </div>

              <div className="flex justify-end gap-2 pt-2 border-t border-slate-800">
                <button
                  type="button"
                  onClick={() => setShowAddModal(false)}
                  className="px-3 py-1.5 bg-slate-800 hover:bg-slate-700 text-slate-300 rounded cursor-pointer"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  className="px-4 py-1.5 bg-emerald-600 hover:bg-emerald-500 text-white font-semibold rounded cursor-pointer"
                >
                  Save & Score Lead
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* Audit Report Viewer Modal */}
      {showAuditViewer && (
        <div className="fixed inset-0 bg-black/70 backdrop-blur-sm z-50 flex items-center justify-center p-4">
          <div className="bg-slate-900 border border-slate-800 rounded-xl max-w-2xl w-full p-5 space-y-4 shadow-2xl font-mono">
            <div className="flex items-center justify-between pb-2 border-b border-slate-800">
              <h3 className="text-sm font-semibold text-slate-100 flex items-center gap-2">
                <FileText className="w-4 h-4 text-purple-400" />
                AUDIT REPORT: {showAuditViewer.audit_id}
              </h3>
              <button onClick={() => setShowAuditViewer(null)} className="text-slate-400 hover:text-slate-200">
                <X className="w-4 h-4" />
              </button>
            </div>

            <pre className="bg-slate-950 border border-slate-800 rounded-lg p-4 text-xs text-slate-200 max-h-96 overflow-y-auto whitespace-pre-wrap font-mono">
              {showAuditViewer.body}
            </pre>
          </div>
        </div>
      )}

      {/* Draft Email Viewer Modal */}
      {showDraftViewer && (
        <div className="fixed inset-0 bg-black/70 backdrop-blur-sm z-50 flex items-center justify-center p-4">
          <div className="bg-slate-900 border border-slate-800 rounded-xl max-w-xl w-full p-5 space-y-4 shadow-2xl font-mono">
            <div className="flex items-center justify-between pb-2 border-b border-slate-800">
              <h3 className="text-sm font-semibold text-slate-100 flex items-center gap-2">
                <Mail className="w-4 h-4 text-sky-400" />
                OUTREACH DRAFT (LOCAL FILE ONLY)
              </h3>
              <button onClick={() => setShowDraftViewer(null)} className="text-slate-400 hover:text-slate-200">
                <X className="w-4 h-4" />
              </button>
            </div>

            <div className="bg-slate-950 border border-slate-800 rounded-lg p-4 space-y-2 text-xs">
              <div className="border-b border-slate-850 pb-2">
                <span className="text-slate-500">Subject: </span>
                <span className="font-semibold text-slate-200">{showDraftViewer.subject}</span>
              </div>
              <pre className="whitespace-pre-wrap text-slate-300 font-sans text-xs pt-2">
                {showDraftViewer.body}
              </pre>
            </div>
          </div>
        </div>
      )}

      {/* OSA Scoped Approval Modal for Outreach Send */}
      {showApprovalModal && (
        <div className="fixed inset-0 bg-black/70 backdrop-blur-sm z-50 flex items-center justify-center p-4">
          <div className="bg-slate-900 border border-rose-900 rounded-xl max-w-md w-full p-5 space-y-4 shadow-2xl font-mono">
            <div className="flex items-center justify-between pb-2 border-b border-slate-800">
              <h3 className="text-sm font-semibold text-rose-300 flex items-center gap-2">
                <ShieldAlert className="w-4 h-4 text-rose-400" />
                OUTBOUND SEND APPROVAL REQUIRED (RED)
              </h3>
              <button onClick={() => setShowApprovalModal(null)} className="text-slate-400 hover:text-slate-200">
                <X className="w-4 h-4" />
              </button>
            </div>

            <p className="text-xs text-slate-300">
              Per SOUL.md: <em>"Outbound outreach drafts require explicit OSA review before sending."</em>
            </p>

            <form onSubmit={handleApprovalSubmit} className="space-y-3 text-xs">
              <div>
                <label className="block text-slate-400 mb-1">OSA Authorization Reference Token</label>
                <input
                  type="text"
                  required
                  value={approvalToken}
                  onChange={(e) => setApprovalToken(e.target.value)}
                  className="w-full bg-slate-950 border border-slate-800 rounded px-2.5 py-1.5 text-slate-200"
                />
              </div>

              <div className="flex justify-end gap-2 pt-2 border-t border-slate-800">
                <button
                  type="button"
                  onClick={() => setShowApprovalModal(null)}
                  className="px-3 py-1.5 bg-slate-800 hover:bg-slate-700 text-slate-300 rounded cursor-pointer"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  className="px-4 py-1.5 bg-rose-600 hover:bg-rose-500 text-white font-semibold rounded cursor-pointer"
                >
                  Authorize External Send
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
};
