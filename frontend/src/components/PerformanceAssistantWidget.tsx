import { useEffect, useState } from "react";
import { useMutation, useQuery } from "@tanstack/react-query";
import { MessageCircle } from "lucide-react";
import { api } from "../lib/api";
import type { ChatMessage, ChatSuggestion, RangeMonths } from "../lib/types";
import { AssistantPanel } from "./AssistantPanel";

interface Props {
  rangeMonths: RangeMonths;
}

export function PerformanceAssistantWidget({ rangeMonths }: Props) {
  const [open, setOpen] = useState(false);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [suggestions, setSuggestions] = useState<ChatSuggestion[]>([]);
  const [greeting, setGreeting] = useState("");
  const [followUp, setFollowUp] = useState("");
  const [usedSuggestionIds, setUsedSuggestionIds] = useState<string[]>([]);
  const [bannerVisible, setBannerVisible] = useState(true);

  const thread = useQuery({
    queryKey: ["performance-chat", rangeMonths],
    queryFn: () => api.performanceChatHistory(rangeMonths),
    enabled: open,
  });

  useEffect(() => {
    setMessages([]);
    setSuggestions([]);
    setGreeting("");
    setFollowUp("");
    setUsedSuggestionIds([]);
    setBannerVisible(true);
  }, [rangeMonths]);

  useEffect(() => {
    if (!thread.data) return;
    setGreeting(thread.data.greeting);
    setSuggestions(thread.data.suggestions);
    if (thread.data.messages.length) {
      setMessages(thread.data.messages);
    }
  }, [thread.data]);

  const send = useMutation({
    mutationFn: (message: string) => api.performanceChat(message, rangeMonths),
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
    },
  });

  const runSuggestion = (item: ChatSuggestion) => {
    if (send.isPending) return;
    setUsedSuggestionIds((current) => [...current, item.id]);
    send.mutate(item.prompt);
  };

  return (
    <div className="case-assistant performance-assistant">
      {open && (
        <AssistantPanel
          eyebrow={`${rangeMonths}-month scoped`}
          title="Performance assistant"
          disclaimer="Decision support only — answers are grounded on the selected dashboard range. I never clear, escalate, forecast, or change operational dispositions."
          greeting={greeting}
          messages={messages}
          suggestions={suggestions}
          usedSuggestionIds={usedSuggestionIds}
          followUp={followUp}
          placeholder="Ask about backlog, SLA, closure rate…"
          loadingLabel="Grounding on operations metrics…"
          bannerVisible={bannerVisible}
          isPending={send.isPending}
          errorMessage={send.isError ? send.error.message : null}
          onClose={() => setOpen(false)}
          onDismissBanner={() => setBannerVisible(false)}
          onFollowUpChange={setFollowUp}
          onSend={(text) => {
            setFollowUp("");
            send.mutate(text);
          }}
          onSuggestion={runSuggestion}
        />
      )}
      <button
        type="button"
        className="case-assistant__fab"
        onClick={() => setOpen((current) => !current)}
        aria-expanded={open}
        aria-label="Open performance assistant"
      >
        <MessageCircle size={20} />
        <span>Performance assistant</span>
      </button>
    </div>
  );
}
