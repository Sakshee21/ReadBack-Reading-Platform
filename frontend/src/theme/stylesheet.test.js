import { describe, it, expect } from "vitest";
import fs from "node:fs";
import path from "node:path";

const css = fs.readFileSync(path.join(process.cwd(), "src/styles/global.css"), "utf8");

describe("global.css theme hooks", () => {
  it("on_accent_variable_exists_with_white_default", () => {
    const root = css.slice(css.indexOf(":root"), css.indexOf("}", css.indexOf(":root")));
    expect(root).toMatch(/--on-accent:\s*#ffffff\s*;/);
  });

  it("no_hard_coded_white_text_on_accent", () => {
    const rules = [...css.matchAll(/([^{}]+)\{([^{}]*)\}/g)];
    const offenders = rules
      .filter(([, , body]) => /background(-color)?:\s*var\(--accent\)/.test(body))
      .filter(([, , body]) => /(^|[;\s])color:\s*(#fff\b|#ffffff\b|white\b)/i.test(body))
      .map(([, sel]) => sel.trim());
    expect(offenders).toEqual([]);
  });

  it("accent_tints_follow_the_accent", () => {
    expect(css).not.toMatch(/rgba\(168,\s*86,\s*47/);
  });
});
