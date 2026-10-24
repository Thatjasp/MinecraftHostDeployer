import { Link } from "react-router-dom";

import { useMe } from "../auth";
import { StateBadge } from "../components/StateBadge";
import { Alert } from "../components/ui";
import { describeServer, useServers } from "../servers";

export default function DashboardPage() {
  const me = useMe();
  const servers = useServers();
  const isAdmin = me.data?.role === "admin";

  return (
    <section>
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-semibold">Servers</h1>
        {isAdmin && (
          <Link
            to="/servers/new"
            className="rounded-md bg-emerald-600 px-3 py-2 text-sm font-medium text-white hover:bg-emerald-500"
          >
            New server
          </Link>
        )}
      </div>

      {servers.isError && (
        <div className="mt-4">
          <Alert>{servers.error.message}</Alert>
        </div>
      )}

      {servers.data?.length === 0 && (
        <div className="mt-6 rounded-xl border border-dashed border-zinc-800 p-10 text-center text-zinc-400">
          No servers yet.{isAdmin ? " Create one to get started." : " Ask an admin to create one."}
        </div>
      )}

      <ul className="mt-6 grid gap-3 sm:grid-cols-2">
        {servers.data?.map((server) => (
          <li key={server.id}>
            <Link
              to={`/servers/${server.id}`}
              className="block rounded-xl border border-zinc-800 bg-zinc-900/40 p-4 hover:border-zinc-600"
            >
              <div className="flex items-center justify-between gap-2">
                <span className="truncate font-medium">{server.name}</span>
                <StateBadge state={server.state} />
              </div>
              <div className="mt-2 truncate text-sm text-zinc-400">{describeServer(server)}</div>
              <div className="text-sm text-zinc-500">
                port {server.port} · {server.memory} RAM
              </div>
            </Link>
          </li>
        ))}
      </ul>
    </section>
  );
}
