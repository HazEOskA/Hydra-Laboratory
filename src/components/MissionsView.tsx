import React, { useCallback, useEffect, useMemo, useState } from 'react';
import {
  AlertTriangle,
  CheckCircle2,
  Database,
  FileCheck,
  FolderGit2,
  Play,
  RefreshCw,
  Server,
  Sparkles,
} from 'lucide-react';
import { Mission, MissionState } from '../types';
import {
  ControlPlaneSnapshot,
  createLiveMission,
  fetchControlPlaneSnapshot,
  HYDRA_API_BASE,
  runNextLiveTask,
} from '../api/controlPlane';

interface MissionsViewProps {
  missions: Mission[];
  onAdvanceMissionState: (missionId: string, nextState: MissionState, reason: string) => void;
  onNavigate: (tab: any) => void;
}

type BackendState = 'checking' | 'live' | 'offline';

export const MissionsView: React.FC<MissionsViewProps> = ({
  missions,
  onAdvanceMissionState,
  onNavigate,
}) => {
  void onAdvanceMissionState;

  const [backendState, setBackendState] = useState<BackendState>('checking');
  const [snapshot, setSnapshot] = useState<ControlPlaneSnapshot | null>(null);
  const [selectedMissionId, setSelectedMissionId] = useState<string>(missions[0]?.mission_id || '');
  const [newMissionTitle, setNewMissionTitle] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');

  const refreshLive = useCallback(async () => {
    setError('');
    try {
      const next = await fetchControlPlaneSnapshot();
      setSnapshot(next);
      setBackendState('live');
    } catch (err: any) {
      setBackendState('offline');
      setError(err?.message || 'Backend API niedostępne');
    }
  }, []);

  useEffect(() => {
    refreshLive();
  }, [refreshLive]);

  const displayMissions = backendState === 'live' && snapshot ? snapshot.missions : missions;

  useEffect(() => {
    if (!displayMissions.length) {
      setSelectedMissionId('');
      return;
    }
    if (!displayMissions.some((mission) => mission.mission_id === selectedMissionId)) {
      setSelectedMissionId(displayMissions[0].mission_id);
    }
  }, [displayMissions, selectedMissionId]);

  const selectedMission =
    displayMissions.find((mission) => mission.mission_id === selectedMissionId) ||
    displayMissions[0];

  const selectedEvents = useMemo(() => {
    if (!snapshot || !selectedMission) return [];
    return snapshot.events
      .filter((event) => event.mission_id === selectedMission.mission_id)
      .slice()
      .reverse();
  }, [snapshot, selectedMission]);

  const selectedTasks = useMemo(() => {
    if (!snapshot || !selectedMission) return [];
    return snapshot.tasks.filter((task) => task.mission_id === selectedMission.mission_id);
  }, [snapshot, selectedMission]);

  const evidenceRefs = useMemo(() => {
    const refs = new Set<string>();
    selectedEvents.forEach((event) => event.evidence_refs.forEach((ref) => refs.add(ref)));
    selectedTasks.forEach((task) => task.evidence_refs.forEach((ref) => refs.add(ref)));
    return Array.from(refs);
  }, [selectedEvents, selectedTasks]);

  const stateFlow: MissionState[] = [
    'CREATED',
    'INTAKE_VALIDATED',
    'PLANNED',
    'QUEUED',
    'DISPATCHED',
    'RUNNING',
    'VALIDATING',
    'COMPLETED',
  ];

  const createMission = async () => {
    const title = newMissionTitle.trim();
    if (!title) return;
    setBusy(true);
    setError('');
    try {
      const next = await createLiveMission(title);
      setSnapshot(next);
      setBackendState('live');
      setNewMissionTitle('');
      if (next.missions[0]) setSelectedMissionId(next.missions[0].mission_id);
    } catch (err: any) {
      setError(err?.message || 'Nie udało się utworzyć misji');
    } finally {
      setBusy(false);
    }
  };

  const runNext = async () => {
    setBusy(true);
    setError('');
    try {
      const next = await runNextLiveTask();
      setSnapshot(next);
      setBackendState('live');
    } catch (err: any) {
      setError(err?.message || 'Nie udało się uruchomić taska');
    } finally {
      setBusy(false);
    }
  };

  const statusClass =
    backendState === 'live'
      ? 'border-emerald-500/40 bg-emerald-950/30 text-emerald-300'
      : backendState === 'offline'
      ? 'border-rose-500/40 bg-rose-950/30 text-rose-300'
      : 'border-amber-500/40 bg-amber-950/30 text-amber-300';

  return (
    <div className="space-y-6">
      <div className="bg-gradient-to-r from-[#030712] via-[#090e24] to-[#030712] border border-amber-500/30 rounded-2xl p-6 shadow-xl">
        <div className="flex flex-col xl:flex-row xl:items-center justify-between gap-5">
          <div className="space-y-2">
            <div className="flex items-center gap-2.5">
              <span className="p-2 rounded-xl bg-amber-500/10 text-amber-400 border border-amber-500/30">
                <FolderGit2 className="w-5 h-5" />
              </span>
              <h2 className="text-lg font-bold font-mono text-amber-100 uppercase tracking-wider">
                MISJE — LIVE CONTROL PLANE SLICE
              </h2>
            </div>
            <p className="text-xs font-mono text-slate-300 max-w-3xl leading-relaxed">
              Ten ekran ma jeden obowiązek: pokazać prawdziwy przepływ
              OSA → Understanding Gate → Michael Angelo → Worker → Pinokio → Evidence.
              Pozostałe zakładki kokpitu nadal mogą zawierać stan demonstracyjny.
            </p>
          </div>

          <div className={'rounded-xl border px-3 py-2 font-mono text-xs ' + statusClass}>
            <div className="flex items-center gap-2 font-bold">
              <Server className="w-4 h-4" />
              {backendState === 'live'
                ? 'LIVE BACKEND'
                : backendState === 'offline'
                ? 'DEMO FALLBACK'
                : 'SPRAWDZAM BACKEND'}
            </div>
            <div className="mt-1 text-[10px] opacity-80">{HYDRA_API_BASE}</div>
          </div>
        </div>

        {backendState === 'offline' && (
          <div className="mt-4 flex items-start gap-2 rounded-xl border border-rose-500/30 bg-rose-950/20 p-3 text-xs font-mono text-rose-200">
            <AlertTriangle className="w-4 h-4 shrink-0 mt-0.5" />
            <div>
              Backend API nie odpowiada. UI nie oznacza danych jako LIVE i pokazuje wyłącznie fallback demonstracyjny.
              {error && <div className="mt-1 text-rose-300">Błąd: {error}</div>}
            </div>
          </div>
        )}
      </div>

      <div className="grid grid-cols-1 xl:grid-cols-12 gap-6">
        <div className="xl:col-span-4 space-y-4">
          <div className="rounded-2xl border border-slate-800 bg-[#05091a] p-4 space-y-3">
            <div className="text-xs font-mono font-bold text-amber-300 uppercase tracking-wider flex items-center gap-2">
              <Sparkles className="w-4 h-4" />
              Nowa prawdziwa misja
            </div>
            <textarea
              value={newMissionTitle}
              onChange={(event) => setNewMissionTitle(event.target.value)}
              disabled={backendState !== 'live' || busy}
              placeholder="Np. Sprawdź integralność Hydra Control Plane"
              className="w-full min-h-24 rounded-xl border border-slate-700 bg-black/40 p-3 text-xs font-mono text-slate-100 outline-none focus:border-amber-500/60 disabled:opacity-50"
            />
            <div className="grid grid-cols-2 gap-2">
              <button
                onClick={createMission}
                disabled={backendState !== 'live' || busy || !newMissionTitle.trim()}
                className="rounded-xl bg-amber-500 px-3 py-2 text-xs font-mono font-bold text-black disabled:opacity-40"
              >
                Utwórz misję
              </button>
              <button
                onClick={runNext}
                disabled={backendState !== 'live' || busy}
                className="rounded-xl border border-emerald-500/40 bg-emerald-950/40 px-3 py-2 text-xs font-mono font-bold text-emerald-300 disabled:opacity-40 flex items-center justify-center gap-1.5"
              >
                <Play className="w-3.5 h-3.5" />
                RUN NEXT
              </button>
            </div>
            <button
              onClick={refreshLive}
              disabled={busy}
              className="w-full rounded-xl border border-slate-700 bg-slate-900/70 px-3 py-2 text-xs font-mono text-slate-300 flex items-center justify-center gap-2"
            >
              <RefreshCw className={'w-3.5 h-3.5 ' + (busy ? 'animate-spin' : '')} />
              Odśwież snapshot
            </button>
            {error && backendState === 'live' && (
              <div className="text-[11px] font-mono text-rose-300">{error}</div>
            )}
          </div>

          <div className="space-y-2.5">
            <div className="text-xs font-mono font-bold text-amber-400 uppercase tracking-wider px-1">
              Rejestr misji ({displayMissions.length})
            </div>
            {displayMissions.map((mission) => {
              const selected = mission.mission_id === selectedMissionId;
              return (
                <button
                  key={mission.mission_id}
                  onClick={() => setSelectedMissionId(mission.mission_id)}
                  className={
                    'w-full text-left p-4 rounded-2xl border transition font-mono ' +
                    (selected
                      ? 'bg-[#060b22] border-amber-500/60 shadow-lg shadow-amber-500/10'
                      : 'bg-[#05091a]/80 border-slate-800/80 hover:border-amber-500/30')
                  }
                >
                  <div className="flex items-center justify-between gap-2">
                    <span className="text-xs font-bold text-amber-200">{mission.mission_id}</span>
                    <span className="text-[10px] px-2 py-0.5 rounded-full border border-slate-700 text-slate-300">
                      {mission.state}
                    </span>
                  </div>
                  <div className="text-xs font-bold text-slate-200 mt-2 line-clamp-2">{mission.title}</div>
                  <div className="text-[10px] text-slate-500 mt-2">{mission.updated_at}</div>
                </button>
              );
            })}
          </div>
        </div>

        <div className="xl:col-span-8 space-y-5">
          {snapshot && backendState === 'live' && (
            <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
              <Metric label="Chain" value={snapshot.chain.ok ? 'VERIFIED' : 'BROKEN'} />
              <Metric label="Queued" value={String(snapshot.queue_stats.QUEUED || 0)} />
              <Metric label="Running" value={String(snapshot.queue_stats.RUNNING || 0)} />
              <Metric label="Completed" value={String(snapshot.queue_stats.COMPLETED || 0)} />
            </div>
          )}

          {selectedMission ? (
            <div className="rounded-2xl border border-amber-500/20 bg-[#05091a] p-6 shadow-md font-mono space-y-6">
              <div className="flex flex-col md:flex-row md:items-center justify-between gap-3 border-b border-slate-800 pb-4">
                <div>
                  <div className="text-base font-bold text-amber-100">{selectedMission.title}</div>
                  <div className="mt-1 text-xs text-slate-400">
                    {selectedMission.mission_id} · {selectedMission.state}
                  </div>
                </div>
                <button
                  onClick={() => onNavigate('ledger')}
                  className="rounded-xl border border-purple-500/30 bg-purple-950/30 px-3 py-2 text-xs text-purple-200"
                >
                  Otwórz Ledger
                </button>
              </div>

              <div>
                <div className="text-xs font-bold text-slate-300 uppercase tracking-wider mb-2">
                  Lifecycle
                </div>
                <div className="flex gap-1 overflow-x-auto pb-2">
                  {stateFlow.map((state, index) => {
                    const currentIndex = stateFlow.indexOf(selectedMission.state);
                    const passed = currentIndex > index;
                    const current = selectedMission.state === state;
                    return (
                      <div
                        key={state}
                        className={
                          'shrink-0 px-2.5 py-1.5 rounded-lg text-[10px] border ' +
                          (current
                            ? 'border-amber-500/60 bg-amber-500/20 text-amber-300'
                            : passed
                            ? 'border-emerald-700/40 bg-emerald-950/30 text-emerald-400'
                            : 'border-slate-800 bg-black/30 text-slate-500')
                        }
                      >
                        {state}
                      </div>
                    );
                  })}
                </div>
              </div>

              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                <div className="rounded-xl border border-slate-800 bg-black/30 p-4">
                  <div className="flex items-center gap-2 text-xs font-bold text-amber-300 mb-3">
                    <Database className="w-4 h-4" />
                    Backend tasks
                  </div>
                  <div className="space-y-2">
                    {selectedTasks.length ? (
                      selectedTasks.map((task) => (
                        <div key={task.task_id} className="rounded-lg border border-slate-800 p-2.5 text-[11px]">
                          <div className="flex justify-between gap-2">
                            <span className="text-slate-200">{task.task_id}</span>
                            <span className="text-emerald-300">{task.status}</span>
                          </div>
                          <div className="text-slate-500 mt-1">{task.type} · {task.permission}</div>
                        </div>
                      ))
                    ) : (
                      <div className="text-[11px] text-slate-500">Brak tasków dla tej misji.</div>
                    )}
                  </div>
                </div>

                <div className="rounded-xl border border-slate-800 bg-black/30 p-4">
                  <div className="flex items-center gap-2 text-xs font-bold text-emerald-300 mb-3">
                    <FileCheck className="w-4 h-4" />
                    Evidence
                  </div>
                  <div className="space-y-2">
                    {evidenceRefs.length ? (
                      evidenceRefs.map((ref) => (
                        <div key={ref} className="rounded-lg border border-emerald-800/40 bg-emerald-950/20 p-2.5 text-[10px] text-emerald-200 break-all">
                          <div className="flex items-center gap-1.5 font-bold mb-1">
                            <CheckCircle2 className="w-3.5 h-3.5" />
                            MECHANICALLY VERIFIED
                          </div>
                          {ref}
                        </div>
                      ))
                    ) : (
                      <div className="text-[11px] text-slate-500">Evidence pojawi się dopiero po VERIFY.</div>
                    )}
                  </div>
                </div>
              </div>

              <div>
                <div className="text-xs font-bold text-slate-300 uppercase tracking-wider mb-3">
                  Ledger events
                </div>
                <div className="space-y-2 max-h-80 overflow-y-auto">
                  {selectedEvents.length ? (
                    selectedEvents.map((event) => (
                      <div key={String(event.seq) + event.event_hash} className="rounded-xl border border-slate-800 bg-black/30 p-3 text-[11px]">
                        <div className="flex items-center justify-between gap-3">
                          <span className="font-bold text-amber-200">{event.actor}</span>
                          <span className="text-slate-500">{event.to_state}</span>
                        </div>
                        <div className="mt-1 text-slate-300">{event.reason}</div>
                        <div className="mt-1 text-[10px] text-slate-600">{event.timestamp}</div>
                      </div>
                    ))
                  ) : (
                    <div className="text-[11px] text-slate-500">Brak live events.</div>
                  )}
                </div>
              </div>

              {snapshot && backendState === 'live' && (
                <div className="rounded-xl border border-slate-800 bg-black/30 p-3 text-[10px] text-slate-500">
                  Source of truth: {snapshot.source_of_truth.missions} · {snapshot.chain.detail}
                </div>
              )}
            </div>
          ) : (
            <div className="rounded-2xl border border-slate-800 bg-[#05091a] p-8 text-center text-sm text-slate-500">
              Brak misji.
            </div>
          )}
        </div>
      </div>
    </div>
  );
};

const Metric: React.FC<{ label: string; value: string }> = ({ label, value }) => (
  <div className="rounded-xl border border-slate-800 bg-[#05091a] p-3 font-mono">
    <div className="text-[10px] uppercase tracking-wider text-slate-500">{label}</div>
    <div className="mt-1 text-sm font-bold text-slate-200">{value}</div>
  </div>
);
