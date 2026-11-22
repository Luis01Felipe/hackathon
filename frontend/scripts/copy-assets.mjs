// Copia o wasm do web-ifc e o worker do @thatopen/fragments para public/.
// A demo não pode depender de CDN: o visualizador carrega tudo do próprio servidor.
import { copyFileSync, existsSync, mkdirSync } from "node:fs";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const root = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const modules = join(root, "node_modules");

const copies = [
  [join(modules, "web-ifc", "web-ifc.wasm"), join(root, "public", "wasm", "web-ifc.wasm")],
  [join(modules, "web-ifc", "web-ifc-mt.wasm"), join(root, "public", "wasm", "web-ifc-mt.wasm")],
  [
    join(modules, "@thatopen", "fragments", "dist", "Worker", "worker.min.mjs"),
    join(root, "public", "fragments", "worker.mjs"),
  ],
];

let missing = 0;
for (const [source, target] of copies) {
  if (!existsSync(source)) {
    console.warn(`[copy-assets] arquivo ausente: ${source}`);
    missing += 1;
    continue;
  }
  mkdirSync(dirname(target), { recursive: true });
  copyFileSync(source, target);
}

console.log(`[copy-assets] ${copies.length - missing} de ${copies.length} arquivo(s) copiados para public/`);
if (missing > 0) process.exitCode = 1;
