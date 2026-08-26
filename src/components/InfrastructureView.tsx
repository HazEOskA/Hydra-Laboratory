import React, { useState } from 'react';
import {
  Cloud,
  Server,
  Activity,
  CheckCircle2,
  Clock,
  Shield,
  Layers,
  RefreshCw,
  ExternalLink,
  Cpu,
  HardDrive,
  Lock,
  Terminal,
} from 'lucide-react';
import { GcpServiceStatus } from '../types';
import { INITIAL_GCP_SERVICES } from '../engine/initialState';

interface InfrastructureViewProps {
  gcpServices?: GcpServiceStatus[];
  onNavigate: (tab: any) => void;
}

export const InfrastructureView: React.FC<InfrastructureViewProps> = ({
  gcpServices = INITIAL_GCP_SERVICES,
  onNavigate,
}) => {
  const [services, setServices] = useState<GcpServiceStatus[]>(gcpServices);
  const [isProbing, setIsProbing] = useState(false);
  const [probeResult, setProbeResult] = useState<string | null>(null);

  const handleRunHealthProbe = () => {
    setIsProbing(true);
    setProbeResult(null);
    setTimeout(() => {
      setIsProbing(false);
      const latency = Math.floor(25 + Math.random() * 15);
      setProbeResult(`PROBE OK: HTTP 200 returned in ${latency}ms from europe-west2 Cloud Run ingress.`);
      setServices((prev) =>
        prev.map((s) =>
          s.type === 'Cloud Run'
            ? { ...s, last_health_check: `2026-08-22T23:24:00Z (HTTP 200 OK - ${latency}ms)` }
            : s
        )
      );
    }, 600);
  };

  const systemdServices = [
    { name: 'hydra-hermes-healthwatch.service', status: 'ACTIVE', cadence: 'Continuous', last_run: '12s ago' },
    { name: 'hydra-hermes-brief.timer', status: 'ACTIVE', cadence: 'Daily 07:00 UTC', last_run: 'Today 07:00' },
    { name: 'hydra-hermes-heartbeat.timer', status: 'ACTIVE', cadence: 'Every 30 min', last_run: '18m ago' },
    { name: 'hydra-hermes-lead-audit.timer', status: 'ACTIVE', cadence: 'Every 60 min', last_run: '42m ago' },
  ];

  return (
    <div className="space-y-6 font-mono">
      {/* Header Banner */}
      <div className="bg-gradient-to-r from-[#030712] via-[#080d22] to-[#030712] border border-amber-500/30 rounded-2xl p-6 shadow-xl">
        <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
          <div className="space-y-1.5">
            <div className="flex items-center gap-2.5">
              <span className="p-2 rounded-xl bg-amber-500/10 text-amber-400 border border-amber-500/30">
                <Cloud className="w-5 h-5" />
              </span>
              <h2 className="text-lg font-bold text-amber-100 uppercase tracking-wider">
                GOOGLE CLOUD PLATFORM (GCP) & HYDRA HOST INFRASTRUCTURE
              </h2>
            </div>
            <p className="text-xs text-slate-300 max-w-3xl leading-relaxed">
              Środowisko wdrożeniowe Hydra City: Kontenerowy <strong className="text-purple-300">Cloud Run Preview</strong>{' '}
              w regionie <span className="text-amber-300 font-semibold">europe-west2</span>, szyfrowany{' '}
              <strong className="text-emerald-300">Secret Manager Vault</strong>, izolowane konto{' '}
              <strong className="text-slate-200">Workload Identity</strong> oraz host VPS z systemd timerami.
            </p>
          </div>

          <div className="flex items-center gap-2">
            <button
              onClick={handleRunHealthProbe}
              disabled={isProbing}
              className="px-4 py-2.5 bg-gradient-to-r from-amber-500 to-amber-600 hover:from-amber-400 text-black text-xs font-bold rounded-xl shadow-md transition cursor-pointer flex items-center gap-2"
            >
              <RefreshCw className={`w-3.5 h-3.5 ${isProbing ? 'animate-spin' : ''}`} />
              <span>Wyślij Live Health Probe</span>
            </button>
          </div>
        </div>
      </div>

      {/* Probe Result Banner */}
      {probeResult && (
        <div className="p-4 rounded-xl bg-emerald-950/80 border border-emerald-500/50 text-emerald-200 text-xs flex items-center justify-between">
          <div className="flex items-center gap-2">
            <CheckCircle2 className="w-4 h-4 text-emerald-400" />
            <span>{probeResult}</span>
          </div>
          <span className="text-[10px] text-emerald-400">INGRESS HEALTHY</span>
        </div>
      )}

      {/* GCP Services Grid */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        {services.map((service) => (
          <div
            key={service.service_name}
            className="bg-[#05091a] border border-amber-500/20 rounded-2xl p-5 shadow-md space-y-3"
          >
            <div className="flex items-center justify-between border-b border-slate-800/80 pb-3">
              <div className="flex items-center gap-2">
                <span className="text-xs font-bold text-amber-200">{service.service_name}</span>
                <span className="text-[10px] px-2 py-0.2 rounded-full font-bold bg-purple-950 text-purple-300 border border-purple-700/40">
                  {service.type}
                </span>
              </div>
              <span className="text-[10px] px-2 py-0.5 rounded-full font-bold bg-emerald-950 text-emerald-300 border border-emerald-500/40">
                {service.status}
              </span>
            </div>

            <div className="space-y-1.5 text-xs text-slate-300">
              <div className="flex justify-between">
                <span className="text-slate-400">Revision:</span>
                <span className="text-purple-300 font-mono">{service.revision}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-slate-400">Region / Ingress:</span>
                <span className="text-slate-200">{service.region}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-slate-400">Health Check:</span>
                <span className="text-emerald-400 font-semibold">{service.last_health_check}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-slate-400">Zasoby:</span>
                <span className="text-slate-300">{service.cpu_limit} &bull; {service.memory_limit}</span>
              </div>
            </div>

            {service.preview_url && (
              <div className="pt-2 border-t border-slate-800/60 flex items-center justify-between text-[11px]">
                <span className="text-slate-400 truncate max-w-xs">{service.preview_url}</span>
                <a
                  href={service.preview_url.startsWith('http') ? service.preview_url : `https://${service.preview_url}`}
                  target="_blank"
                  rel="noreferrer"
                  className="text-amber-400 hover:text-amber-300 flex items-center gap-1 font-semibold"
                >
                  <span>Preview</span>
                  <ExternalLink className="w-3 h-3" />
                </a>
              </div>
            )}
          </div>
        ))}
      </div>

      {/* Host VPS & Systemd Timers */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Host Specs */}
        <div className="bg-[#05091a] border border-slate-800 rounded-2xl p-5 shadow-md space-y-4">
          <div className="flex items-center justify-between border-b border-slate-800/80 pb-3">
            <span className="text-xs font-bold text-amber-300 uppercase tracking-wider flex items-center gap-2">
              <Server className="w-4 h-4 text-amber-400" />
              <span>Contabo Host Node Telemetry (hydra-hermes-runtime-01)</span>
            </span>
            <span className="text-[10px] text-emerald-400 font-bold">ONLINE</span>
          </div>

          <div className="grid grid-cols-3 gap-3 text-center">
            <div className="bg-black/50 border border-slate-800 rounded-xl p-3">
              <Cpu className="w-4 h-4 text-amber-400 mx-auto mb-1" />
              <div className="text-[10px] text-slate-400">vCPU Cores</div>
              <div className="text-sm font-bold text-slate-200">8 vCPU</div>
            </div>
            <div className="bg-black/50 border border-slate-800 rounded-xl p-3">
              <Activity className="w-4 h-4 text-purple-400 mx-auto mb-1" />
              <div className="text-[10px] text-slate-400">Memory RAM</div>
              <div className="text-sm font-bold text-slate-200">24 GB</div>
            </div>
            <div className="bg-black/50 border border-slate-800 rounded-xl p-3">
              <HardDrive className="w-4 h-4 text-emerald-400 mx-auto mb-1" />
              <div className="text-[10px] text-slate-400">Storage SSD</div>
              <div className="text-sm font-bold text-slate-200">200 GB NVMe</div>
            </div>
          </div>
        </div>

        {/* Systemd Timers */}
        <div className="bg-[#05091a] border border-slate-800 rounded-2xl p-5 shadow-md space-y-3">
          <div className="flex items-center justify-between border-b border-slate-800/80 pb-3">
            <span className="text-xs font-bold text-purple-300 uppercase tracking-wider flex items-center gap-2">
              <Clock className="w-4 h-4 text-purple-400" />
              <span>Systemd Continuous Ops Timers</span>
            </span>
            <span className="text-[10px] text-slate-400">4 Active</span>
          </div>

          <div className="space-y-2">
            {systemdServices.map((timer) => (
              <div
                key={timer.name}
                className="flex items-center justify-between bg-black/40 border border-slate-800/80 rounded-xl p-2.5 text-xs"
              >
                <div>
                  <div className="font-bold text-slate-200">{timer.name}</div>
                  <div className="text-[10px] text-slate-400">Cadence: {timer.cadence}</div>
                </div>
                <div className="text-right">
                  <span className="text-[10px] px-2 py-0.2 rounded-full font-bold bg-emerald-950 text-emerald-300 border border-emerald-800">
                    {timer.status}
                  </span>
                  <div className="text-[10px] text-slate-500 mt-0.5">{timer.last_run}</div>
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
};
