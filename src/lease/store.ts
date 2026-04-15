import fs from "node:fs";
import path from "node:path";
import { LeasePolicy, LeaseReceipt } from "../core/types.js";

function ensureDir(dirPath: string): void {
  fs.mkdirSync(dirPath, { recursive: true });
}

function leasesDir(baseDir: string): string {
  return path.resolve(baseDir, "leases");
}

function receiptsDir(baseDir: string): string {
  return path.resolve(baseDir, "receipts");
}

export function activeLeasePath(baseDir: string): string {
  return path.resolve(leasesDir(baseDir), "active-lease.json");
}

export function readActiveLease(baseDir: string): LeasePolicy | null {
  const filePath = activeLeasePath(baseDir);
  if (!fs.existsSync(filePath)) {
    return null;
  }

  return JSON.parse(fs.readFileSync(filePath, "utf8")) as LeasePolicy;
}

export function writeActiveLease(baseDir: string, lease: LeasePolicy): string {
  const filePath = activeLeasePath(baseDir);
  ensureDir(path.dirname(filePath));
  fs.writeFileSync(filePath, `${JSON.stringify(lease, null, 2)}\n`);
  return filePath;
}

export function appendReceipt(baseDir: string, receipt: LeaseReceipt): string {
  const dir = receiptsDir(baseDir);
  ensureDir(dir);
  const filePath = path.resolve(dir, `${receipt.generatedAt.replace(/[:.]/g, "-")}-${receipt.requestId}.json`);
  fs.writeFileSync(filePath, `${JSON.stringify(receipt, null, 2)}\n`);
  return filePath;
}

export function listReceipts(baseDir: string): LeaseReceipt[] {
  const dir = receiptsDir(baseDir);
  if (!fs.existsSync(dir)) {
    return [];
  }

  return fs
    .readdirSync(dir)
    .filter((fileName) => fileName.endsWith(".json"))
    .sort()
    .reverse()
    .map((fileName) => JSON.parse(fs.readFileSync(path.resolve(dir, fileName), "utf8")) as LeaseReceipt);
}
