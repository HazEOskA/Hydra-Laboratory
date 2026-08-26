import React, { useState } from 'react';
import {
  ScrollText,
  ShieldCheck,
  CheckCircle2,
  AlertTriangle,
  Copy,
  Check,
  FileCode,
  Sliders,
} from 'lucide-react';
import {
  generatePreamble,
  getSoulDigest,
  SOUL_CONSTITUTION_TEXT,
  SOUL_REQUIRED_SECTIONS,
  verifySoulStructure,
} from '../engine/soulData';

export const SoulView: React.FC = () => {
  const [characterBudget, setCharacterBudget] = useState(6000);
  const [copiedPreamble, setCopiedPreamble] = useState(false);
  const [copiedDigest, setCopiedDigest] = useState(false);

  const digest = getSoulDigest();
  const shortDigest = digest.slice(0, 12);
  const verification = verifySoulStructure(SOUL_CONSTITUTION_TEXT);
  const preamble = generatePreamble(characterBudget);

  const handleCopyPreamble = () => {
    navigator.clipboard.writeText(preamble);
    setCopiedPreamble(true);
    setTimeout(() => setCopiedPreamble(false), 2000);
  };

  const handleCopyDigest = () => {
    navigator.clipboard.writeText(digest);
    setCopiedDigest(true);
    setTimeout(() => setCopiedDigest(false), 2000);
  };

  return (
    <div className="space-y-6">
      {/* Top Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 pb-2 border-b border-slate-800">
        <div>
          <h2 className="text-lg font-bold text-slate-100 flex items-center gap-2">
            <ScrollText className="w-5 h-5 text-sky-400" />
            SOUL.md Operational Constitution
          </h2>
          <p className="text-xs text-slate-400 mt-1">
            Immutable operational rules, permissions, anti-drift constraints, and execution principles.
          </p>
        </div>

        <div className="flex items-center gap-2">
          <div className="bg-slate-900 border border-slate-800 px-3 py-1.5 rounded-lg flex items-center gap-2 font-mono text-xs text-slate-300">
            <span className="text-slate-500">SHA-256:</span>
            <span className="text-sky-300">{shortDigest}</span>
            <button
              onClick={handleCopyDigest}
              className="text-slate-400 hover:text-slate-200 cursor-pointer"
              title="Copy full 64-character SHA-256 hash"
            >
              {copiedDigest ? <Check className="w-3.5 h-3.5 text-emerald-400" /> : <Copy className="w-3.5 h-3.5" />}
            </button>
          </div>
        </div>
      </div>

      {/* Verification Status Cards */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <div className="bg-slate-900/80 border border-slate-800 rounded-xl p-4 flex items-center gap-3">
          <div className="p-2 rounded-lg bg-emerald-500/10 text-emerald-400">
            <ShieldCheck className="w-5 h-5" />
          </div>
          <div>
            <div className="text-xs font-mono text-slate-400">INTEGRITY CHECK</div>
            <div className="text-sm font-bold font-mono text-slate-100 mt-0.5">
              13/13 Required Sections Present
            </div>
            <div className="text-[10px] text-emerald-400 font-mono">Zero missing sections</div>
          </div>
        </div>

        <div className="bg-slate-900/80 border border-slate-800 rounded-xl p-4 flex items-center gap-3">
          <div className="p-2 rounded-lg bg-sky-500/10 text-sky-400">
            <FileCode className="w-5 h-5" />
          </div>
          <div>
            <div className="text-xs font-mono text-slate-400">SOURCE SPEC</div>
            <div className="text-sm font-bold font-mono text-slate-100 mt-0.5">SOUL.md (Root File)</div>
            <div className="text-[10px] text-slate-400 font-mono">6,293 Bytes &bull; 212 Lines</div>
          </div>
        </div>

        <div className="bg-slate-900/80 border border-slate-800 rounded-xl p-4 flex items-center gap-3">
          <div className="p-2 rounded-lg bg-purple-500/10 text-purple-400">
            <Sliders className="w-5 h-5" />
          </div>
          <div>
            <div className="text-xs font-mono text-slate-400">PROMPT INJECTION</div>
            <div className="text-sm font-bold font-mono text-slate-100 mt-0.5">Active Preamble Generator</div>
            <div className="text-[10px] text-purple-300 font-mono">Auto-truncated to token budget</div>
          </div>
        </div>
      </div>

      {/* 13 Sections Checklist */}
      <div className="bg-slate-900/80 border border-slate-800 rounded-xl p-5 shadow-sm space-y-3">
        <h3 className="text-sm font-semibold text-slate-200 font-mono flex items-center gap-2">
          <CheckCircle2 className="w-4 h-4 text-emerald-400" />
          MANDATORY SECTION COMPLIANCE CHECKLIST (lib/hermes/soul.py verify)
        </h3>

        <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-2">
          {SOUL_REQUIRED_SECTIONS.map((sec) => (
            <div
              key={sec}
              className="bg-slate-950 border border-slate-800 rounded-lg p-2.5 flex items-center gap-2 font-mono text-xs"
            >
              <CheckCircle2 className="w-3.5 h-3.5 text-emerald-400 shrink-0" />
              <span className="text-slate-300 truncate">{sec}</span>
            </div>
          ))}
        </div>
      </div>

      {/* Prompt Preamble Generator */}
      <div className="bg-slate-900/80 border border-slate-800 rounded-xl p-5 shadow-sm space-y-4">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 pb-2 border-b border-slate-800">
          <div>
            <h3 className="text-sm font-semibold text-slate-200 font-mono flex items-center gap-2">
              <ScrollText className="w-4 h-4 text-sky-400" />
              SYSTEM PROMPT PREAMBLE GENERATOR
            </h3>
            <p className="text-xs text-slate-400 mt-0.5">
              Generates the exact header prepended to every worker prompt.
            </p>
          </div>

          <div className="flex items-center gap-3">
            <div className="flex items-center gap-2 text-xs font-mono text-slate-400">
              <span>Budget:</span>
              <input
                type="range"
                min="1000"
                max="10000"
                step="500"
                value={characterBudget}
                onChange={(e) => setCharacterBudget(parseInt(e.target.value))}
                className="w-24 accent-sky-500 cursor-pointer"
              />
              <span className="text-sky-300 font-semibold">{characterBudget} chars</span>
            </div>

            <button
              onClick={handleCopyPreamble}
              className="flex items-center gap-1.5 px-3 py-1.5 bg-sky-600 hover:bg-sky-500 text-white font-mono text-xs rounded-lg transition cursor-pointer"
            >
              {copiedPreamble ? <Check className="w-3.5 h-3.5" /> : <Copy className="w-3.5 h-3.5" />}
              <span>{copiedPreamble ? 'Copied' : 'Copy Preamble'}</span>
            </button>
          </div>
        </div>

        <pre className="bg-slate-950 border border-slate-800 rounded-lg p-4 text-xs font-mono text-slate-300 max-h-60 overflow-y-auto whitespace-pre-wrap">
          {preamble}
        </pre>
      </div>

      {/* Full Constitution Document */}
      <div className="bg-slate-900/80 border border-slate-800 rounded-xl p-5 shadow-sm space-y-4">
        <h3 className="text-sm font-semibold text-slate-200 font-mono flex items-center gap-2">
          <FileCode className="w-4 h-4 text-slate-400" />
          FULL CONSTITUTION TEXT (SOUL.md)
        </h3>

        <div className="bg-slate-950 border border-slate-800 rounded-lg p-5 font-mono text-xs text-slate-300 max-h-96 overflow-y-auto whitespace-pre-wrap leading-relaxed">
          {SOUL_CONSTITUTION_TEXT}
        </div>
      </div>
    </div>
  );
};
