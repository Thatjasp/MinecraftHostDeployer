import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Navigate, NavLink, Outlet } from "react-router-dom";

import { post } from "../api";
import { meKey, useMe } from "../auth";
import { Button } from "./ui";

const navLink = ({ isActive }: { isActive: boolean }) =>
  `rounded-md px-3 py-1.5 text-sm ${isActive ? "bg-zinc-800 text-white" : "text-zinc-400 hover:text-white"}`;

/** Shell for logged-in pages; sends logged-out visitors to /login. */
export function Layout() {
  const me = useMe();
  const queryClient = useQueryClient();
  const logout = useMutation({
    mutationFn: () => post<void>("/auth/logout"),
    onSuccess: () => {
      queryClient.setQueryData(meKey, null);
      queryClient.removeQueries({ predicate: (q) => q.queryKey[0] !== "me" });
    },
  });

  if (me.isPending) return null;
  if (!me.data) return <Navigate to="/login" replace />;

  return (
    <div className="min-h-screen">
      <header className="border-b border-zinc-800">
        <div className="mx-auto flex max-w-5xl items-center gap-2 px-4 py-3">
          <span className="mr-4 font-semibold">MC Panel</span>
          <NavLink to="/" end className={navLink}>
            Servers
          </NavLink>
          {me.data.role === "admin" && (
            <NavLink to="/users" className={navLink}>
              Users
            </NavLink>
          )}
          <span className="ml-auto text-sm text-zinc-400">
            {me.data.username}
            {me.data.role === "admin" && " (admin)"}
          </span>
          <Button variant="secondary" onClick={() => logout.mutate()} disabled={logout.isPending}>
            Log out
          </Button>
        </div>
      </header>
      <main className="mx-auto max-w-5xl px-4 py-6">
        <Outlet />
      </main>
    </div>
  );
}

export function RequireAdmin() {
  const me = useMe();
  return me.data?.role === "admin" ? <Outlet /> : <Navigate to="/" replace />;
}
