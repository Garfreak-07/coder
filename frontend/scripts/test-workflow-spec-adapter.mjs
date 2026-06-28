import { build } from "esbuild";
import { mkdirSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { pathToFileURL } from "node:url";

const outfile = resolve("node_modules/.cache/coder/workflowSpecAdapter.test.mjs");
mkdirSync(dirname(outfile), { recursive: true });

await build({
  entryPoints: ["src/workflowSpecAdapter.test.ts"],
  outfile,
  bundle: true,
  platform: "node",
  format: "esm",
  sourcemap: "inline",
  logLevel: "silent"
});

await import(pathToFileURL(outfile).href);
