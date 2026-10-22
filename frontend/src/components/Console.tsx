import { FitAddon } from "@xterm/addon-fit";
import { Terminal } from "@xterm/xterm";
import "@xterm/xterm/css/xterm.css";
import { useEffect, useRef, useState, type FormEvent, type KeyboardEvent } from "react";

import { sendCommand } from "../servers";

const CYAN = "\x1b[36m";
const GRAY = "\x1b[90m";
const RED = "\x1b[31m";
const RESET = "\x1b[0m";

type ConsoleMessage = { type: "log"; lines: string[] } | { type: "error"; message: string };

/** Live server log (WebSocket) plus a command box that runs commands over RCON. */
export function Console({ serverId, online }: { serverId: number; online: boolean }) {
  const containerRef = useRef<HTMLDivElement>(null);
  const terminalRef = useRef<Terminal | null>(null);
  const [command, setCommand] = useState("");
  const [sending, setSending] = useState(false);
  const history = useRef<string[]>([]);
  const historyIndex = useRef(-1);

  useEffect(() => {
    const terminal = new Terminal({
      convertEol: true,
      disableStdin: true,
      fontSize: 13,
      scrollback: 5000,
      theme: { background: "#09090b" },
    });
    const fit = new FitAddon();
    terminal.loadAddon(fit);
    terminal.open(containerRef.current!);
    fit.fit();
    terminalRef.current = terminal;
    const observer = new ResizeObserver(() => fit.fit());
    observer.observe(containerRef.current!);

    let socket: WebSocket | null = null;
    let retryTimer: number | undefined;
    let disposed = false;

    const connect = () => {
      const scheme = location.protocol === "https:" ? "wss" : "ws";
      socket = new WebSocket(`${scheme}://${location.host}/api/servers/${serverId}/console`);
      // Each connection replays recent history, so start from a clean screen.
      socket.onopen = () => terminal.reset();
      socket.onmessage = (event) => {
        const message = JSON.parse(event.data) as ConsoleMessage;
        if (message.type === "log") terminal.write(message.lines.join("\n") + "\n");
        else terminal.writeln(`${RED}${message.message}${RESET}`);
      };
      socket.onclose = () => {
        if (!disposed) retryTimer = window.setTimeout(connect, 3000);
      };
    };
    connect();

    return () => {
      disposed = true;
      window.clearTimeout(retryTimer);
      socket?.close();
      observer.disconnect();
      terminal.dispose();
      terminalRef.current = null;
    };
  }, [serverId]);

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    const text = command.trim();
    if (!text) return;
    const terminal = terminalRef.current;
    history.current.unshift(text);
    historyIndex.current = -1;
    setCommand("");
    setSending(true);
    terminal?.writeln(`${CYAN}> ${text}${RESET}`);
    try {
      const { output } = await sendCommand(serverId, text);
      if (output.trim()) terminal?.writeln(`${GRAY}${output.trimEnd()}${RESET}`);
    } catch (err) {
      terminal?.writeln(`${RED}${(err as Error).message}${RESET}`);
    } finally {
      setSending(false);
    }
  };

  const browseHistory = (e: KeyboardEvent<HTMLInputElement>) => {
    if (e.key !== "ArrowUp" && e.key !== "ArrowDown") return;
    e.preventDefault();
    const step = e.key === "ArrowUp" ? 1 : -1;
    const next = Math.min(Math.max(historyIndex.current + step, -1), history.current.length - 1);
    historyIndex.current = next;
    setCommand(next === -1 ? "" : history.current[next]);
  };

  return (
    <div className="overflow-hidden rounded-xl border border-zinc-800 bg-zinc-950">
      <div ref={containerRef} className="h-[28rem] p-2" />
      <form onSubmit={submit} className="flex border-t border-zinc-800">
        <span className="px-3 py-2 font-mono text-sm text-zinc-500">&gt;</span>
        <input
          className="flex-1 bg-transparent py-2 pr-3 font-mono text-sm outline-none disabled:opacity-50"
          placeholder={online ? "Type a command, e.g. list or say hello" : "Server is not online"}
          value={command}
          onChange={(e) => setCommand(e.target.value)}
          onKeyDown={browseHistory}
          disabled={!online || sending}
          maxLength={1000}
          autoComplete="off"
          spellCheck={false}
        />
      </form>
    </div>
  );
}
