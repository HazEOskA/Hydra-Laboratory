import { PermissionLevel, TaskItem, TaskStatus } from '../types';
import { computePayloadHash } from './crypto';

export class QueueEngine {
  private tasks: Map<string, TaskItem> = new Map();
  public maxActive = 1;

  constructor(initialTasks?: TaskItem[]) {
    if (initialTasks) {
      for (const t of initialTasks) {
        this.tasks.set(t.task_id, { ...t });
      }
    }
  }

  public getAll(): TaskItem[] {
    return Array.from(this.tasks.values()).sort((a, b) => a.priority - b.priority);
  }

  public get(taskId: string): TaskItem | undefined {
    return this.tasks.get(taskId);
  }

  public listByStatus(status?: TaskStatus): TaskItem[] {
    const list = this.getAll();
    if (status) {
      return list.filter((t) => t.status === status);
    }
    return list;
  }

  public activeCount(): number {
    return Array.from(this.tasks.values()).filter(
      (t) => t.status === 'DISPATCHED' || t.status === 'RUNNING' || t.status === 'VALIDATING'
    ).length;
  }

  public enqueue(
    taskId: string,
    missionId: string,
    taskType: string,
    opts: {
      payload?: Record<string, any>;
      priority?: number;
      permission?: PermissionLevel;
      dependsOn?: string[];
      maxAttempts?: number;
      timeoutSeconds?: number;
      idempotencyKey?: string;
    } = {}
  ): TaskItem {
    const perm = opts.permission || 'GREEN';
    const status: TaskStatus = perm === 'RED' ? 'WAITING_FOR_APPROVAL' : 'QUEUED';
    const now = new Date().toISOString();

    const idempotency =
      opts.idempotencyKey ||
      computePayloadHash({ taskId, missionId, taskType, payload: opts.payload || {} }).slice(0, 32);

    // Check live duplicates
    for (const t of this.tasks.values()) {
      if (
        t.idempotency_key === idempotency &&
        !['CANCELLED', 'DEAD_LETTER', 'FAILED'].includes(t.status)
      ) {
        throw new Error(`A live task already holds idempotency key '${idempotency}' (task: ${t.task_id})`);
      }
    }

    const task: TaskItem = {
      task_id: taskId,
      mission_id: missionId,
      type: taskType,
      priority: opts.priority ?? 50,
      permission: perm,
      status,
      payload: opts.payload || {},
      created_at: now,
      scheduled_at: now,
      attempt: 0,
      max_attempts: opts.maxAttempts || 3,
      timeout_seconds: opts.timeoutSeconds || 900,
      idempotency_key: idempotency,
      depends_on: opts.dependsOn || [],
      evidence_refs: [],
    };

    this.tasks.set(taskId, task);
    return task;
  }

  public claim(workerId = 'hermes-worker-01'): TaskItem | null {
    if (this.activeCount() >= this.maxActive) {
      return null;
    }

    const now = new Date();
    const queuedTasks = this.getAll().filter((t) => t.status === 'QUEUED');

    for (const task of queuedTasks) {
      // Check dependencies
      if (task.depends_on && task.depends_on.length > 0) {
        const met = task.depends_on.every((depId) => {
          const dep = this.tasks.get(depId);
          return dep && dep.status === 'COMPLETED';
        });
        if (!met) continue;
      }

      task.status = 'RUNNING';
      task.started_at = now.toISOString();
      task.attempt += 1;
      task.worker_id = workerId;
      return { ...task };
    }

    return null;
  }

  public approve(taskId: string, approver = 'OSA', expiresMinutes = 60): TaskItem {
    const task = this.tasks.get(taskId);
    if (!task) throw new Error(`Task '${taskId}' not found`);
    if (task.status !== 'WAITING_FOR_APPROVAL' && task.status !== 'BLOCKED') {
      throw new Error(`Task ${taskId} is not awaiting approval (current status: ${task.status})`);
    }

    const now = new Date();
    const expires = new Date(now.getTime() + expiresMinutes * 60 * 1000);

    task.approval = {
      approver,
      granted_at: now.toISOString(),
      expires_at: expires.toISOString(),
      scope: { task_id: taskId, type: task.type },
    };
    task.status = 'QUEUED';
    task.scheduled_at = now.toISOString();
    return { ...task };
  }

  public startValidation(taskId: string): TaskItem {
    const task = this.tasks.get(taskId);
    if (!task) throw new Error(`Task '${taskId}' not found`);
    task.status = 'VALIDATING';
    return { ...task };
  }

  public complete(taskId: string, evidenceRefs: string[]): TaskItem {
    const task = this.tasks.get(taskId);
    if (!task) throw new Error(`Task '${taskId}' not found`);
    if (!evidenceRefs || evidenceRefs.length === 0) {
      throw new Error('Completion requires at least one evidence reference');
    }
    task.status = 'COMPLETED';
    task.finished_at = new Date().toISOString();
    task.evidence_refs = evidenceRefs;
    task.worker_id = null;
    return { ...task };
  }

  public fail(taskId: string, error: string): TaskItem {
    const task = this.tasks.get(taskId);
    if (!task) throw new Error(`Task '${taskId}' not found`);
    task.last_error = error;

    if (task.attempt >= task.max_attempts) {
      task.status = 'DEAD_LETTER';
      task.finished_at = new Date().toISOString();
      task.worker_id = null;
    } else {
      task.status = 'QUEUED';
      task.started_at = null;
      task.worker_id = null;
      const backoffSec = Math.min(30 * Math.pow(2, Math.max(0, task.attempt - 1)), 3600);
      const retryAt = new Date(Date.now() + backoffSec * 1000);
      task.scheduled_at = retryAt.toISOString();
    }
    return { ...task };
  }

  public cancel(taskId: string, reason = 'cancelled by operator'): TaskItem {
    const task = this.tasks.get(taskId);
    if (!task) throw new Error(`Task '${taskId}' not found`);
    task.status = 'CANCELLED';
    task.finished_at = new Date().toISOString();
    task.last_error = reason;
    task.worker_id = null;
    return { ...task };
  }

  public recoverStale(): string[] {
    const recovered: string[] = [];
    for (const task of this.tasks.values()) {
      if (task.status === 'RUNNING') {
        task.status = 'QUEUED';
        task.started_at = null;
        task.worker_id = null;
        recovered.push(task.task_id);
      }
    }
    return recovered;
  }

  public getStats(): Record<TaskStatus, number> {
    const stats: Record<TaskStatus, number> = {
      QUEUED: 0,
      WAITING_FOR_APPROVAL: 0,
      DISPATCHED: 0,
      RUNNING: 0,
      VALIDATING: 0,
      COMPLETED: 0,
      FAILED: 0,
      BLOCKED: 0,
      CANCELLED: 0,
      DEAD_LETTER: 0,
    };
    for (const t of this.tasks.values()) {
      stats[t.status] = (stats[t.status] || 0) + 1;
    }
    return stats;
  }

  public getQueueLagSeconds(): number {
    const queued = this.getAll().filter((t) => t.status === 'QUEUED');
    if (queued.length === 0) return 0;
    const oldest = queued.reduce((min, t) => {
      const time = new Date(t.scheduled_at).getTime();
      return time < min ? time : min;
    }, Date.now());
    return Math.max(0, Math.floor((Date.now() - oldest) / 1000));
  }
}
