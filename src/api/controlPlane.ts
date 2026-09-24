import type { LedgerEvent, Mission, TaskItem } from '../types';

export interface WorkerSnapshot {
  task_id: string;
  mission_id: string;
  worker_id: string | null;
  heartbeat_at: string | null;
  status: string;
}

export interface ControlPlaneSnapshot {
  mode: 'LIVE_CONTROL_PLANE';
  source_of_truth: {
    missions: string;
    queue: string;
    evidence: string;
  };
  missions: Mission[];
  tasks: TaskItem[];
  workers: WorkerSnapshot[];
  events: LedgerEvent[];
  queue_stats: Record<string, number>;
  queue_lag_seconds: number;
  chain: {
    ok: boolean;
    detail: string;
  };
}

const env = ((import.meta as any).env || {}) as Record<string, string | undefined>;
export const HYDRA_API_BASE = String(
  env.VITE_HYDRA_API_URL || 'http://127.0.0.1:8787'
).replace(/\/$/, '');

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(HYDRA_API_BASE + path, {
    ...init,
    headers: {
      'Content-Type': 'application/json',
      ...(init?.headers || {}),
    },
  });

  let payload: any = {};
  try {
    payload = await response.json();
  } catch {
    payload = {};
  }

  if (!response.ok) {
    const detail = payload.detail || payload.error || ('HTTP ' + response.status);
    throw new Error(String(detail));
  }

  return payload as T;
}

export async function fetchControlPlaneSnapshot(): Promise<ControlPlaneSnapshot> {
  return request<ControlPlaneSnapshot>('/api/v1/snapshot');
}

export async function createLiveMission(title: string): Promise<ControlPlaneSnapshot> {
  const payload = await request<{ snapshot: ControlPlaneSnapshot }>('/api/v1/missions', {
    method: 'POST',
    body: JSON.stringify({ title }),
  });
  return payload.snapshot;
}

export async function runNextLiveTask(): Promise<ControlPlaneSnapshot> {
  const payload = await request<{ snapshot: ControlPlaneSnapshot }>('/api/v1/run-next', {
    method: 'POST',
    body: '{}',
  });
  return payload.snapshot;
}
