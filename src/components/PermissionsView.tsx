import React, { useState } from 'react';
import {
  ShieldCheck,
  AlertTriangle,
  CheckCircle2,
  XCircle,
  HelpCircle,
  Play,
  FileCode,
  Lock,
  Search,
  Flame,
  Check,
  X,
  FileCheck,
  RotateCcw,
  Zap,
} from 'lucide-react';
import { Decision, PermissionLevel, PinokioClaim, TaskItem } from '../types';
import { PermissionClassifier } from '../engine/permissionsEngine';
import { RED_PATTERNS, TOOLS_REGISTRY } from '../engine/toolsData';

interface PermissionsViewProps {
  classifier: PermissionClassifier;
  waitingTasks?: TaskItem[];
  pinokioClaims?: PinokioClaim[];
  onApproveTask?: (taskId: string, approver: string) => void;
  onRejectTask?: (taskId: string, reason: string) => void;
  onVerifyClaim?: (claimId: string) => void;
  onTriggerHarakiriDrill?: () => void;
}

export const PermissionsView: React.FC<PermissionsViewProps> = ({
  classifier,
  waitingTasks = [],
  pinokioClaims = [],
  onApproveTask,
  onRejectTask,
  onVerifyClaim,
  onTriggerHarakiriDrill,
}) => {
  const [selectedTool, setSelectedTool] = useState<string>('email');
  const [selectedAction, setSelectedAction] = useState<string>('send');
  const [payloadText, setPayloadText] = useState<string>(
    JSON.stringify({ recipient: 'external@prospect.example', subject: 'Product Offer' }, null, 2)
  );
  const [hasRollback, setHasRollback] = useState<boolean>(false);
  const [classificationResult, setClassificationResult] = useState<Decision | null>(() => {
    try {
      return classifier.classify('email', 'send', { recipient: 'external@prospect.example' }, false);
    } catch {
      return null;
    }
  });
  const [toolSearch, setToolSearch] = useState('');
  const [harakiriStatus, setHarakiriStatus] = useState<string | null>(null);

  const toolNames = classifier.knownTools();
  const currentSpec = classifier.toolSpec(selectedTool);
  const availableActions = currentSpec?.actions ? Object.keys(currentSpec.actions) : ['run', 'inspect', 'execute'];

  const handleClassify = () => {
    try {
      let parsedPayload = {};
      try {
        parsedPayload = JSON.parse(payloadText);
      } catch {
        parsedPayload = { raw: payloadText };
      }
      const res = classifier.classify(selectedTool, selectedAction, parsedPayload, hasRollback);
      setClassificationResult(res);
    } catch (e: any) {
      alert(`Classification error: ${e.message}`);
    }
  };

  const handleHarakiriDrill = () => {
    setHarakiriStatus('DRILL EXECUTED: All active Work Cells halted. Checkpoints flushed to Notary.');
    if (onTriggerHarakiriDrill) onTriggerHarakiriDrill();
    setTimeout(() => setHarakiriStatus(null), 6000);
  };

  const filteredTools = toolNames.filter(
    (t) =>
      t.toLowerCase().includes(toolSearch.toLowerCase()) ||
      TOOLS_REGISTRY[t]?.description.toLowerCase().includes(toolSearch.toLowerCase())
  );

  return (
    <div className="space-y-6">
      {/* Top Header */}
      <div className="bg-gradient-to-r from-[#030712] via-[#090e24] to-[#030712] border border-amber-500/30 rounded-2xl p-6 shadow-xl font-mono">
        <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
          <div className="space-y-1.5">
            <div className="flex items-center gap-2.5">
              <span className="p-2 rounded-xl bg-amber-500/10 text-amber-400 border border-amber-500/30">
                <ShieldCheck className="w-5 h-5" />
              </span>
              <h2 className="text-lg font-bold text-amber-100 uppercase tracking-wider">
                GOVERNMENT & HYPERLOCK GATE (PERMISSION ENGINE)
              </h2>
            </div>
            <p className="text-xs text-slate-300 max-w-3xl leading-relaxed">
              Zasada: <strong className="text-amber-300">NO ACTION WITHOUT AUTHORITY</strong> oraz{' '}
              <strong className="text-purple-300">NO ACTION OUTSIDE MISSION SCOPE</strong>.
              Akcje <span className="text-emerald-400 font-bold">GREEN</span> wykonują się autonomicznie,{' '}
              <span className="text-amber-400 font-bold">YELLOW</span> wymagają audytu i rollbacku, a{' '}
              <span className="text-rose-400 font-bold">RED</span> blokują wykonanie do momentu zatwierdzenia przez Operatora.
            </p>
          </div>

          <div className="flex items-center gap-2 text-xs">
            <span className="px-2.5 py-1 rounded-xl bg-emerald-950/80 text-emerald-300 border border-emerald-500/40">
              GREEN: Auto
            </span>
            <span className="px-2.5 py-1 rounded-xl bg-amber-950/80 text-amber-300 border border-amber-500/40">
              YELLOW: Audit
            </span>
            <span className="px-2.5 py-1 rounded-xl bg-rose-950/80 text-rose-300 border border-rose-500/40">
              RED: Operator
            </span>
          </div>
        </div>
      </div>

      {/* Harakiri Alert if triggered */}
      {harakiriStatus && (
        <div className="p-4 rounded-xl bg-rose-950/80 border border-rose-500 text-rose-200 text-xs font-mono flex items-center justify-between animate-bounce">
          <div className="flex items-center gap-2">
            <Flame className="w-4 h-4 text-rose-400" />
            <span>{harakiriStatus}</span>
          </div>
          <span className="text-[10px] text-rose-300">SAFE ISOLATION CONFIRMED</span>
        </div>
      )}

      {/* Waiting Approvals Queue (RED & YELLOW GATE) */}
      {waitingTasks.length > 0 && (
        <div className="bg-[#05091a] border border-rose-500/40 rounded-2xl p-5 shadow-lg space-y-4 font-mono">
          <div className="flex items-center justify-between border-b border-slate-800/80 pb-3">
            <div className="flex items-center gap-2 text-rose-400 font-bold text-xs uppercase tracking-wider">
              <AlertTriangle className="w-4 h-4 text-rose-400" />
              <span>Oczekujące Zatwierdzenia Operatora ({waitingTasks.length})</span>
            </div>
            <span className="text-[10px] px-2 py-0.5 rounded bg-rose-950 text-rose-300 border border-rose-800 font-bold">
              SCOPED RED GATE
            </span>
          </div>

          <div className="space-y-3">
            {waitingTasks.map((task) => (
              <div
                key={task.task_id}
                className="bg-black/60 border border-rose-500/30 rounded-xl p-4 flex flex-col sm:flex-row sm:items-center justify-between gap-4"
              >
                <div className="space-y-1">
                  <div className="flex items-center gap-2">
                    <span className="text-xs font-bold text-amber-200">{task.task_id}</span>
                    <span className="text-[10px] px-2 py-0.2 rounded bg-rose-950 text-rose-300 border border-rose-700 font-bold">
                      {task.permission}
                    </span>
                    <span className="text-xs text-slate-400">Typ: {task.type}</span>
                  </div>
                  <div className="text-xs text-slate-300">
                    Misja: <strong className="text-purple-300">{task.mission_id}</strong>
                  </div>
                  <div className="text-[11px] text-slate-400 font-mono truncate max-w-xl">
                    Payload: {JSON.stringify(task.payload)}
                  </div>
                </div>

                <div className="flex items-center gap-2 shrink-0">
                  <button
                    onClick={() => onApproveTask && onApproveTask(task.task_id, 'OSA')}
                    className="px-3.5 py-2 bg-emerald-600 hover:bg-emerald-500 text-white text-xs font-bold rounded-xl shadow transition cursor-pointer flex items-center gap-1.5"
                  >
                    <Check className="w-3.5 h-3.5" />
                    <span>Zatwierdź (Grant)</span>
                  </button>

                  <button
                    onClick={() => onRejectTask && onRejectTask(task.task_id, 'Operator rejected')}
                    className="px-3.5 py-2 bg-rose-950/80 hover:bg-rose-900 border border-rose-600/40 text-rose-300 text-xs font-bold rounded-xl transition cursor-pointer flex items-center gap-1.5"
                  >
                    <X className="w-3.5 h-3.5" />
                    <span>Odrzuć</span>
                  </button>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Pinokio Proof Verification Matrix */}
      <div className="bg-[#05091a] border border-emerald-500/30 rounded-2xl p-6 shadow-md font-mono space-y-4">
        <div className="flex items-center justify-between border-b border-slate-800/80 pb-3">
          <div className="flex items-center gap-2">
            <FileCheck className="w-4 h-4 text-emerald-400" />
            <span className="text-xs font-bold text-emerald-300 uppercase tracking-wider">
              Pinokio Verifier — Rejestr Roszczeń i Mechaniczna Weryfikacja
            </span>
          </div>
          <span className="text-[10px] text-slate-400">Claim != Fact without Evidence</span>
        </div>

        <div className="grid grid-cols-1 gap-3">
          {pinokioClaims.map((claim) => (
            <div
              key={claim.claim_id}
              className="bg-black/50 border border-slate-800 rounded-xl p-3.5 flex flex-col md:flex-row md:items-center justify-between gap-3"
            >
              <div className="space-y-1">
                <div className="flex items-center gap-2 flex-wrap">
                  <span className="text-xs font-bold text-amber-200">{claim.claim_id}</span>
                  <span className="text-xs text-slate-300 font-bold">{claim.claim_text}</span>
                  <span className="text-[10px] text-slate-400">({claim.worker_name})</span>
                </div>
                <div className="text-[11px] text-slate-400 flex items-center gap-3 flex-wrap">
                  <span>Komenda: <code className="text-purple-300 font-mono">{claim.command_executed}</code></span>
                  {claim.exit_code !== undefined && <span>Exit code: <strong className={claim.exit_code === 0 ? 'text-emerald-400' : 'text-rose-400'}>{claim.exit_code}</strong></span>}
                </div>
                {claim.artifact_path && (
                  <div className="text-[10px] text-slate-400 truncate max-w-2xl">
                    Artefakt: <span className="text-amber-300/80">{claim.artifact_path}</span>
                  </div>
                )}
              </div>

              <div className="flex items-center gap-2 shrink-0">
                <span
                  className={`text-[10px] px-2.5 py-1 rounded-full font-bold border ${
                    claim.verification_level === 'MECHANICALLY_VERIFIED' || claim.verification_level === 'INDEPENDENTLY_VERIFIED'
                      ? 'bg-emerald-950/80 text-emerald-300 border-emerald-500/40'
                      : claim.verification_level === 'REJECTED'
                      ? 'bg-rose-950/80 text-rose-300 border-rose-500/40'
                      : 'bg-amber-950/80 text-amber-300 border-amber-500/40'
                  }`}
                >
                  {claim.verification_level}
                </span>

                {claim.verification_level === 'CLAIMED' && (
                  <button
                    onClick={() => onVerifyClaim && onVerifyClaim(claim.claim_id)}
                    className="px-2.5 py-1 bg-emerald-950 hover:bg-emerald-900 border border-emerald-600/40 text-emerald-300 text-[10px] font-bold rounded-lg transition cursor-pointer"
                  >
                    Zweryfikuj
                  </button>
                )}
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* Simulator Section */}
      <div className="bg-[#05091a] border border-amber-500/20 rounded-2xl p-6 shadow-md space-y-4 font-mono">
        <div className="flex items-center justify-between border-b border-slate-800/80 pb-3">
          <h3 className="text-xs font-bold text-amber-200 uppercase tracking-wider flex items-center gap-2">
            <Play className="w-4 h-4 text-amber-400" />
            <span>Interactive Permission Classifier Probe</span>
          </h3>
          <span className="text-xs text-slate-400">hermesctl permissions classify</span>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          {/* Tool selector */}
          <div>
            <label className="block text-xs text-slate-300 mb-1">Narzędzie (Tool):</label>
            <select
              value={selectedTool}
              onChange={(e) => {
                setSelectedTool(e.target.value);
                const spec = classifier.toolSpec(e.target.value);
                if (spec?.actions) {
                  setSelectedAction(Object.keys(spec.actions)[0]);
                }
              }}
              className="w-full bg-black/70 border border-slate-700 rounded-xl px-3 py-2 text-xs text-amber-100 focus:outline-none focus:border-amber-400"
            >
              {toolNames.map((t) => (
                <option key={t} value={t}>
                  {t} — {TOOLS_REGISTRY[t]?.description.slice(0, 30)}...
                </option>
              ))}
            </select>
          </div>

          {/* Action selector */}
          <div>
            <label className="block text-xs text-slate-300 mb-1">Akcja (Action):</label>
            <select
              value={selectedAction}
              onChange={(e) => setSelectedAction(e.target.value)}
              className="w-full bg-black/70 border border-slate-700 rounded-xl px-3 py-2 text-xs text-amber-100 focus:outline-none focus:border-amber-400"
            >
              {availableActions.map((a) => (
                <option key={a} value={a}>
                  {a}
                </option>
              ))}
            </select>
          </div>

          {/* Rollback checkbox */}
          <div className="flex items-end pb-2">
            <label className="flex items-center gap-2 text-xs text-slate-300 cursor-pointer">
              <input
                type="checkbox"
                checked={hasRollback}
                onChange={(e) => setHasRollback(e.target.checked)}
                className="w-4 h-4 rounded border-slate-700 bg-black text-amber-500 focus:ring-0 cursor-pointer"
              />
              <span>Dostępny plan rollbacku</span>
            </label>
          </div>
        </div>

        {/* Payload JSON input */}
        <div>
          <label className="block text-xs text-slate-300 mb-1">Payload (JSON lub tekst):</label>
          <textarea
            value={payloadText}
            onChange={(e) => setPayloadText(e.target.value)}
            rows={3}
            className="w-full bg-black/70 border border-slate-700 focus:border-amber-400 rounded-xl p-2.5 text-xs text-amber-100 focus:outline-none font-mono"
          />
        </div>

        <div className="flex items-center justify-between">
          <button
            onClick={handleClassify}
            className="px-4 py-2 bg-gradient-to-r from-amber-500 to-amber-600 hover:from-amber-400 text-black text-xs font-bold rounded-xl shadow-md transition cursor-pointer"
          >
            Sklasyfikuj Uprawnienie
          </button>

          <button
            onClick={handleHarakiriDrill}
            className="px-4 py-2 bg-rose-950/80 hover:bg-rose-900 border border-rose-600/40 text-rose-300 text-xs font-bold rounded-xl transition cursor-pointer flex items-center gap-1.5"
          >
            <Flame className="w-3.5 h-3.5 text-rose-400" />
            <span>Harakiri Isolation Drill</span>
          </button>
        </div>

        {/* Classification Result Card */}
        {classificationResult && (
          <div
            className={`p-4 rounded-xl border font-mono text-xs space-y-2 mt-4 ${
              classificationResult.permission === 'GREEN'
                ? 'bg-emerald-950/30 border-emerald-500/40 text-emerald-200'
                : classificationResult.permission === 'YELLOW'
                ? 'bg-amber-950/30 border-amber-500/40 text-amber-200'
                : 'bg-rose-950/30 border-rose-500/40 text-rose-200'
            }`}
          >
            <div className="flex items-center justify-between">
              <span className="font-bold uppercase tracking-wider text-sm flex items-center gap-2">
                Poziom: {classificationResult.permission}
              </span>
              <span className="text-[10px] px-2 py-0.5 rounded bg-black/60 font-mono">
                Plan: {classificationResult.dispatch_plan}
              </span>
            </div>

            <div>Powód: {classificationResult.reason}</div>
            <div className="text-[10px] text-slate-400">
              Dopasowana reguła: <code>{classificationResult.matched_rule}</code> &bull; Idempotency:{' '}
              <code>{classificationResult.idempotency_key}</code>
            </div>
          </div>
        )}
      </div>
    </div>
  );
};
