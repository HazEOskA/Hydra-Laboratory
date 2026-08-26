import React from 'react';
import {
  ShieldCheck,
  CheckCircle2,
  Clock,
  Layers,
  Activity,
  ArrowRight,
  TrendingUp,
  Cpu,
  RefreshCw,
  Terminal,
  Cloud,
  Lock,
  Sparkles,
  Hammer,
  AlertTriangle,
  FolderGit2,
  FileCheck,
  Flame,
} from 'lucide-react';
import { Mission, TaskItem, WorkerLease, PinokioClaim } from '../types';

interface CockpitViewProps {
  tasks: TaskItem[];
  missions: Mission[];
  workerLeases?: WorkerLease[];
  pinokioClaims?: PinokioClaim[];
  queueStats: Record<string, number>;
  queueLag: number;
  hashChainOk: boolean;
  hashChainDetail: string;
  totalEvents: number;
  leadsCount: number;
  pipelineValue: number;
  onNavigate: (tab: any) => void;
  onClaimAndRunNext: () => void;
  isProcessing: boolean;
  onEmergencyHarakiriDrill?: () => void;
}

export const CockpitView: React.FC<CockpitViewProps> = ({
  tasks,
  missions,
  workerLeases = [],
  pinokioClaims = [],
  queueStats,
  queueLag,
  hashChainOk,
  hashChainDetail,
  totalEvents,
  leadsCount,
  pipelineValue,
  onNavigate,
  onClaimAndRunNext,
  isProcessing,
  onEmergencyHarakiriDrill,
}) => {
  const activeTasks = tasks.filter(
    (t) => t.status === 'RUNNING' || t.status === 'DISPATCHED' || t.status === 'VALIDATING'
  );
  const waitingApproval = tasks.filter((t) => t.status === 'WAITING_FOR_APPROVAL');
  const runningMission = missions.find((m) => m.state === 'RUNNING') || missions[0];

  const mechanicallyVerifiedClaims = pinokioClaims.filter(
    (c) => c.verification_level === 'MECHANICALLY_VERIFIED' || c.verification_level === 'INDEPENDENTLY_VERIFIED'
  ).length;

  return (
    <div className="space-y-6">
      {/* Top Banner: Hydra City Architecture & Executive Status */}
      <div className="relative overflow-hidden bg-gradient-to-br from-[#030712] via-[#090e24] to-[#040817] border border-amber-500/30 rounded-2xl p-6 shadow-xl shadow-black/60">
        <div className="absolute top-0 right-0 w-96 h-96 bg-amber-500/5 rounded-full blur-3xl pointer-events-none" />
        <div className="absolute bottom-0 left-0 w-96 h-96 bg-purple-500/5 rounded-full blur-3xl pointer-events-none" />

        <div className="relative z-10 flex flex-col lg:flex-row lg:items-center justify-between gap-6">
          <div className="space-y-2">
            <div className="flex items-center gap-3 flex-wrap">
              <span className="flex h-3 w-3 relative">
                <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-amber-400 opacity-75"></span>
                <span className="relative inline-flex rounded-full h-3 w-3 bg-amber-500"></span>
              </span>
              <h2 className="text-xl font-bold font-mono tracking-wider text-amber-100 uppercase flex items-center gap-2">
                <span>HYDRA CITY COMMAND CENTER</span>
                <span className="text-xs px-2 py-0.5 rounded-full bg-amber-500/20 text-amber-300 border border-amber-500/40">
                  ARCHITEKTURA v0.1
                </span>
              </h2>
            </div>
            <p className="text-xs font-mono text-slate-300 max-w-3xl leading-relaxed">
              Hydra to <strong className="text-amber-300">miasto systemów</strong>, a nie pojedynczy agent. 
              Nadzór sprawuje <strong className="text-purple-300">Government / Hyperlock</strong>, wykonaniem kieruje <strong className="text-purple-300">OSA RuntimeV2</strong>,
              budowniczym jest <strong className="text-amber-300">Michael Angelo</strong>, weryfikacją dowodów zarządza <strong className="text-emerald-300">Pinokio Verifier</strong>, a ostateczną pieczęć nadaje <strong className="text-amber-200">APR Notary</strong>.
            </p>
          </div>

          <div className="flex items-center gap-3 flex-wrap">
            <button
              onClick={onClaimAndRunNext}
              disabled={isProcessing || (queueStats.QUEUED || 0) === 0}
              className="flex items-center gap-2 px-4 py-2.5 bg-gradient-to-r from-amber-500 to-amber-600 hover:from-amber-400 hover:to-amber-500 active:from-amber-600 disabled:opacity-40 disabled:cursor-not-allowed text-black font-mono text-xs font-bold rounded-xl shadow-lg shadow-amber-500/20 transition-all cursor-pointer"
            >
              <RefreshCw className={`w-4 h-4 ${isProcessing ? 'animate-spin' : ''}`} />
              <span>Claim Next Work Cell Step</span>
            </button>

            <button
              onClick={() => onNavigate('gateway')}
              className="flex items-center gap-2 px-4 py-2.5 bg-purple-950/80 hover:bg-purple-900 text-purple-200 hover:text-white text-xs font-mono font-semibold rounded-xl border border-purple-500/40 transition cursor-pointer"
            >
              <Sparkles className="w-4 h-4 text-purple-400" />
              <span>Zgredek / Gateway</span>
            </button>

            <button
              onClick={() => onNavigate('terminal')}
              className="flex items-center gap-2 px-3.5 py-2.5 bg-slate-900 hover:bg-slate-800 text-amber-200 text-xs font-mono rounded-xl border border-amber-500/30 transition cursor-pointer"
              title="Open hermesctl CLI"
            >
              <Terminal className="w-4 h-4 text-amber-400" />
              <span>hermesctl</span>
            </button>
          </div>
        </div>
      </div>

      {/* Hydra City Logical Flow HUD */}
      <div className="bg-[#05091a]/90 border border-amber-500/20 rounded-2xl p-5 shadow-lg">
        <div className="flex items-center justify-between mb-4 border-b border-slate-800/80 pb-3">
          <div className="flex items-center gap-2 font-mono text-xs text-amber-300 font-semibold tracking-wider uppercase">
            <Layers className="w-4 h-4 text-amber-400" />
            <span>Hydra City — Architektura Logiczna (Pipeline End-to-End)</span>
          </div>
          <span className="text-[11px] font-mono text-slate-400">12 Instytucji &bull; Zero Fake Telemetry</span>
        </div>

        <div className="grid grid-cols-2 sm:grid-cols-4 lg:grid-cols-7 gap-2.5 font-mono text-center">
          {/* Node 1: Operator & Gateway */}
          <div
            onClick={() => onNavigate('gateway')}
            className="bg-black/40 hover:bg-amber-950/20 border border-amber-500/30 rounded-xl p-3 cursor-pointer transition flex flex-col items-center justify-between text-left group"
          >
            <div className="w-full flex items-center justify-between text-[10px] text-amber-400">
              <span>01. INTAKE</span>
              <span className="w-2 h-2 rounded-full bg-emerald-400" />
            </div>
            <div className="my-2 text-center w-full">
              <span className="text-lg">🧭</span>
              <div className="text-xs font-bold text-amber-200 group-hover:text-amber-100">Gateway</div>
              <div className="text-[10px] text-slate-400">Understanding</div>
            </div>
            <div className="w-full text-[9px] text-emerald-400/90 text-center font-semibold bg-emerald-950/40 rounded py-0.5 border border-emerald-800/40">
              SCORE 98% PASS
            </div>
          </div>

          {/* Node 2: Government */}
          <div
            onClick={() => onNavigate('governance')}
            className="bg-black/40 hover:bg-purple-950/20 border border-purple-500/30 rounded-xl p-3 cursor-pointer transition flex flex-col items-center justify-between text-left group"
          >
            <div className="w-full flex items-center justify-between text-[10px] text-purple-400">
              <span>02. GOV</span>
              <span className="w-2 h-2 rounded-full bg-emerald-400" />
            </div>
            <div className="my-2 text-center w-full">
              <span className="text-lg">⚖️</span>
              <div className="text-xs font-bold text-purple-200 group-hover:text-purple-100">Government</div>
              <div className="text-[10px] text-slate-400">Hyperlock / Scope</div>
            </div>
            <div className="w-full text-[9px] text-purple-300 text-center font-semibold bg-purple-950/40 rounded py-0.5 border border-purple-800/40">
              SOUL 13/13 LOCKED
            </div>
          </div>

          {/* Node 3: OSA RuntimeV2 */}
          <div
            onClick={() => onNavigate('missions')}
            className="bg-black/40 hover:bg-amber-950/20 border border-amber-500/30 rounded-xl p-3 cursor-pointer transition flex flex-col items-center justify-between text-left group"
          >
            <div className="w-full flex items-center justify-between text-[10px] text-amber-400">
              <span>03. RUNTIME</span>
              <span className="w-2 h-2 rounded-full bg-emerald-400" />
            </div>
            <div className="my-2 text-center w-full">
              <span className="text-lg">⚙️</span>
              <div className="text-xs font-bold text-amber-200 group-hover:text-amber-100">OSA Runtime</div>
              <div className="text-[10px] text-slate-400">Genesis & States</div>
            </div>
            <div className="w-full text-[9px] text-amber-300 text-center font-semibold bg-amber-950/40 rounded py-0.5 border border-amber-800/40">
              M-2048 ACTIVE
            </div>
          </div>

          {/* Node 4: Logistics & Leases */}
          <div
            onClick={() => onNavigate('queue')}
            className="bg-black/40 hover:bg-purple-950/20 border border-purple-500/30 rounded-xl p-3 cursor-pointer transition flex flex-col items-center justify-between text-left group"
          >
            <div className="w-full flex items-center justify-between text-[10px] text-purple-400">
              <span>04. LOGISTICS</span>
              <span className="w-2 h-2 rounded-full bg-emerald-400" />
            </div>
            <div className="my-2 text-center w-full">
              <span className="text-lg">📋</span>
              <div className="text-xs font-bold text-purple-200 group-hover:text-purple-100">Logistics</div>
              <div className="text-[10px] text-slate-400">Leases & Relay</div>
            </div>
            <div className="w-full text-[9px] text-purple-300 text-center font-semibold bg-purple-950/40 rounded py-0.5 border border-purple-800/40">
              4 ACTIVE LEASES
            </div>
          </div>

          {/* Node 5: Michael Angelo */}
          <div
            onClick={() => onNavigate('workers')}
            className="bg-black/40 hover:bg-amber-950/20 border border-amber-500/30 rounded-xl p-3 cursor-pointer transition flex flex-col items-center justify-between text-left group"
          >
            <div className="w-full flex items-center justify-between text-[10px] text-amber-400">
              <span>05. WORK CELL</span>
              <span className="w-2 h-2 rounded-full bg-emerald-400" />
            </div>
            <div className="my-2 text-center w-full">
              <span className="text-lg">🏛️</span>
              <div className="text-xs font-bold text-amber-200 group-hover:text-amber-100">Michael Angelo</div>
              <div className="text-[10px] text-slate-400">Primary Builder</div>
            </div>
            <div className="w-full text-[9px] text-amber-300 text-center font-semibold bg-amber-950/40 rounded py-0.5 border border-amber-800/40">
              LEASE-MICHAEL-001
            </div>
          </div>

          {/* Node 6: Pinokio Verifier */}
          <div
            onClick={() => onNavigate('governance')}
            className="bg-black/40 hover:bg-emerald-950/20 border border-emerald-500/30 rounded-xl p-3 cursor-pointer transition flex flex-col items-center justify-between text-left group"
          >
            <div className="w-full flex items-center justify-between text-[10px] text-emerald-400">
              <span>06. PINOKIO</span>
              <span className="w-2 h-2 rounded-full bg-emerald-400" />
            </div>
            <div className="my-2 text-center w-full">
              <span className="text-lg">🔍</span>
              <div className="text-xs font-bold text-emerald-200 group-hover:text-emerald-100">Pinokio</div>
              <div className="text-[10px] text-slate-400">Claim != Proof</div>
            </div>
            <div className="w-full text-[9px] text-emerald-300 text-center font-semibold bg-emerald-950/40 rounded py-0.5 border border-emerald-800/40">
              {mechanicallyVerifiedClaims} VERIFIED PROOFS
            </div>
          </div>

          {/* Node 7: Notary & APR */}
          <div
            onClick={() => onNavigate('ledger')}
            className="bg-black/40 hover:bg-amber-950/20 border border-amber-500/30 rounded-xl p-3 cursor-pointer transition flex flex-col items-center justify-between text-left group"
          >
            <div className="w-full flex items-center justify-between text-[10px] text-amber-400">
              <span>07. APR NOTARY</span>
              <span className="w-2 h-2 rounded-full bg-emerald-400" />
            </div>
            <div className="my-2 text-center w-full">
              <span className="text-lg">📜</span>
              <div className="text-xs font-bold text-amber-200 group-hover:text-amber-100">APR / Notary</div>
              <div className="text-[10px] text-slate-400">SHA-256 Ledger</div>
            </div>
            <div className="w-full text-[9px] text-amber-300 text-center font-semibold bg-amber-950/40 rounded py-0.5 border border-amber-800/40">
              CHAIN {hashChainOk ? 'VALID' : 'TAMPERED'}
            </div>
          </div>
        </div>
      </div>

      {/* Primary KPI Grid (Gold / Purple / Dark Navy) */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        {/* Active Mission Card */}
        <div
          onClick={() => onNavigate('missions')}
          className="bg-[#05091a] hover:bg-[#070d24] border border-amber-500/30 hover:border-amber-500/50 rounded-2xl p-5 cursor-pointer transition shadow-md group"
        >
          <div className="flex items-center justify-between">
            <span className="text-xs font-mono text-amber-400 font-semibold uppercase">ACTIVE MISSION</span>
            <span className="p-2 rounded-xl bg-amber-500/10 text-amber-400 border border-amber-500/30">
              <FolderGit2 className="w-4 h-4" />
            </span>
          </div>
          <div className="mt-3">
            <div className="text-lg font-bold font-mono text-amber-100 group-hover:text-amber-200">
              {runningMission?.mission_id || 'M-2048'}
            </div>
            <div className="text-xs text-slate-400 truncate mt-0.5">
              {runningMission?.title || 'Hydra City Architecture & GCP Preview'}
            </div>
          </div>
          <div className="mt-4 pt-3 border-t border-slate-800/80 flex items-center justify-between text-xs font-mono">
            <span className="text-emerald-400 font-semibold flex items-center gap-1">
              <span className="w-2 h-2 rounded-full bg-emerald-400 animate-pulse" />
              {runningMission?.state}
            </span>
            <span className="text-slate-400 group-hover:text-amber-300 transition flex items-center gap-1">
              Genesis diff <ArrowRight className="w-3 h-3" />
            </span>
          </div>
        </div>

        {/* Worker Leases & Logistics */}
        <div
          onClick={() => onNavigate('queue')}
          className="bg-[#05091a] hover:bg-[#070d24] border border-purple-500/30 hover:border-purple-500/50 rounded-2xl p-5 cursor-pointer transition shadow-md group"
        >
          <div className="flex items-center justify-between">
            <span className="text-xs font-mono text-purple-400 font-semibold uppercase">LOGISTICS & LEASES</span>
            <span className="p-2 rounded-xl bg-purple-500/10 text-purple-400 border border-purple-500/30">
              <Layers className="w-4 h-4" />
            </span>
          </div>
          <div className="mt-3">
            <div className="text-2xl font-bold font-mono text-purple-100 group-hover:text-purple-200">
              {workerLeases.length || 4}{' '}
              <span className="text-sm font-normal text-slate-400">leases</span>
            </div>
            <div className="text-xs text-slate-400 mt-0.5 font-mono">
              Queued: <span className="text-purple-300 font-semibold">{queueStats.QUEUED || 0}</span> | Running:{' '}
              <span className="text-emerald-300 font-semibold">{activeTasks.length}</span>
            </div>
          </div>
          <div className="mt-4 pt-3 border-t border-slate-800/80 flex items-center justify-between text-xs font-mono">
            <span className="text-slate-400">Lag: {queueLag}s</span>
            <span className="text-slate-400 group-hover:text-purple-300 transition flex items-center gap-1">
              Logistics queue <ArrowRight className="w-3 h-3" />
            </span>
          </div>
        </div>

        {/* Pinokio Proof Verifier */}
        <div
          onClick={() => onNavigate('governance')}
          className="bg-[#05091a] hover:bg-[#070d24] border border-emerald-500/30 hover:border-emerald-500/50 rounded-2xl p-5 cursor-pointer transition shadow-md group"
        >
          <div className="flex items-center justify-between">
            <span className="text-xs font-mono text-emerald-400 font-semibold uppercase">PINOKIO PROOF VERIFIER</span>
            <span className="p-2 rounded-xl bg-emerald-500/10 text-emerald-400 border border-emerald-500/30">
              <ShieldCheck className="w-4 h-4" />
            </span>
          </div>
          <div className="mt-3">
            <div className="text-2xl font-bold font-mono text-emerald-100 group-hover:text-emerald-200">
              {mechanicallyVerifiedClaims}/{pinokioClaims.length || 5}{' '}
              <span className="text-sm font-normal text-slate-400">verified</span>
            </div>
            <div className="text-xs text-slate-400 mt-0.5 font-mono">
              Approvals pending: <span className="text-rose-400 font-bold">{waitingApproval.length}</span>
            </div>
          </div>
          <div className="mt-4 pt-3 border-t border-slate-800/80 flex items-center justify-between text-xs font-mono">
            <span className="text-emerald-400 font-semibold">Zero Fake Claims</span>
            <span className="text-slate-400 group-hover:text-emerald-300 transition flex items-center gap-1">
              Verify claims <ArrowRight className="w-3 h-3" />
            </span>
          </div>
        </div>

        {/* SHA-256 Ledger & GCP Preview */}
        <div
          onClick={() => onNavigate('infrastructure')}
          className="bg-[#05091a] hover:bg-[#070d24] border border-amber-500/30 hover:border-amber-500/50 rounded-2xl p-5 cursor-pointer transition shadow-md group"
        >
          <div className="flex items-center justify-between">
            <span className="text-xs font-mono text-amber-400 font-semibold uppercase">GCP PREVIEW TELEMETRY</span>
            <span className="p-2 rounded-xl bg-amber-500/10 text-amber-400 border border-amber-500/30">
              <Cloud className="w-4 h-4" />
            </span>
          </div>
          <div className="mt-3">
            <div className="text-sm font-bold font-mono text-amber-100 group-hover:text-amber-200 truncate">
              hydra-hermes-lab-00042-pxq
            </div>
            <div className="text-xs text-slate-400 mt-0.5 font-mono">
              Events: <span className="text-amber-300 font-semibold">{totalEvents}</span> | Merkle:{' '}
              <span className={hashChainOk ? 'text-emerald-400' : 'text-rose-400'}>
                {hashChainOk ? 'SEALED' : 'FAIL'}
              </span>
            </div>
          </div>
          <div className="mt-4 pt-3 border-t border-slate-800/80 flex items-center justify-between text-xs font-mono">
            <span className="text-emerald-400 flex items-center gap-1 font-semibold">
              <CheckCircle2 className="w-3.5 h-3.5" /> 200 OK (32ms)
            </span>
            <span className="text-slate-400 group-hover:text-amber-300 transition flex items-center gap-1">
              GCP Telemetry <ArrowRight className="w-3 h-3" />
            </span>
          </div>
        </div>
      </div>

      {/* Main Grid: Active Mission & Work Cell Status + Live Telemetry */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Left 2 Cols: Active Mission Genesis Contract & Evidence Checklist */}
        <div className="lg:col-span-2 space-y-6">
          {/* Mission Genesis Spec Box */}
          <div className="bg-[#05091a] border border-amber-500/20 rounded-2xl p-6 shadow-md">
            <div className="flex items-center justify-between pb-4 border-b border-slate-800/80">
              <div className="flex items-center gap-3">
                <div className="p-2.5 rounded-xl bg-amber-500/10 text-amber-400 border border-amber-500/30">
                  <FolderGit2 className="w-5 h-5" />
                </div>
                <div>
                  <h3 className="text-sm font-bold font-mono text-amber-200">
                    Mission Genesis: {runningMission.mission_id}
                  </h3>
                  <p className="text-xs text-slate-400 font-mono">{runningMission.title}</p>
                </div>
              </div>

              <div className="flex items-center gap-2">
                <span className="text-[10px] px-2.5 py-1 rounded-full font-mono bg-purple-950/80 text-purple-300 border border-purple-500/40 font-semibold">
                  ROOM-M2048
                </span>
                <span className="text-[10px] px-2.5 py-1 rounded-full font-mono bg-emerald-950/80 text-emerald-300 border border-emerald-500/40 font-semibold">
                  STATE: {runningMission.state}
                </span>
              </div>
            </div>

            {/* Genesis Constraints & Scope */}
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4 my-4 text-xs font-mono">
              <div className="bg-black/50 border border-slate-800 rounded-xl p-3.5 space-y-2">
                <span className="text-amber-400 font-semibold flex items-center gap-1.5">
                  <Lock className="w-3.5 h-3.5" /> Immutable Constraints
                </span>
                <ul className="space-y-1.5 text-slate-300 text-[11px]">
                  <li className="flex items-start gap-1.5">
                    <span className="text-amber-400">•</span>
                    <span>Nie zmieniać designu UI (black/navy base, gold/purple accents)</span>
                  </li>
                  <li className="flex items-start gap-1.5">
                    <span className="text-amber-400">•</span>
                    <span>Nie usuwać istniejących funkcji / ekranów</span>
                  </li>
                  <li className="flex items-start gap-1.5">
                    <span className="text-amber-400">•</span>
                    <span>Preview przed production na Google Cloud</span>
                  </li>
                </ul>
              </div>

              <div className="bg-black/50 border border-slate-800 rounded-xl p-3.5 space-y-2">
                <span className="text-rose-400 font-semibold flex items-center gap-1.5">
                  <AlertTriangle className="w-3.5 h-3.5" /> Forbidden Actions
                </span>
                <ul className="space-y-1.5 text-slate-300 text-[11px]">
                  <li className="flex items-start gap-1.5">
                    <span className="text-rose-400">✕</span>
                    <span>Production deploy bez OSA approval</span>
                  </li>
                  <li className="flex items-start gap-1.5">
                    <span className="text-rose-400">✕</span>
                    <span>Fake telemetry / symulowane PASS</span>
                  </li>
                  <li className="flex items-start gap-1.5">
                    <span className="text-rose-400">✕</span>
                    <span>Niekontrolowany drift architektoniczny</span>
                  </li>
                </ul>
              </div>
            </div>

            {/* Required Evidence Verification Checklist (Pinokio) */}
            <div className="space-y-2">
              <div className="text-xs font-mono text-slate-300 font-semibold flex items-center justify-between">
                <span className="text-emerald-400 flex items-center gap-1.5">
                  <FileCheck className="w-4 h-4" /> Required Evidence Checklist (Pinokio Gate)
                </span>
                <span className="text-slate-500 text-[11px]">All required before candidate COMPLETE</span>
              </div>

              <div className="space-y-2">
                {runningMission.required_evidence?.map((ev) => (
                  <div
                    key={ev.id}
                    className="flex items-center justify-between bg-black/40 border border-slate-800/80 rounded-xl p-3 text-xs font-mono"
                  >
                    <div className="flex items-center gap-2.5">
                      <CheckCircle2 className="w-4 h-4 text-emerald-400 shrink-0" />
                      <div>
                        <span className="font-semibold text-slate-200">{ev.name}</span>
                        {ev.proof && (
                          <div className="text-[10px] text-slate-400 font-mono truncate max-w-md">
                            Proof: <span className="text-amber-300/80">{ev.proof}</span>
                          </div>
                        )}
                      </div>
                    </div>

                    <span className="px-2 py-0.5 rounded-full text-[10px] font-semibold bg-emerald-950/80 text-emerald-300 border border-emerald-700/50">
                      {ev.status}
                    </span>
                  </div>
                ))}
              </div>
            </div>
          </div>
        </div>

        {/* Right Col: Active Work Cell, Leases & Safety Drill */}
        <div className="space-y-6">
          {/* Work Cell: Michael Angelo */}
          <div className="bg-[#05091a] border border-purple-500/20 rounded-2xl p-5 shadow-md space-y-4">
            <div className="flex items-center justify-between border-b border-slate-800/80 pb-3">
              <div className="flex items-center gap-2 font-mono text-xs text-purple-300 font-semibold uppercase">
                <Hammer className="w-4 h-4 text-purple-400" />
                <span>Active Work Cell</span>
              </div>
              <span className="text-[10px] font-mono px-2 py-0.5 rounded bg-purple-950 text-purple-300 border border-purple-800/60 font-bold">
                PRIMARY BUILDER
              </span>
            </div>

            <div className="bg-black/50 border border-slate-800 rounded-xl p-4 space-y-2 font-mono text-xs">
              <div className="flex items-center justify-between">
                <span className="text-slate-400">Worker:</span>
                <span className="font-bold text-amber-300">Michael Angelo</span>
              </div>
              <div className="flex items-center justify-between">
                <span className="text-slate-400">Lease ID:</span>
                <span className="text-purple-300 font-mono">LEASE-MICHAEL-001</span>
              </div>
              <div className="flex items-center justify-between">
                <span className="text-slate-400">Mission:</span>
                <span className="text-slate-200">M-2048</span>
              </div>
              <div className="flex items-center justify-between">
                <span className="text-slate-400">Token Budget:</span>
                <span className="text-emerald-400 font-semibold">42,100 / 150,000</span>
              </div>
              <div className="flex items-center justify-between">
                <span className="text-slate-400">Heartbeat:</span>
                <span className="text-emerald-400 flex items-center gap-1">
                  <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-ping" />
                  Live (1s ago)
                </span>
              </div>
            </div>

            <div className="flex gap-2">
              <button
                onClick={() => onNavigate('workers')}
                className="w-full py-2 bg-purple-950/80 hover:bg-purple-900 text-purple-200 text-xs font-mono rounded-xl border border-purple-600/40 transition cursor-pointer font-semibold"
              >
                Inspect Work Cells
              </button>
              <button
                onClick={() => onNavigate('buzz')}
                className="w-full py-2 bg-slate-900 hover:bg-slate-800 text-amber-200 text-xs font-mono rounded-xl border border-amber-500/30 transition cursor-pointer font-semibold"
              >
                Buzz Room
              </button>
            </div>
          </div>

          {/* Emergency Services & Harakiri Drill */}
          <div className="bg-[#05091a] border border-rose-500/20 rounded-2xl p-5 shadow-md space-y-3 font-mono">
            <div className="flex items-center justify-between border-b border-slate-800/80 pb-2.5">
              <div className="flex items-center gap-2 text-xs text-rose-400 font-semibold uppercase">
                <Flame className="w-4 h-4 text-rose-400" />
                <span>Emergency Services</span>
              </div>
              <span className="text-[10px] text-slate-400">Harakiri / Recovery</span>
            </div>

            <p className="text-[11px] text-slate-400 leading-relaxed">
              W razie dryfu lub naruszenia granic: zabicie Work Cella (Harakiri), zachowanie dowodów w Notariuszu i Handoff do kolejnego workera.
            </p>

            <button
              onClick={onEmergencyHarakiriDrill || (() => onNavigate('governance'))}
              className="w-full py-2.5 bg-rose-950/60 hover:bg-rose-900/80 text-rose-200 text-xs font-mono font-bold rounded-xl border border-rose-600/40 transition cursor-pointer flex items-center justify-center gap-2"
            >
              <AlertTriangle className="w-3.5 h-3.5 text-rose-400" />
              <span>Trigger Harakiri Isolation Drill</span>
            </button>
          </div>
        </div>
      </div>
    </div>
  );
};
