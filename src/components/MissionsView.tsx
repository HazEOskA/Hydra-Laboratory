import React, { useState } from 'react';
import {
  FolderGit2,
  CheckCircle2,
  Clock,
  Lock,
  FileCheck,
  Shield,
  Layers,
  ArrowRight,
  Sparkles,
  RefreshCw,
  AlertTriangle,
  Flame,
  Check,
} from 'lucide-react';
import { Mission, MissionState } from '../types';

interface MissionsViewProps {
  missions: Mission[];
  onAdvanceMissionState: (missionId: string, nextState: MissionState, reason: string) => void;
  onNavigate: (tab: any) => void;
}

export const MissionsView: React.FC<MissionsViewProps> = ({
  missions,
  onAdvanceMissionState,
  onNavigate,
}) => {
  const [selectedMissionId, setSelectedMissionId] = useState<string>(
    missions[0]?.mission_id || 'M-2048'
  );

  const selectedMission =
    missions.find((m) => m.mission_id === selectedMissionId) || missions[0];

  const stateFlow: MissionState[] = [
    'CREATED',
    'INTAKE_VALIDATED',
    'PLANNED',
    'QUEUED',
    'DISPATCHED',
    'RUNNING',
    'VALIDATING',
    'COMPLETED',
    'CLOSED',
  ];

  return (
    <div className="space-y-6">
      {/* Header Banner */}
      <div className="bg-gradient-to-r from-[#030712] via-[#090e24] to-[#030712] border border-amber-500/30 rounded-2xl p-6 shadow-xl">
        <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
          <div className="space-y-1.5">
            <div className="flex items-center gap-2.5">
              <span className="p-2 rounded-xl bg-amber-500/10 text-amber-400 border border-amber-500/30">
                <FolderGit2 className="w-5 h-5" />
              </span>
              <h2 className="text-lg font-bold font-mono text-amber-100 uppercase tracking-wider">
                PROJEKTY & MISJE (GENESIS CONTRACT MATRIX)
              </h2>
            </div>
            <p className="text-xs font-mono text-slate-300 max-w-3xl leading-relaxed">
              Każda misja w Hydra City posiada niezmienny <strong className="text-amber-300">Genesis Contract</strong>,
              punkt odniesienia zablokowany w <strong className="text-purple-300">Notariuszu</strong>, przypisany{' '}
              <strong className="text-amber-200">Work Cell / Lease</strong> i wymaga twardych dowodów (
              <span className="text-emerald-300 font-semibold">Pinokio Gate</span>) przed zatwierdzeniem stanu COMPLETED/CLOSED.
            </p>
          </div>

          <div className="flex items-center gap-2 font-mono text-xs">
            <button
              onClick={() => onNavigate('gateway')}
              className="flex items-center gap-2 px-3.5 py-2 bg-gradient-to-r from-amber-500 to-amber-600 hover:from-amber-400 text-black font-bold rounded-xl shadow-md transition cursor-pointer"
            >
              <Sparkles className="w-4 h-4" />
              <span>Nowa Misja via Zgredek</span>
            </button>
          </div>
        </div>
      </div>

      {/* Main Grid: Mission List (Left) + Selected Mission Detail (Right) */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
        {/* Left 4 cols: Mission List */}
        <div className="lg:col-span-4 space-y-3">
          <div className="text-xs font-mono font-bold text-amber-400 uppercase tracking-wider px-1 flex items-center justify-between">
            <span>Rejestr Misji ({missions.length})</span>
            <span className="text-[10px] text-slate-400 font-normal">Genesis Hash-Locked</span>
          </div>

          <div className="space-y-2.5">
            {missions.map((m) => {
              const isSelected = m.mission_id === selectedMissionId;
              return (
                <div
                  key={m.mission_id}
                  onClick={() => setSelectedMissionId(m.mission_id)}
                  className={`p-4 rounded-2xl border transition-all cursor-pointer font-mono ${
                    isSelected
                      ? 'bg-[#060b22] border-amber-500/60 shadow-lg shadow-amber-500/10'
                      : 'bg-[#05091a]/80 hover:bg-[#05091a] border-slate-800/80 hover:border-amber-500/30'
                  }`}
                >
                  <div className="flex items-center justify-between">
                    <span className="text-xs font-bold text-amber-200">{m.mission_id}</span>
                    <span
                      className={`text-[10px] px-2 py-0.5 rounded-full font-semibold ${
                        m.state === 'RUNNING'
                          ? 'bg-amber-950/80 text-amber-300 border border-amber-500/40'
                          : m.state === 'CLOSED' || m.state === 'COMPLETED'
                          ? 'bg-emerald-950/80 text-emerald-300 border border-emerald-500/40'
                          : 'bg-purple-950/80 text-purple-300 border border-purple-500/40'
                      }`}
                    >
                      {m.state}
                    </span>
                  </div>

                  <div className="text-xs font-bold text-slate-200 mt-2 truncate">{m.title}</div>

                  <div className="text-[10px] text-slate-400 mt-2 flex items-center justify-between pt-2 border-t border-slate-800/60">
                    <span className="truncate">Worker: {m.assigned_worker || 'Michael Angelo'}</span>
                    <span className="text-slate-500">{m.created_at.slice(0, 10)}</span>
                  </div>
                </div>
              );
            })}
          </div>
        </div>

        {/* Right 8 cols: Selected Mission Detail */}
        <div className="lg:col-span-8 space-y-6">
          {selectedMission && (
            <div className="bg-[#05091a] border border-amber-500/20 rounded-2xl p-6 shadow-md font-mono space-y-6">
              {/* Mission Header */}
              <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 border-b border-slate-800/80 pb-4">
                <div>
                  <div className="flex items-center gap-2 flex-wrap">
                    <h3 className="text-base font-bold text-amber-100">{selectedMission.title}</h3>
                    <span className="text-xs px-2.5 py-0.5 rounded-full bg-amber-500/20 text-amber-300 border border-amber-500/40 font-bold">
                      {selectedMission.mission_id}
                    </span>
                  </div>
                  <div className="text-xs text-slate-400 mt-1 flex items-center gap-2 flex-wrap">
                    <span>Otwarta: {selectedMission.created_at}</span>
                    <span>&bull;</span>
                    <span>Notary Entry: <strong className="text-purple-300">{selectedMission.notary_entry_id || 'NOTARY-M2048'}</strong></span>
                    <span>&bull;</span>
                    <span>Buzz Room: <strong className="text-amber-300">{selectedMission.buzz_room_id || 'ROOM-M2048'}</strong></span>
                  </div>
                </div>

                <div className="flex items-center gap-2">
                  {selectedMission.apr_seal && (
                    <span className="text-xs px-3 py-1 rounded-xl bg-emerald-950/80 border border-emerald-500/40 text-emerald-300 font-bold flex items-center gap-1.5 shadow-sm">
                      <Shield className="w-3.5 h-3.5 text-emerald-400" />
                      <span>{selectedMission.apr_seal}</span>
                    </span>
                  )}
                </div>
              </div>

              {/* State Machine Transition Flow */}
              <div className="space-y-2">
                <span className="text-xs font-bold text-slate-300 uppercase tracking-wider flex items-center gap-2">
                  <Layers className="w-3.5 h-3.5 text-purple-400" />
                  <span>Stan Maszyny Stanowej (Hydra City Lifecycle)</span>
                </span>

                <div className="flex items-center gap-1 overflow-x-auto py-2 scrollbar-thin">
                  {stateFlow.map((st, index) => {
                    const isCurrent = selectedMission.state === st;
                    const isPassed = stateFlow.indexOf(selectedMission.state) > index;
                    return (
                      <React.Fragment key={st}>
                        <div
                          className={`px-2.5 py-1.5 rounded-lg text-[10px] font-mono whitespace-nowrap font-semibold border ${
                            isCurrent
                              ? 'bg-amber-500/20 text-amber-300 border-amber-500/60 shadow-md shadow-amber-500/10'
                              : isPassed
                              ? 'bg-emerald-950/40 text-emerald-400 border-emerald-700/40'
                              : 'bg-black/30 text-slate-500 border-slate-800'
                          }`}
                        >
                          {st}
                        </div>
                        {index < stateFlow.length - 1 && (
                          <span className={`text-xs ${isPassed ? 'text-emerald-500' : 'text-slate-700'}`}>
                            &rarr;
                          </span>
                        )}
                      </React.Fragment>
                    );
                  })}
                </div>
              </div>

              {/* Genesis Contract Constraints & Scope */}
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4 text-xs">
                <div className="bg-black/50 border border-slate-800 rounded-xl p-4 space-y-2">
                  <span className="text-amber-400 font-bold flex items-center gap-1.5">
                    <Lock className="w-3.5 h-3.5" /> Genesis Constraints
                  </span>
                  <ul className="space-y-1 text-slate-300 text-[11px]">
                    {selectedMission.constraints?.map((c, i) => (
                      <li key={i} className="flex items-start gap-1.5">
                        <span className="text-amber-400">•</span>
                        <span>{c}</span>
                      </li>
                    )) || (
                      <li>Brak dodatkowych ograniczeń.</li>
                    )}
                  </ul>
                </div>

                <div className="bg-black/50 border border-slate-800 rounded-xl p-4 space-y-2">
                  <span className="text-rose-400 font-bold flex items-center gap-1.5">
                    <AlertTriangle className="w-3.5 h-3.5" /> Genesis Forbidden
                  </span>
                  <ul className="space-y-1 text-slate-300 text-[11px]">
                    {selectedMission.forbidden?.map((f, i) => (
                      <li key={i} className="flex items-start gap-1.5">
                        <span className="text-rose-400">✕</span>
                        <span>{f}</span>
                      </li>
                    )) || (
                      <li>Brak specyficznych zakazów.</li>
                    )}
                  </ul>
                </div>
              </div>

              {/* Required Evidence Items (Pinokio Gate) */}
              <div className="space-y-3">
                <div className="flex items-center justify-between">
                  <span className="text-xs font-bold text-emerald-400 uppercase tracking-wider flex items-center gap-2">
                    <FileCheck className="w-4 h-4 text-emerald-400" />
                    <span>Weryfikacja Dowodów (Pinokio Checklist)</span>
                  </span>
                  <span className="text-[10px] text-slate-400">Mechanicznie sprawdzane &bull; zero fake claims</span>
                </div>

                <div className="space-y-2">
                  {selectedMission.required_evidence?.map((ev) => (
                    <div
                      key={ev.id}
                      className="flex items-center justify-between bg-black/40 border border-slate-800/80 rounded-xl p-3 text-xs"
                    >
                      <div className="flex items-center gap-2.5">
                        <CheckCircle2 className="w-4 h-4 text-emerald-400 shrink-0" />
                        <div>
                          <div className="font-bold text-slate-200">{ev.name}</div>
                          {ev.proof && (
                            <div className="text-[10px] text-slate-400 truncate max-w-lg">
                              Proof: <span className="text-amber-300/90">{ev.proof}</span>
                            </div>
                          )}
                        </div>
                      </div>

                      <span className="px-2.5 py-0.5 rounded-full text-[10px] font-semibold bg-emerald-950/80 text-emerald-300 border border-emerald-700/50">
                        {ev.status}
                      </span>
                    </div>
                  ))}
                </div>
              </div>

              {/* Action Toolbar */}
              <div className="pt-4 border-t border-slate-800/80 flex items-center justify-between gap-3 flex-wrap">
                <button
                  onClick={() => onNavigate('buzz')}
                  className="px-4 py-2 bg-purple-950/80 hover:bg-purple-900 border border-purple-600/40 text-purple-200 text-xs rounded-xl transition cursor-pointer font-semibold"
                >
                  Otwórz Pokój Buzz (M-2048)
                </button>

                <button
                  onClick={() => onNavigate('ledger')}
                  className="px-4 py-2 bg-slate-900 hover:bg-slate-800 border border-amber-500/30 text-amber-200 text-xs rounded-xl transition cursor-pointer font-semibold"
                >
                  Dziennik Notariusza & Hash Ledger
                </button>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
};
