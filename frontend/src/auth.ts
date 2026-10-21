import { useQuery } from "@tanstack/react-query";

import { ApiError, api } from "./api";

export type Role = "admin" | "user";
export type UserStatus = "pending" | "active" | "disabled";

export interface User {
  id: number;
  username: string;
  role: Role;
  status: UserStatus;
  created_at: string;
}

export const meKey = ["me"] as const;

/** The logged-in user, or null when logged out. */
export function useMe() {
  return useQuery({
    queryKey: meKey,
    queryFn: async () => {
      try {
        return await api<User>("/auth/me");
      } catch (e) {
        if (e instanceof ApiError && e.status === 401) return null;
        throw e;
      }
    },
    retry: false,
    staleTime: 60_000,
  });
}

/** True until the first (admin) account exists. */
export function useNeedsSetup() {
  return useQuery({
    queryKey: ["setup"],
    queryFn: async () => (await api<{ needs_setup: boolean }>("/auth/setup")).needs_setup,
  });
}
