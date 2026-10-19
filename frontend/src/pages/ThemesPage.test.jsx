// @vitest-environment jsdom
import { describe, it, expect, beforeEach, afterEach, vi } from "vitest";
import { render, screen, fireEvent, cleanup, waitFor, within } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import ThemesPage from "./ThemesPage";

const logged = [];
const api = { getThemes: vi.fn(), getThemePassages: vi.fn(), listBooks: vi.fn(), setThemeConsent: vi.fn() };
vi.mock("../api", () => ({
  api: {
    getThemes: (...a) => api.getThemes(...a),
    getThemePassages: (...a) => api.getThemePassages(...a),
    listBooks: (...a) => api.listBooks(...a),
    setThemeConsent: (...a) => api.setThemeConsent(...a),
  },
  logEvent: (type, fields) => logged.push({ type, ...fields }),
}));

const THEMES = {
  themes: [
    { theme: "romance", label: "Romance & courtship", count: 2 },
    { theme: "mystery_detection", label: "Mystery & detection", count: 1 },
  ],
  tagging: { tagged: 3, pending: 0, failed: 0 },
};
const PASSAGES = [
  { micro_session_id: 11, chapter_index: 1, chapter_title: "The Ball", session_number: 3, preview: "Lovers met at the ball.", score: 5,
    themes: [{ theme: "romance", label: "Romance & courtship", score: 5 }] },
  { micro_session_id: 12, chapter_index: 1, chapter_title: "The Ball", session_number: 4, preview: "A murder at the manor.", score: 3,
    themes: [{ theme: "mystery_detection", label: "Mystery & detection", score: 5 }, { theme: "romance", label: "Romance & courtship", score: 3 }] },
];
const BOOK = { id: 2, title: "Alice", is_user_uploaded: false, theme_tagging_consent: false };

function setup({ themes = THEMES, book = BOOK } = {}) {
  api.getThemes.mockResolvedValue(themes);
  api.getThemePassages.mockResolvedValue(PASSAGES);
  api.listBooks.mockResolvedValue([book]);
  return render(
    <MemoryRouter initialEntries={["/books/2/themes"]}>
      <Routes>
        <Route path="/books/:bookId/themes" element={<ThemesPage />} />
      </Routes>
    </MemoryRouter>
  );
}

beforeEach(() => {
  logged.length = 0;
  Object.values(api).forEach((f) => f.mockReset());
});
afterEach(cleanup);

describe("ThemesPage", () => {
  it("lists_themes_with_counts_and_logs_opened_once", async () => {
    setup();
    expect(await screen.findByRole("radio", { name: /Romance & courtship \(2\)/ })).toBeTruthy();
    expect(screen.getByRole("radio", { name: /Mystery & detection \(1\)/ })).toBeTruthy();
    expect(screen.getByText(/only passages you have reached/i)).toBeTruthy();
    expect(logged.filter((e) => e.type === "themes_opened")).toEqual([{ type: "themes_opened", bookId: 2, count: 2 }]);
  });

  it("choosing_a_theme_shows_its_passages_with_theme_names_as_text_and_go_links", async () => {
    setup();
    fireEvent.click(await screen.findByRole("radio", { name: /Romance & courtship/ }));
    await screen.findByText("Lovers met at the ball.");
    expect(api.getThemePassages).toHaveBeenCalledWith("2", "romance");
    const second = screen.getByText("A murder at the manor.").closest("article");
    expect(within(second).getByText("Mystery & detection")).toBeTruthy();
    expect(within(second).getByRole("link", { name: "Go to passage" }).getAttribute("href")).toBe("/read/2?ms=12");
    expect(screen.getByText("Session 3")).toBeTruthy();
    expect(logged.find((e) => e.type === "theme_filter_selected")).toMatchObject({ theme: "romance", bookId: 2 });
    fireEvent.click(within(second).getByRole("link", { name: "Go to passage" }));
    expect(logged.find((e) => e.type === "theme_passage_opened")).toMatchObject({ theme: "romance", bookId: 2 });
    expect(JSON.stringify(logged)).not.toContain("Lovers met");
  });

  it("empty_state_when_no_tags_yet", async () => {
    setup({ themes: { themes: [], tagging: { tagged: 0, pending: 0, failed: 0 } } });
    expect(await screen.findByText(/no theme tags for the passages you have read yet/i)).toBeTruthy();
    expect(screen.queryByRole("radio")).toBeNull();
  });

  it("shows_still_being_prepared_when_tagging_is_pending", async () => {
    setup({ themes: { themes: [], tagging: { tagged: 0, pending: 2, failed: 0 } } });
    expect(await screen.findByText(/still being prepared/i)).toBeTruthy();
  });

  it("owner_of_a_consented_upload_can_withdraw_after_confirming", async () => {
    api.setThemeConsent.mockResolvedValue({ theme_tagging_consent: false });
    setup({ book: { id: 2, title: "Mine", is_user_uploaded: true, theme_tagging_consent: true } });
    fireEvent.click(await screen.findByRole("button", { name: "Withdraw theme tagging" }));
    expect(api.setThemeConsent).not.toHaveBeenCalled();
    expect(screen.getByText(/deletes this book's theme tags/i)).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Yes, withdraw" }));
    await waitFor(() => expect(api.setThemeConsent).toHaveBeenCalledWith("2", false));
    await screen.findByRole("button", { name: "Allow theme tagging" });
    expect(logged.find((e) => e.type === "theme_consent_changed")).toMatchObject({ granted: false, bookId: 2 });
  });

  it("owner_without_consent_can_allow_it", async () => {
    api.setThemeConsent.mockResolvedValue({ theme_tagging_consent: true });
    setup({ book: { id: 2, title: "Mine", is_user_uploaded: true, theme_tagging_consent: false } });
    fireEvent.click(await screen.findByRole("button", { name: "Allow theme tagging" }));
    await waitFor(() => expect(api.setThemeConsent).toHaveBeenCalledWith("2", true));
    expect(logged.find((e) => e.type === "theme_consent_changed")).toMatchObject({ granted: true });
  });

  it("a_shared_book_has_no_tagging_controls_its_tags_are_already_there", async () => {
    setup();
    await screen.findByRole("radio", { name: /Romance/ });
    expect(screen.queryByRole("button", { name: /theme tag/i })).toBeNull();
    expect(screen.queryByRole("button", { name: /Enable|Turn off|Allow|Withdraw/ })).toBeNull();
  });

  it("load_failure_shows_a_message", async () => {
    api.getThemes.mockRejectedValue(new Error("down"));
    api.listBooks.mockResolvedValue([BOOK]);
    render(
      <MemoryRouter initialEntries={["/books/2/themes"]}>
        <Routes>
          <Route path="/books/:bookId/themes" element={<ThemesPage />} />
        </Routes>
      </MemoryRouter>
    );
    expect((await screen.findByRole("alert")).textContent).toMatch(/could not load/i);
  });

  it("links_back_to_reading_and_notes", async () => {
    setup();
    await screen.findByRole("radio", { name: /Romance/ });
    expect(screen.getByRole("link", { name: "Back to reading" }).getAttribute("href")).toBe("/read/2");
    expect(screen.getByRole("link", { name: "Notes" }).getAttribute("href")).toBe("/books/2/notes");
  });

  it("announces_the_results_politely_and_labels_each_passage_s_theme_list", async () => {
    const { container } = setup();
    fireEvent.click(await screen.findByRole("radio", { name: /Romance & courtship/ }));
    await screen.findByText("Lovers met at the ball.");
    const live = container.querySelector('[aria-live="polite"]');
    expect(live).toBeTruthy();
    expect(live.textContent).toContain("Lovers met at the ball.");
    expect(screen.getAllByRole("list", { name: "Themes in this passage" })).toHaveLength(2);
    expect(screen.getByRole("heading", { name: /Passages for Romance & courtship/ })).toBeTruthy();
  });

  it("a_slow_answer_for_an_earlier_theme_never_overwrites_the_current_one", async () => {
    let answerRomance;
    api.getThemePassages.mockImplementation((_book, theme) =>
      theme === "romance"
        ? new Promise((resolve) => {
            answerRomance = resolve;
          })
        : Promise.resolve([PASSAGES[1]])
    );
    api.getThemes.mockResolvedValue(THEMES);
    api.listBooks.mockResolvedValue([BOOK]);
    render(
      <MemoryRouter initialEntries={["/books/2/themes"]}>
        <Routes>
          <Route path="/books/:bookId/themes" element={<ThemesPage />} />
        </Routes>
      </MemoryRouter>
    );
    fireEvent.click(await screen.findByRole("radio", { name: /Romance/ }));
    fireEvent.click(screen.getByRole("radio", { name: /Mystery/ }));
    await screen.findByText("A murder at the manor.");
    answerRomance([PASSAGES[0]]);
    await new Promise((r) => setTimeout(r, 0));
    expect(screen.queryByText("Lovers met at the ball.")).toBeNull();
    expect(screen.getByText("A murder at the manor.")).toBeTruthy();
  });

  it("passages_in_flight_when_consent_is_withdrawn_do_not_reappear", async () => {
    let answer;
    api.getThemePassages.mockReturnValue(
      new Promise((resolve) => {
        answer = resolve;
      })
    );
    api.setThemeConsent.mockResolvedValue({ theme_tagging_consent: false });
    api.getThemes.mockResolvedValue(THEMES);
    api.listBooks.mockResolvedValue([{ id: 2, title: "Mine", is_user_uploaded: true, theme_tagging_consent: true }]);
    render(
      <MemoryRouter initialEntries={["/books/2/themes"]}>
        <Routes>
          <Route path="/books/:bookId/themes" element={<ThemesPage />} />
        </Routes>
      </MemoryRouter>
    );
    fireEvent.click(await screen.findByRole("radio", { name: /Romance/ }));
    fireEvent.click(screen.getByRole("button", { name: "Withdraw theme tagging" }));
    fireEvent.click(screen.getByRole("button", { name: "Yes, withdraw" }));
    await screen.findByRole("button", { name: "Allow theme tagging" });
    answer(PASSAGES);
    await new Promise((r) => setTimeout(r, 0));
    expect(screen.queryByText("Lovers met at the ball.")).toBeNull();
  });
});
