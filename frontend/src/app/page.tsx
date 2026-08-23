"use client";

import { useState, useRef, useEffect } from "react";
import { Pencil, RotateCw, Copy, Check } from "lucide-react";

type Message = {
  role: "user" | "assistant";
  content: string;
  timestamp: Date;
};

function SpinnerAsterisk() {
  const angles = [0, 45, 90, 135, 180, 225, 270, 315];
  return (
    <svg
      viewBox="0 0 100 100"
      className="h-4 w-4 animate-spin text-lime-400"
      style={{ animationDuration: "0.9s" }}
    >
      {angles.map((angle) => (
        <line
          key={angle}
          x1="50"
          y1="50"
          x2="50"
          y2="22"
          stroke="currentColor"
          strokeWidth="10"
          strokeLinecap="round"
          transform={`rotate(${angle} 50 50)`}
        />
      ))}
    </svg>
  );
}

export default function Home() {
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [conversationId, setConversationId] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [backendOnline, setBackendOnline] = useState<boolean | null>(null);
  const [copiedIndex, setCopiedIndex] = useState<number | null>(null);
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    fetch("/api/health")
      .then((res) => (res.ok ? setBackendOnline(true) : setBackendOnline(false)))
      .catch(() => setBackendOnline(false));
  }, []);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  async function runStream(prompt: string, onDelta: (delta: string) => void) {
    const res = await fetch("/api/chat/stream", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ conversation_id: conversationId, message: prompt }),
    });
    if (!res.body) throw new Error("no stream");

    const reader = res.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });

      const events = buffer.split("\n\n");
      buffer = events.pop() ?? "";

      for (const evt of events) {
        const lines = evt.split("\n");
        const eventLine = lines.find((l) => l.startsWith("event: "));
        const dataLine = lines.find((l) => l.startsWith("data: "));
        if (!dataLine) continue;
        const data = dataLine.slice("data: ".length);

        if (eventLine?.includes("conversation")) {
          setConversationId(data);
        } else if (eventLine?.includes("done")) {
          continue;
        } else {
          const { delta } = JSON.parse(data);
          onDelta(delta);
        }
      }
    }
  }

  async function sendMessage() {
    if (!input.trim() || loading) return;
    const text = input;
    setInput("");
    setMessages((prev) => [
      ...prev,
      { role: "user", content: text, timestamp: new Date() },
      { role: "assistant", content: "", timestamp: new Date() },
    ]);
    setLoading(true);

    try {
      await runStream(text, (delta) => {
        setMessages((prev) => {
          const updated = [...prev];
          const last = updated[updated.length - 1];
          updated[updated.length - 1] = { ...last, content: last.content + delta };
          return updated;
        });
      });
    } catch {
      setMessages((prev) => {
        const updated = [...prev];
        updated[updated.length - 1] = {
          role: "assistant",
          content: "Failed to reach the backend.",
          timestamp: new Date(),
        };
        return updated;
      });
    } finally {
      setLoading(false);
    }
  }

  async function retryMessage(assistantIndex: number) {
    if (loading) return;
    const userText = messages[assistantIndex - 1]?.content;
    if (!userText) return;

    setMessages((prev) => {
      const updated = [...prev];
      updated[assistantIndex] = { role: "assistant", content: "", timestamp: new Date() };
      return updated;
    });
    setLoading(true);

    try {
      await runStream(userText, (delta) => {
        setMessages((prev) => {
          const updated = [...prev];
          const target = updated[assistantIndex];
          updated[assistantIndex] = { ...target, content: target.content + delta };
          return updated;
        });
      });
    } catch {
      setMessages((prev) => {
        const updated = [...prev];
        updated[assistantIndex] = {
          role: "assistant",
          content: "Failed to reach the backend.",
          timestamp: new Date(),
        };
        return updated;
      });
    } finally {
      setLoading(false);
    }
  }

  function editMessage(userIndex: number) {
    setInput(messages[userIndex].content);
  }

  function copyMessage(content: string, index: number) {
    function fallbackCopy() {
      const textarea = document.createElement("textarea");
      textarea.value = content;
      textarea.style.position = "fixed";
      textarea.style.opacity = "0";
      document.body.appendChild(textarea);
      textarea.focus();
      textarea.select();
      try {
        document.execCommand("copy");
      } catch {
        // ignore
      }
      document.body.removeChild(textarea);
    }

    if (navigator.clipboard && window.isSecureContext) {
      navigator.clipboard.writeText(content).catch(fallbackCopy);
    } else {
      fallbackCopy();
    }

    setCopiedIndex(index);
    setTimeout(() => setCopiedIndex(null), 1500);
  }

  function formatTime(date: Date) {
    return date.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
  }

  function handleKeyDown(e: React.KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      sendMessage();
    }
  }

  return (
    <main className="flex h-screen flex-col bg-zinc-950 font-mono text-zinc-200">
      <header className="flex items-center justify-between border-b border-zinc-800 px-5 py-3">
        <span className="text-sm font-semibold tracking-tight text-zinc-100">
          aegis<span className="text-lime-400">.</span>chat
        </span>
        <div className="flex items-center gap-2 text-xs text-zinc-500">
          <span
            className={`h-2 w-2 rounded-full ${
              backendOnline === null ? "bg-zinc-600" : backendOnline ? "animate-pulse bg-lime-400" : "bg-zinc-600"
            }`}
          />
          {backendOnline === null ? "checking" : backendOnline ? "backend online" : "backend offline"}
        </div>
      </header>

      <div className="flex-1 overflow-y-auto px-4 py-6">
        <div className="mx-auto flex max-w-2xl flex-col gap-1">
          {messages.length === 0 && (
            <p className="mt-24 text-center text-sm text-zinc-600">Send a message to start the conversation.</p>
          )}
          {messages.map((m, i) => {
            const isStreaming = loading && i === messages.length - 1 && m.role === "assistant";
            const isThinking = isStreaming && m.content === "";
            return (
              <div key={i} className="group flex flex-col gap-1">
                <div className={`flex ${m.role === "user" ? "justify-end" : "justify-start"}`}>
                  <div
                    className={`max-w-[80%] whitespace-pre-wrap rounded-lg px-4 py-2 text-sm leading-relaxed ${
                      m.role === "user"
                        ? "bg-lime-400 text-zinc-950"
                        : "border border-zinc-800 bg-zinc-900 text-zinc-200"
                    }`}
                  >
                    {isThinking ? <SpinnerAsterisk /> : m.content}
                  </div>
                </div>

                {!isStreaming && (
                  <div
                    className={`flex items-center gap-2 text-zinc-600 opacity-0 transition-opacity group-hover:opacity-100 ${
                      m.role === "user" ? "justify-end" : "justify-start"
                    }`}
                  >
                    {m.role === "user" && (
                      <button onClick={() => editMessage(i)} className="hover:text-lime-400" title="Edit">
                        <Pencil size={13} />
                      </button>
                    )}
                    {m.role === "assistant" && (
                      <button onClick={() => retryMessage(i)} className="hover:text-lime-400" title="Retry">
                        <RotateCw size={13} />
                      </button>
                    )}
                    <button onClick={() => copyMessage(m.content, i)} className="hover:text-lime-400" title="Copy">
                      {copiedIndex === i ? <Check size={13} /> : <Copy size={13} />}
                    </button>
                    <span className="text-[11px]">{formatTime(m.timestamp)}</span>
                  </div>
                )}
              </div>
            );
          })}
          <div ref={bottomRef} />
        </div>
      </div>

      <div className="border-t border-zinc-800 bg-zinc-950 px-4 py-4">
        <div className="mx-auto flex max-w-2xl items-end gap-2">
          <textarea
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={handleKeyDown}
            rows={1}
            placeholder="Type a message..."
            className="flex-1 resize-none rounded-lg border border-zinc-800 bg-zinc-900 px-4 py-3 text-sm text-zinc-200 placeholder-zinc-600 outline-none focus:border-lime-400"
          />
          <button
            onClick={sendMessage}
            disabled={loading || !input.trim()}
            className="rounded-lg bg-lime-400 px-4 py-3 text-sm font-medium text-zinc-950 transition-opacity disabled:opacity-30"
          >
            Send
          </button>
        </div>
      </div>
    </main>
  );
}