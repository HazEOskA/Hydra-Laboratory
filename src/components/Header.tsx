import React from 'react';
import {
  Shield,
  Activity,
  Server,
  Cpu,
  CheckCircle2,
  AlertTriangle,
  Terminal,
  Lock,
  Flame,
  Cloud,
  Layers,
} from 'lucide-react';
import { getSoulDigest } from '../engine/soulData';

interface HeaderProps {
  systemHealth: { ok: boolean; statusText: string };
  activeCount: number;
  activeLeasesCount: number;
  promptsUsedToday: number;
  dailyPromptCap: number;
  cloudRunRevision: string;
  onOpenTerminal: () => void;
  onEmergencyLockdown?: () => void;
}

export const Header: React.FC<HeaderProps> = ({
  systemHealth,
  activeCount,
  activeLeasesCount,
  promptsUsedToday,
  dailyPromptCap,
  cloudRunRevision,
  onOpenTerminal,
  onEmergencyLockdown,
}) => {
  const soulDigest = getSoulDigest();
  const soulShort = soulDigest.slice(0, 10);
  const promptPercent = Math.min(100, Math.round((promptsUsedToday / dailyPromptCap) * 100));

  return (
    <header className="border-b border-amber-500/20 bg-gradient-to-r from-[#030712] via-[#080d22] to-[#030712] backdrop-blur-md sticky top-0 z-40 shadow-lg shadow-black/40">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-3 flex flex-wrap items-center justify-between gap-4">
        {/* Brand & City Architecture Header */}
        <div className="flex items-center gap-3.5">
          <div className="relative group">
            <div className="h-11 w-11 rounded-xl bg-gradient-to-br from-amber-500/20 via-purple-600/20 to-black border border-amber-500/40 flex items-center justify-center text-amber-400 font-mono font-bold text-lg shadow-inner shadow-amber-500/10">
              <span className="text-xl select-none">🏛️</span>
            </div>
            <div className="absolute -bottom-1 -right-1 w-3.5 h-3.5 rounded-full bg-emerald-500 border-2 border-black animate-pulse" title="Runtime Live" />
          </div>

          <div>
            <div className="flex items-center gap-2 flex-wrap">
              <h1 className="text-base font-bold text-amber-100 tracking-wider uppercase font-mono flex items-center gap-1.5">
                <span>HYDRA HERMES LAB</span>
                <span className="text-xs text-amber-500/80 font-normal">/</span>
                <span className="text-xs text-purple-300 font-medium lowercase font-sans">hydra city v0.1</span>
              </h1>

              <span className="text-[10px] px-2 py-0.5 rounded-full font-mono bg-purple-950/80 border border-purple-600/40 text-purple-300 font-semibold tracking-wide">
                OSA RUNTIMEV2
              </span>

              <span
                className={`inline-flex items-center gap-1 text-[11px] px-2.5 py-0.5 rounded-full font-mono font-semibold ${
                  systemHealth.ok
                    ? 'bg-emerald-950/80 border border-emerald-500/40 text-emerald-300'
                    : 'bg-rose-950/80 border border-rose-500/40 text-rose-300'
                }`}
              >
                {systemHealth.ok ? (
                  <CheckCircle2 className="w-3 h-3 text-emerald-400" />
                ) : (
                  <AlertTriangle className="w-3 h-3 text-rose-400" />
                )}
                {systemHealth.statusText}
              </span>
            </div>

            <div className="flex items-center gap-3 text-xs text-slate-400 mt-1 font-mono flex-wrap">
              <span className="flex items-center gap-1 text-slate-300">
                <Server className="w-3 h-3 text-amber-400" /> Contabo VPS: <span className="text-amber-300/90 font-semibold">runtime-01</span>
              </span>
              <span className="text-slate-600">•</span>
              <span className="flex items-center gap-1 text-purple-300">
                <Cloud className="w-3 h-3 text-purple-400" /> GCP Cloud Run: <span className="text-purple-200 font-semibold">{cloudRunRevision}</span>
              </span>
              <span className="text-slate-600">•</span>
              <span className="flex items-center gap-1 text-amber-300/90">
                <Lock className="w-3 h-3 text-amber-400" /> Sovereign Authority: <span className="text-emerald-400">OSA-GOD-LAYER</span>
              </span>
            </div>
          </div>
        </div>

        {/* Telemetry Pills & Quick Controls */}
        <div className="flex items-center gap-2.5 flex-wrap">
          {/* Daily Token / Prompt Meter */}
          <div className="hidden lg:flex flex-col gap-1 bg-black/60 border border-amber-500/20 rounded-lg px-3 py-1.5 min-w-[170px]">
            <div className="flex justify-between text-[10px] font-mono text-slate-400">
              <span className="text-amber-400/90">Daily Prompt Floor</span>
              <span className="text-amber-200 font-semibold">{promptsUsedToday}/{dailyPromptCap}</span>
            </div>
            <div className="w-full bg-slate-900 h-1.5 rounded-full overflow-hidden border border-slate-800">
              <div
                className={`h-full transition-all duration-300 ${
                  promptPercent > 80 ? 'bg-amber-500' : 'bg-gradient-to-r from-amber-500 to-purple-500'
                }`}
                style={{ width: `${promptPercent}%` }}
              />
            </div>
          </div>

          {/* Constitution Digest Badge */}
          <div className="hidden md:flex items-center gap-1.5 bg-black/60 border border-purple-500/30 px-2.5 py-1.5 rounded-lg font-mono text-xs text-purple-200">
            <span className="text-purple-400 font-semibold">SOUL:</span>
            <span className="text-slate-200">{soulShort}</span>
            <span className="w-2 h-2 rounded-full bg-emerald-400 shadow-sm shadow-emerald-400" title="13/13 Invariants Locked" />
          </div>

          {/* Active Leases / Work Cells */}
          <div className="flex items-center gap-1.5 bg-black/60 border border-amber-500/30 px-2.5 py-1.5 rounded-lg font-mono text-xs text-amber-200">
            <Layers className="w-3.5 h-3.5 text-amber-400" />
            <span className="text-slate-400">Leases:</span>
            <span className="text-amber-300 font-bold">{activeLeasesCount}</span>
          </div>

          {/* Active Tasks Pill */}
          <div className="flex items-center gap-1.5 bg-black/60 border border-purple-500/30 px-2.5 py-1.5 rounded-lg font-mono text-xs">
            <Activity className="w-3.5 h-3.5 text-purple-400 animate-pulse" />
            <span className="text-slate-400">Running:</span>
            <span className="text-purple-300 font-bold">{activeCount}</span>
          </div>

          {/* hermesctl Terminal Toggle */}
          <button
            onClick={onOpenTerminal}
            className="flex items-center gap-1.5 bg-slate-900 hover:bg-amber-950/60 active:bg-amber-900/80 text-amber-200 hover:text-amber-100 px-3 py-1.5 rounded-lg text-xs font-mono border border-amber-500/40 hover:border-amber-400 transition cursor-pointer shadow-sm shadow-black"
            title="Open hermesctl interactive CLI"
          >
            <Terminal className="w-3.5 h-3.5 text-amber-400" />
            <span className="font-semibold">hermesctl</span>
          </button>
        </div>
      </div>
    </header>
  );
};
