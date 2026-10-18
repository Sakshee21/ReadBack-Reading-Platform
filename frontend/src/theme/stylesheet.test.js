import { describe, it, expect } from "vitest";
import fs from "node:fs";
import path from "node:path";

const stylesDir = path.join(process.cwd(), "src/styles");
const read = (name) => fs.readFileSync(path.join(stylesDir, name), "utf8");
const css = read("global.css");
const allCss = fs.readdirSync(stylesDir).filter((f) => f.endsWith(".css"));

const rules = (text) => [...text.matchAll(/([^{}]+)\{([^{}]*)\}/g)].map(([, sel, body]) => ({ sel: sel.trim(), body }));

describe("global.css theme hooks", () => {
  it("on_accent_variable_exists_with_white_default", () => {
    const root = css.slice(css.indexOf(":root"), css.indexOf("}", css.indexOf(":root")));
    expect(root).toMatch(/--on-accent:\s*#ffffff\s*;/);
  });

  it("accent_tints_follow_the_accent", () => {
    expect(css).not.toMatch(/rgba\(168,\s*86,\s*47/);
  });
});

describe("every stylesheet", () => {
  it("no_stylesheet_puts_hard_coded_white_text_on_an_accent_background", () => {
    const offenders = [];
    for (const file of allCss) {
      for (const { sel, body } of rules(read(file))) {
        if (
          /background(-color)?:\s*var\(--accent\)/.test(body) &&
          /(^|[;\s])color:\s*(#fff\b|#ffffff\b|white\b)/i.test(body)
        )
          offenders.push(`${file}: ${sel}`);
      }
    }
    expect(offenders).toEqual([]);
  });

  it("book_tints_only_use_data_theme_selectors_and_never_important", () => {
    const themes = read("themes.css");
    expect(themes).not.toMatch(/!important/);
    const selectors = rules(themes)
      .map((r) => r.sel)
      .filter((s) => !s.startsWith("@"));
    expect(selectors.length).toBeGreaterThan(0);
    // Inline variables on the root beat these, so a chosen theme always wins.
    for (const sel of selectors) expect(sel).toMatch(/\[data-theme=/);
  });

  it("focus_rings_in_the_appearance_controls_use_the_text_colour", () => {
    expect(read("appearance.css")).not.toMatch(/outline:[^;]*var\(--accent\)/);
  });

  it("only_passage_paragraphs_get_the_fade_in_animation", () => {
    expect(read("motion.css")).toMatch(/\.fade-in-text \.hl-text > p\s*\{/);
  });
});
