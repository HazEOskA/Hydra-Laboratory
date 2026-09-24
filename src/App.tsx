import React, { useState, useMemo, useCallback } from 'react';
import { Header } from './components/Header';
import { Navigation, NavTab } from './components/Navigation';
import { CockpitView } from './components/CockpitView';
import { GatewayView } from './components/GatewayView';
import { MissionsView } from './components/MissionsView';
import { QueueView } from './components/QueueView';
import { WorkersView } from './components/WorkersView';
import { PermissionsView } from './components/PermissionsView';
import { LedgerView } from './components/LedgerView';
import { RouterView } from './components/RouterView';
import { RevenueView } from './components/RevenueView';
import { BuzzView } from './components/BuzzView';
import { InfrastructureView } from './components/InfrastructureView';
import { RecoveryView } from './components/RecoveryView';
import { SoulView } from './components/SoulView';
import { TerminalView } from './components/TerminalView';

import { PermissionClassifier } from './engine/permissionsEngine';
import { QueueEngine } from './engine/queueEngine';
import { LedgerEngine } from './engine/ledgerEngine';
import { ModelRouterEngine } from './engine/routerEngine';
import { RevenueLedgerEngine } from './engine/revenueEngine';

import {
  INITIAL_LEADS,
  INITIAL_MISSIONS,
  INITIAL_TASKS,
  INITIAL_WORKER_LEASES,
  INITIAL_PINOKIO_CLAIMS,
  INITIAL_BUZZ_ROOMS,
  INITIAL_UNDERSTANDING_STATE,
  INITIAL_NOTARY_ENTRIES,
  INITIAL_GCP_SERVICES,
  generateInitialEvents,
} from './engine/initialState';
import {
  LeadState,
  MissionState,
  WorkerLease,
  PinokioClaim,
  BuzzRoom,
  UnderstandingGateState,
} from './types';

export const App: React.FC = () => {
  const [activeTab, setActiveTab] = useState<NavTab>('cockpit');
  const [versionCounter, setVersionCounter] = useState(0);
  const [isProcessing, setIsProcessing] = useState(false);
  const [promptsUsedToday, setPromptsUsedToday] = useState(42);
  const dailyPromptCap = 240;

  // Hydra City Reactive States
  const [workerLeases, setWorkerLeases] = useState<WorkerLease[]>(INITIAL_WORKER_LEASES);
  const [pinokioClaims, setPinokioClaims] = useState<PinokioClaim[]>(INITIAL_PINOKIO_CLAIMS);
  const [buzzRooms, setBuzzRooms] = useState<BuzzRoom[]>(INITIAL_BUZZ_ROOMS);
  const [understandingState, setUnderstandingState] = useState<UnderstandingGateState>(
    INITIAL_UNDERSTANDING_STATE
  );

  // Persistent Singletons for Hermes God-Layer Subsystems
  const classifier = useMemo(() => new PermissionClassifier(), []);
  const queueEngine = useMemo(() => new QueueEngine(INITIAL_TASKS), []);
  const ledgerEngine = useMemo(
    () => new LedgerEngine(INITIAL_MISSIONS, generateInitialEvents()),
    []
  );
  const routerEngine = useMemo(() => new ModelRouterEngine(), []);
  const revenueEngine = useMemo(() => new RevenueLedgerEngine(INITIAL_LEADS), []);

  const triggerUpdate = useCallback(() => {
    setVersionCounter((v) => v + 1);
  }, []);

  // Reactive view models
  const tasks = queueEngine.getAll();
  const queueStats = queueEngine.getStats();
  const queueLag = queueEngine.getQueueLagSeconds();
  const missions = ledgerEngine.getMissions();
  const events = ledgerEngine.getEvents();
  const leads = revenueEngine.getLeads();
  const audits = revenueEngine.getAudits();
  const drafts = revenueEngine.getDrafts();
  const followups = revenueEngine.getFollowups();
  const hashChainResult = ledgerEngine.verifyChain();
  const revenueTotals = revenueEngine.getTotals();

  const waitingApprovalCount = queueStats.WAITING_FOR_APPROVAL || 0;
  const queuedCount = queueStats.QUEUED || 0;
  const activeTaskCount = queueEngine.activeCount();

  // Queue & Work Cell runner handlers
  const handleClaimNext = useCallback(() => {
    setIsProcessing(true);
    setTimeout(() => {
      const task = queueEngine.claim();
      if (task) {
        setPromptsUsedToday((p) => Math.min(dailyPromptCap, p + 1));
        try {
          ledgerEngine.transition(task.mission_id, 'DISPATCHED', {
            taskId: task.task_id,
            reason: `Task ${task.task_id} claimed and dispatched to Michael Angelo Work Cell`,
          });
        } catch {
          // Non-blocking transition if mission in different state
        }
      }
      setIsProcessing(false);
      triggerUpdate();
    }, 350);
  }, [queueEngine, ledgerEngine, triggerUpdate]);

  const handleValidate = useCallback(
    (taskId: string) => {
      const task = queueEngine.startValidation(taskId);
      try {
        ledgerEngine.transition(task.mission_id, 'VALIDATING', {
          taskId: task.task_id,
          reason: `Validating task outputs against invariants with Pinokio`,
        });
      } catch {
        // Safe fallback
      }
      triggerUpdate();
    },
    [queueEngine, ledgerEngine, triggerUpdate]
  );

  const handleComplete = useCallback(
    (taskId: string, evidenceRefs: string[]) => {
      const task = queueEngine.complete(taskId, evidenceRefs);
      try {
        ledgerEngine.transition(task.mission_id, 'COMPLETED', {
          taskId: task.task_id,
          reason: `Task completed with mechanically verified evidence`,
          evidenceRefs,
        });
      } catch {
        ledgerEngine.recordAudit(task.mission_id, {
          actor: 'hermes',
          reason: `Task ${task.task_id} completed`,
          taskId: task.task_id,
          evidenceRefs,
        });
      }
      triggerUpdate();
    },
    [queueEngine, ledgerEngine, triggerUpdate]
  );

  const handleFail = useCallback(
    (taskId: string, error: string) => {
      const task = queueEngine.fail(taskId, error);
      ledgerEngine.recordAudit(task.mission_id, {
        actor: 'hermes',
        reason: `Task execution failed: ${error}`,
        taskId: task.task_id,
        marker: 'FAILURE_RECORD',
      });
      triggerUpdate();
    },
    [queueEngine, ledgerEngine, triggerUpdate]
  );

  const handleCancel = useCallback(
    (taskId: string) => {
      queueEngine.cancel(taskId);
      triggerUpdate();
    },
    [queueEngine, triggerUpdate]
  );

  const handleApprove = useCallback(
    (taskId: string, approver: string, expiresMinutes: number = 60) => {
      const task = queueEngine.approve(taskId, approver, expiresMinutes);
      ledgerEngine.recordAudit(task.mission_id, {
        actor: approver,
        reason: `Scoped OSA approval granted (expires in ${expiresMinutes}m)`,
        taskId: task.task_id,
        marker: 'APPROVAL_GRANT',
      });
      triggerUpdate();
    },
    [queueEngine, ledgerEngine, triggerUpdate]
  );

  const handleRecoverStale = useCallback(() => {
    const recovered = queueEngine.recoverStale();
    if (recovered.length > 0) {
      ledgerEngine.recordAudit('system', {
        actor: 'health-watch',
        reason: `Recovered ${recovered.length} stale task leases: ${recovered.join(', ')}`,
        marker: 'LEASE_RECOVERY',
      });
    }
    triggerUpdate();
  }, [queueEngine, ledgerEngine, triggerUpdate]);

  const handleEnqueue = useCallback(
    (
      taskId: string,
      missionId: string,
      type: string,
      permission: 'GREEN' | 'YELLOW' | 'RED',
      priority: number,
      payload: Record<string, any>,
      dependsOn: string[]
    ) => {
      queueEngine.enqueue(taskId, missionId, type, {
        permission,
        priority,
        payload,
        dependsOn,
      });
      triggerUpdate();
    },
    [queueEngine, triggerUpdate]
  );

  const handleMissionCreate = useCallback(
    (missionId: string, title: string) => {
      ledgerEngine.createMission(missionId, title, 'OSA');
      triggerUpdate();
    },
    [ledgerEngine, triggerUpdate]
  );

  const handleAdvanceMissionState = useCallback(
    (missionId: string, nextState: MissionState, reason: string) => {
      try {
        ledgerEngine.transition(missionId, nextState, {
          actor: 'OSA',
          reason,
        });
      } catch (e: any) {
        ledgerEngine.recordAudit(missionId, {
          actor: 'OSA',
          reason: `Mission state transition to ${nextState}: ${reason}`,
        });
      }
      triggerUpdate();
    },
    [ledgerEngine, triggerUpdate]
  );

  const handleCompileGenesis = useCallback(
    (genesisData: any) => {
      const newMId = `M-${Math.floor(1000 + Math.random() * 9000)}`;
      ledgerEngine.createMission(newMId, genesisData.goal, 'UnderstandingGate');
      ledgerEngine.recordAudit(newMId, {
        actor: 'UnderstandingGate',
        reason: `Mission Genesis compiled & locked: ${genesisData.goal}`,
        evidenceRefs: [`genesis/${newMId}.json`],
      });

      // Add to Buzz
      setBuzzRooms((prev) => [
        ...prev,
        {
          room_id: `ROOM-${newMId}`,
          mission_id: newMId,
          name: `Mission ${newMId}: ${genesisData.goal.slice(0, 30)}...`,
          topic: genesisData.goal,
          status: 'ACTIVE',
          created_at: new Date().toISOString(),
          participants: [
            { id: 'osa', name: 'OSA / Operator', role: 'OPERATOR', avatar: '👑' },
            { id: 'gov', name: 'Government', role: 'GOVERNMENT', avatar: '⚖️' },
            { id: 'michael', name: 'Michael Angelo', role: 'MICHAEL_ANGELO', avatar: '🏛️' },
          ],
          messages: [
            {
              id: `msg-${Date.now()}`,
              room_id: `ROOM-${newMId}`,
              sender_id: 'gov',
              sender_name: 'Understanding Gate',
              role: 'GOVERNMENT',
              text: `Genesis Contract skompilowany dla misji ${newMId}. Punkt odniesienia zablokowany.`,
              timestamp: new Date().toLocaleTimeString(),
              type: 'APPROVAL',
            },
          ],
        },
      ]);

      setActiveTab('missions');
      triggerUpdate();
    },
    [ledgerEngine, triggerUpdate]
  );

  const handleHandoffLease = useCallback(
    (leaseId: string, newRole: string) => {
      setWorkerLeases((prev) =>
        prev.map((l) =>
          l.lease_id === leaseId
            ? {
                ...l,
                role: newRole as any,
                checkpoint_hash: `chk-${Math.random().toString(36).substring(2, 8)}-relay-ok`,
                heartbeat_at: new Date().toISOString(),
              }
            : l
        )
      );
      ledgerEngine.recordAudit('system', {
        actor: 'Logistics',
        reason: `Handoff Relay executed on lease ${leaseId} to role ${newRole}`,
        marker: 'LEASE_HANDOFF',
      });
      triggerUpdate();
    },
    [ledgerEngine, triggerUpdate]
  );

  const handleRevokeLease = useCallback(
    (leaseId: string) => {
      setWorkerLeases((prev) => prev.filter((l) => l.lease_id !== leaseId));
      ledgerEngine.recordAudit('system', {
        actor: 'Government',
        reason: `Lease ${leaseId} revoked by Operator`,
        marker: 'LEASE_REVOKE',
      });
      triggerUpdate();
    },
    [ledgerEngine, triggerUpdate]
  );

  const handleVerifyClaim = useCallback(
    (claimId: string) => {
      setPinokioClaims((prev) =>
        prev.map((c) =>
          c.claim_id === claimId
            ? { ...c, verification_level: 'MECHANICALLY_VERIFIED', exit_code: 0 }
            : c
        )
      );
      ledgerEngine.recordAudit('system', {
        actor: 'Pinokio',
        reason: `Claim ${claimId} mechanically verified against build/health evidence`,
        marker: 'PINOKIO_VERIFIED',
      });
      triggerUpdate();
    },
    [ledgerEngine, triggerUpdate]
  );

  const handleTriggerHarakiri = useCallback(() => {
    ledgerEngine.recordAudit('system', {
      actor: 'Government',
      reason: `EMERGENCY HARAKIRI DRILL EXECUTED: All Work Cells frozen. Checkpoints flushed to Notary.`,
      marker: 'HARAKIRI_SAFETY_DRILL',
    });
    triggerUpdate();
  }, [ledgerEngine, triggerUpdate]);

  const handleSendMessage = useCallback(
    (roomId: string, text: string) => {
      setBuzzRooms((prev) =>
        prev.map((room) =>
          room.room_id === roomId
            ? {
                ...room,
                messages: [
                  ...room.messages,
                  {
                    id: `msg-${Date.now()}`,
                    room_id: roomId,
                    sender_id: 'osa',
                    sender_name: 'OSA / Operator',
                    role: 'OPERATOR',
                    text,
                    timestamp: new Date().toLocaleTimeString(),
                    type: 'INTENT',
                  },
                ],
              }
            : room
        )
      );
    },
    []
  );

  const handleRollbackCheckpoint = useCallback(
    (missionId: string, checkpointHash: string) => {
      ledgerEngine.recordAudit(missionId, {
        actor: 'OSA',
        reason: `Atomic Rollback executed to checkpoint ${checkpointHash}`,
        marker: 'CHECKPOINT_ROLLBACK',
      });
      triggerUpdate();
    },
    [ledgerEngine, triggerUpdate]
  );

  // Revenue Ops Handlers
  const handleAddLead = useCallback(
    (leadData: any) => {
      revenueEngine.addLead(leadData);
      triggerUpdate();
    },
    [revenueEngine, triggerUpdate]
  );

  const handleGenerateAuditAndDraft = useCallback(
    (leadId: string) => {
      const auditId = `audit-${leadId}-${Date.now().toString().slice(-4)}`;
      const draftId = `draft-${leadId}-${Date.now().toString().slice(-4)}`;
      const followupId = `followup-${leadId}-${Date.now().toString().slice(-4)}`;

      revenueEngine.createAuditAndDraft(leadId, {
        auditId,
        draftId,
        followupId,
      });

      ledgerEngine.recordAudit('mission-003-continuous-ops', {
        actor: 'hermes-revenue-ops',
        reason: `Generated mini-audit ${auditId} and draft email ${draftId} for lead ${leadId}`,
        evidenceRefs: [auditId, draftId],
        marker: 'REVENUE_AUDIT_DRAFT',
      });

      triggerUpdate();
    },
    [revenueEngine, ledgerEngine, triggerUpdate]
  );

  const handleSetLeadState = useCallback(
    (leadId: string, newState: LeadState, approvalRef?: string) => {
      revenueEngine.setState(leadId, newState, approvalRef);
      ledgerEngine.recordAudit('mission-003-continuous-ops', {
        actor: approvalRef || 'OSA',
        reason: `Lead ${leadId} state transitioned to ${newState}`,
        marker: 'LEAD_STATE_CHANGE',
      });
      triggerUpdate();
    },
    [revenueEngine, ledgerEngine, triggerUpdate]
  );

  return (
    <div className="min-h-screen bg-[#030614] text-slate-100 flex flex-col selection:bg-amber-500 selection:text-black">
      {/* Header Bar with Realtime Status & Hydra City Telemetry */}
      <Header
        systemHealth={{
          ok: hashChainResult.ok,
          statusText: hashChainResult.ok ? 'Runtime Healthy' : 'Ledger Degraded',
        }}
        activeCount={activeTaskCount}
        activeLeasesCount={workerLeases.length}
        promptsUsedToday={promptsUsedToday}
        dailyPromptCap={dailyPromptCap}
        cloudRunRevision="hydra-hermes-lab-00042-pxq"
        onOpenTerminal={() => setActiveTab('terminal')}
        onEmergencyLockdown={handleTriggerHarakiri}
      />

      {/* Navigation Subsystem */}
      <Navigation
        activeTab={activeTab}
        onSelectTab={setActiveTab}
        waitingApprovalCount={waitingApprovalCount}
        queuedCount={queuedCount}
        activeMissionCount={missions.filter((m) => m.state === 'RUNNING').length}
        unreadBuzzCount={1}
      />

      {/* Main View Area */}
      <main className="flex-1 max-w-7xl w-full mx-auto px-4 sm:px-6 lg:px-8 py-6">
        {activeTab === 'cockpit' && (
          <CockpitView
            tasks={tasks}
            missions={missions}
            workerLeases={workerLeases}
            pinokioClaims={pinokioClaims}
            queueStats={queueStats}
            queueLag={queueLag}
            hashChainOk={hashChainResult.ok}
            hashChainDetail={hashChainResult.detail}
            totalEvents={events.length}
            leadsCount={leads.length}
            pipelineValue={revenueTotals.pipeline_value}
            onNavigate={setActiveTab}
            onClaimAndRunNext={handleClaimNext}
            isProcessing={isProcessing}
            onEmergencyHarakiriDrill={handleTriggerHarakiri}
          />
        )}

        {activeTab === 'gateway' && (
          <GatewayView
            understandingState={understandingState}
            onCompileGenesis={handleCompileGenesis}
          />
        )}

        {activeTab === 'missions' && (
          <MissionsView
            missions={missions}
            onAdvanceMissionState={handleAdvanceMissionState}
            onNavigate={setActiveTab}
          />
        )}

        {activeTab === 'queue' && (
          <QueueView
            tasks={tasks}
            queueStats={queueStats}
            onClaim={handleClaimNext}
            onApprove={handleApprove}
            onValidate={handleValidate}
            onComplete={handleComplete}
            onFail={handleFail}
            onCancel={handleCancel}
            onRecoverStale={handleRecoverStale}
            onEnqueue={handleEnqueue}
          />
        )}

        {activeTab === 'workers' && (
          <WorkersView
            leases={workerLeases}
            tasks={tasks}
            onHandoffLease={handleHandoffLease}
            onRevokeLease={handleRevokeLease}
            onNavigate={setActiveTab}
          />
        )}

        {activeTab === 'governance' && (
          <PermissionsView
            classifier={classifier}
            waitingTasks={tasks.filter((t) => t.status === 'WAITING_FOR_APPROVAL')}
            pinokioClaims={pinokioClaims}
            onApproveTask={handleApprove}
            onRejectTask={(tId, r) => handleFail(tId, r)}
            onVerifyClaim={handleVerifyClaim}
            onTriggerHarakiriDrill={handleTriggerHarakiri}
          />
        )}

        {activeTab === 'ledger' && (
          <LedgerView
            ledgerEngine={ledgerEngine}
            missions={missions}
            events={events}
            onMissionCreate={handleMissionCreate}
            onRefresh={triggerUpdate}
            onSealMission={(mId) => handleAdvanceMissionState(mId, 'CLOSED', 'Sealed with APR Proof')}
          />
        )}

        {activeTab === 'router' && (
          <RouterView routerEngine={routerEngine} onHealthChange={triggerUpdate} />
        )}

        {activeTab === 'revenue' && (
          <RevenueView
            revenueEngine={revenueEngine}
            leads={leads}
            audits={audits}
            drafts={drafts}
            followups={followups}
            onAddLead={handleAddLead}
            onGenerateAuditAndDraft={handleGenerateAuditAndDraft}
            onSetLeadState={handleSetLeadState}
          />
        )}

        {activeTab === 'buzz' && (
          <BuzzView
            buzzRooms={buzzRooms}
            onSendMessage={handleSendMessage}
            onNavigate={setActiveTab}
          />
        )}

        {activeTab === 'infrastructure' && (
          <InfrastructureView
            gcpServices={INITIAL_GCP_SERVICES}
            onNavigate={setActiveTab}
          />
        )}

        {activeTab === 'recovery' && (
          <RecoveryView
            missions={missions}
            leases={workerLeases}
            tasks={tasks}
            onRollbackCheckpoint={handleRollbackCheckpoint}
            onRevokeLease={handleRevokeLease}
            onRetryDeadLetter={(tId) => handleValidate(tId)}
          />
        )}

        {activeTab === 'soul' && <SoulView />}

        {activeTab === 'terminal' && (
          <TerminalView
            classifier={classifier}
            queueEngine={queueEngine}
            ledgerEngine={ledgerEngine}
            routerEngine={routerEngine}
            revenueEngine={revenueEngine}
          />
        )}
      </main>

      {/* Footer */}
      <footer className="border-t border-amber-500/10 bg-[#020510] py-4 text-center text-xs font-mono text-slate-500">
        <div className="max-w-7xl mx-auto px-4 flex flex-col sm:flex-row items-center justify-between gap-2">
          <span className="text-amber-300/80 font-semibold">
            HYDRA HERMES LAB &bull; Hydra City Logical Architecture v0.1
          </span>
          <span className="text-slate-500">
            SHA-256 Merkle Ledger &bull; Pinokio Verifier &bull; Google Cloud Run Preview (europe-west2)
          </span>
        </div>
      </footer>
    </div>
  );
};
export default App;
