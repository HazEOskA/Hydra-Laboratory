import React, { useState } from 'react';
import {
  FileCheck,
  ShieldCheck,
  CheckCircle2,
  AlertTriangle,
  Layers,
  Plus,
  RefreshCw,
  Hash,
  Clock,
  User,
  ArrowRight,
  Shield,
  Lock,
  Sparkles,
} from 'lucide-react';
import { LedgerEvent, Mission, NotaryLedgerEntry } from '../types';
import { LedgerEngine } from '../engine/ledgerEngine';
import { INITIAL_NOTARY_ENTRIES } from '../engine/initialState';

interface LedgerViewProps {
  ledgerEngine: LedgerEngine;
  missions: Mission[];
  events: LedgerEvent[];
  notaryEntries?: NotaryLedgerEntry[];
  onMissionCreate: (missionId: string, title: string) => void;
  onRefresh: () => void;
  onSealMission?: (missionId: string) => void;
}

export const LedgerView: React.FC<LedgerViewProps> = ({
  ledgerEngine,
  missions,
  events,
  notaryEntries = INITIAL_NOTARY_ENTRIES,
  onMissionCreate,
  onRefresh,
  onSealMission,
}) => {
  const [verificationResult, setVerificationResult] = useState<{
    ok: boolean;
    detail: string;
    totalEvents: number;
    brokenSeq?: number;
  }>(() => ledgerEngine.verifyChain());

  const [selectedMission, setSelectedMission] = useState<string>('ALL');
  const [showCreateMissionModal, setShowCreateMissionModal] = useState(false);
  const [newMissionId, setNewMissionId] = useState(`M-${Date.now().toString().slice(-4)}`);
  const [newMissionTitle, setNewMissionTitle] = useState('');
  const [sealStatus, setSealStatus] = useState<string | null>(null);

  const handleVerify = () => {
    const res = ledgerEngine.verifyChain();
    setVerificationResult(res);
  };

  const handleSeal = (mId: string) => {
    if (onSealMission) onSealMission(mId);
    setSealStatus(`MISSION ${mId} SEALED: Cryptographic APR Proof receipt recorded into City Notary.`);
    setTimeout(() => setSealStatus(null), 5000);
  };

  const handleCreateSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    onMissionCreate(newMissionId, newMissionTitle || newMissionId);
    setShowCreateMissionModal(false);
    setNewMissionId(`M-${Date.now().toString().slice(-4)}`);
    setNewMissionTitle('');
    handleVerify();
  };

  const filteredEvents = events.filter((e) => {
    if (selectedMission === 'ALL') return true;
    return e.mission_id === selectedMission;
  });

  return (
    <div className="space-y-6 font-mono">
      {/* Top Header Banner */}
      <div className="bg-gradient-to-r from-[#030712] via-[#090e24] to-[#030712] border border-amber-500/30 rounded-2xl p-6 shadow-xl">
        <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
          <div className="space-y-1.5">
            <div className="flex items-center gap-2.5">
              <span className="p-2 rounded-xl bg-amber-500/10 text-amber-400 border border-amber-500/30">
                <FileCheck className="w-5 h-5" />
              </span>
              <h2 className="text-lg font-bold text-amber-100 uppercase tracking-wider">
                CITY NOTARY & SHA-256 EVIDENCE LEDGER (APR PROOFS)
              </h2>
            </div>
            <p className="text-xs text-slate-300 max-w-3xl leading-relaxed">
              Zasada: <strong className="text-amber-300">NO CLAIM WITHOUT EVIDENCE</strong> oraz{' '}
              <strong className="text-purple-300">NO MISSION CLOSE WITHOUT NOTARY</strong>.
              Dziennik stanu jest niezmienny (append-only), powiązany kryptograficznym łańcuchem SHA-256 i pieczętowany certyfikatem APR.
            </p>
          </div>

          <div className="flex items-center gap-2">
            <button
              onClick={handleVerify}
              className="flex items-center gap-1.5 px-3.5 py-2 bg-slate-900 hover:bg-slate-800 text-amber-200 text-xs font-bold rounded-xl border border-amber-500/30 transition cursor-pointer"
            >
              <RefreshCw className="w-3.5 h-3.5 text-amber-400" />
              <span>Przelicz Łańcuch Hash</span>
            </button>
            <button
              onClick={() => setShowCreateMissionModal(true)}
              className="flex items-center gap-1.5 px-3.5 py-2 bg-gradient-to-r from-amber-500 to-amber-600 hover:from-amber-400 text-black text-xs font-bold rounded-xl shadow-md transition cursor-pointer"
            >
              <Plus className="w-3.5 h-3.5" />
              <span>Otwórz Wpis Misji</span>
            </button>
          </div>
        </div>
      </div>

      {sealStatus && (
        <div className="p-4 rounded-xl bg-emerald-950/80 border border-emerald-500/50 text-emerald-200 text-xs flex items-center justify-between">
          <div className="flex items-center gap-2">
            <CheckCircle2 className="w-4 h-4 text-emerald-400" />
            <span>{sealStatus}</span>
          </div>
          <span className="text-[10px] text-emerald-400 font-bold">SEALED & IMMUTABLE</span>
        </div>
      )}

      {/* Chain Verification Status HUD */}
      <div
        className={`border rounded-2xl p-5 shadow-md flex items-center justify-between gap-4 ${
          verificationResult.ok
            ? 'bg-emerald-950/30 border-emerald-500/40 text-emerald-300'
            : 'bg-rose-950/30 border-rose-500/40 text-rose-300'
        }`}
      >
        <div className="flex items-center gap-3">
          {verificationResult.ok ? (
            <CheckCircle2 className="w-6 h-6 text-emerald-400 shrink-0" />
          ) : (
            <AlertTriangle className="w-6 h-6 text-rose-400 shrink-0" />
          )}
          <div>
            <div className="font-bold text-sm">
              {verificationResult.ok
                ? 'SHA-256 HASH-CHAIN INTEGRITY VERIFIED (TAMPER-PROOF)'
                : 'INTEGRITY BREACH DETECTED'}
            </div>
            <div className="text-xs text-slate-300 mt-0.5">{verificationResult.detail}</div>
          </div>
        </div>

        <div className="text-right">
          <div className="text-xs text-slate-400">Total Events</div>
          <div className="text-xl font-bold text-amber-200">{verificationResult.totalEvents}</div>
        </div>
      </div>

      {/* City Notary Journal Entries */}
      <div className="bg-[#05091a] border border-amber-500/20 rounded-2xl p-6 shadow-md space-y-4">
        <div className="flex items-center justify-between border-b border-slate-800/80 pb-3">
          <div className="flex items-center gap-2">
            <Shield className="w-4 h-4 text-amber-400" />
            <span className="text-xs font-bold text-amber-200 uppercase tracking-wider">
              Oficjalny Dziennik Notariusza (Notary Journal)
            </span>
          </div>
          <span className="text-[10px] text-slate-400">APR Sealed Receipts</span>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          {notaryEntries.map((entry) => (
            <div
              key={entry.entry_id}
              className="bg-black/50 border border-slate-800 rounded-xl p-4 space-y-2 hover:border-amber-500/40 transition text-xs"
            >
              <div className="flex items-center justify-between">
                <span className="font-bold text-amber-200">{entry.mission_id}</span>
                <span
                  className={`text-[10px] px-2 py-0.2 rounded-full font-bold border ${
                    entry.status === 'SEALED'
                      ? 'bg-emerald-950 text-emerald-300 border-emerald-600/40'
                      : 'bg-amber-950 text-amber-300 border-amber-600/40'
                  }`}
                >
                  {entry.status}
                </span>
              </div>

              <div className="text-[11px] text-slate-400">
                Entry ID: <strong className="text-purple-300">{entry.entry_id}</strong>
              </div>

              <div className="text-[10px] text-slate-500 truncate">
                Genesis: <span className="font-mono text-slate-400">{entry.genesis_hash.slice(0, 16)}...</span>
              </div>

              {entry.apr_proof_receipt && (
                <div className="p-2 rounded bg-black/60 border border-emerald-900/60 text-[10px] text-emerald-300 flex items-center justify-between">
                  <span>APR: {entry.apr_proof_receipt}</span>
                  <CheckCircle2 className="w-3 h-3 text-emerald-400" />
                </div>
              )}

              {entry.status === 'OPEN' && (
                <button
                  onClick={() => handleSeal(entry.mission_id)}
                  className="w-full py-1.5 bg-gradient-to-r from-amber-500 to-amber-600 hover:from-amber-400 text-black text-xs font-bold rounded-lg transition cursor-pointer mt-2"
                >
                  Zapieczętuj Misję (APR Seal)
                </button>
              )}
            </div>
          ))}
        </div>
      </div>

      {/* Filter & Event Timeline */}
      <div className="bg-[#05091a] border border-slate-800 rounded-2xl p-6 shadow-md space-y-4">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 border-b border-slate-800/80 pb-3">
          <div className="flex items-center gap-2">
            <Hash className="w-4 h-4 text-purple-400" />
            <span className="text-xs font-bold text-slate-200 uppercase tracking-wider">
              Kryptograficzna Oś Zdarzeń ({filteredEvents.length})
            </span>
          </div>

          <div className="flex items-center gap-2">
            <span className="text-xs text-slate-400">Filtruj Misję:</span>
            <select
              value={selectedMission}
              onChange={(e) => setSelectedMission(e.target.value)}
              className="bg-black border border-slate-700 rounded-xl px-3 py-1.5 text-xs text-amber-200 focus:outline-none focus:border-amber-400"
            >
              <option value="ALL">Wszystkie misje</option>
              {missions.map((m) => (
                <option key={m.mission_id} value={m.mission_id}>
                  {m.mission_id} ({m.title.slice(0, 25)}...)
                </option>
              ))}
            </select>
          </div>
        </div>

        {/* Events Table / Feed */}
        <div className="space-y-3">
          {filteredEvents.map((ev) => (
            <div
              key={ev.seq}
              className="bg-black/50 border border-slate-800/80 rounded-xl p-4 space-y-2 text-xs hover:border-amber-500/30 transition"
            >
              <div className="flex items-center justify-between flex-wrap gap-2">
                <div className="flex items-center gap-2">
                  <span className="px-2 py-0.5 rounded bg-amber-500/20 text-amber-300 font-bold border border-amber-500/40">
                    #{ev.seq}
                  </span>
                  <span className="font-bold text-slate-200">{ev.mission_id}</span>
                  <span className="text-slate-500">&bull;</span>
                  <span className="text-purple-300">{ev.task_id}</span>
                </div>

                <div className="flex items-center gap-2 text-[10px] text-slate-400">
                  <span>Aktor: <strong className="text-amber-300">{ev.actor}</strong></span>
                  <span>&bull;</span>
                  <span>{ev.timestamp}</span>
                </div>
              </div>

              <div className="flex items-center gap-2 text-slate-300">
                <span className="px-2 py-0.2 rounded bg-slate-900 text-slate-400 font-semibold">{ev.from_state || 'START'}</span>
                <span>&rarr;</span>
                <span className="px-2 py-0.2 rounded bg-emerald-950 text-emerald-300 border border-emerald-800 font-bold">
                  {ev.to_state}
                </span>
                <span className="text-slate-400 ml-2">&bull; {ev.reason}</span>
              </div>

              {ev.evidence_refs?.length > 0 && (
                <div className="text-[10px] text-slate-400 flex items-center gap-1.5 flex-wrap">
                  <span className="text-emerald-400">Dowody:</span>
                  {ev.evidence_refs.map((r, i) => (
                    <code key={i} className="px-1.5 py-0.2 bg-black rounded border border-slate-800 text-amber-200">
                      {r}
                    </code>
                  ))}
                </div>
              )}

              <div className="text-[9px] text-slate-600 font-mono flex items-center justify-between pt-1 border-t border-slate-800/40">
                <span>Prev: {ev.previous_event_hash.slice(0, 16)}...</span>
                <span>Hash: {ev.event_hash.slice(0, 16)}...</span>
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* New Mission Modal */}
      {showCreateMissionModal && (
        <div className="fixed inset-0 bg-black/80 backdrop-blur-sm z-50 flex items-center justify-center p-4">
          <div className="bg-[#05091a] border border-amber-500/40 rounded-2xl p-6 max-w-md w-full space-y-4 shadow-2xl">
            <h3 className="text-sm font-bold text-amber-200 uppercase tracking-wider">
              Otwórz Nowy Wpis Misji w Notariuszu
            </h3>
            <form onSubmit={handleCreateSubmit} className="space-y-3 text-xs">
              <div>
                <label className="block text-slate-300 mb-1">Mission ID:</label>
                <input
                  type="text"
                  value={newMissionId}
                  onChange={(e) => setNewMissionId(e.target.value)}
                  className="w-full bg-black border border-slate-700 rounded-xl px-3 py-2 text-amber-100 focus:outline-none focus:border-amber-400 font-mono"
                  required
                />
              </div>

              <div>
                <label className="block text-slate-300 mb-1">Tytuł Misji:</label>
                <input
                  type="text"
                  value={newMissionTitle}
                  onChange={(e) => setNewMissionTitle(e.target.value)}
                  placeholder="np. Wdrożenie nowego modułu integracji"
                  className="w-full bg-black border border-slate-700 rounded-xl px-3 py-2 text-amber-100 focus:outline-none focus:border-amber-400 font-mono"
                  required
                />
              </div>

              <div className="flex justify-end gap-2 pt-3">
                <button
                  type="button"
                  onClick={() => setShowCreateMissionModal(false)}
                  className="px-3 py-1.5 bg-slate-900 text-slate-300 rounded-xl hover:bg-slate-800"
                >
                  Anuluj
                </button>
                <button
                  type="submit"
                  className="px-4 py-1.5 bg-gradient-to-r from-amber-500 to-amber-600 text-black font-bold rounded-xl hover:from-amber-400"
                >
                  Utwórz & Zainicjuj w Notariuszu
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
};
