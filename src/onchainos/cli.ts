import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { execFileSync } from "node:child_process";

export interface OnchainOsResponse<T = unknown> {
  ok: boolean;
  data?: T;
  error?: string;
  raw?: unknown;
}

function parseEnvFile(content: string): Record<string, string> {
  const pairs: Record<string, string> = {};

  for (const rawLine of content.split(/\r?\n/)) {
    const line = rawLine.trim();
    if (!line || line.startsWith("#")) {
      continue;
    }

    const separator = line.indexOf("=");
    if (separator === -1) {
      continue;
    }

    const key = line.slice(0, separator).trim();
    let value = line.slice(separator + 1).trim();

    if (
      (value.startsWith('"') && value.endsWith('"')) ||
      (value.startsWith("'") && value.endsWith("'"))
    ) {
      value = value.slice(1, -1);
    }

    pairs[key] = value;
  }

  return pairs;
}

function parseJsonFromText(text: string): unknown {
  const trimmed = text.trim();
  if (!trimmed) {
    return null;
  }

  try {
    return JSON.parse(trimmed);
  } catch {
    const objectStart = Math.min(
      ...[trimmed.indexOf("{"), trimmed.indexOf("[")].filter((value) => value >= 0)
    );

    if (Number.isFinite(objectStart) && objectStart >= 0) {
      return JSON.parse(trimmed.slice(objectStart));
    }

    return trimmed;
  }
}

function readOnchainOsHomeEnv(): Record<string, string> {
  const envPath = path.join(os.homedir(), ".config", "onchainos.env");
  if (!fs.existsSync(envPath)) {
    return {};
  }

  return parseEnvFile(fs.readFileSync(envPath, "utf8"));
}

function readProjectEnv(cwd = process.cwd()): Record<string, string> {
  const merged: Record<string, string> = {};

  for (const fileName of [".env", ".env.local"]) {
    const filePath = path.resolve(cwd, fileName);
    if (!fs.existsSync(filePath)) {
      continue;
    }

    Object.assign(merged, parseEnvFile(fs.readFileSync(filePath, "utf8")));
  }

  return merged;
}

function withProxyEnv(env: Record<string, string | undefined>): Record<string, string> {
  const next: Record<string, string> = {};

  for (const [key, value] of Object.entries(env)) {
    if (typeof value === "string") {
      next[key] = value;
    }
  }

  next.PATH = `${process.env.HOME}/.local/bin:${next.PATH || process.env.PATH || ""}`;

  const proxy =
    next.OKX_AGENT_PROXY ||
    next.ONCHAINOS_PROXY ||
    next.HTTPS_PROXY ||
    next.HTTP_PROXY ||
    "";

  if (proxy) {
    next.HTTPS_PROXY = proxy;
    next.HTTP_PROXY = proxy;
  }

  return next;
}

export class OnchainOsCliClient {
  private readonly bins: string[];
  private readonly timeoutMs: number;

  constructor(input?: { binPath?: string; timeoutMs?: number }) {
    const configuredTimeoutMs = Number(process.env.ONCHAINOS_TIMEOUT_MS ?? "30000");
    this.bins = [
      input?.binPath,
      process.env.ONCHAINOS_BIN,
      path.join(os.homedir(), ".local", "bin", "onchainos"),
      "onchainos"
    ].filter((value): value is string => Boolean(value));
    this.timeoutMs =
      input?.timeoutMs ??
      (Number.isFinite(configuredTimeoutMs) && configuredTimeoutMs > 0 ? configuredTimeoutMs : 30_000);
  }

  private run(args: string[]): OnchainOsResponse {
    const env = withProxyEnv({
      ...readOnchainOsHomeEnv(),
      ...readProjectEnv(),
      ...process.env
    });

    let lastError = "onchainos binary not found";

    for (const bin of this.bins) {
      if (bin.includes(path.sep) && !fs.existsSync(bin)) {
        continue;
      }

      try {
        const output = execFileSync(bin, args, {
          env,
          timeout: this.timeoutMs,
          encoding: "utf8",
          stdio: ["ignore", "pipe", "pipe"]
        });
        const parsed = parseJsonFromText(output);

        if (typeof parsed === "object" && parsed && "ok" in parsed) {
          const payload = parsed as { ok: boolean; data?: unknown; error?: string };
          return {
            ok: payload.ok,
            data: payload.data,
            error: payload.error,
            raw: parsed
          };
        }

        return {
          ok: true,
          data: parsed,
          raw: parsed
        };
      } catch (error) {
        const failure = error as NodeJS.ErrnoException & {
          stdout?: Buffer | string;
          stderr?: Buffer | string;
        };
        const stdout = typeof failure.stdout === "string" ? failure.stdout : failure.stdout?.toString() ?? "";
        const stderr = typeof failure.stderr === "string" ? failure.stderr : failure.stderr?.toString() ?? "";
        const combined = `${stdout}\n${stderr}`.trim();

        if (combined) {
          try {
            const parsed = parseJsonFromText(combined);
            if (typeof parsed === "object" && parsed && "ok" in parsed) {
              const payload = parsed as { ok: boolean; data?: unknown; error?: string };
              return {
                ok: payload.ok,
                data: payload.data,
                error: payload.error,
                raw: parsed
              };
            }
          } catch {
            // fall through to plain-text error
          }
        }

        lastError = combined || failure.message || `failed to execute ${bin}`;
      }
    }

    return {
      ok: false,
      error: lastError
    };
  }

  isAvailable(): boolean {
    return this.run(["--version"]).ok;
  }

  walletStatus(): OnchainOsResponse {
    return this.run(["wallet", "status"]);
  }

  walletBalance(chainId: number): OnchainOsResponse {
    return this.run(["wallet", "balance", "--chain", String(chainId), "--force"]);
  }

  defiPositions(address: string, chainId: number): OnchainOsResponse {
    return this.run(["defi", "positions", "--address", address, "--chains", String(chainId)]);
  }

  tokenSearch(query: string, chainId: number): OnchainOsResponse {
    return this.run(["token", "search", "--query", query, "--chains", String(chainId)]);
  }

  swapQuote(input: {
    fromAddress: string;
    toAddress: string;
    amount: string;
    chainId: number;
  }): OnchainOsResponse {
    return this.run([
      "swap",
      "quote",
      "--from",
      input.fromAddress,
      "--to",
      input.toAddress,
      "--amount",
      input.amount,
      "--chain",
      String(input.chainId)
    ]);
  }

  swapExecute(input: {
    fromAddress: string;
    toAddress: string;
    amount: string;
    chainId: number;
    chainName?: string;
    walletAddress?: string;
    readableAmount?: string;
    slippagePct?: number;
  }): OnchainOsResponse {
    const args = [
      "swap",
      "execute",
      "--from",
      input.fromAddress,
      "--to",
      input.toAddress,
      "--amount",
      input.amount,
      "--chain",
      input.chainName ?? String(input.chainId),
      "--wallet",
      input.walletAddress ?? "default",
      "--slippage",
      String(input.slippagePct ?? 0.5)
    ];

    if (input.readableAmount) {
      const amountIndex = args.indexOf("--amount");
      args.splice(amountIndex, 2, "--readable-amount", input.readableAmount);
    }

    return this.run(args);
  }

  tokenScan(address: string, chainId: number): OnchainOsResponse {
    return this.run(["security", "token-scan", "--address", address, "--chain", String(chainId)]);
  }
}
