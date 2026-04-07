import type { BaseEventEnvelope, OutboundMessage } from "../types";

export interface SocketClientCallbacks {
  onConnecting: () => void;
  onOpen: () => void;
  onClose: () => void;
  onError: (message: string) => void;
  onEvent: (event: BaseEventEnvelope) => void;
}

export interface SocketClient {
  connect: () => void;
  disconnect: () => void;
  send: (message: OutboundMessage) => void;
}

export interface SocketClientOptions {
  baseUrl: string;
  sessionId: string;
  callbacks: SocketClientCallbacks;
}

export function createSocketClient(options: SocketClientOptions): SocketClient {
  let socket: WebSocket | null = null;

  return {
    connect() {
      options.callbacks.onConnecting();
      socket = new WebSocket(`${options.baseUrl.replace(/\/$/, "")}/ws/blog/${options.sessionId}`);
      socket.addEventListener("open", () => {
        options.callbacks.onOpen();
      });
      socket.addEventListener("close", () => {
        options.callbacks.onClose();
      });
      socket.addEventListener("error", () => {
        options.callbacks.onError("WebSocket connection error.");
      });
      socket.addEventListener("message", (messageEvent) => {
        try {
          const event = JSON.parse(String(messageEvent.data)) as BaseEventEnvelope;
          options.callbacks.onEvent(event);
        } catch (error) {
          options.callbacks.onError(
            error instanceof Error ? error.message : "Could not parse incoming WebSocket event.",
          );
        }
      });
    },
    disconnect() {
      socket?.close();
      socket = null;
    },
    send(message) {
      if (!socket || socket.readyState !== WebSocket.OPEN) {
        options.callbacks.onError("WebSocket is not connected.");
        return;
      }
      socket.send(JSON.stringify(message));
    },
  };
}
