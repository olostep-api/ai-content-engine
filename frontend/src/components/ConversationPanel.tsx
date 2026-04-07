import ReactMarkdown from "react-markdown";
import rehypeSanitize from "rehype-sanitize";

import type { ConversationItem } from "../types";

interface ConversationPanelProps {
  conversation: ConversationItem[];
  canApproveOutline: boolean;
  onApproveOutline: () => void;
  showDraftingLive: boolean;
}

export function ConversationPanel({
  conversation,
  canApproveOutline,
  onApproveOutline,
  showDraftingLive,
}: ConversationPanelProps) {
  const lastAssistantMessageIndex = [...conversation]
    .map((item, index) => (item.kind === "message" && item.role === "assistant" ? index : -1))
    .filter((index) => index >= 0)
    .pop();

  return (
    <section className="conversation-panel" aria-label="Conversation">
      <div className="conversation-list">
        {conversation.map((item) => {
          if (item.kind === "message") {
            const author = item.role === "user" ? "You" : "Agent";
            return (
              <article key={item.id} className={`chat-row chat-row-${item.role}`}>
                <div className={`message-stack message-stack-${item.role}`}>
                  <div className={`chat-bubble chat-${item.role} chat-${item.variant}`}>
                    <span className="chat-label">{author}</span>
                    <p>{item.text}</p>
                  </div>
                  {showDraftingLive && item.role === "assistant" && conversation.indexOf(item) === lastAssistantMessageIndex ? (
                    <div className="drafting-inline" role="status" aria-live="polite">
                      <span className="drafting-pulse" aria-hidden="true">
                        <span />
                        <span />
                        <span />
                      </span>
                      <span>Drafting blog</span>
                    </div>
                  ) : null}
                </div>
              </article>
            );
          }

          if (item.artifactKind === "outline") {
            return (
              <article key={item.id} className="artifact-card artifact-outline">
                <div className="artifact-header">
                  <span className="chat-label">Outline</span>
                  <h2>{item.payload.title}</h2>
                </div>

                <div className="outline-sections">
                  {item.payload.sections.map((section) => (
                    <section key={section.heading} className="outline-section">
                      <h3>{section.heading}</h3>
                      <ul>
                        {section.bullets.map((bullet) => (
                          <li key={bullet}>{bullet}</li>
                        ))}
                      </ul>
                    </section>
                  ))}
                </div>

                <div className="artifact-actions">
                  <button
                    className="button button-primary"
                    type="button"
                    onClick={onApproveOutline}
                    disabled={!canApproveOutline}
                  >
                    Approve Outline
                  </button>
                </div>

                <p className="artifact-hint">Need changes? Reply in chat and Max will revise it.</p>
              </article>
            );
          }

          return (
            <article key={item.id} className="artifact-card artifact-draft">
              <div className="artifact-header">
                <span className="chat-label">{item.streaming ? "Drafting" : "Draft"}</span>
              </div>

              <div className="markdown-body">
                <ReactMarkdown rehypePlugins={[rehypeSanitize]}>
                  {stripTrailingSourcesSection(item.payload.markdown)}
                </ReactMarkdown>
              </div>

              {item.payload.sources.length > 0 ? (
                <section className="sources">
                  <h3>Sources</h3>
                  <ul>
                    {item.payload.sources.map((source) => (
                      <li key={source.url}>
                        <a href={source.url} target="_blank" rel="noreferrer">
                          {source.title || source.url}
                        </a>
                      </li>
                    ))}
                  </ul>
                </section>
              ) : null}
            </article>
          );
        })}
      </div>
    </section>
  );
}

function stripTrailingSourcesSection(markdown: string): string {
  const normalized = markdown.replace(/\r\n/g, "\n");
  const lines = normalized.split("\n");
  let index = lines.length - 1;

  while (index >= 0 && lines[index].trim() === "") {
    index -= 1;
  }

  for (let cursor = index; cursor >= 0; cursor -= 1) {
    const trimmed = lines[cursor].trim();

    if (/^#{1,6}\s+sources\s*$/i.test(trimmed) || /^sources\s*$/i.test(trimmed)) {
      return lines.slice(0, cursor).join("\n").trimEnd();
    }

    if (
      trimmed === "" ||
      /^([-*+]|\d+\.)\s+/.test(trimmed) ||
      /^>\s*/.test(trimmed) ||
      /^\[[^\]]+\]\([^)]+\)$/.test(trimmed) ||
      /^https?:\/\/\S+$/i.test(trimmed)
    ) {
      continue;
    }

    break;
  }

  return markdown;
}
