import { Navigate, useNavigate, useParams } from "react-router-dom";

import { useMe } from "../auth";
import { Console } from "../components/Console";
import { StateBadge } from "../components/StateBadge";
import { Alert, Button } from "../components/ui";
import { isOnline, isRunning, useDeleteServer, useServer, useServerAction } from "../servers";

export default function ServerPage() {
  const id = Number(useParams().id);
  const me = useMe();
  const navigate = useNavigate();
  const server = useServer(id);
  const action = useServerAction(id);
  const remove = useDeleteServer();

  if (server.isError) {
    return server.error.message === "Server not found" ? (
      <Navigate to="/" replace />
    ) : (
      <Alert>{server.error.message}</Alert>
    );
  }
  if (!server.data) return null;

  const { state, detail, name } = server.data;
  const busy = action.isPending || state === "pulling" || state === "stopping";
  const confirmDelete = () => {
    const typed = prompt(`This deletes the server and its world. Type "${name}" to confirm.`);
    if (typed === name) remove.mutate(id, { onSuccess: () => navigate("/") });
  };

  return (
    <section className="space-y-4">
      <div className="flex flex-wrap items-center gap-3">
        <h1 className="text-xl font-semibold">{name}</h1>
        <StateBadge state={state} />
        <div className="ml-auto flex gap-2">
          {isRunning(state) ? (
            <>
              <Button variant="secondary" disabled={busy} onClick={() => action.mutate("restart")}>
                Restart
              </Button>
              <Button variant="secondary" disabled={busy} onClick={() => action.mutate("stop")}>
                Stop
              </Button>
            </>
          ) : (
            <Button disabled={busy} onClick={() => action.mutate("start")}>
              Start
            </Button>
          )}
          {me.data?.role === "admin" && (
            <Button variant="danger" disabled={busy || remove.isPending} onClick={confirmDelete}>
              Delete
            </Button>
          )}
        </div>
      </div>

      <p className="text-sm text-zinc-400">
        {server.data.server_type.toLowerCase()} {server.data.version} · {server.data.image_tag} ·{" "}
        {server.data.memory} RAM · connect to <span className="font-mono">&lt;host&gt;:{server.data.port}</span>
      </p>

      {detail && <Alert>{detail}</Alert>}
      {action.isError && <Alert>{action.error.message}</Alert>}
      {remove.isError && <Alert>{remove.error.message}</Alert>}

      <Console serverId={id} online={isOnline(state)} />
    </section>
  );
}
