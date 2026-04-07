import { act, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import App from "./App";
import type { SocketClient, SocketClientOptions } from "./lib/ws";
import type { BaseEventEnvelope, OutboundMessage } from "./types";

class MemoryStorage implements Storage {
  private store = new Map<string, string>();

  get length() {
    return this.store.size;
  }

  clear() {
    this.store.clear();
  }

  getItem(key: string) {
    return this.store.get(key) ?? null;
  }

  key(index: number) {
    return Array.from(this.store.keys())[index] ?? null;
  }

  removeItem(key: string) {
    this.store.delete(key);
  }

  setItem(key: string, value: string) {
    this.store.set(key, value);
  }
}

class FakeSocketClient implements SocketClient {
  sent: OutboundMessage[] = [];
  callbacks: SocketClientOptions["callbacks"];

  constructor(options: SocketClientOptions) {
    this.callbacks = options.callbacks;
  }

  connect() {
    this.callbacks.onConnecting();
    this.callbacks.onOpen();
  }

  disconnect() {
    this.callbacks.onClose();
  }

  send(message: OutboundMessage) {
    this.sent.push(message);
  }

  emit(event: BaseEventEnvelope) {
    this.callbacks.onEvent(event);
  }
}

describe("App", () => {
  it("renders the simplified Max chat shell", () => {
    const storage = new MemoryStorage();
    const client = new FakeSocketClient({
      baseUrl: "ws://127.0.0.1:8000",
      sessionId: "session-1",
      callbacks: {
        onConnecting() { },
        onOpen() { },
        onClose() { },
        onError() { },
        onEvent() { },
      },
    });

    render(
      <App
        storage={storage}
        clientFactory={(options) => Object.assign(client, { callbacks: options.callbacks })}
      />,
    );

    expect(screen.getByRole("heading", { name: "Olostep" })).toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "Event Log" })).not.toBeInTheDocument();
  });

  it("shows only an approve outline action and keeps revisions in chat", async () => {
    const user = userEvent.setup();
    const storage = new MemoryStorage();
    const client = new FakeSocketClient({
      baseUrl: "ws://127.0.0.1:8000",
      sessionId: "session-1",
      callbacks: {
        onConnecting() { },
        onOpen() { },
        onClose() { },
        onError() { },
        onEvent() { },
      },
    });

    render(
      <App
        storage={storage}
        clientFactory={(options) => Object.assign(client, { callbacks: options.callbacks })}
      />,
    );

    await act(async () => {
      client.emit({
        type: "assistant_message",
        session_id: "session-1",
        run_id: "run-2",
        phase: "outline",
        data: { message: "I have an outline ready." },
      });
      client.emit({
        type: "artifact_ready",
        session_id: "session-1",
        run_id: "run-2",
        phase: "outline",
        data: {
          kind: "outline",
          payload: {
            title: "Draft title",
            sections: [{ heading: "Intro", bullets: ["Point one"] }],
            sources: [],
          },
        },
      });
      client.emit({
        type: "run_complete",
        session_id: "session-1",
        run_id: "run-2",
        phase: "outline",
        data: { status: "awaiting_user" },
      });
    });

    expect(screen.queryByRole("button", { name: "Request Changes" })).not.toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Approve Outline" }));

    expect(screen.getAllByRole("status")).toHaveLength(2);
    expect(screen.getByText("Drafting blog")).toBeInTheDocument();
    expect(screen.getByText("Reviewing your outline feedback...")).toBeInTheDocument();

    expect(client.sent[client.sent.length - 1]).toEqual({
      type: "user_message",
      text: "Approve this outline and continue to the draft.",
    });
  });

  it("hides internal draft review notes and renders sources once", () => {
    const storage = new MemoryStorage();
    const client = new FakeSocketClient({
      baseUrl: "ws://127.0.0.1:8000",
      sessionId: "session-1",
      callbacks: {
        onConnecting() { },
        onOpen() { },
        onClose() { },
        onError() { },
        onEvent() { },
      },
    });

    render(
      <App
        storage={storage}
        clientFactory={(options) => Object.assign(client, { callbacks: options.callbacks })}
      />,
    );

    act(() => {
      client.emit({
        type: "internal_message",
        session_id: "session-1",
        run_id: "run-3",
        phase: "draft",
        data: {
          message:
            "The draft is well aligned with the brief and outline, covering the technical aspects clearly and using realistic industry examples.",
        },
      });
      client.emit({
        type: "assistant_message",
        session_id: "session-1",
        run_id: "run-3",
        phase: "draft",
        data: { message: "I have a draft ready." },
      });
      client.emit({
        type: "artifact_delta",
        session_id: "session-1",
        run_id: "run-3",
        phase: "draft",
        data: { kind: "draft", delta: "# Final draft\n\nA useful body paragraph." },
      });
      client.emit({
        type: "artifact_ready",
        session_id: "session-1",
        run_id: "run-3",
        phase: "draft",
        data: {
          kind: "draft",
          payload: {
            markdown: "# Final draft\n\nA useful body paragraph.\n\n## Sources\n- [Source one](https://example.com)",
            sources: [{ title: "Source one", url: "https://example.com" }],
          },
        },
      });
    });

    expect(screen.getByRole("heading", { name: "Final draft" })).toBeInTheDocument();
    expect(screen.queryByText(/The draft is well aligned with the brief/i)).not.toBeInTheDocument();
    expect(screen.getAllByRole("heading", { name: "Sources" })).toHaveLength(1);
    expect(screen.getByRole("link", { name: "Source one" })).toBeInTheDocument();
  });

  it("sends normal chat messages from the composer", async () => {
    const user = userEvent.setup();
    const storage = new MemoryStorage();
    const client = new FakeSocketClient({
      baseUrl: "ws://127.0.0.1:8000",
      sessionId: "session-1",
      callbacks: {
        onConnecting() { },
        onOpen() { },
        onClose() { },
        onError() { },
        onEvent() { },
      },
    });

    render(
      <App
        storage={storage}
        clientFactory={(options) => Object.assign(client, { callbacks: options.callbacks })}
      />,
    );

    await user.type(screen.getByRole("textbox", { name: "Message Agent" }), "Write a blog about AI agents.");
    await user.click(screen.getByRole("button", { name: "Send" }));

    expect(client.sent[0]).toEqual({
      type: "user_message",
      text: "Write a blog about AI agents.",
    });
  });
});
