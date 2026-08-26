import React from 'react';
import {
  LayoutDashboard,
  ShieldCheck,
  ListTodo,
  FileCheck,
  Network,
  DollarSign,
  ScrollText,
  Terminal,
  Compass,
  FolderGit2,
  Hammer,
  MessageSquareCode,
  Cloud,
  RotateCcw,
} from 'lucide-react';

export type NavTab =
  | 'cockpit'
  | 'gateway'
  | 'missions'
  | 'queue'
  | 'workers'
  | 'governance'
  | 'ledger'
  | 'router'
  | 'revenue'
  | 'buzz'
  | 'infrastructure'
  | 'recovery'
  | 'soul'
  | 'terminal';

interface NavigationProps {
  activeTab: NavTab;
  onSelectTab: (tab: NavTab) => void;
  waitingApprovalCount: number;
  queuedCount: number;
  activeMissionCount?: number;
  unreadBuzzCount?: number;
}

export const Navigation: React.FC<NavigationProps> = ({
  activeTab,
  onSelectTab,
  waitingApprovalCount,
  queuedCount,
  activeMissionCount = 2,
  unreadBuzzCount = 1,
}) => {
  const tabs: Array<{
    id: NavTab;
    label: string;
    icon: React.FC<{ className?: string }>;
    badge?: number | string;
    badgeColor?: string;
  }> = [
    { id: 'cockpit', label: 'Centrum Dowodzenia', icon: LayoutDashboard },
    { id: 'gateway', label: 'Zgredek / Gateway', icon: Compass },
    {
      id: 'missions',
      label: 'Projekty & Misje',
      icon: FolderGit2,
      badge: activeMissionCount > 0 ? activeMissionCount : undefined,
      badgeColor: 'bg-amber-950/80 text-amber-300 border border-amber-600/40',
    },
    {
      id: 'queue',
      label: 'Kolejka (Logistyka)',
      icon: ListTodo,
      badge: queuedCount > 0 ? queuedCount : undefined,
      badgeColor: 'bg-purple-950/80 text-purple-300 border border-purple-600/40',
    },
    { id: 'workers', label: 'Michael Angelo & Miniony', icon: Hammer },
    {
      id: 'governance',
      label: 'Zatwierdzenia & Hyperlock',
      icon: ShieldCheck,
      badge: waitingApprovalCount > 0 ? waitingApprovalCount : undefined,
      badgeColor: 'bg-rose-950/90 text-rose-300 border border-rose-600/50 animate-pulse font-bold',
    },
    { id: 'ledger', label: 'Dowody & Notariusz / APR', icon: FileCheck },
    { id: 'router', label: 'NVIDIA & Modele', icon: Network },
    { id: 'revenue', label: 'Portfel & Budżety', icon: DollarSign },
    {
      id: 'buzz',
      label: 'Skrzynka & Buzz',
      icon: MessageSquareCode,
      badge: unreadBuzzCount > 0 ? unreadBuzzCount : undefined,
      badgeColor: 'bg-purple-950/80 text-purple-300 border border-purple-600/40',
    },
    { id: 'infrastructure', label: 'Infrastruktura (GCP)', icon: Cloud },
    { id: 'recovery', label: 'Recovery & Logi', icon: RotateCcw },
    { id: 'soul', label: 'SOUL Konstytucja', icon: ScrollText },
    { id: 'terminal', label: 'Operator CLI', icon: Terminal },
  ];

  return (
    <nav className="border-b border-amber-500/20 bg-[#05091a]/80 backdrop-blur-md sticky top-[69px] z-30 shadow-md">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        <div className="flex space-x-1.5 overflow-x-auto py-2.5 scrollbar-thin scrollbar-thumb-amber-500/20">
          {tabs.map((tab) => {
            const Icon = tab.icon;
            const isActive = activeTab === tab.id;
            return (
              <button
                key={tab.id}
                onClick={() => onSelectTab(tab.id)}
                className={`flex items-center gap-2 px-3 py-1.5 rounded-lg text-xs font-mono font-medium whitespace-nowrap transition-all duration-200 cursor-pointer ${
                  isActive
                    ? 'bg-gradient-to-r from-amber-500/15 via-purple-500/15 to-transparent text-amber-200 border border-amber-500/50 shadow-sm shadow-amber-500/10 font-semibold'
                    : 'text-slate-400 hover:text-amber-100 hover:bg-slate-900/60 border border-transparent'
                }`}
              >
                <Icon
                  className={`w-3.5 h-3.5 ${
                    isActive ? 'text-amber-400' : 'text-slate-500'
                  }`}
                />
                <span>{tab.label}</span>
                {tab.badge !== undefined && (
                  <span
                    className={`px-1.5 py-0.2 rounded-full text-[10px] font-mono font-semibold ${tab.badgeColor}`}
                  >
                    {tab.badge}
                  </span>
                )}
              </button>
            );
          })}
        </div>
      </div>
    </nav>
  );
};
