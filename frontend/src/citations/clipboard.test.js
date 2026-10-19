// @vitest-environment jsdom
import { describe, it, expect, beforeEach, afterEach, vi } from "vitest";
import { copyRich } from "./clipboard";

const original = { clipboard: navigator.clipboard, item: globalThis.ClipboardItem };
afterEach(() => {
  Object.defineProperty(navigator, "clipboard", { value: original.clipboard, configurable: true });
  globalThis.ClipboardItem = original.item;
});

function setClipboard(value) {
  Object.defineProperty(navigator, "clipboard", { value, configurable: true });
}

describe("copyRich", () => {
  beforeEach(() => {
    globalThis.ClipboardItem = class {
      constructor(items) {
        this.items = items;
      }
    };
  });

  it("writes_html_and_plain_text_together_when_it_can", async () => {
    const write = vi.fn().mockResolvedValue();
    setClipboard({ write, writeText: vi.fn() });
    expect(await copyRich({ html: "<i>x</i>", text: "x" })).toBe("rich");
    const item = write.mock.calls[0][0][0];
    expect(Object.keys(item.items).sort()).toEqual(["text/html", "text/plain"]);
  });

  it("falls_back_to_plain_text_when_rich_copy_is_refused", async () => {
    const writeText = vi.fn().mockResolvedValue();
    setClipboard({ write: vi.fn().mockRejectedValue(new Error("denied")), writeText });
    expect(await copyRich({ html: "<i>x</i>", text: "x" })).toBe("plain");
    expect(writeText).toHaveBeenCalledWith("x");
  });

  it("falls_back_to_plain_text_when_there_is_no_rich_clipboard", async () => {
    globalThis.ClipboardItem = undefined;
    const writeText = vi.fn().mockResolvedValue();
    setClipboard({ writeText });
    expect(await copyRich({ html: "<i>x</i>", text: "x" })).toBe("plain");
  });

  it("rejects_when_nothing_can_be_copied", async () => {
    setClipboard(undefined);
    await expect(copyRich({ html: "", text: "x" })).rejects.toThrow();
    setClipboard({ writeText: vi.fn().mockRejectedValue(new Error("denied")) });
    globalThis.ClipboardItem = undefined;
    await expect(copyRich({ html: "", text: "x" })).rejects.toThrow();
  });
});
