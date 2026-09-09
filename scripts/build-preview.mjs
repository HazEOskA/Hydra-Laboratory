import { access, cp, mkdir, readFile, rm } from "node:fs/promises";
import { execFileSync } from "node:child_process";
import { resolve } from "node:path";

const root = process.cwd();
const web = resolve(root, "web");
const output = resolve(root, "dist");

const required = [
  "index.html",
  "app.js",
  "styles.css",
  "runtime-config.js",
  "assets/brand/hydra-wordmark.webp",
  "assets/illustrations/apr-evidence.webp",
  "assets/illustrations/michael-angelo-lens.webp",
  "assets/illustrations/model-router-core.webp",
  "assets/illustrations/monitoring-hydra.webp",
  "assets/illustrations/night-watch.webp",
  "assets/illustrations/openshell-claw.webp",
  "assets/illustrations/policies-ai.webp",
  "assets/illustrations/zgredek-observatory.webp"
];

for (const relative of required) {
  await access(resolve(web, relative));
}

const [html, app, css, config] = await Promise.all([
  readFile(resolve(web, "index.html"), "utf8"),
  readFile(resolve(web, "app.js"), "utf8"),
  readFile(resolve(web, "styles.css"), "utf8"),
  readFile(resolve(web, "runtime-config.js"), "utf8")
]);

execFileSync(process.execPath, ["--check", resolve(web, "app.js")], { stdio: "inherit" });

const nav = [
  "Dashboard", "Policies AI", "Michael Angelo", "Missions", "Agent Fleet",
  "Repositories", "Sandboxes", "Approvals", "APR Evidence", "Artifacts",
  "Infrastructure", "Audit Log", "Settings"
];
for (const label of nav) {
  if (!app.includes(`"${label}"`)) throw new Error(`Missing navigation item: ${label}`);
}

const contracts = [
  [html.includes('/runtime-config.js'), "runtime config script missing"],
  [html.includes('/app.js'), "application script missing"],
  [app.includes("Zgredek"), "Zgredek surface missing"],
  [app.includes("HYDRA runtime API is not connected in this preview."), "fail-closed runtime message missing"],
  [app.includes("disabled: !HYDRA_CONFIG.apiEnabled"), "runtime mutation disable gate missing"],
  [!app.includes("innerHTML"), "unsafe innerHTML detected"],
  [config.includes("apiEnabled: false"), "Vercel preview must default to API disconnected"],
  [css.includes("#d4af37"), "locked gold token missing"],
  [css.includes("#a855f7"), "locked purple token missing"]
];
for (const [ok, message] of contracts) {
  if (!ok) throw new Error(message);
}

await rm(output, { recursive: true, force: true });
await mkdir(output, { recursive: true });
await cp(web, output, { recursive: true });

console.log("HYDRA_PREVIEW_GATE PASS");
console.log("Navigation:", nav.length, "routes");
console.log("Runtime mutations:", "FAIL-CLOSED");
console.log("Output:", output);
