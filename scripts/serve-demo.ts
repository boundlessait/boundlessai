import fs from "node:fs";
import http from "node:http";
import path from "node:path";
import { readRuntimeEnvFromFiles } from "../src/config/env.js";

const env = readRuntimeEnvFromFiles();
const rootDir = path.resolve(env.LEASE_DATA_DIR);
const port = Number(process.env.PORT || 4312);

function contentTypeFor(filePath: string): string {
  if (filePath.endsWith(".html")) return "text/html; charset=utf-8";
  if (filePath.endsWith(".json")) return "application/json; charset=utf-8";
  return "text/plain; charset=utf-8";
}

const server = http.createServer((req, res) => {
  const urlPath = (req.url || "/").split("?")[0];
  const relative = urlPath === "/" ? "/index.html" : urlPath;
  const filePath = path.resolve(rootDir, `.${relative}`);

  if (!filePath.startsWith(rootDir) || !fs.existsSync(filePath) || fs.statSync(filePath).isDirectory()) {
    res.writeHead(404, { "content-type": "text/plain; charset=utf-8" });
    res.end("Not found");
    return;
  }

  res.writeHead(200, { "content-type": contentTypeFor(filePath) });
  res.end(fs.readFileSync(filePath));
});

server.listen(port, () => {
  console.log(`demo_root=${rootDir}`);
  console.log(`demo_url=http://127.0.0.1:${port}`);
});
