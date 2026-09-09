import React, { useState } from 'react';
import {
  Compass,
  Sparkles,
  ShieldCheck,
  AlertTriangle,
  CheckCircle2,
  Lock,
  ArrowRight,
  HelpCircle,
  FileCode,
  Layers,
  Send,
  RotateCcw,
} from 'lucide-react';
import { UnderstandingGateState } from '../types';

interface GatewayViewProps {
  onCompileGenesis: (genesis: any) => void;
  understandingState: UnderstandingGateState;
}

export const GatewayView: React.FC<GatewayViewProps> = ({
  onCompileGenesis,
  understandingState,
}) => {
  const [operatorIntent, setOperatorIntent] = useState(understandingState.raw_intent);
  const [currentScore, setCurrentScore] = useState(understandingState.understanding_score);
  const [goalClarity, setGoalClarity] = useState<'HIGH' | 'MEDIUM' | 'LOW'>(understandingState.goal_clarity);
  const [scopeBounded, setScopeBounded] = useState(understandingState.scope_bounded);
  const [forbiddenDefined, setForbiddenDefined] = useState(understandingState.forbidden_defined);
  const [successClear, setSuccessClear] = useState(understandingState.success_criteria_clear);
  const [compiledOutput, setCompiledOutput] = useState<any>(understandingState.compiled_genesis);
  const [verdict, setVerdict] = useState<'PASS' | 'ASK_USER' | 'BLOCKED'>(understandingState.verdict);
  const [clarifications, setClarifications] = useState<string[]>(understandingState.clarification_needed || []);

  const handleEvaluate = (text: string) => {
    setOperatorIntent(text);
    const lower = text.toLowerCase();

    if (lower.includes('wdróż na prod bez testów') || lower.includes('bypass') || lower.includes('wyłącz reguły')) {
      setCurrentScore(12);
      setGoalClarity('LOW');
      setScopeBounded(false);
      setForbiddenDefined(false);
      setSuccessClear(false);
      setVerdict('BLOCKED');
      setClarifications(['Naruszenie SOUL.md: Zakaz wdrażania na produkcję bez testów i zgody operatora.']);
      setCompiledOutput(null);
    } else if (lower.length < 20 || lower.includes('coś fajnego') || lower.includes('zrób cokolwiek')) {
      setCurrentScore(42);
      setGoalClarity('LOW');
      setScopeBounded(false);
      setForbiddenDefined(false);
      setSuccessClear(false);
      setVerdict('ASK_USER');
      setClarifications([
        'Brak precyzyjnego celu — podaj konkretny problem biznesowy.',
        'Brak zdefiniowanych granic (co wchodzi w scope, a co jest zabronione).',
        'Brak kryteriów sukcesu (jakie dowody Pinokio ma zweryfikować?).',
      ]);
      setCompiledOutput(null);
    } else {
      // Clear intent
      setCurrentScore(98);
      setGoalClarity('HIGH');
      setScopeBounded(true);
      setForbiddenDefined(true);
      setSuccessClear(true);
      setVerdict('PASS');
      setClarifications([]);
      const genesis = {
        goal: text,
        constraints: [
          'Nie zmieniać designu UI (zachować black/navy base, gold/purple accents)',
          'Nie usuwać istniejących funkcji',
          'Preview przed production na Google Cloud',
          'Zero mockowanych PASS — mechaniczna weryfikacja dowodów',
        ],
        scope: ['Frontend (React + Vite)', 'Hydra City API adapter', 'GCP preview telemetry', 'Notary ledger'],
        forbidden: [
          'Production deploy bez approval',
          'Fake telemetry / fake metric generators',
          'Usuwanie istniejących ekranów',
        ],
        required_evidence: [
          'Build PASS (exit code 0, dist bundle generated)',
          'API health PASS (HTTP 200 on preview URL)',
          'Browser smoke test PASS (responsive layout)',
          'Deployed Cloud Run revision recorded',
          'Source SHA hash-chained in Notary',
        ],
      };
      setCompiledOutput(genesis);
    }
  };

  const handleApplyPreset = (preset: 'PREVIEW' | 'VAGUE' | 'FORBIDDEN') => {
    if (preset === 'PREVIEW') {
      handleEvaluate('Podepnij aktualny frontend Hydry pod nową architekturę i wystaw preview na GCP.');
    } else if (preset === 'VAGUE') {
      handleEvaluate('Zrób mi coś fajnego z AI na szybko.');
    } else if (preset === 'FORBIDDEN') {
      handleEvaluate('Wdróż na prod bez testów i omiń bramki bezpieczeństwa.');
    }
  };

  return (
    <div className="space-y-6">
      {/* Header Banner */}
      <div className="bg-gradient-to-r from-[#030712] via-[#0b102b] to-[#030712] border border-amber-500/30 rounded-2xl p-6 shadow-xl">
        <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
          <div className="space-y-1.5">
            <div className="flex items-center gap-2.5">
              <span className="p-2 rounded-xl bg-amber-500/10 text-amber-400 border border-amber-500/30">
                <Compass className="w-5 h-5" />
              </span>
              <h2 className="text-lg font-bold font-mono text-amber-100 uppercase tracking-wider">
                ZGREDEK / CITY GATEWAY & UNDERSTANDING GATE
              </h2>
            </div>
            <p className="text-xs font-mono text-slate-300 max-w-3xl leading-relaxed">
              Pierwsza linia obrony Hydry. Zgredek przyjmuje intencję Operatora, bada spójność logiczną w{' '}
              <strong className="text-amber-300">Understanding Gate</strong>, pyta w razie niejasności (
              <span className="text-purple-300 font-semibold">ASK_USER</span>) i kompiluje niezmienne{' '}
              <strong className="text-emerald-300">Mission Genesis</strong> przed uruchomieniem jakiegokolwiek Work Cella.
            </p>
          </div>

          <div className="flex items-center gap-2 font-mono text-xs">
            <span className="px-3 py-1.5 rounded-xl bg-black/60 border border-amber-500/30 text-amber-300">
              Authority: <strong className="text-emerald-400">OPERATOR-DIRECT</strong>
            </span>
          </div>
        </div>
      </div>

      {/* Preset Intent Selectors */}
      <div className="flex items-center gap-2 flex-wrap font-mono text-xs">
        <span className="text-slate-400 mr-2">Przetestuj scenariusz:</span>
        <button
          onClick={() => handleApplyPreset('PREVIEW')}
          className="px-3 py-1.5 rounded-lg bg-black/60 hover:bg-amber-950/40 border border-amber-500/40 text-amber-200 hover:text-amber-100 transition cursor-pointer"
        >
          ✓ 1. Hydra UI & GCP Preview (Clear - PASS)
        </button>
        <button
          onClick={() => handleApplyPreset('VAGUE')}
          className="px-3 py-1.5 rounded-lg bg-black/60 hover:bg-purple-950/40 border border-purple-500/40 text-purple-200 hover:text-purple-100 transition cursor-pointer"
        >
          ? 2. 'Zrób coś fajnego' (Vague - ASK_USER)
        </button>
        <button
          onClick={() => handleApplyPreset('FORBIDDEN')}
          className="px-3 py-1.5 rounded-lg bg-black/60 hover:bg-rose-950/40 border border-rose-500/40 text-rose-200 hover:text-rose-100 transition cursor-pointer"
        >
          ✕ 3. 'Wdróż bez testów' (Forbidden - BLOCKED)
        </button>
      </div>

      {/* Main Grid: Intake Input & Live Gate Evaluation */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
        {/* Left 6 cols: Intake Form */}
        <div className="lg:col-span-6 space-y-4">
          <div className="bg-[#05091a] border border-amber-500/20 rounded-2xl p-5 shadow-md space-y-4">
            <div className="flex items-center justify-between border-b border-slate-800/80 pb-3">
              <span className="text-xs font-mono font-bold text-amber-300 uppercase tracking-wider flex items-center gap-2">
                <Sparkles className="w-4 h-4 text-amber-400" />
                <span>Operator Intent Input</span>
              </span>
              <span className="text-[10px] font-mono text-slate-400">Intake / Gateway v0.1</span>
            </div>

            <div>
              <label className="block text-xs font-mono text-slate-300 mb-1.5">
                Opisz cel lub zadanie dla miasta Hydra:
              </label>
              <textarea
                value={operatorIntent}
                onChange={(e) => handleEvaluate(e.target.value)}
                rows={5}
                className="w-full bg-black/70 border border-slate-700 focus:border-amber-400 rounded-xl p-3 text-xs font-mono text-amber-100 placeholder-slate-500 focus:outline-none transition"
                placeholder="Wpisz intencję..."
              />
            </div>

            <div className="flex items-center justify-between gap-3 pt-2">
              <button
                onClick={() => handleEvaluate(operatorIntent)}
                className="flex items-center gap-2 px-4 py-2 bg-slate-900 hover:bg-slate-800 border border-amber-500/30 text-amber-200 text-xs font-mono rounded-xl transition cursor-pointer font-semibold"
              >
                <RotateCcw className="w-3.5 h-3.5" />
                <span>Przelicz Gate</span>
              </button>

              {verdict === 'PASS' && compiledOutput && (
                <button
                  onClick={() => onCompileGenesis(compiledOutput)}
                  className="flex items-center gap-2 px-4 py-2 bg-gradient-to-r from-amber-500 to-amber-600 hover:from-amber-400 text-black text-xs font-mono font-bold rounded-xl shadow-md shadow-amber-500/20 transition cursor-pointer"
                >
                  <Lock className="w-3.5 h-3.5" />
                  <span>Kompiluj & Otwórz Genesis w Notariuszu</span>
                </button>
              )}
            </div>
          </div>
        </div>

        {/* Right 6 cols: Understanding Gate Evaluation Card */}
        <div className="lg:col-span-6 space-y-4">
          <div className="bg-[#05091a] border border-purple-500/20 rounded-2xl p-5 shadow-md space-y-4 font-mono">
            <div className="flex items-center justify-between border-b border-slate-800/80 pb-3">
              <div className="flex items-center gap-2">
                <ShieldCheck className="w-4 h-4 text-purple-400" />
                <span className="text-xs font-bold text-purple-300 uppercase tracking-wider">
                  Understanding Gate Scorecard
                </span>
              </div>

              <span
                className={`px-2.5 py-0.5 rounded-full text-xs font-bold ${
                  verdict === 'PASS'
                    ? 'bg-emerald-950/80 border border-emerald-500/40 text-emerald-300'
                    : verdict === 'ASK_USER'
                    ? 'bg-amber-950/80 border border-amber-500/40 text-amber-300'
                    : 'bg-rose-950/80 border border-rose-500/40 text-rose-300'
                }`}
              >
                {verdict} ({currentScore}/100)
              </span>
            </div>

            {/* Criteria checks */}
            <div className="space-y-2 text-xs">
              <div className="flex items-center justify-between p-2.5 rounded-xl bg-black/40 border border-slate-800/80">
                <span className="text-slate-300">Jasność celu (Goal Clarity):</span>
                <span
                  className={`font-semibold ${
                    goalClarity === 'HIGH'
                      ? 'text-emerald-400'
                      : goalClarity === 'MEDIUM'
                      ? 'text-amber-400'
                      : 'text-rose-400'
                  }`}
                >
                  {goalClarity}
                </span>
              </div>

              <div className="flex items-center justify-between p-2.5 rounded-xl bg-black/40 border border-slate-800/80">
                <span className="text-slate-300">Granice zakresu (Scope Bounded):</span>
                <span className={scopeBounded ? 'text-emerald-400 font-semibold' : 'text-rose-400 font-semibold'}>
                  {scopeBounded ? 'TAK (Ograniczony)' : 'NIE (Zbyt szeroki / brak)'}
                </span>
              </div>

              <div className="flex items-center justify-between p-2.5 rounded-xl bg-black/40 border border-slate-800/80">
                <span className="text-slate-300">Zdefiniowane zakazy (Forbidden Defined):</span>
                <span className={forbiddenDefined ? 'text-emerald-400 font-semibold' : 'text-rose-400 font-semibold'}>
                  {forbiddenDefined ? 'TAK (Blokady aktywne)' : 'NIE'}
                </span>
              </div>

              <div className="flex items-center justify-between p-2.5 rounded-xl bg-black/40 border border-slate-800/80">
                <span className="text-slate-300">Kryteria sukcesu i dowody (Evidence Clear):</span>
                <span className={successClear ? 'text-emerald-400 font-semibold' : 'text-rose-400 font-semibold'}>
                  {successClear ? 'TAK (Pinokio Gate)' : 'NIE'}
                </span>
              </div>
            </div>

            {/* Clarification Box if ASK_USER or BLOCKED */}
            {clarifications.length > 0 && (
              <div
                className={`p-3.5 rounded-xl border text-xs space-y-1.5 ${
                  verdict === 'ASK_USER'
                    ? 'bg-amber-950/30 border-amber-500/40 text-amber-200'
                    : 'bg-rose-950/30 border-rose-500/40 text-rose-200'
                }`}
              >
                <div className="font-bold flex items-center gap-1.5">
                  <HelpCircle className="w-3.5 h-3.5" />
                  <span>{verdict === 'ASK_USER' ? 'Wymagane doprecyzowanie (ASK_USER):' : 'Błąd walidacji / Blokada:'}</span>
                </div>
                <ul className="list-disc list-inside space-y-1 text-[11px] text-slate-300">
                  {clarifications.map((c, i) => (
                    <li key={i}>{c}</li>
                  ))}
                </ul>
              </div>
            )}
          </div>
        </div>
      </div>

      {/* Compiled Genesis Preview (When PASS) */}
      {compiledOutput && (
        <div className="bg-[#05091a] border border-amber-500/20 rounded-2xl p-6 shadow-md font-mono space-y-4">
          <div className="flex items-center justify-between border-b border-slate-800/80 pb-3">
            <div className="flex items-center gap-2">
              <FileCode className="w-4 h-4 text-amber-400" />
              <span className="text-xs font-bold text-amber-200 uppercase tracking-wider">
                Compiled Mission Genesis Contract (Niezmienna Umowa Misji)
              </span>
            </div>
            <span className="text-[10px] px-2.5 py-0.5 rounded bg-emerald-950 text-emerald-300 border border-emerald-800/60 font-semibold">
              READY TO LOCK
            </span>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-3 gap-4 text-xs">
            <div className="bg-black/50 border border-slate-800 rounded-xl p-3.5 space-y-2">
              <span className="text-amber-300 font-bold">Constraints:</span>
              <ul className="space-y-1 text-slate-300 text-[11px]">
                {compiledOutput.constraints?.map((c: string, idx: number) => (
                  <li key={idx} className="flex items-start gap-1">
                    <span className="text-amber-400">•</span>
                    <span>{c}</span>
                  </li>
                ))}
              </ul>
            </div>

            <div className="bg-black/50 border border-slate-800 rounded-xl p-3.5 space-y-2">
              <span className="text-purple-300 font-bold">Scope & Capabilities:</span>
              <ul className="space-y-1 text-slate-300 text-[11px]">
                {compiledOutput.scope?.map((s: string, idx: number) => (
                  <li key={idx} className="flex items-start gap-1">
                    <span className="text-purple-400">•</span>
                    <span>{s}</span>
                  </li>
                ))}
              </ul>
            </div>

            <div className="bg-black/50 border border-slate-800 rounded-xl p-3.5 space-y-2">
              <span className="text-emerald-300 font-bold">Required Evidence (Pinokio):</span>
              <ul className="space-y-1 text-slate-300 text-[11px]">
                {compiledOutput.required_evidence?.map((e: string, idx: number) => (
                  <li key={idx} className="flex items-start gap-1">
                    <span className="text-emerald-400">✓</span>
                    <span>{e}</span>
                  </li>
                ))}
              </ul>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};
