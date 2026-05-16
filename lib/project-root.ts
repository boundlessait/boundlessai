import fs from 'node:fs';
import path from 'node:path';

const PROJECT_PACKAGE_NAME = 'boundless';
const PROJECT_DIR_ALIASES = ['boundlessai', 'boundless', 'xlayer-trust-leases'];

function isProjectRoot(candidate: string): boolean {
  if (!candidate) {
    return false;
  }

  const packageJsonPath = path.join(candidate, 'package.json');
  const dataDirPath = path.join(candidate, 'data', 'trust-leases');
  if (!fs.existsSync(packageJsonPath) || !fs.existsSync(dataDirPath)) {
    return false;
  }

  try {
    const packageJson = JSON.parse(fs.readFileSync(packageJsonPath, 'utf8')) as { name?: string };
    return packageJson.name === PROJECT_PACKAGE_NAME;
  } catch {
    return false;
  }
}

export function resolveProjectRoot(cwd = process.cwd()): string {
  const envRoot = process.env.BOUNDLESS_APP_ROOT;
  if (envRoot && isProjectRoot(envRoot)) {
    return envRoot;
  }

  const direct = path.resolve(cwd);
  if (isProjectRoot(direct)) {
    return direct;
  }

  for (const alias of PROJECT_DIR_ALIASES) {
    const nested = path.join(direct, 'projects', alias);
    if (isProjectRoot(nested)) {
      return nested;
    }
  }

  let cursor = direct;
  while (true) {
    if (PROJECT_DIR_ALIASES.includes(path.basename(cursor)) && isProjectRoot(cursor)) {
      return cursor;
    }

    const parent = path.dirname(cursor);
    if (parent === cursor) {
      break;
    }
    cursor = parent;
  }

  return direct;
}
