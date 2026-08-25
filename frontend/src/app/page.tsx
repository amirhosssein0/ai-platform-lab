"use client";

import { useState, useRef, useEffect } from "react";
import {
  Pencil,
  RotateCw,
  Copy,
  Check,
  Paperclip,
  FileText,
  Image as ImageIcon,
  X,
  Plus,
} from "lucide-react";

type Message = {
  role: "user" | "assistant";
  content: string;
  timestamp: Date;
  attachment?: string;
  attachmentKind?: "document" | "image";
  attachmentPreview?: string;
};

type Conversation = {
  id: string;
  title: string;
  created_at: string;
};

const IMAGE_MIME_TYPES = ["image/jpeg", "image/png", "image/webp"];
const MAX_IMAGE_SIZE_MB = 8;

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

function fileToDataUrl(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(reader.result as string);
    reader.onerror = reject;
    reader.readAsDataURL(file);
  });
}

export default function Home() {
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [conversationId, setConversationId] = useState<string | null>(null);
  const [conversations, setConversations] = useState<Conversation[]>([]);
  const [loading, setLoading] = useState(false);
  const [backendOnline, setBackendOnline] = useState<boolean | null>(null);
  const [copiedIndex, setCopiedIndex] = useState<number | null>(null);
  const [attachedFile, setAttachedFile] = useState<File | null>(null);
  const [fileError, setFileError] = useState<string | null>(null);
  const bottomRef = useRef<HTMLDivElement>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    fetch("/api/health")
      .then((res) => (res.ok ? setBackendOnline(true) : setBackendOnline(false)))
      .catch(() => setBackendOnline(false));
    loadConversations();
  }, []);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  async function loadConversations() {
    try {
      const res = await fetch("/api/conversations");
      if (!res.ok) return;
      setConversations(await res.json());
    } catch {
      // ignore
    }
  }

  async function selectConversation(id: string) {
    if (loading) return;
    try {
      const res = await fetch(`/api/conversations/${id}/messages`);
      if (!res.ok) return;
      const data = await res.json();
      setMessages(
        data.map((m: { role: "user" | "assistant"; content: string; timestamp: string }) => ({
          role: m.role,
          content: m.content,
          timestamp: new Date(m.timestamp),
        }))
      );
      setConversationId(id);
      setInput("");
      setAttachedFile(null);
    } catch {
      // ignore
    }
  }

  function startNewChat() {
    setMessages([]);
    setConversationId(null);
    setInput("");
    setAttachedFile(null);
  }

  async function runStream(
    prompt: string,
    image: string | undefined,
    onDelta: (delta: string) => void
  ) {
    const res = await fetch("/api/chat/stream", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ conversation_id: conversationId, message: prompt, image }),
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

  async function uploadFile(file: File): Promise<boolean> {
    const formData = new FormData();
    formData.append("file", file);
    try {
      const res = await fetch("/api/documents/upload", { method: "POST", body: formData });
      return res.ok;
    } catch {
      return false;
    }
  }

  async function sendMessage() {
    if ((!input.trim() && !attachedFile) || loading) return;
    const text = input.trim();
    const file = attachedFile;
    const isImage = file ? IMAGE_MIME_TYPES.includes(file.type) : false;

    setInput("");
    setAttachedFile(null);

    let imageDataUrl: string | undefined;
    let displayText = text;

    if (file && isImage) {
      imageDataUrl = await fileToDataUrl(file);
      if (!displayText) displayText = "Describe this image.";
    }

    setMessages((prev) => [
      ...prev,
      {
        role: "user",
        content: displayText,
        timestamp: new Date(),
        attachment: file?.name,
        attachmentKind: file ? (isImage ? "image" : "document") : undefined,
        attachmentPreview: isImage ? imageDataUrl : undefined,
      },
      { role: "assistant", content: "", timestamp: new Date() },
    ]);
    setLoading(true);

    try {
      if (file && !isImage) {
        const ok = await uploadFile(file);
        if (!ok) throw new Error("upload failed");
      }

      if (displayText || imageDataUrl) {
        await runStream(displayText || "Describe this image.", imageDataUrl, (delta) => {
          setMessages((prev) => {
            const updated = [...prev];
            const last = updated[updated.length - 1];
            updated[updated.length - 1] = { ...last, content: last.content + delta };
            return updated;
          });
        });
      } else {
        setMessages((prev) => {
          const updated = [...prev];
          updated[updated.length - 1] = {
            role: "assistant",
            content: `Indexed ${file?.name}. Ask me anything about it.`,
            timestamp: new Date(),
          };
          return updated;
        });
      }
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
      loadConversations();
    }
  }

  async function retryMessage(assistantIndex: number) {
    if (loading) return;
    const userMsg = messages[assistantIndex - 1];
    if (!userMsg) return;

    setMessages((prev) => {
      const updated = [...prev];
      updated[assistantIndex] = { role: "assistant", content: "", timestamp: new Date() };
      return updated;
    });
    setLoading(true);

    try {
      await runStream(
        userMsg.content,
        userMsg.attachmentKind === "image" ? userMsg.attachmentPreview : undefined,
        (delta) => {
          setMessages((prev) => {
            const updated = [...prev];
            const target = updated[assistantIndex];
            updated[assistantIndex] = { ...target, content: target.content + delta };
            return updated;
          });
        }
      );
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

  function handleFileSelect(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    e.target.value = "";
    if (!file) return;

    if (IMAGE_MIME_TYPES.includes(file.type) && file.size > MAX_IMAGE_SIZE_MB * 1024 * 1024) {
      setFileError(`Image exceeds ${MAX_IMAGE_SIZE_MB}MB limit`);
      setTimeout(() => setFileError(null), 3000);
      return;
    }
    setAttachedFile(file);
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
    <div className="flex h-screen bg-zinc-950 font-mono text-zinc-200">
      {/* Sidebar */}
      <aside className="flex w-64 flex-col border-r border-zinc-800">
        <div className="border-b border-zinc-800 p-3">
          <button
            onClick={startNewChat}
            className="flex w-full items-center justify-center gap-2 rounded-lg border border-zinc-800 py-2 text-sm text-zinc-200 transition-colors hover:border-lime-400 hover:text-lime-400"
          >
            <Plus size={14} />
            New chat
          </button>
        </div>
        <div className="flex-1 overflow-y-auto p-2">
          {conversations.map((c) => (
            <button
              key={c.id}
              onClick={() => selectConversation(c.id)}
              className={`mb-1 block w-full truncate rounded-lg px-3 py-2 text-left text-xs ${
                c.id === conversationId
                  ? "bg-zinc-800 text-lime-400"
                  : "text-zinc-400 hover:bg-zinc-900 hover:text-zinc-200"
              }`}
            >
              {c.title}
            </button>
          ))}
        </div>
      </aside>

      {/* Main chat column */}
      <main className="flex flex-1 flex-col">
        <header className="flex items-center justify-between border-b border-zinc-800 px-5 py-3">
          <span className="text-sm font-semibold tracking-tight text-zinc-100">
            aegis<span className="text-lime-400">.</span>chat
          </span>
          <div className="flex items-center gap-2 text-xs text-zinc-500">
            <span
              className={`h-2 w-2 rounded-full ${
                backendOnline === null
                  ? "bg-zinc-600"
                  : backendOnline
                  ? "animate-pulse bg-lime-400"
                  : "bg-zinc-600"
              }`}
            />
            {backendOnline === null ? "checking" : backendOnline ? "backend online" : "backend offline"}
          </div>
        </header>

        <div className="flex-1 overflow-y-auto px-4 py-6">
          <div className="mx-auto flex max-w-2xl flex-col gap-1">
            {messages.length === 0 && (
              <p className="mt-24 text-center text-sm text-zinc-600">
                Send a message to start the conversation.
              </p>
            )}
            {messages.map((m, i) => {
              const isStreaming = loading && i === messages.length - 1 && m.role === "assistant";
              const isThinking = isStreaming && m.content === "";
              return (
                <div key={i} className="group flex flex-col gap-1">
                  {m.role === "user" && m.attachment && (
                    <div className="flex justify-end">
                      {m.attachmentKind === "image" && m.attachmentPreview ? (
                        <img
                          src={m.attachmentPreview}
                          alt={m.attachment}
                          className="h-20 w-20 rounded-lg border border-zinc-800 object-cover"
                        />
                      ) : (
                        <div className="flex items-center gap-2 rounded-lg border border-zinc-800 bg-zinc-900 px-3 py-2 text-xs text-zinc-300">
                          <FileText size={14} className="text-lime-400" />
                          {m.attachment}
                        </div>
                      )}
                    </div>
                  )}
                  {m.content !== "" || m.role === "assistant" ? (
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
                  ) : null}

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
          <div className="mx-auto max-w-2xl">
            {attachedFile && (
              <div className="mb-2 flex w-fit items-center gap-2 rounded-lg border border-zinc-800 bg-zinc-900 px-3 py-2 text-xs text-zinc-300">
                {IMAGE_MIME_TYPES.includes(attachedFile.type) ? (
                  <ImageIcon size={14} className="text-lime-400" />
                ) : (
                  <FileText size={14} className="text-lime-400" />
                )}
                <span>{attachedFile.name}</span>
                <button onClick={() => setAttachedFile(null)} className="text-zinc-500 hover:text-zinc-200">
                  <X size={13} />
                </button>
              </div>
            )}
            {fileError && <p className="mb-2 text-xs text-red-400">{fileError}</p>}
            <div className="flex items-end gap-2">
              <input
                ref={fileInputRef}
                type="file"
                accept=".pdf,.txt,.md,image/jpeg,image/png,image/webp"
                onChange={handleFileSelect}
                className="hidden"
              />
              <button
                onClick={() => fileInputRef.current?.click()}
                className="rounded-lg border border-zinc-800 p-3 text-zinc-400 transition-colors hover:border-lime-400 hover:text-lime-400"
                title="Attach document or image"
              >
                <Paperclip size={16} />
              </button>
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
                disabled={loading || (!input.trim() && !attachedFile)}
                className="rounded-lg bg-lime-400 px-4 py-3 text-sm font-medium text-zinc-950 transition-opacity disabled:opacity-30"
              >
                Send
              </button>
            </div>
          </div>
        </div>
      </main>
    </div>
  );
}