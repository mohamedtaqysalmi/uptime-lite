(function () {
  const MAX_RESULTS = 40;
  const nInput = document.getElementById("failure-threshold");
  const mInput = document.getElementById("recovery-threshold");
  const stateLine = document.getElementById("state-line");
  const counter = document.getElementById("counter");
  const trail = document.getElementById("trail");
  const events = document.getElementById("events");
  const patterns = document.getElementById("patterns");
  const passButton = document.getElementById("send-pass");
  const failButton = document.getElementById("send-fail");

  // "." is a pass and "x" a fail, the same notation as debounce-cases.json.
  let sequence = "";

  function threshold(input) {
    const value = Number.parseInt(input.value, 10);
    if (!Number.isFinite(value)) return 1;
    return Math.min(Math.max(value, 1), 10);
  }

  function render() {
    const n = threshold(nInput);
    const m = threshold(mInput);
    const { state, events: raised } = window.Debounce.run(sequence, n, m);
    const markAt = new Set(raised.map(([index]) => index));

    stateLine.replaceChildren();
    const tag = document.createElement("strong");
    tag.className = state.status === "up" ? "tag tag-ok" : "tag tag-no";
    tag.textContent = state.status === "up" ? "UP" : "DOWN";
    stateLine.append("State: ", tag);

    counter.textContent =
      state.status === "up"
        ? `Failures in a row: ${state.failures} of ${n} needed to open an incident`
        : `Passes in a row: ${state.successes} of ${m} needed to resolve it`;

    trail.replaceChildren();
    Array.from(sequence).forEach((char, index) => {
      const li = document.createElement("li");
      const pass = char === ".";
      li.className = (pass ? "pass" : "fail") + (markAt.has(index) ? " mark" : "");
      li.textContent = pass ? "P" : "F";
      li.title = `Result ${index + 1}: ${pass ? "pass" : "fail"}`;
      trail.appendChild(li);
    });

    events.replaceChildren();
    if (!raised.length) {
      const li = document.createElement("li");
      li.textContent = sequence
        ? "No incident opened or resolved, so no alert would be sent."
        : "Nothing yet. Send a result.";
      events.appendChild(li);
    }
    raised.forEach(([index, kind]) => {
      const li = document.createElement("li");
      li.textContent =
        kind === "opened"
          ? `Result ${index + 1}: incident opened, alert sent.`
          : `Result ${index + 1}: incident resolved, alert sent.`;
      events.appendChild(li);
    });

    const full = sequence.length >= MAX_RESULTS;
    passButton.disabled = full;
    failButton.disabled = full;
  }

  function send(char) {
    if (sequence.length < MAX_RESULTS) {
      sequence += char;
      render();
    }
  }

  passButton.addEventListener("click", () => send("."));
  failButton.addEventListener("click", () => send("x"));
  document.getElementById("reset").addEventListener("click", () => {
    sequence = "";
    render();
  });
  nInput.addEventListener("input", render);
  mInput.addEventListener("input", render);

  [
    ["One blip", "x."],
    ["Flapping", "x.x.x.x.x."],
    ["Outage, then recovery", "xxx..."],
    ["Recovery interrupted", "xxx.x..."],
  ].forEach(([label, pattern]) => {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "chip";
    button.textContent = label;
    button.addEventListener("click", () => {
      sequence = pattern;
      render();
    });
    patterns.appendChild(button);
  });

  render();
})();
