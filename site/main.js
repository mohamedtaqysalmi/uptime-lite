const copyBtn = document.getElementById("copy-btn");
const quickCode = document.getElementById("quick-code");

if (copyBtn && quickCode) {
  copyBtn.addEventListener("click", async () => {
    const text = quickCode.textContent || "";
    try {
      await navigator.clipboard.writeText(text);
      copyBtn.textContent = "Copied";
      window.setTimeout(() => {
        copyBtn.textContent = "Copy commands";
      }, 1600);
    } catch {
      copyBtn.textContent = "Copy failed";
    }
  });
}
