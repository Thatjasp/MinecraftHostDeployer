import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api, del, patch } from "../api";
import { useMe, type User } from "../auth";
import { Alert, Button } from "../components/ui";

const statusColor = {
  pending: "text-amber-400",
  active: "text-emerald-400",
  disabled: "text-zinc-500",
};

export default function UsersPage() {
  const me = useMe();
  const queryClient = useQueryClient();
  const users = useQuery({ queryKey: ["users"], queryFn: () => api<User[]>("/users") });

  const update = useMutation({
    mutationFn: ({ id, ...changes }: Pick<User, "id"> & Partial<Pick<User, "role" | "status">>) =>
      patch<User>(`/users/${id}`, changes),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["users"] }),
  });
  const remove = useMutation({
    mutationFn: (id: number) => del(`/users/${id}`),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["users"] }),
  });
  const busy = update.isPending || remove.isPending;
  const error = update.error ?? remove.error ?? users.error;

  return (
    <section>
      <h1 className="text-xl font-semibold">Users</h1>
      {error && (
        <div className="mt-4">
          <Alert>{error.message}</Alert>
        </div>
      )}
      <div className="mt-6 overflow-x-auto rounded-xl border border-zinc-800">
        <table className="w-full text-left text-sm">
          <thead className="bg-zinc-900 text-zinc-400">
            <tr>
              <th className="px-4 py-2 font-medium">Username</th>
              <th className="px-4 py-2 font-medium">Role</th>
              <th className="px-4 py-2 font-medium">Status</th>
              <th className="px-4 py-2 font-medium">Created</th>
              <th className="px-4 py-2" />
            </tr>
          </thead>
          <tbody className="divide-y divide-zinc-800">
            {users.data?.map((user) => (
              <tr key={user.id}>
                <td className="px-4 py-2">{user.username}</td>
                <td className="px-4 py-2">{user.role}</td>
                <td className={`px-4 py-2 ${statusColor[user.status]}`}>{user.status}</td>
                <td className="px-4 py-2 text-zinc-400">
                  {new Date(user.created_at).toLocaleDateString()}
                </td>
                <td className="px-4 py-2">
                  {user.id === me.data?.id ? (
                    <span className="text-zinc-500">you</span>
                  ) : (
                    <div className="flex justify-end gap-2">
                      {user.status !== "active" && (
                        <Button
                          disabled={busy}
                          onClick={() => update.mutate({ id: user.id, status: "active" })}
                        >
                          {user.status === "pending" ? "Approve" : "Enable"}
                        </Button>
                      )}
                      {user.status === "active" && (
                        <Button
                          variant="secondary"
                          disabled={busy}
                          onClick={() => update.mutate({ id: user.id, status: "disabled" })}
                        >
                          Disable
                        </Button>
                      )}
                      <Button
                        variant="secondary"
                        disabled={busy}
                        onClick={() =>
                          update.mutate({
                            id: user.id,
                            role: user.role === "admin" ? "user" : "admin",
                          })
                        }
                      >
                        {user.role === "admin" ? "Make user" : "Make admin"}
                      </Button>
                      <Button
                        variant="danger"
                        disabled={busy}
                        onClick={() => {
                          if (confirm(`Delete user ${user.username}?`)) remove.mutate(user.id);
                        }}
                      >
                        Delete
                      </Button>
                    </div>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}
