import React, { useState } from 'react';
import {
  Network,
  Cpu,
  CheckCircle2,
  AlertTriangle,
  XCircle,
  Play,
  Activity,
  Layers,
  Shield,
} from 'lucide-react';
import { ModelCapability, ProviderHealthStatus, RoutingDecision } from '../types';
import { TASK_CLASSES } from '../engine/modelsData';
import { ModelRouterEngine } from '../engine/routerEngine';

interface RouterViewProps {
  routerEngine: ModelRouterEngine;
  onHealthChange: () => void;
}

export const RouterView: React.FC<RouterViewProps> = ({ routerEngine, onHealthChange }) => {
  const [selectedTaskClass, setSelectedTaskClass] = useState<string>('CODE_GENERATION');
  const [selectedCaps, setSelectedCaps] = useState<ModelCapability[]>(['code', 'reasoning']);
  const [contextTokens, setContextTokens] = useState<number>(16000);
  const [privateOnly, setPrivateOnly] = useState<boolean>(false);
  const [excludedModel, setExcludedModel] = useState<string>('');

  const [routingResult, setRoutingResult] = useState<RoutingDecision | null>(() => {
    return routerEngine.select('CODE_GENERATION', {
      requiredCapabilities: ['code', 'reasoning'],
      contextTokens: 16000,
    });
  });

  const catalog = routerEngine.getModels();
  const healthTable = routerEngine.getHealthTable();

  const handleSimulate = () => {
    const res = routerEngine.select(selectedTaskClass, {
      requiredCapabilities: selectedCaps,
      contextTokens: contextTokens > 0 ? contextTokens : undefined,
      privateOnly,
      exclude: excludedModel ? [excludedModel] : [],
    });
    setRoutingResult(res);
  };

  const handleToggleHealth = (model: string, newStatus: ProviderHealthStatus) => {
    routerEngine.setProviderHealth(model, newStatus, newStatus === 'DOWN' ? 0 : 250);
    onHealthChange();
    handleSimulate();
  };

  const allCapabilities: ModelCapability[] = [
    'text',
    'reasoning',
    'code',
    'tools',
    'long_context',
    'classification',
    'vision',
  ];

  const toggleCap = (cap: ModelCapability) => {
    if (selectedCaps.includes(cap)) {
      setSelectedCaps(selectedCaps.filter((c) => c !== cap));
    } else {
      setSelectedCaps([...selectedCaps, cap]);
    }
  };

  return (
    <div className="space-y-6">
      {/* Top Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 pb-2 border-b border-slate-800">
        <div>
          <h2 className="text-lg font-bold text-slate-100 flex items-center gap-2">
            <Network className="w-5 h-5 text-sky-400" />
            Model Router & Capability-Aware Fallback Pool
          </h2>
          <p className="text-xs text-slate-400 mt-1">
            Walks task fallback chains and strictly BLOCKS with reason rather than substituting an incapable model.
          </p>
        </div>

        <div className="text-xs font-mono text-slate-400 bg-slate-900 border border-slate-800 px-3 py-1.5 rounded-lg">
          Inference Endpoint: <code className="text-sky-300">https://inference.local:4000/v1</code>
        </div>
      </div>

      {/* Simulator Card */}
      <div className="bg-slate-900/80 border border-slate-800 rounded-xl p-5 shadow-sm space-y-4">
        <div className="flex items-center justify-between">
          <h3 className="text-sm font-semibold text-slate-200 font-mono flex items-center gap-2">
            <Play className="w-4 h-4 text-emerald-400" />
            ROUTING DECISION SIMULATOR
          </h3>
          <span className="text-xs font-mono text-slate-400">hermesctl models route</span>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
          {/* Task Class */}
          <div>
            <label className="block text-xs font-mono text-slate-400 mb-1">Task Class</label>
            <select
              value={selectedTaskClass}
              onChange={(e) => setSelectedTaskClass(e.target.value)}
              className="w-full bg-slate-950 border border-slate-800 rounded-lg px-3 py-2 text-xs font-mono text-slate-200 focus:outline-none focus:border-sky-500"
            >
              {TASK_CLASSES.map((tc) => (
                <option key={tc} value={tc}>
                  {tc}
                </option>
              ))}
            </select>
          </div>

          {/* Context Token Window Demand */}
          <div>
            <label className="block text-xs font-mono text-slate-400 mb-1">Context Tokens</label>
            <input
              type="number"
              value={contextTokens}
              onChange={(e) => setContextTokens(parseInt(e.target.value) || 0)}
              className="w-full bg-slate-950 border border-slate-800 rounded-lg px-3 py-2 text-xs font-mono text-slate-200 focus:outline-none focus:border-sky-500"
              step={8000}
            />
          </div>

          {/* Exclude previous failed model */}
          <div>
            <label className="block text-xs font-mono text-slate-400 mb-1">Exclude Failed Model</label>
            <select
              value={excludedModel}
              onChange={(e) => setExcludedModel(e.target.value)}
              className="w-full bg-slate-950 border border-slate-800 rounded-lg px-3 py-2 text-xs font-mono text-slate-200 focus:outline-none focus:border-sky-500"
            >
              <option value="">None (fresh attempt)</option>
              {Object.keys(catalog).map((m) => (
                <option key={m} value={m}>
                  {m}
                </option>
              ))}
            </select>
          </div>

          {/* Simulate Action Button */}
          <div className="flex flex-col justify-end gap-2">
            <label className="flex items-center gap-2 text-xs font-mono text-slate-300 cursor-pointer">
              <input
                type="checkbox"
                checked={privateOnly}
                onChange={(e) => setPrivateOnly(e.target.checked)}
                className="rounded bg-slate-950 border-slate-800 text-sky-500 focus:ring-0"
              />
              <span>Strict local / private only</span>
            </label>

            <button
              onClick={handleSimulate}
              className="w-full py-2 px-4 bg-sky-600 hover:bg-sky-500 text-white font-semibold text-xs font-mono rounded-lg transition cursor-pointer flex items-center justify-center gap-2"
            >
              <Network className="w-4 h-4" />
              <span>Evaluate Route</span>
            </button>
          </div>
        </div>

        {/* Required Capabilities Pills */}
        <div>
          <label className="block text-xs font-mono text-slate-400 mb-1.5">
            Required Capabilities (Must be strictly satisfied by model)
          </label>
          <div className="flex flex-wrap gap-2">
            {allCapabilities.map((cap) => {
              const active = selectedCaps.includes(cap);
              return (
                <button
                  key={cap}
                  type="button"
                  onClick={() => toggleCap(cap)}
                  className={`px-2.5 py-1 rounded-md text-xs font-mono transition cursor-pointer ${
                    active
                      ? 'bg-sky-950 text-sky-300 border border-sky-700 font-semibold'
                      : 'bg-slate-950 text-slate-400 border border-slate-800 hover:border-slate-700'
                  }`}
                >
                  {cap}
                </button>
              );
            })}
          </div>
        </div>

        {/* Decision Trace Result */}
        {routingResult && (
          <div
            className={`border rounded-lg p-4 font-mono text-xs space-y-3 transition-all ${
              routingResult.status === 'ROUTED'
                ? 'bg-emerald-950/40 border-emerald-800 text-emerald-200'
                : routingResult.status === 'DEGRADED'
                ? 'bg-amber-950/40 border-amber-800 text-amber-200'
                : 'bg-rose-950/40 border-rose-800 text-rose-200'
            }`}
          >
            <div className="flex flex-wrap items-center justify-between gap-2 border-b border-current/20 pb-2">
              <div className="flex items-center gap-2">
                <span className="font-bold text-sm">STATUS: {routingResult.status}</span>
                {routingResult.selected && (
                  <span className="px-2 py-0.5 rounded bg-black/40 text-xs font-bold text-slate-100">
                    → {routingResult.selected} ({routingResult.provider})
                  </span>
                )}
              </div>
              <span className="text-[11px] opacity-80">
                Considered {routingResult.considered.length} models in chain
              </span>
            </div>

            <div className="text-xs">
              <span className="opacity-75">Decision Reason: </span>
              <span className="font-semibold">{routingResult.reason}</span>
            </div>

            {Object.keys(routingResult.rejected).length > 0 && (
              <div className="pt-2 border-t border-current/10 space-y-1">
                <div className="text-[11px] opacity-75 font-semibold">Considered & Rejection Chain:</div>
                <div className="grid grid-cols-1 md:grid-cols-2 gap-2 text-[11px]">
                  {Object.entries(routingResult.rejected).map(([model, rejReason]) => (
                    <div key={model} className="bg-black/30 p-2 rounded">
                      <span className="font-semibold">{model}: </span>
                      <span className="opacity-90">{rejReason}</span>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>
        )}
      </div>

      {/* Provider Health Matrix & Model Specs */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Live Provider Health Table */}
        <div className="bg-slate-900/80 border border-slate-800 rounded-xl p-5 shadow-sm space-y-4">
          <div className="flex items-center justify-between">
            <h3 className="text-sm font-semibold text-slate-200 font-mono flex items-center gap-2">
              <Activity className="w-4 h-4 text-emerald-400" />
              LIVE MODEL HEALTH & LATENCY
            </h3>
            <span className="text-xs font-mono text-slate-500">scripts/health-watch.sh</span>
          </div>

          <div className="divide-y divide-slate-800">
            {Object.entries(healthTable).map(([modelName, health]) => (
              <div key={modelName} className="py-3 first:pt-0 last:pb-0 space-y-2 font-mono text-xs">
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    <span className="font-semibold text-slate-200">{modelName}</span>
                    <span className="text-[10px] text-slate-500 font-sans">({health.provider})</span>
                  </div>

                  {/* Status Toggle buttons */}
                  <div className="flex items-center gap-1">
                    {(['HEALTHY', 'DEGRADED', 'DOWN'] as ProviderHealthStatus[]).map((st) => (
                      <button
                        key={st}
                        onClick={() => handleToggleHealth(modelName, st)}
                        className={`px-1.5 py-0.5 rounded text-[10px] cursor-pointer transition ${
                          health.status === st
                            ? st === 'HEALTHY'
                              ? 'bg-emerald-950 text-emerald-300 border border-emerald-700 font-bold'
                              : st === 'DEGRADED'
                              ? 'bg-amber-950 text-amber-300 border border-amber-700 font-bold'
                              : 'bg-rose-950 text-rose-300 border border-rose-700 font-bold'
                            : 'bg-slate-950 text-slate-500 hover:text-slate-300'
                        }`}
                      >
                        {st}
                      </button>
                    ))}
                  </div>
                </div>

                <div className="flex items-center justify-between text-[11px] text-slate-400">
                  <span>Latency: <strong className="text-slate-200">{health.latency_ms}ms</strong></span>
                  <span>Failures: <strong className={health.recent_failures > 0 ? 'text-rose-400' : 'text-emerald-400'}>{health.recent_failures}</strong></span>
                  <span className="text-slate-500">Last probe: {new Date(health.last_check).toLocaleTimeString()}</span>
                </div>
              </div>
            ))}
          </div>
        </div>

        {/* Model Catalog Specifications */}
        <div className="bg-slate-900/80 border border-slate-800 rounded-xl p-5 shadow-sm space-y-4">
          <div className="flex items-center justify-between">
            <h3 className="text-sm font-semibold text-slate-200 font-mono flex items-center gap-2">
              <Cpu className="w-4 h-4 text-purple-400" />
              CAPABILITY CATALOG (config/models.yaml)
            </h3>
            <span className="text-xs font-mono text-slate-500">{Object.keys(catalog).length} Specs</span>
          </div>

          <div className="divide-y divide-slate-800">
            {Object.entries(catalog).map(([mName, spec]) => (
              <div key={mName} className="py-3 first:pt-0 last:pb-0 space-y-1.5 font-mono text-xs">
                <div className="flex items-center justify-between">
                  <span className="font-semibold text-slate-100">{mName}</span>
                  <span className="text-[11px] text-slate-400">
                    Window: {spec.context_window ? `${spec.context_window.toLocaleString()} tok` : 'unlimited'}
                  </span>
                </div>

                <div className="flex flex-wrap gap-1">
                  {spec.capabilities.map((c) => (
                    <span
                      key={c}
                      className="px-1.5 py-0.2 rounded bg-slate-950 text-slate-300 border border-slate-800 text-[10px]"
                    >
                      {c}
                    </span>
                  ))}
                  {spec.local && (
                    <span className="px-1.5 py-0.2 rounded bg-emerald-950 text-emerald-300 border border-emerald-800 text-[10px]">
                      LOCAL ON-HOST
                    </span>
                  )}
                </div>

                {spec.notes && <p className="text-[11px] text-slate-500 font-sans">{spec.notes}</p>}
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
};
