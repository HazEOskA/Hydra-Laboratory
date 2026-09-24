import { access, cp, mkdir, rm } from "node:fs/promises";
import { execFileSync } from "node:child_process";
import { resolve } from "node:path";

const root = process.cwd();
const web = resolve(root, "web");
const output = resolve(root, "dist");

for (const relative of ["index.html", "app.js", "styles.css"]) {
  await access(resolve(web, relative));
}

execFileSync(process.execPath, ["--check", resolve(web, "app.js")], {
  stdio: "inherit"
});

await rm(output, { recursive: true, force: true });
await mkdir(output, { recursive: true });
await cp(web, output, { recursive: true });

console.log("HYDRA_PREVIEW_BUILD PASS");
console.log("Source:", web);
console.log("Output:", output);
