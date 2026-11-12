// JavaScript port of uptime_lite.incidents.evaluate, for the demo on this page only.
// tests/js/debounce.test.mjs runs it against debounce-cases.json, the same cases the
// Python tests run against the real state machine.
(function (root) {
  function initial() {
    return { status: "up", failures: 0, successes: 0 };
  }

  // Returns the next state and "opened", "resolved" or null.
  function step(state, ok, failureThreshold, recoveryThreshold) {
    if (state.status === "up") {
      if (ok) return { state: initial(), event: null };
      const failures = state.failures + 1;
      if (failures >= failureThreshold) {
        return { state: { status: "down", failures, successes: 0 }, event: "opened" };
      }
      return { state: { status: "up", failures, successes: 0 }, event: null };
    }
    if (!ok) {
      return {
        state: { status: "down", failures: state.failures + 1, successes: 0 },
        event: null,
      };
    }
    const successes = state.successes + 1;
    if (successes >= recoveryThreshold) return { state: initial(), event: "resolved" };
    return { state: { status: "down", failures: 0, successes }, event: null };
  }

  // pattern: "." is a pass, "x" is a fail.
  function run(pattern, failureThreshold, recoveryThreshold) {
    let state = initial();
    const events = [];
    Array.from(pattern).forEach((char, index) => {
      const next = step(state, char === ".", failureThreshold, recoveryThreshold);
      state = next.state;
      if (next.event) events.push([index, next.event]);
    });
    return { state, events };
  }

  const api = { initial, step, run };
  if (typeof module !== "undefined" && module.exports) module.exports = api;
  else root.Debounce = api;
})(typeof window !== "undefined" ? window : globalThis);
