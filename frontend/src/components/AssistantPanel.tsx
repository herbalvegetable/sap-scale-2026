import { Bot, Send, X } from "lucide-react";
import type { ChatMessage, ChatSuggestion } from "../lib/types";
import { humanizeLabel } from "../lib/utils";
import { ChatInlineChart } from "./ChatInlineChart";

export interface AssistantDraftActions {
  pendingDraft: string | null;
  pendingEmail: string | null;
  hasInsight: boolean;
  onInsertDraft: (snippet: string) => void;
  onInsertEmail: (email: string) => void;
  onClearDraft: () => void;
  onClearEmail: () => void;
}

interface Props {
  eyebrow: string;
  title: string;
  disclaimer: string;
  greeting: string;
  messages: ChatMessage[];
  suggestions: ChatSuggestion[];
  usedSuggestionIds: string[];
  followUp: string;
  placeholder: string;
  loadingLabel: string;
  bannerVisible: boolean;
  isPending: boolean;
  errorMessage?: string | null;
  draftActions?: AssistantDraftActions;
  onClose: () => void;
  onDismissBanner: () => void;
  onFollowUpChange: (value: string) => void;
  onSend: (message: string) => void;
  onSuggestion: (item: ChatSuggestion) => void;
}

export function AssistantPanel({
  eyebrow,
  title,
  disclaimer,
  greeting,
  messages,
  suggestions,
  usedSuggestionIds,
  followUp,
  placeholder,
  loadingLabel,
  bannerVisible,
  isPending,
  errorMessage,
  draftActions,
  onClose,
  onDismissBanner,
  onFollowUpChange,
  onSend,
  onSuggestion,
}: Props) {
  const remainingSuggestions = suggestions.filter((item) => !usedSuggestionIds.includes(item.id));

  return (
    <section className="case-assistant__panel" aria-label={title}>
      <header className="case-assistant__header">
        <div>
          <p className="eyebrow">{eyebrow}</p>
          <h2><Bot size={16} /> {title}</h2>
        </div>
        <button type="button" onClick={onClose} aria-label={`Close ${title}`}>
          <X size={16} />
        </button>
      </header>
      {bannerVisible && (
        <div className="case-assistant__banner" role="status">
          <span>{disclaimer}</span>
          <button
            type="button"
            className="case-assistant__banner-close"
            onClick={onDismissBanner}
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
          <article
            key={`${message.role}-${index}-${message.created_at}`}
            className={`chat-bubble chat-bubble--${message.role}`}
          >
            <p>{message.content}</p>
            {message.chart && <ChatInlineChart chart={message.chart} />}
            {message.citations?.length > 0 && (
              message.chart ? (
                <div className="chat-evidence-list">
                  <strong>Supporting evidence</strong>
                  <ol>
                    {message.citations.map((citation) => (
                      <li key={`${citation.label}-${citation.source}-${citation.value}`}>
                        <span className="chat-evidence-list__kind">{humanizeLabel(citation.kind)}</span>
                        <div>
                          <b>{humanizeLabel(citation.label)}</b>
                          <p>{citation.value}</p>
                          <small>{humanizeLabel(citation.source)}</small>
                        </div>
                      </li>
                    ))}
                  </ol>
                </div>
              ) : (
                <div className="chat-citations">
                  {message.citations.map((citation) => (
                    <span
                      key={`${citation.label}-${citation.source}`}
                      title={`${citation.value} · ${humanizeLabel(citation.source)}`}
                    >
                      {humanizeLabel(citation.kind)}: {humanizeLabel(citation.label)}
                    </span>
                  ))}
                </div>
              )
            )}
            {draftActions &&
              message.role === "assistant" &&
              index === messages.length - 1 &&
              (draftActions.pendingDraft || draftActions.pendingEmail) && (
                <div className="chat-draft-actions">
                  {draftActions.pendingDraft && (
                    draftActions.hasInsight ? (
                      <button
                        type="button"
                        className="ui-button ui-button--outline ui-button--small"
                        onClick={() => {
                          draftActions.onInsertDraft(draftActions.pendingDraft!);
                          draftActions.onClearDraft();
                        }}
                      >
                        Insert into case notes
                      </button>
                    ) : (
                      <small>Generate Actionable Insights first to insert case notes.</small>
                    )
                  )}
                  {draftActions.pendingEmail && (
                    draftActions.hasInsight ? (
                      <button
                        type="button"
                        className="ui-button ui-button--outline ui-button--small"
                        onClick={() => {
                          draftActions.onInsertEmail(draftActions.pendingEmail!);
                          draftActions.onClearEmail();
                        }}
                      >
                        Update Draft Email
                      </button>
                    ) : (
                      <small>Generate Actionable Insights first to update the Draft Email module.</small>
                    )
                  )}
                </div>
              )}
          </article>
        ))}
        {isPending && (
          <article className="chat-bubble chat-bubble--assistant chat-bubble--loading">
            <p>{loadingLabel}</p>
          </article>
        )}
        {errorMessage && <div className="inline-error">{errorMessage}</div>}
      </div>
      {remainingSuggestions.length > 0 && (
        <div className="case-assistant__suggestions">
          {remainingSuggestions.map((item) => (
            <button
              key={item.id}
              type="button"
              className="suggestion-chip"
              disabled={isPending}
              onClick={() => onSuggestion(item)}
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
          if (!text || isPending) return;
          onSend(text);
        }}
      >
        <input
          value={followUp}
          onChange={(event) => onFollowUpChange(event.target.value)}
          placeholder={placeholder}
          disabled={isPending}
          aria-label={`Ask the ${title.toLowerCase()}`}
        />
        <button type="submit" disabled={isPending || !followUp.trim()} aria-label="Send">
          <Send size={16} />
        </button>
      </form>
    </section>
  );
}
