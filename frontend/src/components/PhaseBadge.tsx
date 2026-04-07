import type { Phase } from "../types";

interface PhaseBadgeProps {
  phase: Phase | null;
}

export function PhaseBadge({ phase }: PhaseBadgeProps) {
  if (!phase) {
    return <span className="phase-badge phase-badge-muted">idle</span>;
  }

  return <span className={`phase-badge phase-${phase}`}>{phase}</span>;
}
