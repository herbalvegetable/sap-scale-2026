import { useEffect, useState } from "react";
import { useMutation, useQuery } from "@tanstack/react-query";
import { Bot, MessageCircle, Send, X } from "lucide-react";
import { api } from "../lib/api";
import type { ChatMessage, ChatSuggestion } from "../lib/types";
import { ChatInlineChart } from "./ChatInlineChart";

interface Props {
  alertId: string;
  hasInsight: boolean;
  onInsertDraft: (snippet: string) => void;
}

export function CaseAssistantWidget({ alertId, hasInsight, onInsertDraft }: Props) {
  const [open, setOpen] = useState(false);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [suggestions, setSuggestions] = useState<ChatSuggestion[]>([]);
  const [greeting, setGreeting] = useState("");
  const [followUp, setFollowUp] = useState("");
  const [pendingDraft, setPendingDraft] = useState<string | null>(null);
  const [usedSuggestionIds, setUsedSuggestionIds] = useState<string[]>([]);
  const [bannerVisible, setBannerVisible] = useState(true);

  const thread = useQuery({
    queryKey: ["chat", alertId],
    queryFn: () => api.chatHistory(alertId),
    enabled: open,
  });

  useEffect(() => {
    setOpen(false);
    setMessages([]);
    setSuggestions([]);
    setGreeting("");
    setFollowUp("");
    setPendingDraft(null);
    setUsedSuggestionIds([]);
    setBannerVisible(true);
  }, [alertId]);

  useEffect(() => {
    if (!thread.data) return;
    setGreeting(thread.data.greeting);
    setSuggestions(thread.data.suggestions);
    if (thread.data.messages.length) {
      setMessages(thread.data.messages);
    }
  }, [thread.data]);

  const send = useMutation({
    mutationFn: (message: string) => api.chat(alertId, message),
    onSuccess: (data, message) => {
      const now = new Date().toISOString();
      setMessages((current) => [
        ...current,
        { role: "user", content: message, citations: [], created_at: now },
        {
          role: "assistant",
          content: data.reply,
          citations: data.citations,
          chart: data.chart,
          created_at: now,
        },
      ]);
      setPendingDraft(data.suggested_draft_snippet ?? null);
    },
  });

  const remainingSuggestions = suggestions.filter((item) => !usedSuggestionIds.includes(item.id));

  const runSuggestion = (item: ChatSuggestion) => {
    if (send.isPending) return;
    setUsedSuggestionIds((current) => [...current, item.id]);
    send.mutate(item.prompt);
  };

  return (
    <div className="case-assistant">
      {open && (
        <section className="case-assistant__panel" aria-label="Case assistant">
          <header className="case-assistant__header">
            <div>
              <p className="eyebrow">Transaction-scoped</p>
              <h2><Bot size={16} /> Case assistant</h2>
            </div>
            <button type="button" onClick={() => setOpen(false)} aria-label="Close case assistant"><X size={16} /></button>
          </header>
          {bannerVisible && (
            <div className="case-assistant__banner" role="status">
              <span>Decision support only — use Approve/Override on Actionable Insights to act. I never clear, escalate, or file.</span>
              <button
                type="button"
                className="case-assistant__banner-close"
                onClick={() => setBannerVisible(false)}
                aria-label="Dismiss disclaimer"
              >
                <X size={14} />
              </button>
            </div>
          )}
          <div className="case-assistant__messages">
            {greeting && (
              <article className="chat-bubble chat-bubble--assistant">
                <p>{greeting}</p>
              </article>
            )}
            {messages.map((message, index) => (
              <article key={`${message.role}-${index}-${message.created_at}`} className={`chat-bubble chat-bubble--${message.role}`}>
                <p>{message.content}</p>
                {message.chart && <ChatInlineChart chart={message.chart} />}
                {message.citations?.length > 0 && (
                  <div className="chat-citations">
                    {message.citations.map((citation) => (
                      <span key={`${citation.label}-${citation.source}`} title={`${citation.value} · ${citation.source}`}>
                        {citation.kind}: {citation.label}
                      </span>
                    ))}
                  </div>
                )}
                {message.role === "assistant" && pendingDraft && index === messages.length - 1 && (
                  <div className="chat-draft-actions">
                    {hasInsight ? (
                      <button
                        type="button"
                        className="ui-button ui-button--outline ui-button--small"
                        onClick={() => {
                          onInsertDraft(pendingDraft);
                          setPendingDraft(null);
                        }}
                      >
                        Insert into draft notes
                      </button>
                    ) : (
                      <small>Generate Actionable Insights first to insert this draft into the recommendation card.</small>
                    )}
                  </div>
                )}
              </article>
            ))}
            {send.isPending && (
              <article className="chat-bubble chat-bubble--assistant chat-bubble--loading">
                <p>Grounding on this case…</p>
              </article>
            )}
            {send.isError && <div className="inline-error">{send.error.message}</div>}
          </div>
          {remainingSuggestions.length > 0 && (
            <div className="case-assistant__suggestions">
              {remainingSuggestions.map((item) => (
                <button
                  key={item.id}
                  type="button"
                  className="suggestion-chip"
                  disabled={send.isPending}
                  onClick={() => runSuggestion(item)}
                >
                  {item.label}
                </button>
              ))}
            </div>
          )}
          <form
            className="case-assistant__composer"
            onSubmit={(event) => {
              event.preventDefault();
              const text = followUp.trim();
              if (!text || send.isPending) return;
              setFollowUp("");
              send.mutate(text);
            }}
          >
            <input
              value={followUp}
              onChange={(event) => setFollowUp(event.target.value)}
              placeholder="Ask anything about this case…"
              disabled={send.isPending}
              aria-label="Ask the case assistant"
            />
            <button type="submit" disabled={send.isPending || !followUp.trim()} aria-label="Send">
              <Send size={16} />
            </button>
          </form>
        </section>
      )}
      <button
        type="button"
        className="case-assistant__fab"
        onClick={() => setOpen((current) => !current)}
        aria-expanded={open}
        aria-label="Open case assistant"
      >
        <MessageCircle size={20} />
        <span>Case assistant</span>
      </button>
    </div>
  );
}
