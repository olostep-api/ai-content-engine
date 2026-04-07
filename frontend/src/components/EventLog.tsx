import { useState } from "react";

import { PhaseBadge } from "./PhaseBadge";
import type { EventLogItem } from "../types";

interface EventLogProps {
  events: EventLogItem[];
}

export function EventLog({ events }: EventLogProps) {
  const [open, setOpen] = useState(false);

  return (
    <section className="panel event-log-panel">
      <div className="panel-header">
        <div>
          <p className="eyebrow">Diagnostics</p>
          <h2>Event Log</h2>
        </div>
        <button className="button button-ghost" type="button" onClick={() => setOpen((value) => !value)}>
          {open ? "Hide Events" : "Show Events"}
        </button>
      </div>
      {open ? (
        <div className="event-log-list">
          {events.length === 0 ? (
            <p className="muted">No events received yet.</p>
          ) : (
            events.map((event) => (
              <article key={event.id} className="event-item">
                <div className="event-meta">
                  <strong>{event.type}</strong>
                  <PhaseBadge phase={event.phase} />
                  <span className="muted">{new Date(event.receivedAt).toLocaleTimeString()}</span>
                </div>
                <pre>{JSON.stringify(event.data, null, 2)}</pre>
              </article>
            ))
          )}
        </div>
      ) : (
        <p className="muted">Collapsed by default. Open to inspect WebSocket traffic and tool activity.</p>
      )}
    </section>
  );
}
