import React, { useState } from 'react';
import {
  ListTodo,
  Play,
  CheckCircle2,
  AlertOctagon,
  Clock,
  Plus,
  RotateCcw,
  Check,
  X,
  FileCheck,
  KeyRound,
  Filter,
} from 'lucide-react';
import { TaskItem, TaskStatus } from '../types';

interface QueueViewProps {
  tasks: TaskItem[];
  queueStats: Record<string, number>;
  onClaim: () => void;
  onApprove: (taskId: string, approver: string, expiresMinutes: number) => void;
  onValidate: (taskId: string) => void;
  onComplete: (taskId: string, evidenceRefs: string[]) => void;
  onFail: (taskId: string, error: string) => void;
  onCancel: (taskId: string) => void;
  onRecoverStale: () => void;
  onEnqueue: (
    taskId: string,
    missionId: string,
    type: string,
    permission: 'GREEN' | 'YELLOW' | 'RED',
    priority: number,
    payload: Record<string, any>,
    dependsOn: string[]
  ) => void;
}

export const QueueView: React.FC<QueueViewProps> = ({
  tasks,
  queueStats,
  onClaim,
  onApprove,
  onValidate,
  onComplete,
  onFail,
  onCancel,
  onRecoverStale,
  onEnqueue,
}) => {
  const [filterStatus, setFilterStatus] = useState<string>('ALL');
  const [showEnqueueModal, setShowEnqueueModal] = useState(false);
  const [showApproveModal, setShowApproveModal] = useState<TaskItem | null>(null);
  const [showCompleteModal, setShowCompleteModal] = useState<TaskItem | null>(null);

  // Enqueue form state
  const [newTaskId, setNewTaskId] = useState(`task-${Date.now().toString().slice(-4)}`);
  const [newMissionId, setNewMissionId] = useState('mission-003-continuous-ops');
  const [newType, setNewType] = useState('shell.inspect');
  const [newPermission, setNewPermission] = useState<'GREEN' | 'YELLOW' | 'RED'>('GREEN');
  const [newPriority, setNewPriority] = useState(50);
  const [newPayload, setNewPayload] = useState('{\n  "prompt": "Inspect worker state"\n}');
  const [newDependsOn, setNewDependsOn] = useState('');

  // Complete form state
  const [evidenceInput, setEvidenceInput] = useState('journal/evidence-run.log');

  // Approve form state
  const [approverName, setApproverName] = useState('OSA (Bartosz Osiński)');
  const [approvalExpires, setApprovalExpires] = useState(60);

  const filteredTasks = tasks.filter((t) => {
    if (filterStatus === 'ALL') return true;
    return t.status === filterStatus;
  });

  const handleEnqueueSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    try {
      let parsedPayload = {};
      try {
        parsedPayload = JSON.parse(newPayload);
      } catch {
        parsedPayload = { text: newPayload };
      }
      const deps = newDependsOn
        .split(',')
        .map((s) => s.trim())
        .filter(Boolean);
      onEnqueue(newTaskId, newMissionId, newType, newPermission, newPriority, parsedPayload, deps);
      setShowEnqueueModal(false);
      setNewTaskId(`task-${Date.now().toString().slice(-4)}`);
    } catch (err: any) {
      alert(`Enqueue error: ${err.message}`);
    }
  };

  const handleCompleteSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!showCompleteModal) return;
    const refs = evidenceInput
      .split('\n')
      .map((s) => s.trim())
      .filter(Boolean);
    if (refs.length === 0) {
      alert('Completion requires at least one evidence reference');
      return;
    }
    onComplete(showCompleteModal.task_id, refs);
    setShowCompleteModal(null);
  };

  const handleApproveSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!showApproveModal) return;
    onApprove(showApproveModal.task_id, approverName, approvalExpires);
    setShowApproveModal(null);
  };

  return (
    <div className="space-y-6">
      {/* Top Header & Actions */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 pb-2 border-b border-slate-800">
        <div>
          <h2 className="text-lg font-bold text-slate-100 flex items-center gap-2">
            <ListTodo className="w-5 h-5 text-sky-400" />
            Durable SQLite Task Queue & Runner
          </h2>
          <p className="text-xs text-slate-400 mt-1">
            ACID task scheduling, lease recovery, dependency checks, and scoped approvals.
          </p>
        </div>

        <div className="flex items-center gap-2">
          <button
            onClick={() => onClaim()}
            className="flex items-center gap-1.5 px-3 py-1.5 bg-sky-600 hover:bg-sky-500 text-white font-mono text-xs rounded-lg transition cursor-pointer"
          >
            <Play className="w-3.5 h-3.5" />
            <span>Claim Next</span>
          </button>
          <button
            onClick={() => onRecoverStale()}
            className="flex items-center gap-1.5 px-3 py-1.5 bg-slate-800 hover:bg-slate-700 text-slate-300 font-mono text-xs rounded-lg border border-slate-700 transition cursor-pointer"
            title="Release running tasks back to queued state"
          >
            <RotateCcw className="w-3.5 h-3.5" />
            <span>Recover Stale</span>
          </button>
          <button
            onClick={() => setShowEnqueueModal(true)}
            className="flex items-center gap-1.5 px-3 py-1.5 bg-emerald-700 hover:bg-emerald-600 text-white font-mono text-xs rounded-lg transition cursor-pointer"
          >
            <Plus className="w-3.5 h-3.5" />
            <span>Enqueue Task</span>
          </button>
        </div>
      </div>

      {/* Stats Bar */}
      <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-6 gap-3">
        {Object.entries(queueStats).map(([status, count]) => (
          <button
            key={status}
            onClick={() => setFilterStatus(filterStatus === status ? 'ALL' : status)}
            className={`p-3 rounded-lg border text-left transition cursor-pointer ${
              filterStatus === status
                ? 'bg-slate-800 border-sky-500'
                : 'bg-slate-900/80 border-slate-800 hover:border-slate-700'
            }`}
          >
            <div className="text-[11px] font-mono text-slate-400 truncate">{status}</div>
            <div className="text-xl font-bold font-mono text-slate-100 mt-1">{count}</div>
          </button>
        ))}
      </div>

      {/* Tasks Table */}
      <div className="bg-slate-900/80 border border-slate-800 rounded-xl overflow-hidden shadow-sm">
        <div className="p-3.5 border-b border-slate-800 flex items-center justify-between">
          <div className="flex items-center gap-2 text-xs font-mono text-slate-300">
            <Filter className="w-3.5 h-3.5 text-slate-400" />
            <span>Filter: <strong className="text-sky-300">{filterStatus}</strong></span>
            <span>({filteredTasks.length} tasks)</span>
          </div>

          {filterStatus !== 'ALL' && (
            <button
              onClick={() => setFilterStatus('ALL')}
              className="text-xs text-sky-400 hover:text-sky-300 font-mono cursor-pointer"
            >
              Clear Filter
            </button>
          )}
        </div>

        <div className="overflow-x-auto">
          <table className="w-full text-left text-xs font-mono">
            <thead className="bg-slate-950/80 text-slate-400 border-b border-slate-800">
              <tr>
                <th className="py-3 px-4">Priority / ID</th>
                <th className="py-3 px-4">Type & Mission</th>
                <th className="py-3 px-4">Permission</th>
                <th className="py-3 px-4">Status</th>
                <th className="py-3 px-4">Payload Summary</th>
                <th className="py-3 px-4 text-right">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-800/80 text-slate-300">
              {filteredTasks.length === 0 ? (
                <tr>
                  <td colSpan={6} className="py-8 text-center text-slate-500">
                    No tasks found matching filter '{filterStatus}'
                  </td>
                </tr>
              ) : (
                filteredTasks.map((t) => (
                  <tr key={t.task_id} className="hover:bg-slate-850/50">
                    <td className="py-3 px-4">
                      <div className="flex items-center gap-2">
                        <span className="w-6 h-6 rounded bg-slate-800 flex items-center justify-center font-bold text-slate-300">
                          {t.priority}
                        </span>
                        <div>
                          <div className="font-semibold text-slate-100">{t.task_id}</div>
                          <div className="text-[10px] text-slate-500">
                            Attempts: {t.attempt}/{t.max_attempts}
                          </div>
                        </div>
                      </div>
                    </td>

                    <td className="py-3 px-4">
                      <div className="font-semibold text-sky-300">{t.type}</div>
                      <div className="text-[10px] text-slate-500 truncate max-w-xs">{t.mission_id}</div>
                      {t.depends_on.length > 0 && (
                        <div className="text-[10px] text-amber-400/80">
                          Depends on: {t.depends_on.join(', ')}
                        </div>
                      )}
                    </td>

                    <td className="py-3 px-4">
                      <span
                        className={`px-2 py-0.5 rounded text-[11px] font-semibold ${
                          t.permission === 'GREEN'
                            ? 'bg-emerald-950 text-emerald-300 border border-emerald-800'
                            : t.permission === 'YELLOW'
                            ? 'bg-amber-950 text-amber-300 border border-amber-800'
                            : 'bg-rose-950 text-rose-300 border border-rose-800'
                        }`}
                      >
                        {t.permission}
                      </span>
                    </td>

                    <td className="py-3 px-4">
                      <span
                        className={`inline-flex items-center gap-1 px-2 py-0.5 rounded text-[11px] font-medium ${
                          t.status === 'COMPLETED'
                            ? 'bg-emerald-950/80 text-emerald-300 border border-emerald-800'
                            : t.status === 'RUNNING'
                            ? 'bg-sky-950/80 text-sky-300 border border-sky-800 animate-pulse'
                            : t.status === 'VALIDATING'
                            ? 'bg-purple-950/80 text-purple-300 border border-purple-800'
                            : t.status === 'WAITING_FOR_APPROVAL'
                            ? 'bg-rose-950/80 text-rose-300 border border-rose-800'
                            : t.status === 'QUEUED'
                            ? 'bg-slate-800 text-slate-300'
                            : 'bg-slate-900 text-slate-400 border border-slate-800'
                        }`}
                      >
                        {t.status}
                      </span>
                      {t.worker_id && (
                        <div className="text-[10px] text-slate-500 mt-0.5">Worker: {t.worker_id}</div>
                      )}
                    </td>

                    <td className="py-3 px-4 max-w-xs">
                      <p className="text-[11px] text-slate-300 truncate" title={JSON.stringify(t.payload)}>
                        {t.payload.prompt || t.payload.category || JSON.stringify(t.payload)}
                      </p>
                      {t.last_error && (
                        <p className="text-[10px] text-rose-400 truncate mt-0.5">Error: {t.last_error}</p>
                      )}
                      {t.evidence_refs.length > 0 && (
                        <p className="text-[10px] text-emerald-400 truncate mt-0.5">
                          Evidence: {t.evidence_refs.join(', ')}
                        </p>
                      )}
                      {t.approval && (
                        <p className="text-[10px] text-sky-400 truncate mt-0.5">
                          Approved by {t.approval.approver}
                        </p>
                      )}
                    </td>

                    <td className="py-3 px-4 text-right">
                      <div className="flex items-center justify-end gap-1.5">
                        {t.status === 'WAITING_FOR_APPROVAL' && (
                          <button
                            onClick={() => setShowApproveModal(t)}
                            className="px-2 py-1 bg-rose-700 hover:bg-rose-600 text-white rounded text-[11px] flex items-center gap-1 cursor-pointer"
                            title="Grant scoped approval (OSA)"
                          >
                            <KeyRound className="w-3 h-3" />
                            <span>Approve</span>
                          </button>
                        )}

                        {t.status === 'RUNNING' && (
                          <>
                            <button
                              onClick={() => onValidate(t.task_id)}
                              className="px-2 py-1 bg-purple-700 hover:bg-purple-600 text-white rounded text-[11px] flex items-center gap-1 cursor-pointer"
                              title="Transition to Validating state"
                            >
                              <CheckCircle2 className="w-3 h-3" />
                              <span>Validate</span>
                            </button>
                            <button
                              onClick={() => onFail(t.task_id, 'Manual failure triggered in UI')}
                              className="px-2 py-1 bg-rose-900/60 hover:bg-rose-800 text-rose-200 rounded text-[11px] cursor-pointer"
                              title="Trigger fail & backoff"
                            >
                              Fail
                            </button>
                          </>
                        )}

                        {t.status === 'VALIDATING' && (
                          <button
                            onClick={() => {
                              setShowCompleteModal(t);
                              setEvidenceInput(`docs/evidence-${t.task_id}.log`);
                            }}
                            className="px-2 py-1 bg-emerald-700 hover:bg-emerald-600 text-white rounded text-[11px] flex items-center gap-1 cursor-pointer"
                            title="Complete task with evidence seal"
                          >
                            <FileCheck className="w-3 h-3" />
                            <span>Seal Done</span>
                          </button>
                        )}

                        {['QUEUED', 'WAITING_FOR_APPROVAL'].includes(t.status) && (
                          <button
                            onClick={() => onCancel(t.task_id)}
                            className="px-2 py-1 bg-slate-800 hover:bg-slate-700 text-slate-400 rounded text-[11px] cursor-pointer"
                            title="Cancel task"
                          >
                            Cancel
                          </button>
                        )}
                      </div>
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </div>

      {/* Enqueue Modal */}
      {showEnqueueModal && (
        <div className="fixed inset-0 bg-black/70 backdrop-blur-sm z-50 flex items-center justify-center p-4">
          <div className="bg-slate-900 border border-slate-800 rounded-xl max-w-lg w-full p-5 space-y-4 shadow-2xl font-mono">
            <div className="flex items-center justify-between pb-2 border-b border-slate-800">
              <h3 className="text-sm font-semibold text-slate-100 flex items-center gap-2">
                <Plus className="w-4 h-4 text-emerald-400" />
                ENQUEUE TASK MANIFEST
              </h3>
              <button
                onClick={() => setShowEnqueueModal(false)}
                className="text-slate-400 hover:text-slate-200 cursor-pointer"
              >
                <X className="w-4 h-4" />
              </button>
            </div>

            <form onSubmit={handleEnqueueSubmit} className="space-y-3 text-xs">
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="block text-slate-400 mb-1">Task ID</label>
                  <input
                    type="text"
                    required
                    value={newTaskId}
                    onChange={(e) => setNewTaskId(e.target.value)}
                    className="w-full bg-slate-950 border border-slate-800 rounded px-2.5 py-1.5 text-slate-200"
                  />
                </div>
                <div>
                  <label className="block text-slate-400 mb-1">Mission ID</label>
                  <input
                    type="text"
                    required
                    value={newMissionId}
                    onChange={(e) => setNewMissionId(e.target.value)}
                    className="w-full bg-slate-950 border border-slate-800 rounded px-2.5 py-1.5 text-slate-200"
                  />
                </div>
              </div>

              <div className="grid grid-cols-3 gap-3">
                <div>
                  <label className="block text-slate-400 mb-1">Type</label>
                  <input
                    type="text"
                    required
                    value={newType}
                    onChange={(e) => setNewType(e.target.value)}
                    className="w-full bg-slate-950 border border-slate-800 rounded px-2.5 py-1.5 text-slate-200"
                    placeholder="shell.inspect"
                  />
                </div>
                <div>
                  <label className="block text-slate-400 mb-1">Permission</label>
                  <select
                    value={newPermission}
                    onChange={(e) => setNewPermission(e.target.value as any)}
                    className="w-full bg-slate-950 border border-slate-800 rounded px-2.5 py-1.5 text-slate-200"
                  >
                    <option value="GREEN">GREEN</option>
                    <option value="YELLOW">YELLOW</option>
                    <option value="RED">RED</option>
                  </select>
                </div>
                <div>
                  <label className="block text-slate-400 mb-1">Priority (1-100)</label>
                  <input
                    type="number"
                    value={newPriority}
                    onChange={(e) => setNewPriority(parseInt(e.target.value) || 50)}
                    className="w-full bg-slate-950 border border-slate-800 rounded px-2.5 py-1.5 text-slate-200"
                  />
                </div>
              </div>

              <div>
                <label className="block text-slate-400 mb-1">Depends On (comma-separated IDs)</label>
                <input
                  type="text"
                  value={newDependsOn}
                  onChange={(e) => setNewDependsOn(e.target.value)}
                  placeholder="010-runtime-heartbeat, task-02"
                  className="w-full bg-slate-950 border border-slate-800 rounded px-2.5 py-1.5 text-slate-200"
                />
              </div>

              <div>
                <label className="block text-slate-400 mb-1">Payload (JSON)</label>
                <textarea
                  rows={3}
                  value={newPayload}
                  onChange={(e) => setNewPayload(e.target.value)}
                  className="w-full bg-slate-950 border border-slate-800 rounded p-2.5 text-slate-200"
                />
              </div>

              <div className="flex justify-end gap-2 pt-2 border-t border-slate-800">
                <button
                  type="button"
                  onClick={() => setShowEnqueueModal(false)}
                  className="px-3 py-1.5 bg-slate-800 hover:bg-slate-700 text-slate-300 rounded cursor-pointer"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  className="px-4 py-1.5 bg-emerald-600 hover:bg-emerald-500 text-white font-semibold rounded cursor-pointer"
                >
                  Enqueue
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* Approve Modal */}
      {showApproveModal && (
        <div className="fixed inset-0 bg-black/70 backdrop-blur-sm z-50 flex items-center justify-center p-4">
          <div className="bg-slate-900 border border-rose-900 rounded-xl max-w-md w-full p-5 space-y-4 shadow-2xl font-mono">
            <div className="flex items-center justify-between pb-2 border-b border-slate-800">
              <h3 className="text-sm font-semibold text-rose-300 flex items-center gap-2">
                <KeyRound className="w-4 h-4 text-rose-400" />
                OSA SCOPED APPROVAL GRANT
              </h3>
              <button
                onClick={() => setShowApproveModal(null)}
                className="text-slate-400 hover:text-slate-200 cursor-pointer"
              >
                <X className="w-4 h-4" />
              </button>
            </div>

            <div className="text-xs text-slate-300 space-y-2 bg-slate-950 p-3 rounded border border-slate-800">
              <div>Task: <strong className="text-rose-300">{showApproveModal.task_id}</strong></div>
              <div>Type: <strong className="text-slate-200">{showApproveModal.type}</strong></div>
              <p className="text-[11px] text-slate-400">{JSON.stringify(showApproveModal.payload)}</p>
            </div>

            <form onSubmit={handleApproveSubmit} className="space-y-3 text-xs">
              <div>
                <label className="block text-slate-400 mb-1">Approver (Sovereign Authority)</label>
                <input
                  type="text"
                  required
                  value={approverName}
                  onChange={(e) => setApproverName(e.target.value)}
                  className="w-full bg-slate-950 border border-slate-800 rounded px-2.5 py-1.5 text-slate-200"
                />
              </div>

              <div>
                <label className="block text-slate-400 mb-1">Approval Expiration (Minutes)</label>
                <input
                  type="number"
                  required
                  value={approvalExpires}
                  onChange={(e) => setApprovalExpires(parseInt(e.target.value) || 60)}
                  className="w-full bg-slate-950 border border-slate-800 rounded px-2.5 py-1.5 text-slate-200"
                />
              </div>

              <div className="flex justify-end gap-2 pt-2 border-t border-slate-800">
                <button
                  type="button"
                  onClick={() => setShowApproveModal(null)}
                  className="px-3 py-1.5 bg-slate-800 hover:bg-slate-700 text-slate-300 rounded cursor-pointer"
                >
                  Reject / Cancel
                </button>
                <button
                  type="submit"
                  className="px-4 py-1.5 bg-rose-600 hover:bg-rose-500 text-white font-semibold rounded cursor-pointer"
                >
                  Grant Approval
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* Complete Task Evidence Modal */}
      {showCompleteModal && (
        <div className="fixed inset-0 bg-black/70 backdrop-blur-sm z-50 flex items-center justify-center p-4">
          <div className="bg-slate-900 border border-emerald-900 rounded-xl max-w-md w-full p-5 space-y-4 shadow-2xl font-mono">
            <div className="flex items-center justify-between pb-2 border-b border-slate-800">
              <h3 className="text-sm font-semibold text-emerald-300 flex items-center gap-2">
                <FileCheck className="w-4 h-4 text-emerald-400" />
                SEAL TASK WITH EVIDENCE
              </h3>
              <button
                onClick={() => setShowCompleteModal(null)}
                className="text-slate-400 hover:text-slate-200 cursor-pointer"
              >
                <X className="w-4 h-4" />
              </button>
            </div>

            <p className="text-xs text-slate-300">
              Per SOUL.md Principle 4: <em>"A claim without evidence is unverified."</em> Provide log paths or test seals.
            </p>

            <form onSubmit={handleCompleteSubmit} className="space-y-3 text-xs">
              <div>
                <label className="block text-slate-400 mb-1">Evidence References (one per line)</label>
                <textarea
                  rows={3}
                  required
                  value={evidenceInput}
                  onChange={(e) => setEvidenceInput(e.target.value)}
                  placeholder="journal/evidence-run.log&#10;tests/output.json"
                  className="w-full bg-slate-950 border border-slate-800 rounded p-2.5 text-slate-200"
                />
              </div>

              <div className="flex justify-end gap-2 pt-2 border-t border-slate-800">
                <button
                  type="button"
                  onClick={() => setShowCompleteModal(null)}
                  className="px-3 py-1.5 bg-slate-800 hover:bg-slate-700 text-slate-300 rounded cursor-pointer"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  className="px-4 py-1.5 bg-emerald-600 hover:bg-emerald-500 text-white font-semibold rounded cursor-pointer"
                >
                  Record Done in Ledger
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
};
