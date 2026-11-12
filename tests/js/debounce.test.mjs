import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { createRequire } from "node:module";
import test from "node:test";

const require = createRequire(import.meta.url);
const Debounce = require("../../site/debounce.js");
const { cases } = JSON.parse(readFileSync(new URL("../../site/debounce-cases.json", import.meta.url)));

for (const item of cases) {
  test(item.name, () => {
    const { state, events } = Debounce.run(
      item.pattern,
      item.failure_threshold,
      item.recovery_threshold,
    );
    assert.deepEqual(events, item.events);
    assert.deepEqual(state, item.final);
  });
}
