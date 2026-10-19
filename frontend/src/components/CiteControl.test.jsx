// @vitest-environment jsdom
import { describe, it, expect, beforeEach, afterEach, vi } from "vitest";
import { render, screen, fireEvent, cleanup, waitFor } from "@testing-library/react";
import { SettingsProvider } from "../SettingsContext";
import CiteControl from "./CiteControl";

const logged = [];
const copy = { fn: vi.fn() };
vi.mock("../api", () => ({ logEvent: (type, fields) => logged.push({ type, ...fields }) }));
vi.mock("../citations/clipboard", () => ({ copyRich: (...a) => copy.fn(...a) }));

const book = {
  title: "Frankenstein; or, the modern prometheus",
  author: "Shelley, Mary Wollstonecraft",
  published_year: 1818,
  gutenberg_id: 84,
  is_user_uploaded: false,
};
const highlight = {
  id: 7,
  micro_session_id: 300,
  chapter_index: 5,
  chapter_title: "Chapter 5",
  quote: "It was on a dreary night\nof November",
};

function setup() {
  return render(
    <SettingsProvider>
      <CiteControl book={book} highlight={highlight} bookId={4} />
    </SettingsProvider>
  );
}

beforeEach(() => {
  logged.length = 0;
  localStorage.clear();
  copy.fn = vi.fn().mockResolvedValue("rich");
});
afterEach(cleanup);

describe("CiteControl", () => {
  it("copies_the_quote_with_an_apa_in_text_citation_and_html_italics", async () => {
    setup();
    fireEvent.click(screen.getByRole("button", { name: "Copy quote with citation" }));
    await waitFor(() => expect(copy.fn).toHaveBeenCalled());
    const { text, html } = copy.fn.mock.calls[0][0];
    expect(text).toBe("“It was on a dreary night of November” (Shelley, 1818, Chapter 5)");
    expect(html).toContain("(Shelley, 1818, Chapter 5)");
    expect((await screen.findByRole("status")).textContent).toMatch(/copied/i);
  });

  it("copies_the_in_text_citation_alone_and_the_reference_entry", async () => {
    setup();
    fireEvent.click(screen.getByRole("button", { name: "Copy citation" }));
    await waitFor(() => expect(copy.fn).toHaveBeenCalledTimes(1));
    expect(copy.fn.mock.calls[0][0].text).toBe("(Shelley, 1818, Chapter 5)");
    fireEvent.click(screen.getByRole("button", { name: "Copy reference entry" }));
    await waitFor(() => expect(copy.fn).toHaveBeenCalledTimes(2));
    expect(copy.fn.mock.calls[1][0].text).toBe(
      "Shelley, M. W. (1818). Frankenstein; or, the modern prometheus. Project Gutenberg. https://www.gutenberg.org/ebooks/84"
    );
    expect(copy.fn.mock.calls[1][0].html).toContain("<i>Frankenstein; or, the modern prometheus</i>");
  });

  it("changing_the_style_changes_the_output_and_is_remembered", async () => {
    setup();
    fireEvent.change(screen.getByLabelText("Citation style"), { target: { value: "mla" } });
    fireEvent.click(screen.getByRole("button", { name: "Copy citation" }));
    await waitFor(() => expect(copy.fn).toHaveBeenCalled());
    expect(copy.fn.mock.calls[0][0].text).toBe("(Shelley, ch. 5)");
    expect(JSON.parse(localStorage.getItem("readback_settings")).citationStyle).toBe("mla");
  });

  it("chicago_gives_the_quote_then_the_footnote", async () => {
    setup();
    fireEvent.change(screen.getByLabelText("Citation style"), { target: { value: "chicago" } });
    fireEvent.click(screen.getByRole("button", { name: "Copy quote with citation" }));
    await waitFor(() => expect(copy.fn).toHaveBeenCalled());
    expect(copy.fn.mock.calls[0][0].text).toBe(
      "“It was on a dreary night of November”\n\nMary Wollstonecraft Shelley, Frankenstein; or, the modern prometheus (1818; Project Gutenberg), chap. 5."
    );
  });

  it("can_add_a_link_back_to_the_exact_passage", async () => {
    setup();
    fireEvent.click(screen.getByLabelText("Include link to this passage"));
    fireEvent.click(screen.getByRole("button", { name: "Copy quote with citation" }));
    await waitFor(() => expect(copy.fn).toHaveBeenCalled());
    expect(copy.fn.mock.calls[0][0].text.endsWith(`\n${window.location.origin}/read/4?ms=300&h=7`)).toBe(true);
  });

  it("says_when_only_plain_text_was_copied", async () => {
    copy.fn = vi.fn().mockResolvedValue("plain");
    setup();
    fireEvent.click(screen.getByRole("button", { name: "Copy citation" }));
    expect((await screen.findByRole("status")).textContent).toMatch(/plain text/i);
  });

  it("never_claims_success_when_the_clipboard_refuses", async () => {
    copy.fn = vi.fn().mockRejectedValue(new Error("denied"));
    setup();
    fireEvent.click(screen.getByRole("button", { name: "Copy citation" }));
    const status = await screen.findByRole("status");
    expect(status.textContent).toMatch(/could not copy/i);
    expect(status.textContent).not.toMatch(/^copied/i);
  });

  it("logs_the_copy_without_the_quote", async () => {
    setup();
    fireEvent.click(screen.getByRole("button", { name: "Copy quote with citation" }));
    await waitFor(() => expect(logged.length).toBe(1));
    expect(logged[0]).toMatchObject({ type: "cite_copied", bookId: 4, style: "apa", kind: "quote", link: false });
    expect(JSON.stringify(logged)).not.toContain("dreary");
  });
});
