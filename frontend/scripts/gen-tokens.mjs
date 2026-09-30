import { readFileSync, writeFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, resolve } from "node:path";
import { buildTokens } from "./tokens.mjs";

const here = dirname(fileURLToPath(import.meta.url));
const json = JSON.parse(readFileSync(resolve(here, "../../docs/design-tokens.json"), "utf8"));
writeFileSync(resolve(here, "../src/styles/tokens.generated.css"), buildTokens(json).css);
console.log("tokens.generated.css written");
