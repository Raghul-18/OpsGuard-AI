"use client";

import { useState, useRef, useEffect } from "react";
import { useChat } from "@/hooks/useChat";
import { CitedResponse } from "@/components/CitedResponse";
import { Send, Trash2, Bot, User, AlertCircle } from "lucide-react";
import { cn } from "@/lib/utils";

const SUGGESTED = [
  "Which couriers are overcharging us on weight?",
  "What's our RTO rate this month?",
  "Show me SKUs below reorder level",
  "Calculate P&L for our top 5 SKUs",
];

export default function ChatPage() {
  const { messages, isLoading, sendMessage, clearHistory } = useChat();
  const [input, setInput] = useState("");
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  const handleSend = () => {
    if (!input.trim() || isLoading) return;
    sendMessage(input.trim());
    setInput("");
  };

  const handleKey = (e: React.KeyboardEvent) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  const isEmpty = messages.length === 0;

  return (
    <div className="flex flex-col h-full">
      {/* Header */}
      <div className="flex items-center justify-between px-6 py-4 border-b border-border shrink-0">
        <div>
          <h1 className="font-display text-[15px] font-600 text-ink">
            Ask OpsGuard
          </h1>
          <p className="text-[11px] text-ink-muted mt-0.5">
            Every number is cited · Sources shown on hover
          </p>
        </div>
        {!isEmpty && (
          <button
            onClick={clearHistory}
            className="flex items-center gap-1.5 text-[12px] text-ink-muted hover:text-ink transition-colors"
          >
            <Trash2 className="w-3.5 h-3.5" />
            Clear
          </button>
        )}
      </div>

      {/* Messages */}
      <div className="flex-1 overflow-y-auto px-6 py-6 space-y-5">
        {isEmpty ? (
          <div className="flex flex-col items-center justify-center h-full gap-8 opacity-0 animate-fade-up" style={{ animationFillMode: "forwards" }}>
            <div className="text-center">
              <div className="w-12 h-12 rounded-2xl bg-accent-dim flex items-center justify-center mx-auto mb-4 shadow-accent-glow">
                <Bot className="w-6 h-6 text-accent" />
              </div>
              <h2 className="font-display text-lg font-600 text-ink">
                What do you want to know?
              </h2>
              <p className="text-[13px] text-ink-muted mt-1.5 max-w-xs mx-auto">
                Ask about disputes, margins, RTO rates, or inventory. All answers are cited.
              </p>
            </div>
            <div className="grid grid-cols-1 gap-2 w-full max-w-md">
              {SUGGESTED.map((q) => (
                <button
                  key={q}
                  onClick={() => sendMessage(q)}
                  className="text-left text-[13px] text-ink-muted px-4 py-3 rounded-lg border border-border bg-surface-2 hover:bg-surface-3 hover:text-ink transition-all duration-150"
                >
                  {q}
                </button>
              ))}
            </div>
          </div>
        ) : (
          messages.map((msg, i) => (
            <div
              key={i}
              className={cn(
                "flex gap-3 opacity-0 animate-fade-up",
                msg.role === "user" ? "flex-row-reverse" : "flex-row"
              )}
              style={{
                animationDelay: "0ms",
                animationFillMode: "forwards",
              }}
            >
              {/* Avatar */}
              <div
                className={cn(
                  "w-7 h-7 rounded-lg flex items-center justify-center shrink-0 mt-0.5",
                  msg.role === "user"
                    ? "bg-surface-4 text-ink-muted"
                    : "bg-accent-dim text-accent"
                )}
              >
                {msg.role === "user" ? (
                  <User className="w-3.5 h-3.5" />
                ) : (
                  <Bot className="w-3.5 h-3.5" />
                )}
              </div>

              {/* Bubble */}
              <div
                className={cn(
                  "max-w-[80%] rounded-xl px-4 py-3 text-[13px] leading-relaxed",
                  msg.role === "user"
                    ? "bg-surface-3 text-ink border border-border"
                    : "bg-surface-2 text-ink border border-border"
                )}
              >
                {msg.isLoading ? (
                  <div className="flex items-center gap-1.5 py-0.5">
                    <span className="typing-dot" />
                    <span className="typing-dot" />
                    <span className="typing-dot" />
                  </div>
                ) : msg.error ? (
                  <div className="flex items-center gap-2 text-danger">
                    <AlertCircle className="w-4 h-4 shrink-0" />
                    <span>{msg.error}</span>
                  </div>
                ) : msg.role === "assistant" ? (
                  <CitedResponse text={msg.content} citations={msg.citations} />
                ) : (
                  msg.content
                )}
              </div>
            </div>
          ))
        )}
        <div ref={bottomRef} />
      </div>

      {/* Input */}
      <div className="shrink-0 px-6 py-4 border-t border-border">
        <div className="flex items-end gap-3 bg-surface-2 border border-border rounded-xl px-4 py-3 focus-within:border-accent/40 transition-colors">
          <textarea
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={handleKey}
            placeholder="Ask about weight disputes, RTO rates, margins…"
            rows={1}
            className="flex-1 bg-transparent text-[13px] text-ink placeholder:text-ink-muted resize-none outline-none leading-relaxed max-h-32"
            style={{ minHeight: "22px" }}
          />
          <button
            onClick={handleSend}
            disabled={!input.trim() || isLoading}
            className="w-8 h-8 rounded-lg bg-accent flex items-center justify-center shrink-0 hover:bg-accent/90 transition-colors disabled:opacity-40 disabled:cursor-not-allowed shadow-accent-glow"
          >
            <Send className="w-3.5 h-3.5 text-surface" />
          </button>
        </div>
        <p className="text-[10px] text-ink-faint mt-2 text-center font-mono">
          ↵ to send · Shift+↵ for new line · Numbers without citations are removed
        </p>
      </div>
    </div>
  );
}
