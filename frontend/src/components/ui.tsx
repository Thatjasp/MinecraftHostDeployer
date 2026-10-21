import type { ButtonHTMLAttributes, InputHTMLAttributes, ReactNode } from "react";

export function Field({
  label,
  ...props
}: InputHTMLAttributes<HTMLInputElement> & { label: string }) {
  return (
    <label className="block">
      <span className="mb-1 block text-sm text-zinc-400">{label}</span>
      <input
        className="w-full rounded-md border border-zinc-700 bg-zinc-900 px-3 py-2 outline-none focus:border-emerald-500"
        {...props}
      />
    </label>
  );
}

const buttonStyles = {
  primary: "bg-emerald-600 text-white hover:bg-emerald-500",
  secondary: "border border-zinc-700 text-zinc-200 hover:bg-zinc-800",
  danger: "border border-red-900 text-red-300 hover:bg-red-950",
};

export function Button({
  variant = "primary",
  className = "",
  ...props
}: ButtonHTMLAttributes<HTMLButtonElement> & { variant?: keyof typeof buttonStyles }) {
  return (
    <button
      className={`rounded-md px-3 py-2 text-sm font-medium transition disabled:opacity-50 ${buttonStyles[variant]} ${className}`}
      {...props}
    />
  );
}

export function Alert({ kind = "error", children }: { kind?: "error" | "info"; children: ReactNode }) {
  const styles =
    kind === "error"
      ? "border-red-900 bg-red-950/50 text-red-300"
      : "border-emerald-900 bg-emerald-950/50 text-emerald-300";
  return <div className={`rounded-md border px-3 py-2 text-sm ${styles}`}>{children}</div>;
}

export function AuthCard({ title, children }: { title: string; children: ReactNode }) {
  return (
    <main className="flex min-h-screen items-center justify-center p-4">
      <div className="w-full max-w-sm rounded-xl border border-zinc-800 bg-zinc-900/60 p-6">
        <h1 className="mb-6 text-xl font-semibold">{title}</h1>
        {children}
      </div>
    </main>
  );
}
