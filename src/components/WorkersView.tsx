import React, { useState } from 'react';
import {
  Hammer,
  Users,
  Shield,
  Layers,
  Clock,
  Activity,
  ArrowRight,
  CheckCircle2,
  AlertTriangle,
  RotateCcw,
  Key,
  Terminal,
  Zap,
  Lock,
} from 'lucide-react';
import { WorkerLease, TaskItem } from '../types';

interface WorkersViewProps {
  leases: WorkerLease[];
  tasks: TaskItem[];
  onHandoffLease: (leaseId: string, newRole: string) => void;
  onRevokeLease: (leaseId: string) => void;
  onNavigate: (tab: any) => void;
}

export const WorkersView: React.FC<WorkersViewProps> = ({
  leases,
  tasks,
  onHandoffLease,
  onRevokeLease,
  onNavigate,
}) => {
  const [selectedLeaseId, setSelectedLeaseId] = useState<string>(
    leases[0]?.lease_id || 'LEASE-MICHAEL-001'
  );

  const selectedLease =
    leases.find((l) => l.lease_id === selectedLeaseId) || leases[0];

  const assignedTask = tasks.find((t) => t.task_id === selectedLease?.task_id);

  return (
    <div className="space-y-6">
      {/* Header Banner */}
      <div className="bg-gradient-to-r from-[#030712] via-[#0b102b] to-[#030712] border border-purple-500/30 rounded-2xl p-6 shadow-xl">
        <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
          <div className="space-y-1.5">
            <div className="flex items-center gap-2.5">
              <span className="p-2 rounded-xl bg-purple-500/10 text-purple-400 border border-purple-500/30">
                <Hammer className="w-5 h-5" />
              </span>
              <h2 className="text-lg font-bold font-mono text-purple-100 uppercase tracking-wider">
                MICHAEL ANGELO & WORK CELLS (MINION WORKERS)
              </h2>
            </div>
            <p className="text-xs font-mono text-slate-300 max-w-3xl leading-relaxed">
              Żaden agent nie posiada całej misji na własność (<strong className="text-amber-300">No Single Worker Owns The Mission</strong>).
              Wykonanie odbywa się w izolowanych <strong className="text-purple-300">Work Cells</strong> pod ograniczonym czasowo{' '}
              <strong className="text-amber-200">Lease</strong> z limitem tokenów i obowiązkowym checkpointem przed przekazaniem (
              <span className="text-emerald-300 font-semibold">Handoff Relay</span>).
            </p>
          </div>

          <div className="flex items-center gap-2 font-mono text-xs">
            <span className="px-3 py-1.5 rounded-xl bg-black/60 border border-purple-500/30 text-purple-300">
              Active Leases: <strong className="text-emerald-400">{leases.length}</strong>
            </span>
          </div>
        </div>
      </div>

      {/* Leases Grid */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
        {/* Left 4 cols: Leases List */}
        <div className="lg:col-span-4 space-y-3">
          <div className="text-xs font-mono font-bold text-purple-400 uppercase tracking-wider px-1 flex items-center justify-between">
            <span>Aktywne Leasy ({leases.length})</span>
            <span className="text-[10px] text-slate-400">Time & Token Capped</span>
          </div>

          <div className="space-y-2.5">
            {leases.map((lease) => {
              const isSelected = lease.lease_id === selectedLeaseId;
              const tokenPercent = Math.min(
                100,
                Math.round((lease.budget_tokens_used / lease.budget_tokens_limit) * 100)
              );

              return (
                <div
                  key={lease.lease_id}
                  onClick={() => setSelectedLeaseId(lease.lease_id)}
                  className={`p-4 rounded-2xl border transition-all cursor-pointer font-mono ${
                    isSelected
                      ? 'bg-[#0a0f2e] border-purple-500/60 shadow-lg shadow-purple-500/10'
                      : 'bg-[#05091a]/80 hover:bg-[#05091a] border-slate-800/80 hover:border-purple-500/30'
                  }`}
                >
                  <div className="flex items-center justify-between">
                    <span className="text-xs font-bold text-purple-200">{lease.worker_name}</span>
                    <span className="text-[10px] px-2 py-0.5 rounded-full font-bold bg-purple-950 text-purple-300 border border-purple-700/50">
                      {lease.role}
                    </span>
                  </div>

                  <div className="text-[11px] text-slate-400 mt-2">
                    Mission: <strong className="text-amber-300">{lease.mission_id}</strong> &bull; Task:{' '}
                    <strong className="text-slate-300">{lease.task_id}</strong>
                  </div>

                  {/* Token Budget Progress */}
                  <div className="mt-3 space-y-1">
                    <div className="flex justify-between text-[10px] text-slate-400">
                      <span>Token Budget</span>
                      <span>{lease.budget_tokens_used.toLocaleString()} / {lease.budget_tokens_limit.toLocaleString()}</span>
                    </div>
                    <div className="w-full bg-slate-900 h-1.5 rounded-full overflow-hidden border border-slate-800">
                      <div
                        className={`h-full ${
                          tokenPercent > 80 ? 'bg-amber-500' : 'bg-purple-500'
                        }`}
                        style={{ width: `${tokenPercent}%` }}
                      />
                    </div>
                  </div>

                  <div className="text-[10px] text-slate-400 mt-3 pt-2 border-t border-slate-800/60 flex items-center justify-between">
                    <span className="flex items-center gap-1 text-emerald-400">
                      <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-ping" />
                      Status: {lease.status}
                    </span>
                    <span className="text-slate-500">Expires: {lease.expires_at.slice(11, 19)}</span>
                  </div>
                </div>
              );
            })}
          </div>
        </div>

        {/* Right 8 cols: Selected Lease & Work Cell Detail */}
        <div className="lg:col-span-8 space-y-6">
          {selectedLease && (
            <div className="bg-[#05091a] border border-purple-500/20 rounded-2xl p-6 shadow-md font-mono space-y-6">
              {/* Lease Title */}
              <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 border-b border-slate-800/80 pb-4">
                <div>
                  <div className="flex items-center gap-2.5">
                    <h3 className="text-base font-bold text-purple-100">{selectedLease.worker_name}</h3>
                    <span className="text-xs px-2.5 py-0.5 rounded-full bg-purple-500/20 text-purple-300 border border-purple-500/40 font-bold">
                      {selectedLease.lease_id}
                    </span>
                  </div>
                  <p className="text-xs text-slate-400 mt-1">
                    Rola: <strong className="text-amber-300">{selectedLease.role}</strong> &bull; Work Cell Sandbox Active
                  </p>
                </div>

                <div className="flex items-center gap-2">
                  <button
                    onClick={() => onHandoffLease(selectedLease.lease_id, 'SPECIALIST')}
                    className="px-3 py-1.5 bg-gradient-to-r from-purple-600 to-purple-700 hover:from-purple-500 text-white text-xs rounded-xl shadow-md transition cursor-pointer font-semibold flex items-center gap-1.5"
                  >
                    <RotateCcw className="w-3.5 h-3.5" />
                    <span>Handoff Relay</span>
                  </button>

                  <button
                    onClick={() => onRevokeLease(selectedLease.lease_id)}
                    className="px-3 py-1.5 bg-rose-950/80 hover:bg-rose-900 border border-rose-600/40 text-rose-300 text-xs rounded-xl transition cursor-pointer font-semibold"
                  >
                    Revoke Lease
                  </button>
                </div>
              </div>

              {/* Checkpoint & Security Invariants */}
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4 text-xs">
                <div className="bg-black/50 border border-slate-800 rounded-xl p-4 space-y-2">
                  <span className="text-amber-400 font-bold flex items-center gap-1.5">
                    <Lock className="w-3.5 h-3.5" /> Checkpoint Hash (No Handoff Without Checkpoint)
                  </span>
                  <div className="p-2.5 rounded bg-black border border-amber-500/30 text-amber-300 text-[11px] break-all">
                    {selectedLease.checkpoint_hash}
                  </div>
                  <p className="text-[10px] text-slate-400">
                    Gwarantuje, że stan pamięci podręcznej i pliki są zrzucane do rejestru przed zmianą workera.
                  </p>
                </div>

                <div className="bg-black/50 border border-slate-800 rounded-xl p-4 space-y-2">
                  <span className="text-purple-400 font-bold flex items-center gap-1.5">
                    <Zap className="w-3.5 h-3.5" /> Granice Uprawnień Work Cella
                  </span>
                  <ul className="space-y-1 text-slate-300 text-[11px]">
                    <li className="flex items-center gap-1.5">
                      <CheckCircle2 className="w-3 h-3 text-emerald-400" />
                      <span>Zezwolone: file.read, file.write (w zakresie misji)</span>
                    </li>
                    <li className="flex items-center gap-1.5">
                      <CheckCircle2 className="w-3 h-3 text-emerald-400" />
                      <span>Zezwolone: build.execute, test.run</span>
                    </li>
                    <li className="flex items-center gap-1.5">
                      <span className="text-rose-400">✕</span>
                      <span>Zabronione: bezpośredni deploy na produkcję</span>
                    </li>
                  </ul>
                </div>
              </div>

              {/* Assigned Task Detail */}
              {assignedTask && (
                <div className="bg-black/40 border border-slate-800 rounded-xl p-4 space-y-3">
                  <div className="flex items-center justify-between">
                    <span className="text-xs font-bold text-slate-200 flex items-center gap-2">
                      <Activity className="w-4 h-4 text-purple-400" />
                      <span>Przypisane Zadanie w Kolejce: {assignedTask.task_id}</span>
                    </span>
                    <span className="px-2 py-0.5 rounded text-[10px] font-bold bg-amber-950 text-amber-300 border border-amber-600/40">
                      {assignedTask.permission}
                    </span>
                  </div>

                  <div className="text-xs text-slate-300">
                    Typ: <strong className="text-amber-300">{assignedTask.type}</strong> &bull; Status:{' '}
                    <strong className="text-emerald-400">{assignedTask.status}</strong>
                  </div>

                  <div className="text-[11px] text-slate-400 bg-black/60 p-2.5 rounded border border-slate-800 font-mono">
                    Payload: {JSON.stringify(assignedTask.payload, null, 2)}
                  </div>
                </div>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  );
};
