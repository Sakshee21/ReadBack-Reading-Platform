/**
 * Copy a passage and its citation. Prefers rich text (so italic titles survive
 * a paste into Word) together with plain text; falls back to plain text alone.
 * Resolves "rich" or "plain"; rejects when nothing could be copied, so the
 * caller never claims a copy that did not happen.
 */
export async function copyRich({ html, text }) {
  const clipboard = typeof navigator !== "undefined" ? navigator.clipboard : undefined;
  if (clipboard?.write && typeof ClipboardItem !== "undefined") {
    try {
      await clipboard.write([
        new ClipboardItem({
          "text/html": new Blob([html], { type: "text/html" }),
          "text/plain": new Blob([text], { type: "text/plain" }),
        }),
      ]);
      return "rich";
    } catch {
      // refused or unsupported: try plain text below
    }
  }
  if (clipboard?.writeText) {
    await clipboard.writeText(text);
    return "plain";
  }
  throw new Error("The clipboard is not available.");
}
