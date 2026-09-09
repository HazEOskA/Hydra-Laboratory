import React, { useState } from 'react';
import {
  MessageSquareCode,
  Send,
  Sparkles,
  Shield,
  Layers,
  Clock,
  CheckCircle2,
  AlertTriangle,
  Mail,
  Users,
  Lock,
} from 'lucide-react';
import { BuzzRoom, BuzzMessage } from '../types';

interface BuzzViewProps {
  buzzRooms: BuzzRoom[];
  onSendMessage: (roomId: string, text: string) => void;
  onNavigate: (tab: any) => void;
}

export const BuzzView: React.FC<BuzzViewProps> = ({
  buzzRooms,
  onSendMessage,
  onNavigate,
}) => {
  const [selectedRoomId, setSelectedRoomId] = useState<string>(
    buzzRooms[0]?.room_id || 'ROOM-M2048'
  );
  const [messageInput, setMessageInput] = useState('');

  const selectedRoom =
    buzzRooms.find((r) => r.room_id === selectedRoomId) || buzzRooms[0];

  const handleSend = (e: React.FormEvent) => {
    e.preventDefault();
    if (!messageInput.trim()) return;
    onSendMessage(selectedRoom.room_id, messageInput.trim());
    setMessageInput('');
  };

  const getRoleBadge = (role: string) => {
    switch (role) {
      case 'OPERATOR':
        return 'bg-amber-950 text-amber-300 border-amber-600/40';
      case 'GOVERNMENT':
        return 'bg-rose-950 text-rose-300 border-rose-600/40';
      case 'RUNTIME':
        return 'bg-purple-950 text-purple-300 border-purple-600/40';
      case 'MICHAEL_ANGELO':
        return 'bg-blue-950 text-blue-300 border-blue-600/40';
      case 'NOTARY':
        return 'bg-amber-950 text-amber-200 border-amber-500/40';
      case 'APR':
        return 'bg-emerald-950 text-emerald-300 border-emerald-600/40';
      default:
        return 'bg-slate-900 text-slate-300 border-slate-700';
    }
  };

  return (
    <div className="space-y-6 font-mono">
      {/* Header Banner */}
      <div className="bg-gradient-to-r from-[#030712] via-[#090e24] to-[#030712] border border-amber-500/30 rounded-2xl p-6 shadow-xl">
        <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
          <div className="space-y-1.5">
            <div className="flex items-center gap-2.5">
              <span className="p-2 rounded-xl bg-amber-500/10 text-amber-400 border border-amber-500/30">
                <MessageSquareCode className="w-5 h-5" />
              </span>
              <h2 className="text-lg font-bold text-amber-100 uppercase tracking-wider">
                SKRZYNKA & BUZZ (MISSION COLLABORATION ROOMS)
              </h2>
            </div>
            <p className="text-xs text-slate-300 max-w-3xl leading-relaxed">
              Buzz to systemowa szyna komunikacyjna dla każdego projektu w Hydra City. 
              Tutaj <strong className="text-amber-300">Operator</strong>, <strong className="text-purple-300">Government</strong>,{' '}
              <strong className="text-blue-300">Michael Angelo</strong> i <strong className="text-emerald-300">APR Verifier</strong>{' '}
              wymieniają intencje, telemetrię i pieczęcie w czasie rzeczywistym.
            </p>
          </div>

          <div className="flex items-center gap-2 text-xs">
            <span className="px-3 py-1.5 rounded-xl bg-black/60 border border-amber-500/30 text-amber-300">
              Active Rooms: <strong className="text-emerald-400">{buzzRooms.length}</strong>
            </span>
          </div>
        </div>
      </div>

      {/* Main Chat Interface */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
        {/* Left 4 cols: Room Selector */}
        <div className="lg:col-span-4 space-y-3">
          <div className="text-xs font-bold text-amber-400 uppercase tracking-wider px-1">
            Pokoje Misji ({buzzRooms.length})
          </div>

          <div className="space-y-2">
            {buzzRooms.map((room) => {
              const isSelected = room.room_id === selectedRoomId;
              return (
                <div
                  key={room.room_id}
                  onClick={() => setSelectedRoomId(room.room_id)}
                  className={`p-4 rounded-2xl border transition-all cursor-pointer ${
                    isSelected
                      ? 'bg-[#0a0f2e] border-amber-500/60 shadow-lg shadow-amber-500/10'
                      : 'bg-[#05091a]/80 hover:bg-[#05091a] border-slate-800/80 hover:border-amber-500/30'
                  }`}
                >
                  <div className="flex items-center justify-between">
                    <span className="text-xs font-bold text-amber-200">{room.name}</span>
                    <span className="text-[10px] px-2 py-0.2 rounded-full font-bold bg-emerald-950 text-emerald-300 border border-emerald-700/50">
                      {room.status}
                    </span>
                  </div>
                  <div className="text-[11px] text-slate-400 mt-1 truncate">{room.topic}</div>
                  <div className="text-[10px] text-slate-500 mt-2 flex items-center justify-between">
                    <span>{room.participants.length} uczestników</span>
                    <span>{room.messages.length} wiadomości</span>
                  </div>
                </div>
              );
            })}
          </div>
        </div>

        {/* Right 8 cols: Live Room Chat Stream */}
        <div className="lg:col-span-8 space-y-4">
          <div className="bg-[#05091a] border border-amber-500/20 rounded-2xl p-5 shadow-md flex flex-col h-[520px]">
            {/* Room Header */}
            <div className="flex items-center justify-between border-b border-slate-800/80 pb-3">
              <div>
                <h3 className="text-sm font-bold text-amber-100">{selectedRoom.name}</h3>
                <p className="text-xs text-slate-400 truncate max-w-md">{selectedRoom.topic}</p>
              </div>

              {/* Participants Avatars */}
              <div className="flex items-center -space-x-1.5">
                {selectedRoom.participants.map((p) => (
                  <div
                    key={p.id}
                    className="w-7 h-7 rounded-full bg-slate-900 border border-amber-500/40 flex items-center justify-center text-xs shadow"
                    title={`${p.name} (${p.role})`}
                  >
                    {p.avatar}
                  </div>
                ))}
              </div>
            </div>

            {/* Message Stream */}
            <div className="flex-1 overflow-y-auto py-4 space-y-3.5 pr-2 scrollbar-thin">
              {selectedRoom.messages.map((msg) => (
                <div
                  key={msg.id}
                  className="bg-black/50 border border-slate-800/80 rounded-xl p-3 space-y-1.5 text-xs hover:border-amber-500/30 transition"
                >
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-2">
                      <span className="font-bold text-slate-200">{msg.sender_name}</span>
                      <span
                        className={`text-[9px] px-2 py-0.2 rounded-full font-bold border ${getRoleBadge(
                          msg.role
                        )}`}
                      >
                        {msg.role}
                      </span>
                    </div>
                    <span className="text-[10px] text-slate-500">{msg.timestamp}</span>
                  </div>

                  <p className="text-slate-300 leading-relaxed text-[11px] font-mono whitespace-pre-wrap">
                    {msg.text}
                  </p>
                </div>
              ))}
            </div>

            {/* Send Message Form */}
            <form onSubmit={handleSend} className="pt-3 border-t border-slate-800/80 flex items-center gap-2">
              <input
                type="text"
                value={messageInput}
                onChange={(e) => setMessageInput(e.target.value)}
                placeholder="Wyślij intencję / komendę jako Operator..."
                className="flex-1 bg-black/70 border border-slate-700 focus:border-amber-400 rounded-xl px-4 py-2.5 text-xs text-amber-100 placeholder-slate-500 focus:outline-none transition"
              />
              <button
                type="submit"
                className="px-4 py-2.5 bg-gradient-to-r from-amber-500 to-amber-600 hover:from-amber-400 text-black text-xs font-bold rounded-xl shadow-md transition cursor-pointer flex items-center gap-1.5"
              >
                <Send className="w-3.5 h-3.5" />
                <span>Wyślij</span>
              </button>
            </form>
          </div>
        </div>
      </div>
    </div>
  );
};
