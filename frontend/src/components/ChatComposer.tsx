import { FormEvent, useState } from "react";

interface ChatComposerProps {
  disabled: boolean;
  onSend: (text: string) => void;
  onCancel: () => void;
  canCancel: boolean;
}

export function ChatComposer({ disabled, onSend, onCancel, canCancel }: ChatComposerProps) {
  const [value, setValue] = useState("");

  function handleSubmit(event: FormEvent) {
    event.preventDefault();
    const trimmed = value.trim();
    if (!trimmed || disabled) {
      return;
    }
    onSend(trimmed);
    setValue("");
  }

  return (
    <form className="composer" onSubmit={handleSubmit}>
      <label className="composer-label" htmlFor="prompt-input">
        Message Agent
      </label>

      <div className="composer-surface">
        <textarea
          id="prompt-input"
          className="composer-textarea"
          rows={4}
          placeholder="Ask for a blog, approve an outline, or request revisions."
          value={value}
          disabled={disabled}
          onChange={(event) => setValue(event.target.value)}
        />

        <div className="composer-actions">
          <button className="button button-primary" type="submit" disabled={disabled || !value.trim()}>
            Send
          </button>
          <button className="button button-secondary" type="button" onClick={onCancel} disabled={!canCancel}>
            Stop
          </button>
        </div>
      </div>
    </form>
  );
}
