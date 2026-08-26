import React, { useState } from 'react';
import {
  RotateCcw,
  AlertTriangle,
  Flame,
  Shield,
  Layers,
  CheckCircle2,
  Clock,
  Lock,
  RefreshCw,
  Archive,
} from 'lucide-react';
import { Mission, WorkerLease, TaskItem } from '../types';

interface RecoveryViewProps {
  missions: Mission[];
  leases: WorkerLease[];
  tasks: TaskItem[];
  onRollbackCheckpoint: (missionId: string, checkpointHash: string) => void;
  onRevokeLease: (leaseId: string) => void;
  onRetryDeadLetter: (taskId: string) => void;
}

export const RecoveryView: React.FC<RecoveryViewProps> = ({
  missions,
  leases,
  tasks,
  onRollbackCheckpoint,
  onRevokeLease,
  onRetryDeadLetter,
}) => {
  const [selectedMissionId, setSelectedMissionId] = useState<string>('M-2048');
  const [actionMessage, setActionMessage] = useState<string | null>(null);

  const deadLetterTasks = tasks.filter(
    (t) => t.status === 'DEAD_LETTER' || t.status === 'FAILED'
  );

  const checkpoints = [
    {
      hash: 'chk-8f2a1b-src-adapter-ok',
      mission_id: 'M-2048',
      created_at: '2026-08-22T23:15:00Z',
      description: 'Clean frontend adapter build verified by Pinokio',
      actor: 'Michael Angelo',
    },
    {
      hash: 'chk-3d9c4e-pinokio-rules',
      mission_id: 'M-2048',
      created_at: '2026-08-22T22:45:00Z',
      description: 'Understanding Gate & Genesis Contract initialized',
      actor: 'UnderstandingGate',
    },
    {
      hash: 'chk-5b1e7a-boundary-audit',
      mission_id: 'mission-003-continuous-ops',
      created_at: '2026-08-22T21:00:00Z',
      description: 'Preflight boundary audit complete',
      actor: 'Claude Specialist',
    },
  ];

  const handleTriggerRollback = (chkHash: string) => {
    onRollbackCheckpoint(selectedMissionId, chkHash);
    setActionMessage(`ROLLBACK EXECUTED: Mission ${selectedMissionId} state restored to ${chkHash}.`);
    setTimeout(() => setActionMessage(null), 5000);
  };

  return (
    <div className="space-y-6 font-mono">
      {/* Header Banner */}
      <div className="bg-gradient-to-r from-[#030712] via-[#090e24] to-[#030712] border border-rose-500/30 rounded-2xl p-6 shadow-xl">
        <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
          <div className="space-y-1.5">
            <div className="flex items-center gap-2.5">
              <span className="p-2 rounded-xl bg-rose-500/10 text-rose-400 border border-rose-500/30">
                <RotateCcw className="w-5 h-5" />
              </span>
              <h2 className="text-lg font-bold text-rose-100 uppercase tracking-wider">
                RECOVERY, CHECKPOINTS & DEAD-LETTER TRIAGE
              </h2>
            </div>
            <p className="text-xs text-slate-300 max-w-3xl leading-relaxed">
              Mechanizm samo-leczenia Hydry. W razie awarii lub dryfu, stan misji może zostać przywrócony z{' '}
              <strong className="text-amber-300">kryptograficznego checkpointu</strong>, zawieszone leasy mogą zostać unieważnione, a błędne zadania skierowane do triage'u.
            </p>
          </div>

          <div className="flex items-center gap-2 text-xs">
            <span className="px-3 py-1.5 rounded-xl bg-black/60 border border-rose-500/30 text-rose-300 font-bold">
              Checkpoints: <strong className="text-emerald-400">{checkpoints.length}</strong>
            </span>
          </div>
        </div>
      </div>

      {actionMessage && (
        <div className="p-4 rounded-xl bg-amber-950/80 border border-amber-500/50 text-amber-200 text-xs flex items-center justify-between animate-pulse">
          <div className="flex items-center gap-2">
            <CheckCircle2 className="w-4 h-4 text-amber-400" />
            <span>{actionMessage}</span>
          </div>
          <span className="text-[10px] text-amber-400 font-bold">NOTARY RECORDED</span>
        </div>
      )}

      {/* Grid: Checkpoint Rollback (Left) + Stale Leases & Dead Letter (Right) */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
        {/* Left 7 cols: Verified Checkpoint History */}
        <div className="lg:col-span-7 space-y-4">
          <div className="bg-[#05091a] border border-amber-500/20 rounded-2xl p-5 shadow-md space-y-4">
            <div className="flex items-center justify-between border-b border-slate-800/80 pb-3">
              <span className="text-xs font-bold text-amber-300 uppercase tracking-wider flex items-center gap-2">
                <Lock className="w-4 h-4 text-amber-400" />
                <span>Zarejestrowane Checkpointy w Notariuszu</span>
              </span>
              <span className="text-[10px] text-slate-400">Atomic Rollback Available</span>
            </div>

            <div className="space-y-3">
              {checkpoints.map((chk) => (
                <div
                  key={chk.hash}
                  className="bg-black/50 border border-slate-800 rounded-xl p-4 space-y-2 hover:border-amber-500/40 transition"
                >
                  <div className="flex items-center justify-between">
                    <span className="text-xs font-bold text-amber-200">{chk.hash}</span>
                    <span className="text-[10px] text-purple-300">{chk.mission_id}</span>
                  </div>

                  <p className="text-xs text-slate-300">{chk.description}</p>

                  <div className="pt-2 border-t border-slate-800/60 flex items-center justify-between text-[10px] text-slate-400">
                    <span>Autor: <strong className="text-slate-300">{chk.actor}</strong> &bull; {chk.created_at.slice(11, 19)}</span>
                    <button
                      onClick={() => handleTriggerRollback(chk.hash)}
                      className="px-2.5 py-1 bg-amber-950 hover:bg-amber-900 border border-amber-600/40 text-amber-300 rounded-lg transition cursor-pointer font-bold flex items-center gap-1"
                    >
                      <RotateCcw className="w-3 h-3" />
                      <span>Rollback</span>
                    </button>
                  </div>
                </div>
              ))}
            </div>
          </div>
        </div>

        {/* Right 5 cols: Dead Letter & Active Quarantine */}
        <div className="lg:col-span-5 space-y-4">
          <div className="bg-[#05091a] border border-rose-500/20 rounded-2xl p-5 shadow-md space-y-4">
            <div className="flex items-center justify-between border-b border-slate-800/80 pb-3">
              <span className="text-xs font-bold text-rose-300 uppercase tracking-wider flex items-center gap-2">
                <Archive className="w-4 h-4 text-rose-400" />
                <span>Dead-Letter & Failed Tasks ({deadLetterTasks.length})</span>
              </span>
            </div>

            {deadLetterTasks.length === 0 ? (
              <div className="text-center py-8 text-xs text-slate-400">
                <CheckCircle2 className="w-8 h-8 text-emerald-400 mx-auto mb-2 opacity-60" />
                <p>Kolejka Dead-Letter jest czysta.</p>
                <p className="text-[10px] text-slate-500 mt-1">Wszystkie zadania wykonane lub aktywne.</p>
              </div>
            ) : (
              <div className="space-y-2">
                {deadLetterTasks.map((t) => (
                  <div
                    key={t.task_id}
                    className="bg-black/50 border border-rose-800/60 rounded-xl p-3 text-xs space-y-1.5"
                  >
                    <div className="flex items-center justify-between">
                      <span className="font-bold text-rose-200">{t.task_id}</span>
                      <span className="text-[10px] text-rose-400">{t.status}</span>
                    </div>
                    <div className="text-[11px] text-slate-400">{t.last_error || 'Timeout exceeded'}</div>
                    <button
                      onClick={() => onRetryDeadLetter(t.task_id)}
                      className="w-full py-1.5 bg-rose-950 hover:bg-rose-900 border border-rose-700 text-rose-200 text-xs rounded-lg font-bold"
                    >
                      Ponów Próbę (Retry)
                    </button>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
};
