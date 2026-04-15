import fs from "node:fs";
import path from "node:path";
import { OperatorMode, OperatorState } from "../core/types.js";

function ensureDir(dirPath: string): void {
  fs.mkdirSync(dirPath, { recursive: true });
}

function statePath(baseDir: string): string {
  return path.resolve(baseDir, "operator-state.json");
}

function eventsDir(baseDir: string): string {
  return path.resolve(baseDir, "operator-events");
}

export function defaultOperatorState(operatorName: string): OperatorState {
  return {
    operatorName,
    mode: "active",
    lastCommand: "initialize",
    updatedAt: new Date().toISOString()
  };
}

export function readOperatorState(baseDir: string, operatorName: string): OperatorState {
  const filePath = statePath(baseDir);
  if (!fs.existsSync(filePath)) {
    return defaultOperatorState(operatorName);
  }

  return JSON.parse(fs.readFileSync(filePath, "utf8")) as OperatorState;
}

export function applyOperatorCommand(input: {
  baseDir: string;
  operatorName: string;
  mode: OperatorMode;
  lastCommand: OperatorState["lastCommand"];
  note?: string;
}): { state: OperatorState; statePath: string; eventPath: string } {
  const generatedAt = new Date().toISOString();
  const state: OperatorState = {
    operatorName: input.operatorName,
    mode: input.mode,
    lastCommand: input.lastCommand,
    note: input.note,
    updatedAt: generatedAt
  };

  ensureDir(input.baseDir);
  const writtenStatePath = statePath(input.baseDir);
  fs.writeFileSync(writtenStatePath, `${JSON.stringify(state, null, 2)}\n`);

  const eventDir = eventsDir(input.baseDir);
  ensureDir(eventDir);
  const eventPath = path.resolve(eventDir, `${generatedAt.replace(/[:.]/g, "-")}.json`);
  fs.writeFileSync(eventPath, `${JSON.stringify({ ...state, command: input.lastCommand }, null, 2)}\n`);

  return { state, statePath: writtenStatePath, eventPath };
}
