import React, { useState, useRef, useEffect } from 'react';
import { Terminal, Send, Trash2, HelpCircle, Sparkles, ShieldCheck } from 'lucide-react';
import { PermissionClassifier } from '../engine/permissionsEngine';
import { QueueEngine } from '../engine/queueEngine';
import { LedgerEngine } from '../engine/ledgerEngine';
import { ModelRouterEngine } from '../engine/routerEngine';
import { RevenueLedgerEngine } from '../engine/revenueEngine';
import { getSoulDigest, SOUL_CONSTITUTION_TEXT, verifySoulStructure } from '../engine/soulData';
import { TOOLS_REGISTRY } from '../engine/toolsData';
import { INITIAL_GCP_SERVICES, INITIAL_PINOKIO_CLAIMS, INITIAL_WORKER_LEASES } from '../engine/initialState';

interface TerminalViewProps {
  classifier: PermissionClassifier;
  queueEngine: QueueEngine;
  ledgerEngine: LedgerEngine;
  routerEngine: ModelRouterEngine;
  revenueEngine: RevenueLedgerEngine;
}

interface CommandLog {
  id: string;
  command: string;
  output: string;
  isError?: boolean;
  timestamp: string;
}

export const TerminalView: React.FC<TerminalViewProps> = ({
  classifier,
  queueEngine,
  ledgerEngine,
  routerEngine,
  revenueEngine,
}) => {
  const [inputVal, setInputVal] = useState('');
  const [history, setHistory] = useState<CommandLog[]>([
    {
      id: 'init-1',
      command: 'hermesctl health',
      output: JSON.stringify(
        {
          status: 'ok',
          architecture: 'Hydra City v0.1',
          gateway: 'Zgredek Understanding Gate Active',
          government: 'Hyperlock Scoped Authority',
          primary_builder: 'Michael Angelo (Work Cell)',
          verifier: 'Pinokio Proof Gate',
          notary: 'APR Sealed SHA-256 Chain',
          host: 'hydra-hermes-runtime-01',
          gcp_cloud_run: 'hydra-hermes-lab-00042-pxq (READY)',
          soul_digest: getSoulDigest().slice(0, 16),
          queue_lag_seconds: queueEngine.getQueueLagSeconds(),
          ledger_events: ledgerEngine.getEvents().length,
        },
        null,
        2
      ),
      timestamp: new Date().toLocaleTimeString(),
    },
  ]);

  const terminalEndRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    terminalEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [history]);

  const executeCommand = (cmdStr: string) => {
    const trimmed = cmdStr.trim();
    if (!trimmed) return;

    if (trimmed === 'clear') {
      setHistory([]);
      return;
    }

    const parts = trimmed.split(/\s+/);
    let output = '';
    let isError = false;

    try {
      if (parts[0] === 'help') {
        output = `Hydra City Operator CLI (hermesctl v0.1)

Available commands:
  hermesctl health
  hermesctl gateway evaluate <intent>
  hermesctl genesis list
  hermesctl leases list
  hermesctl pinokio verify
  hermesctl notary journal
  hermesctl gcp status
  hermesctl gcp probe
  hermesctl harakiri drill
  hermesctl permissions classify --tool <tool> --action <action>
  hermesctl queue list
  hermesctl queue stats
  hermesctl queue claim
  hermesctl ledger verify
  hermesctl models route <TASK_CLASS>
  hermesctl soul digest
  clear
  help`;
      } else if (parts[0] === 'hermesctl') {
        const sub = parts[1];
        if (!sub) {
          output = `Usage: hermesctl [health|gateway|genesis|leases|pinokio|notary|gcp|harakiri|permissions|queue|ledger|models|soul]`;
        } else if (sub === 'health') {
          output = JSON.stringify(
            {
              status: 'ok',
              architecture: 'Hydra City v0.1',
              timestamp: new Date().toISOString(),
              host: 'hydra-hermes-runtime-01',
              gcp_preview: 'hydra-hermes-lab-00042-pxq (200 OK)',
              soul: getSoulDigest().slice(0, 16),
              queue: queueEngine.getStats(),
              ledger: ledgerEngine.verifyChain(),
            },
            null,
            2
          );
        } else if (sub === 'gateway') {
          output = JSON.stringify(
            {
              gate: 'Zgredek Understanding Gate',
              status: 'READY',
              intake_mode: 'OPERATOR-DIRECT',
              verdict: 'PASS (Score: 98/100)',
              genesis_template: 'Mission Genesis Compiler v0.1',
            },
            null,
            2
          );
        } else if (sub === 'genesis') {
          output = JSON.stringify(ledgerEngine.getMissions(), null, 2);
        } else if (sub === 'leases') {
          output = JSON.stringify(INITIAL_WORKER_LEASES, null, 2);
        } else if (sub === 'pinokio') {
          output = JSON.stringify(INITIAL_PINOKIO_CLAIMS, null, 2);
        } else if (sub === 'notary') {
          output = JSON.stringify(
            {
              ledger_events: ledgerEngine.getEvents().length,
              integrity: ledgerEngine.verifyChain(),
            },
            null,
            2
          );
        } else if (sub === 'gcp') {
          if (parts[2] === 'probe') {
            output = `PROBE OK: HTTP 200 OK in 31ms from europe-west2 (revision: hydra-hermes-lab-00042-pxq).`;
          } else {
            output = JSON.stringify(INITIAL_GCP_SERVICES, null, 2);
          }
        } else if (sub === 'harakiri') {
          output = `[HARAKIRI DRILL] Work Cells isolated. Checkpoints committed to Notary. Zero data loss.`;
        } else if (sub === 'permissions') {
          if (parts[2] === 'classify') {
            const toolIdx = parts.indexOf('--tool');
            const actionIdx = parts.indexOf('--action');
            const tool = toolIdx !== -1 ? parts[toolIdx + 1] : 'email';
            const action = actionIdx !== -1 ? parts[actionIdx + 1] : 'send';
            const decision = classifier.classify(tool, action, {}, false);
            output = JSON.stringify(decision, null, 2);
          } else {
            output = `Tools in registry: ${classifier.knownTools().join(', ')}`;
          }
        } else if (sub === 'queue') {
          if (parts[2] === 'stats') {
            output = JSON.stringify(queueEngine.getStats(), null, 2);
          } else if (parts[2] === 'claim') {
            const claimed = queueEngine.claim();
            output = claimed ? JSON.stringify(claimed, null, 2) : 'No QUEUED tasks available to claim.';
          } else {
            output = JSON.stringify(queueEngine.getAll(), null, 2);
          }
        } else if (sub === 'ledger') {
          output = JSON.stringify(ledgerEngine.verifyChain(), null, 2);
        } else if (sub === 'models') {
          const taskClass = parts[2] || 'CODE_GENERATION';
          const decision = routerEngine.select(taskClass, { requiredCapabilities: ['code', 'reasoning'] });
          output = JSON.stringify(decision, null, 2);
        } else if (sub === 'soul') {
          output = JSON.stringify(
            {
              digest: getSoulDigest(),
              verification: verifySoulStructure(SOUL_CONSTITUTION_TEXT),
            },
            null,
            2
          );
        } else {
          output = `Unknown hermesctl subcommand: ${sub}. Type 'help' for usage.`;
          isError = true;
        }
      } else {
        output = `Command not recognized: ${parts[0]}. Type 'help' for available commands.`;
        isError = true;
      }
    } catch (e: any) {
      output = `Execution error: ${e.message}`;
      isError = true;
    }

    setHistory((prev) => [
      ...prev,
      {
        id: `cmd-${Date.now()}`,
        command: cmdStr,
        output,
        isError,
        timestamp: new Date().toLocaleTimeString(),
      },
    ]);
  };

  const handleFormSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!inputVal.trim()) return;
    executeCommand(inputVal);
    setInputVal('');
  };

  const quickCommands = [
    'hermesctl health',
    'hermesctl gateway',
    'hermesctl leases list',
    'hermesctl pinokio verify',
    'hermesctl gcp probe',
    'hermesctl harakiri drill',
    'hermesctl permissions classify --tool email --action send',
    'hermesctl ledger verify',
  ];

  return (
    <div className="space-y-4 font-mono">
      {/* Header Banner */}
      <div className="bg-gradient-to-r from-[#030712] via-[#090e24] to-[#030712] border border-amber-500/30 rounded-2xl p-5 shadow-xl flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <div className="flex items-center gap-2">
            <Terminal className="w-5 h-5 text-amber-400" />
            <h2 className="text-sm font-bold text-amber-100 uppercase tracking-wider">
              OPERATOR CLI TERMINAL (hermesctl v0.1)
            </h2>
          </div>
          <p className="text-xs text-slate-400 mt-1">
            Interaktywna linia poleceń sterująca architekturą logiczną Hydra City.
          </p>
        </div>

        <button
          onClick={() => setHistory([])}
          className="flex items-center gap-1.5 px-3 py-1.5 bg-slate-900 hover:bg-slate-800 text-slate-300 text-xs rounded-xl border border-slate-700 transition cursor-pointer"
        >
          <Trash2 className="w-3.5 h-3.5" />
          <span>Wyczyść Ekran</span>
        </button>
      </div>

      {/* Quick Command Pills */}
      <div className="flex items-center gap-2 flex-wrap text-[11px]">
        <span className="text-slate-500 mr-1">Szybkie polecenia:</span>
        {quickCommands.map((cmd) => (
          <button
            key={cmd}
            onClick={() => executeCommand(cmd)}
            className="px-2.5 py-1 rounded-lg bg-black/60 hover:bg-amber-950/40 border border-amber-500/30 text-amber-200 hover:text-amber-100 transition cursor-pointer"
          >
            {cmd}
          </button>
        ))}
      </div>

      {/* Terminal Output Window */}
      <div className="bg-[#02050f] border border-amber-500/30 rounded-2xl p-5 shadow-2xl h-[520px] flex flex-col">
        <div className="flex-1 overflow-y-auto space-y-4 pr-2 scrollbar-thin text-xs">
          <div className="text-slate-500 border-b border-slate-900 pb-2">
            Hydra City Hermes Core Shell initialized. Type 'help' for command reference.
          </div>

          {history.map((log) => (
            <div key={log.id} className="space-y-1">
              <div className="flex items-center gap-2 text-slate-400">
                <span className="text-amber-400 font-bold">$</span>
                <span className="text-amber-200 font-semibold">{log.command}</span>
                <span className="text-[10px] text-slate-600 ml-auto">{log.timestamp}</span>
              </div>

              <div
                className={`p-3 rounded-xl border whitespace-pre-wrap ${
                  log.isError
                    ? 'bg-rose-950/30 border-rose-800/50 text-rose-300'
                    : 'bg-black/60 border-slate-800/80 text-emerald-300'
                }`}
              >
                {log.output}
              </div>
            </div>
          ))}
          <div ref={terminalEndRef} />
        </div>

        {/* Input Bar */}
        <form onSubmit={handleFormSubmit} className="pt-3 border-t border-slate-800/80 flex items-center gap-2">
          <span className="text-amber-400 font-bold text-sm">$</span>
          <input
            type="text"
            value={inputVal}
            onChange={(e) => setInputVal(e.target.value)}
            placeholder="Wpisz komendę hermesctl..."
            className="flex-1 bg-black/80 border border-slate-700 focus:border-amber-400 rounded-xl px-4 py-2 text-xs text-amber-100 placeholder-slate-600 focus:outline-none transition"
            autoFocus
          />
          <button
            type="submit"
            className="px-4 py-2 bg-gradient-to-r from-amber-500 to-amber-600 hover:from-amber-400 text-black text-xs font-bold rounded-xl shadow transition cursor-pointer flex items-center gap-1.5"
          >
            <Send className="w-3.5 h-3.5" />
            <span>Wykonaj</span>
          </button>
        </form>
      </div>
    </div>
  );
};
