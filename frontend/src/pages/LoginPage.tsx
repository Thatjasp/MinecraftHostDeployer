import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useState, type FormEvent } from "react";
import { Link, Navigate } from "react-router-dom";

import { post } from "../api";
import { meKey, useMe, useNeedsSetup, type User } from "../auth";
import { Alert, AuthCard, Button, Field } from "../components/ui";

export default function LoginPage() {
  const me = useMe();
  const needsSetup = useNeedsSetup();
  const queryClient = useQueryClient();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");

  const login = useMutation({
    mutationFn: () => post<User>("/auth/login", { username, password }),
    onSuccess: (user) => queryClient.setQueryData(meKey, user),
  });

  if (me.data) return <Navigate to="/" replace />;
  if (needsSetup.data) return <Navigate to="/register" replace />;

  const submit = (e: FormEvent) => {
    e.preventDefault();
    login.mutate();
  };

  return (
    <AuthCard title="Log in">
      <form onSubmit={submit} className="space-y-4">
        {login.isError && <Alert>{login.error.message}</Alert>}
        <Field
          label="Username"
          autoComplete="username"
          value={username}
          onChange={(e) => setUsername(e.target.value)}
          required
        />
        <Field
          label="Password"
          type="password"
          autoComplete="current-password"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          required
        />
        <Button type="submit" className="w-full" disabled={login.isPending}>
          {login.isPending ? "Logging in…" : "Log in"}
        </Button>
      </form>
      <p className="mt-4 text-center text-sm text-zinc-400">
        No account?{" "}
        <Link to="/register" className="text-emerald-400 hover:underline">
          Create one
        </Link>
      </p>
    </AuthCard>
  );
}
