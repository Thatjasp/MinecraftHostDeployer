import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useState, type FormEvent } from "react";
import { Link, Navigate } from "react-router-dom";

import { post } from "../api";
import { meKey, useMe, useNeedsSetup, type User } from "../auth";
import { Alert, AuthCard, Button, Field } from "../components/ui";

export default function RegisterPage() {
  const me = useMe();
  const needsSetup = useNeedsSetup();
  const queryClient = useQueryClient();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [mismatch, setMismatch] = useState(false);

  const register = useMutation({
    mutationFn: () => post<User>("/auth/register", { username, password }),
    onSuccess: (user) => {
      // Only the first (admin) account is logged in straight away.
      if (user.status === "active") queryClient.setQueryData(meKey, user);
      queryClient.setQueryData(["setup"], false);
    },
  });

  if (me.data) return <Navigate to="/" replace />;

  if (register.data?.status === "pending") {
    return (
      <AuthCard title="Account created">
        <Alert kind="info">
          Your account <b>{register.data.username}</b> is waiting for an admin to approve it. You
          can log in once it's approved.
        </Alert>
        <Link to="/login" className="mt-4 block text-center text-sm text-emerald-400 hover:underline">
          Back to log in
        </Link>
      </AuthCard>
    );
  }

  const submit = (e: FormEvent) => {
    e.preventDefault();
    setMismatch(password !== confirm);
    if (password === confirm) register.mutate();
  };

  return (
    <AuthCard title={needsSetup.data ? "Create the admin account" : "Create an account"}>
      <form onSubmit={submit} className="space-y-4">
        {needsSetup.data && (
          <Alert kind="info">No accounts exist yet. This first account will be the admin.</Alert>
        )}
        {mismatch && <Alert>Passwords don't match</Alert>}
        {register.isError && <Alert>{register.error.message}</Alert>}
        <Field
          label="Username (3–32 letters, numbers, _ or -)"
          autoComplete="username"
          value={username}
          onChange={(e) => setUsername(e.target.value)}
          pattern="[A-Za-z0-9_\-]{3,32}"
          required
        />
        <Field
          label="Password (at least 8 characters)"
          type="password"
          autoComplete="new-password"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          minLength={8}
          maxLength={128}
          required
        />
        <Field
          label="Confirm password"
          type="password"
          autoComplete="new-password"
          value={confirm}
          onChange={(e) => setConfirm(e.target.value)}
          required
        />
        <Button type="submit" className="w-full" disabled={register.isPending}>
          {register.isPending ? "Creating…" : "Create account"}
        </Button>
      </form>
      {!needsSetup.data && (
        <p className="mt-4 text-center text-sm text-zinc-400">
          Already have an account?{" "}
          <Link to="/login" className="text-emerald-400 hover:underline">
            Log in
          </Link>
        </p>
      )}
    </AuthCard>
  );
}
