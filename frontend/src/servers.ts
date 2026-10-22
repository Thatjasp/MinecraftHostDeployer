import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api, del, post } from "./api";

export type ServerState =
  | "stopped"
  | "pulling"
  | "starting"
  | "online"
  | "unhealthy"
  | "stopping"
  | "error"
  | "unknown";

export interface Server {
  id: number;
  name: string;
  port: number;
  memory: string;
  image_tag: string;
  server_type: string;
  version: string;
  motd: string;
  created_at: string;
  state: ServerState;
  detail: string | null;
}

export interface ServerCreate {
  name: string;
  version: string;
  port: number | null;
  memory: string;
  image_tag: string;
  motd: string;
  accept_eula: boolean;
}

// Must match IMAGE_TAGS in backend/app/servers.py.
export const IMAGE_TAGS: { tag: string; label: string }[] = [
  { tag: "latest", label: "latest (newest Java, for the newest Minecraft)" },
  { tag: "java25", label: "Java 25 (Minecraft 26.1+)" },
  { tag: "java21", label: "Java 21 (Minecraft 1.20.5 – 1.21.x)" },
  { tag: "java17", label: "Java 17 (Minecraft 1.17 – 1.20.4)" },
  { tag: "java11", label: "Java 11" },
  { tag: "java8", label: "Java 8 (Minecraft 1.16 and older)" },
];

/** States in which the server process is up and accepts console commands. */
export const isOnline = (state: ServerState) => state === "online" || state === "unhealthy";
/** States from which Stop makes sense. */
export const isRunning = (state: ServerState) => isOnline(state) || state === "starting";

export const serversKey = ["servers"] as const;

export function useServers() {
  return useQuery({
    queryKey: serversKey,
    queryFn: () => api<Server[]>("/servers"),
    refetchInterval: 3000,
  });
}

export function useServer(id: number) {
  return useQuery({
    queryKey: [...serversKey, id],
    queryFn: () => api<Server>(`/servers/${id}`),
    refetchInterval: 2000,
  });
}

export function useServerAction(id: number) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (action: "start" | "stop" | "restart") => post<Server>(`/servers/${id}/${action}`),
    onSuccess: (server) => {
      queryClient.setQueryData([...serversKey, id], server);
      queryClient.invalidateQueries({ queryKey: serversKey });
    },
  });
}

export function useDeleteServer() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (id: number) => del(`/servers/${id}`),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: serversKey }),
  });
}

export const sendCommand = (id: number, command: string) =>
  post<{ output: string }>(`/servers/${id}/command`, { command });
