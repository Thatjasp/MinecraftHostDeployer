import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useState, type FormEvent } from "react";
import { useNavigate } from "react-router-dom";

import { post } from "../api";
import { Alert, Button, Field } from "../components/ui";
import {
  IMAGE_TAGS,
  lookupPack,
  serversKey,
  uploadModpack,
  type PackPreview,
  type Server,
  type ServerCreate,
  type ServerSource,
} from "../servers";

type SourceKind = "curseforge" | "upload" | "vanilla";

const SOURCE_TABS: { kind: SourceKind; label: string }[] = [
  { kind: "curseforge", label: "CurseForge pack" },
  { kind: "upload", label: "Upload zip" },
  { kind: "vanilla", label: "Vanilla" },
];

const selectStyles =
  "w-full rounded-md border border-zinc-700 bg-zinc-900 px-3 py-2 outline-none focus:border-emerald-500";

function PackCard({ pack }: { pack: PackPreview }) {
  const runtime = [pack.loader, pack.mc_version].filter(Boolean).join(" ") || "version unknown";
  return (
    <div className="flex gap-3 rounded-lg border border-zinc-800 bg-zinc-900/60 p-3">
      {pack.logo_url && (
        <img src={pack.logo_url} alt="" className="size-14 shrink-0 rounded-md object-cover" />
      )}
      <div className="min-w-0 text-sm">
        <div className="font-medium">
          {pack.page_url ? (
            <a href={pack.page_url} target="_blank" rel="noreferrer" className="hover:underline">
              {pack.name}
            </a>
          ) : (
            pack.name
          )}
        </div>
        <div className="text-zinc-400">
          {runtime}
          {pack.file_name && ` · ${pack.file_name}`}
        </div>
        {pack.kind === "client" && (
          <div className="text-zinc-500">CurseForge export: mods download when the server first starts.</div>
        )}
        {pack.kind === "server" && <div className="text-zinc-500">Server pack: mods are included.</div>}
        {pack.summary && <div className="mt-1 line-clamp-2 text-zinc-500">{pack.summary}</div>}
      </div>
    </div>
  );
}

export default function CreateServerPage() {
  const navigate = useNavigate();
  const queryClient = useQueryClient();

  const [sourceKind, setSourceKind] = useState<SourceKind>("curseforge");
  const [packRef, setPackRef] = useState("");
  const [version, setVersion] = useState("LATEST");
  const [preview, setPreview] = useState<PackPreview | null>(null);
  const [uploadProgress, setUploadProgress] = useState<number | null>(null);

  const [name, setName] = useState("");
  const [port, setPort] = useState("");
  const [memory, setMemory] = useState("6");
  const [imageTag, setImageTag] = useState("latest");
  const [motd, setMotd] = useState("");
  const [acceptEula, setAcceptEula] = useState(false);

  const showPreview = (pack: PackPreview) => {
    setPreview(pack);
    setImageTag(pack.suggested_image_tag);
    setName((current) => current || pack.name.slice(0, 40));
  };

  const lookup = useMutation({ mutationFn: lookupPack, onSuccess: showPreview });
  const upload = useMutation({
    mutationFn: (file: File) => uploadModpack(file, setUploadProgress),
    onSuccess: showPreview,
    onSettled: () => setUploadProgress(null),
  });
  const create = useMutation({
    mutationFn: (body: ServerCreate) => post<Server>("/servers", body),
    onSuccess: (server) => {
      queryClient.invalidateQueries({ queryKey: serversKey });
      navigate(`/servers/${server.id}`);
    },
  });

  const switchSource = (kind: SourceKind) => {
    setSourceKind(kind);
    setPreview(null);
    lookup.reset();
    upload.reset();
    setMemory(kind === "vanilla" ? "4" : "6");
    setImageTag("latest");
  };

  const source: ServerSource | null =
    sourceKind === "vanilla"
      ? { type: "vanilla", version }
      : sourceKind === "curseforge" && preview
        ? { type: "curseforge", ref: packRef }
        : sourceKind === "upload" && preview?.upload_id
          ? { type: "upload", upload_id: preview.upload_id }
          : null;

  const submit = (e: FormEvent) => {
    e.preventDefault();
    if (!source) return;
    create.mutate({
      name,
      source,
      port: port ? Number(port) : null,
      memory: `${memory}G`,
      image_tag: imageTag,
      motd,
      accept_eula: acceptEula,
    });
  };

  const error = lookup.error ?? upload.error ?? create.error;

  return (
    <section className="max-w-xl">
      <h1 className="text-xl font-semibold">New server</h1>

      <div className="mt-6 flex gap-1 rounded-lg border border-zinc-800 p-1">
        {SOURCE_TABS.map(({ kind, label }) => (
          <button
            key={kind}
            type="button"
            onClick={() => switchSource(kind)}
            className={`flex-1 rounded-md px-3 py-1.5 text-sm ${
              sourceKind === kind ? "bg-zinc-800 text-white" : "text-zinc-400 hover:text-white"
            }`}
          >
            {label}
          </button>
        ))}
      </div>

      <div className="mt-4 space-y-3">
        {sourceKind === "curseforge" && (
          <form
            className="flex items-end gap-2"
            onSubmit={(e) => {
              e.preventDefault();
              setPreview(null);
              lookup.mutate(packRef);
            }}
          >
            <div className="flex-1">
              <Field
                label="CurseForge modpack URL or slug"
                placeholder="https://www.curseforge.com/minecraft/modpacks/all-the-mods-9"
                value={packRef}
                onChange={(e) => {
                  setPackRef(e.target.value);
                  setPreview(null);
                }}
                required
              />
            </div>
            <Button type="submit" variant="secondary" disabled={lookup.isPending}>
              {lookup.isPending ? "Looking up…" : "Look up"}
            </Button>
          </form>
        )}

        {sourceKind === "upload" && (
          <label className="block">
            <span className="mb-1 block text-sm text-zinc-400">
              CurseForge export or server pack (.zip)
            </span>
            <input
              type="file"
              accept=".zip,application/zip"
              disabled={upload.isPending}
              onChange={(e) => {
                const file = e.target.files?.[0];
                setPreview(null);
                if (file) upload.mutate(file);
              }}
              className="block w-full text-sm text-zinc-400 file:mr-3 file:rounded-md file:border-0 file:bg-zinc-800 file:px-3 file:py-2 file:text-zinc-200 hover:file:bg-zinc-700"
            />
            {uploadProgress !== null && (
              <div className="mt-2 h-1.5 overflow-hidden rounded-full bg-zinc-800">
                <div
                  className="h-full bg-emerald-500 transition-all"
                  style={{ width: `${Math.round(uploadProgress * 100)}%` }}
                />
              </div>
            )}
          </label>
        )}

        {sourceKind === "vanilla" && (
          <Field
            label="Minecraft version"
            value={version}
            onChange={(e) => setVersion(e.target.value)}
            placeholder="LATEST or 1.21.1"
            required
          />
        )}

        {preview && <PackCard pack={preview} />}
        {error && <Alert>{error.message}</Alert>}
      </div>

      <form onSubmit={submit} className="mt-6 space-y-4 border-t border-zinc-800 pt-6">
        <Field
          label="Server name"
          value={name}
          onChange={(e) => setName(e.target.value)}
          maxLength={40}
          required
        />
        <div className="grid gap-4 sm:grid-cols-2">
          <Field
            label="Port (blank = auto)"
            type="number"
            min={1024}
            max={65535}
            value={port}
            onChange={(e) => setPort(e.target.value)}
            placeholder="25565"
          />
          <Field
            label="Memory (GB)"
            type="number"
            min={1}
            max={64}
            value={memory}
            onChange={(e) => setMemory(e.target.value)}
            required
          />
        </div>
        <label className="block">
          <span className="mb-1 block text-sm text-zinc-400">Java version</span>
          <select className={selectStyles} value={imageTag} onChange={(e) => setImageTag(e.target.value)}>
            {IMAGE_TAGS.map(({ tag, label }) => (
              <option key={tag} value={tag}>
                {label}
                {preview?.suggested_image_tag === tag ? " (suggested)" : ""}
              </option>
            ))}
          </select>
        </label>
        <Field
          label="Message of the day (optional)"
          value={motd}
          onChange={(e) => setMotd(e.target.value)}
          maxLength={120}
        />
        <label className="flex items-start gap-2 text-sm">
          <input
            type="checkbox"
            className="mt-0.5 accent-emerald-500"
            checked={acceptEula}
            onChange={(e) => setAcceptEula(e.target.checked)}
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
        <Button type="submit" disabled={!source || create.isPending}>
          {create.isPending ? "Creating…" : "Create and start"}
        </Button>
        {!source && sourceKind !== "vanilla" && (
          <p className="text-sm text-zinc-500">
            {sourceKind === "curseforge" ? "Look up a pack first." : "Upload a zip first."}
          </p>
        )}
      </form>
    </section>
  );
}
