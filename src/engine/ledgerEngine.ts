import { LedgerEvent, Mission, MissionState } from '../types';
import { computePayloadHash } from './crypto';

export const GENESIS_HASH = '0'.repeat(64);

export const MISSION_STATES: MissionState[] = [
  'CREATED',
  'INTAKE_VALIDATED',
  'PLANNED',
  'WAITING_FOR_APPROVAL',
  'QUEUED',
  'DISPATCHED',
  'RUNNING',
  'VALIDATING',
  'COMPLETED',
  'CLOSED',
  'FAILED',
  'BLOCKED',
  'CANCELLED',
  'ROLLED_BACK',
  'HARAKIRI',
];

export const TRANSITIONS: Record<MissionState, MissionState[]> = {
  CREATED: ['INTAKE_VALIDATED', 'FAILED', 'CANCELLED', 'BLOCKED', 'HARAKIRI'],
  INTAKE_VALIDATED: ['PLANNED', 'FAILED', 'CANCELLED', 'BLOCKED', 'HARAKIRI'],
  PLANNED: ['WAITING_FOR_APPROVAL', 'QUEUED', 'FAILED', 'CANCELLED', 'BLOCKED', 'HARAKIRI'],
  WAITING_FOR_APPROVAL: ['QUEUED', 'BLOCKED', 'CANCELLED', 'FAILED', 'HARAKIRI'],
  QUEUED: ['DISPATCHED', 'CANCELLED', 'BLOCKED', 'FAILED', 'HARAKIRI'],
  DISPATCHED: ['RUNNING', 'FAILED', 'BLOCKED', 'CANCELLED', 'HARAKIRI'],
  RUNNING: ['VALIDATING', 'FAILED', 'BLOCKED', 'CANCELLED', 'HARAKIRI'],
  VALIDATING: ['COMPLETED', 'CLOSED', 'FAILED', 'BLOCKED', 'ROLLED_BACK', 'HARAKIRI'],
  COMPLETED: ['CLOSED', 'ROLLED_BACK', 'HARAKIRI'],
  CLOSED: ['ROLLED_BACK'],
  FAILED: ['QUEUED', 'ROLLED_BACK', 'CANCELLED', 'BLOCKED', 'HARAKIRI'],
  BLOCKED: ['QUEUED', 'CANCELLED', 'FAILED', 'HARAKIRI'],
  CANCELLED: [],
  ROLLED_BACK: [],
  HARAKIRI: ['ROLLED_BACK'],
};

export class LedgerEngine {
  private missions: Map<string, Mission> = new Map();
  private eventsList: LedgerEvent[] = [];

  constructor(initialMissions?: Mission[], initialEvents?: LedgerEvent[]) {
    if (initialMissions) {
      for (const m of initialMissions) {
        this.missions.set(m.mission_id, { ...m });
      }
    }
    if (initialEvents) {
      this.eventsList = initialEvents.map((e) => ({ ...e }));
    }
  }

  public getMissions(): Mission[] {
    return Array.from(this.missions.values());
  }

  public getEvents(missionId?: string): LedgerEvent[] {
    if (missionId) {
      return this.eventsList.filter((e) => e.mission_id === missionId);
    }
    return [...this.eventsList];
  }

  public getHeadHash(): string {
    if (this.eventsList.length === 0) return GENESIS_HASH;
    return this.eventsList[this.eventsList.length - 1].event_hash;
  }

  public createMission(missionId: string, title = '', actor = 'hermes'): LedgerEvent {
    const now = new Date().toISOString();
    const mission: Mission = {
      mission_id: missionId,
      title: title || missionId,
      state: 'CREATED',
      created_at: now,
      updated_at: now,
    };
    this.missions.set(missionId, mission);

    return this.appendEvent({
      mission_id: missionId,
      task_id: '',
      from_state: '',
      to_state: 'CREATED',
      actor,
      reason: 'mission created',
      evidence_refs: [],
    });
  }

  public transition(
    missionId: string,
    toState: MissionState,
    opts: {
      actor?: string;
      reason?: string;
      taskId?: string;
      evidenceRefs?: string[];
    } = {}
  ): LedgerEvent {
    const mission = this.missions.get(missionId);
    if (!mission) {
      throw new Error(`Unknown mission: ${missionId}`);
    }

    const fromState = mission.state;
    const allowed = TRANSITIONS[fromState] || [];
    if (!allowed.includes(toState)) {
      throw new Error(`${missionId}: ${fromState} -> ${toState} is not an allowed transition`);
    }

    if (toState === 'COMPLETED' && fromState !== 'VALIDATING') {
      throw new Error('COMPLETED is reachable only from VALIDATING state');
    }

    const refs = opts.evidenceRefs || [];
    if (toState === 'COMPLETED' && refs.length === 0) {
      throw new Error('COMPLETED requires at least one evidence reference');
    }

    const now = new Date().toISOString();
    mission.state = toState;
    mission.updated_at = now;

    return this.appendEvent({
      mission_id: missionId,
      task_id: opts.taskId || '',
      from_state: fromState,
      to_state: toState,
      actor: opts.actor || 'hermes',
      reason: opts.reason || `Transitioned to ${toState}`,
      evidence_refs: refs,
    });
  }

  public recordAudit(
    missionId: string,
    opts: {
      actor: string;
      reason: string;
      taskId?: string;
      evidenceRefs?: string[];
      marker?: string;
    }
  ): LedgerEvent {
    const marker = opts.marker || 'AUDIT';
    return this.appendEvent({
      mission_id: missionId,
      task_id: opts.taskId || '',
      from_state: marker,
      to_state: marker,
      actor: opts.actor,
      reason: opts.reason,
      evidence_refs: opts.evidenceRefs || [],
    });
  }

  private appendEvent(record: {
    mission_id: string;
    task_id: string;
    from_state: string;
    to_state: string;
    actor: string;
    reason: string;
    evidence_refs: string[];
  }): LedgerEvent {
    const previous = this.getHeadHash();
    const timestamp = new Date().toISOString();
    const payload = {
      mission_id: record.mission_id,
      task_id: record.task_id,
      from_state: record.from_state,
      to_state: record.to_state,
      timestamp,
      actor: record.actor,
      reason: record.reason,
      evidence_refs: record.evidence_refs,
      previous_event_hash: previous,
    };
    const eventHash = computePayloadHash(payload);

    const event: LedgerEvent = {
      seq: this.eventsList.length + 1,
      mission_id: record.mission_id,
      task_id: record.task_id,
      from_state: record.from_state,
      to_state: record.to_state,
      timestamp,
      actor: record.actor,
      reason: record.reason,
      evidence_refs: record.evidence_refs,
      previous_event_hash: previous,
      event_hash: eventHash,
    };

    this.eventsList.push(event);
    return event;
  }

  public verifyChain(): { ok: boolean; detail: string; totalEvents: number; brokenSeq?: number } {
    let previous = GENESIS_HASH;
    let count = 0;

    for (const event of this.eventsList) {
      if (event.previous_event_hash !== previous) {
        return {
          ok: false,
          detail: `seq ${event.seq}: previous hash mismatch (${event.previous_event_hash.slice(0, 12)}... vs expected ${previous.slice(0, 12)}...)`,
          totalEvents: this.eventsList.length,
          brokenSeq: event.seq,
        };
      }

      const payload = {
        mission_id: event.mission_id,
        task_id: event.task_id,
        from_state: event.from_state,
        to_state: event.to_state,
        timestamp: event.timestamp,
        actor: event.actor,
        reason: event.reason,
        evidence_refs: event.evidence_refs,
        previous_event_hash: event.previous_event_hash,
      };

      const computed = computePayloadHash(payload);
      if (computed !== event.event_hash) {
        return {
          ok: false,
          detail: `seq ${event.seq}: event hash integrity mismatch (data was tampered)`,
          totalEvents: this.eventsList.length,
          brokenSeq: event.seq,
        };
      }

      previous = event.event_hash;
      count++;
    }

    return {
      ok: true,
      detail: `Chain verified over ${count} hash-linked events`,
      totalEvents: count,
    };
  }
}
