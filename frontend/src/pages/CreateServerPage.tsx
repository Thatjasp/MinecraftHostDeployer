import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useState, type FormEvent } from "react";
import { useNavigate } from "react-router-dom";

import { post } from "../api";
import { Alert, Button, Field } from "../components/ui";
import { IMAGE_TAGS, serversKey, type Server, type ServerCreate } from "../servers";

export default function CreateServerPage() {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [form, setForm] = useState({
    name: "",
    version: "LATEST",
    port: "",
    memory: "4",
    image_tag: "latest",
    motd: "",
    accept_eula: false,
  });
  const set = (key: keyof typeof form) => (value: string | boolean) =>
    setForm((f) => ({ ...f, [key]: value }));

  const create = useMutation({
    mutationFn: (body: ServerCreate) => post<Server>("/servers", body),
    onSuccess: (server) => {
      queryClient.invalidateQueries({ queryKey: serversKey });
      navigate(`/servers/${server.id}`);
    },
  });

  const submit = (e: FormEvent) => {
    e.preventDefault();
    create.mutate({
      ...form,
      port: form.port ? Number(form.port) : null,
      memory: `${form.memory}G`,
    });
  };

  return (
    <section className="max-w-xl">
      <h1 className="text-xl font-semibold">New server</h1>
      <p className="mt-1 text-sm text-zinc-400">
        Vanilla for now; CurseForge modpacks come in the next step.
      </p>

      <form onSubmit={submit} className="mt-6 space-y-4">
        {create.isError && <Alert>{create.error.message}</Alert>}
        <Field
          label="Name"
          value={form.name}
          onChange={(e) => set("name")(e.target.value)}
          maxLength={40}
          required
        />
        <div className="grid gap-4 sm:grid-cols-3">
          <Field
            label="Minecraft version"
            value={form.version}
            onChange={(e) => set("version")(e.target.value)}
            placeholder="LATEST or 1.21.1"
            required
          />
          <Field
            label="Port (blank = auto)"
            type="number"
            min={1024}
            max={65535}
            value={form.port}
            onChange={(e) => set("port")(e.target.value)}
            placeholder="25565"
          />
          <Field
            label="Memory (GB)"
            type="number"
            min={1}
            max={64}
            value={form.memory}
            onChange={(e) => set("memory")(e.target.value)}
            required
          />
        </div>
        <label className="block">
          <span className="mb-1 block text-sm text-zinc-400">Java version</span>
          <select
            className="w-full rounded-md border border-zinc-700 bg-zinc-900 px-3 py-2 outline-none focus:border-emerald-500"
            value={form.image_tag}
            onChange={(e) => set("image_tag")(e.target.value)}
          >
            {IMAGE_TAGS.map(({ tag, label }) => (
              <option key={tag} value={tag}>
                {label}
              </option>
            ))}
          </select>
        </label>
        <Field
          label="Message of the day (optional)"
          value={form.motd}
          onChange={(e) => set("motd")(e.target.value)}
          maxLength={120}
        />
        <label className="flex items-start gap-2 text-sm">
          <input
            type="checkbox"
            className="mt-0.5 accent-emerald-500"
            checked={form.accept_eula}
            onChange={(e) => set("accept_eula")(e.target.checked)}
            required
          />
          <span>
            I accept the{" "}
            <a
              href="https://aka.ms/MinecraftEULA"
              target="_blank"
              rel="noreferrer"
              className="text-emerald-400 hover:underline"
            >
              Minecraft EULA
            </a>
          </span>
        </label>
        <Button type="submit" disabled={create.isPending}>
          {create.isPending ? "Creating…" : "Create and start"}
        </Button>
      </form>
    </section>
  );
}
