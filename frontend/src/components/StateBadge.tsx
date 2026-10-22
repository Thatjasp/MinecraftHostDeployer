import type { ServerState } from "../servers";

const styles: Record<ServerState, string> = {
  online: "bg-emerald-950 text-emerald-300 border-emerald-800",
  starting: "bg-sky-950 text-sky-300 border-sky-800",
  pulling: "bg-sky-950 text-sky-300 border-sky-800",
  stopping: "bg-amber-950 text-amber-300 border-amber-800",
  unhealthy: "bg-amber-950 text-amber-300 border-amber-800",
  error: "bg-red-950 text-red-300 border-red-800",
  unknown: "bg-red-950 text-red-300 border-red-800",
  stopped: "bg-zinc-900 text-zinc-400 border-zinc-700",
};

const labels: Partial<Record<ServerState, string>> = {
  pulling: "downloading image",
};

export function StateBadge({ state }: { state: ServerState }) {
  const busy = state === "starting" || state === "pulling" || state === "stopping";
  return (
    <span
      className={`inline-flex items-center gap-1.5 rounded-full border px-2 py-0.5 text-xs ${styles[state]}`}
    >
      <span className={`size-1.5 rounded-full bg-current ${busy ? "animate-pulse" : ""}`} />
      {labels[state] ?? state}
    </span>
  );
}
