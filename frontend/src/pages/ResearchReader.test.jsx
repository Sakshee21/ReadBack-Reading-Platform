// @vitest-environment jsdom
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import ResearchReader from "./ResearchReader";
import { SettingsProvider } from "../SettingsContext";

const logged = [];
const api = {
  getResearchDocument: vi.fn(),
  readResearchSection: vi.fn(),
  getResearchTagStatus: vi.fn(),
  setResearchConsent: vi.fn(),
  queueResearchTags: vi.fn(),
  requestKeyPoints: vi.fn(),
  updateResearchMetadata: vi.fn(),
  listHighlights: vi.fn(),
};

vi.mock("../api", () => ({
  API_URL: "http://test",
  api: new Proxy(
    {},
    {
      get: (_t, name) => (...args) => api[name](...args),
    }
  ),
  logEvent: (type, fields) => logged.push({ type, ...fields }),
  researchExportUrl: () => "http://test/research/export/sections.csv",
}));

const SECTIONS = [
  { id: 10, index: 0, title: "", kind: "front_matter", word_count: 27, chunk_count: 0, readable: false },
  { id: 11, index: 1, title: "Abstract", kind: "abstract", word_count: 72, chunk_count: 1, readable: true },
  { id: 12, index: 2, title: "I. INTRODUCTION", kind: "body", word_count: 516, chunk_count: 2, readable: true },
  { id: 13, index: 3, title: "REFERENCES", kind: "references", word_count: 85, chunk_count: 0, readable: false },
];

const DOCUMENT = {
  id: 7,
  title: "Attention Scaffolding for Sustained Long-Form Reading",
  authors: "A. Reader, B. Writer, and C. Editor",
  doc_kind: "paper",
  year: 2021,
  venue: "IEEE Transactions on Learning Technologies",
  doi: "10.1109/TLT.2021.1234567",
  page_count: 4,
  word_count: 1900,
  section_count: 4,
  status: "ready",
  tagging_consent: false,
  tagging_enabled: false,
  sections: SECTIONS,
  captions: ["Fig. 1. Mean active session length by study week."],
  warnings: ["3 of 4 pages are multi-column; columns were read down, not across."],
};

const READ = (over = {}) => ({
  document_id: 7,
  section: SECTIONS[2],
  chunks: [
    { id: 101, index: 0, text: "The activation energy required to begin a reading session is high.", word_count: 11 },
    { id: 102, index: 1, text: "Our contribution is threefold.", word_count: 4 },
  ],
  previous_section_id: 11,
  next_section_id: null,
  tags: [{ micro_session_id: 101, tags: [{ tag: "problem_motivation", label: "Problem & motivation", score: 5 }] }],
  key_points: null,
  ...over,
});

function mount() {
  return render(
    <SettingsProvider>
      <MemoryRouter initialEntries={["/research/7?section=12"]}>
        <Routes>
          <Route path="/research/:documentId" element={<ResearchReader />} />
        </Routes>
      </MemoryRouter>
    </SettingsProvider>
  );
}

beforeEach(() => {
  logged.length = 0;
  api.getResearchDocument.mockResolvedValue(DOCUMENT);
  api.readResearchSection.mockResolvedValue(READ());
  api.getResearchTagStatus.mockResolvedValue({
    enabled: false,
    queued: 0,
    running: 0,
    done: 0,
    failed: 0,
    untagged: 3,
    total: 3,
    message: "Tagging is off: you have not given consent for this document.",
  });
  api.listHighlights.mockResolvedValue([]);
});

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

describe("the research reader", () => {
  it("shows the section it was asked for, with its text", async () => {
    mount();
    expect(await screen.findByRole("heading", { level: 1, name: "I. INTRODUCTION" })).toBeTruthy();
    expect(screen.getByText(/The activation energy required/)).toBeTruthy();
    expect(screen.getByText(/Our contribution is threefold/)).toBeTruthy();
  });

  it("lists every section, marking the ones outside the reading flow", async () => {
    mount();
    await screen.findByRole("heading", { level: 1, name: "I. INTRODUCTION" });
    const nav = screen.getByRole("navigation", { name: "Sections" });
    expect(nav.textContent).toContain("Abstract");
    expect(nav.textContent).toContain("REFERENCES");

    const references = Array.from(nav.querySelectorAll("button")).find((b) =>
      b.textContent.includes("REFERENCES")
    );
    expect(references.className).toContain("is-aside");
  });

  it("has none of the reading-habit mechanics", async () => {
    mount();
    await screen.findByRole("heading", { level: 1, name: "I. INTRODUCTION" });
    const page = document.body.textContent;
    for (const word of ["Next up in", "streak", "Streak", "Picture this scene", "cliffhanger"]) {
      expect(page).not.toContain(word);
    }
    // And no reading-session calls exist on the research client at all.
    expect(api.startSession).toBeUndefined();
  });

  it("logs no reading events", async () => {
    mount();
    await screen.findByRole("heading", { level: 1, name: "I. INTRODUCTION" });
    expect(logged.filter((e) => e.type.startsWith("session_"))).toEqual([]);
  });

  it("moves to the previous section and leaves the next one disabled at the end", async () => {
    mount();
    await screen.findByRole("heading", { level: 1, name: "I. INTRODUCTION" });
    expect(screen.getByRole("button", { name: "Next section" }).disabled).toBe(true);

    api.readResearchSection.mockResolvedValue(
      READ({ section: SECTIONS[1], previous_section_id: null, next_section_id: 12, tags: [] })
    );
    fireEvent.click(screen.getByRole("button", { name: "Previous section" }));
    expect(await screen.findByRole("heading", { level: 1, name: "Abstract" })).toBeTruthy();
    expect(api.readResearchSection).toHaveBeenCalledWith(7, 11);
  });

  it("shows the tags a chunk carries", async () => {
    mount();
    await screen.findByRole("heading", { level: 1, name: "I. INTRODUCTION" });
    const tags = screen.getByRole("list", { name: "Section tags" });
    expect(tags.textContent).toContain("Problem & motivation");
  });

  it("renders a section with no chunks as plain text", async () => {
    api.readResearchSection.mockResolvedValue(
      READ({
        section: SECTIONS[3],
        chunks: [{ id: 0, index: 0, text: "[1] A. Paivio, Mental Representations.", word_count: 5 }],
        tags: [],
      })
    );
    mount();
    await screen.findByRole("heading", { level: 1, name: "REFERENCES" });
    expect(screen.getByText(/A. Paivio, Mental Representations/)).toBeTruthy();
  });
});

describe("citation details", () => {
  it("shows what the document stated", async () => {
    mount();
    await screen.findByRole("heading", { level: 1, name: "I. INTRODUCTION" });
    expect(screen.getByText("10.1109/TLT.2021.1234567")).toBeTruthy();
    expect(screen.getByText("IEEE Transactions on Learning Technologies")).toBeTruthy();
  });

  it("says a field was not found rather than inventing one", async () => {
    api.getResearchDocument.mockResolvedValue({ ...DOCUMENT, year: null, doi: null });
    mount();
    await screen.findByRole("heading", { level: 1, name: "I. INTRODUCTION" });
    expect(screen.getAllByText("not found").length).toBeGreaterThanOrEqual(2);
  });

  it("saves corrected details", async () => {
    api.updateResearchMetadata.mockResolvedValue({ ...DOCUMENT, year: 2020 });
    mount();
    await screen.findByRole("heading", { level: 1, name: "I. INTRODUCTION" });

    fireEvent.click(screen.getByRole("button", { name: "Edit details" }));
    fireEvent.change(screen.getByLabelText(/^Year/), { target: { value: "2020" } });
    fireEvent.click(screen.getByRole("button", { name: "Save" }));

    await waitFor(() =>
      expect(api.updateResearchMetadata).toHaveBeenCalledWith(
        7,
        expect.objectContaining({ year: 2020 })
      )
    );
  });

  it("sends null, not an empty string, for a year that is cleared", async () => {
    api.updateResearchMetadata.mockResolvedValue(DOCUMENT);
    mount();
    await screen.findByRole("heading", { level: 1, name: "I. INTRODUCTION" });
    fireEvent.click(screen.getByRole("button", { name: "Edit details" }));
    fireEvent.change(screen.getByLabelText(/^Year/), { target: { value: "" } });
    fireEvent.click(screen.getByRole("button", { name: "Save" }));

    await waitFor(() =>
      expect(api.updateResearchMetadata).toHaveBeenCalledWith(
        7,
        expect.objectContaining({ year: null })
      )
    );
  });
});

describe("tagging controls", () => {
  it("reports the queue status in words", async () => {
    mount();
    expect(
      await screen.findByText(/you have not given consent for this document/)
    ).toBeTruthy();
  });

  it("asks for consent before offering to tag", async () => {
    mount();
    await screen.findByRole("heading", { level: 1, name: "I. INTRODUCTION" });
    expect(screen.queryByRole("button", { name: /Start tagging/ })).toBeNull();
  });

  it("offers to start tagging once consent is given", async () => {
    api.setResearchConsent.mockResolvedValue({
      enabled: true,
      queued: 0,
      running: 0,
      done: 0,
      failed: 0,
      untagged: 3,
      total: 3,
      message: "0 of 3 sections tagged.",
    });
    // Starts unconsented, so the click is the act of giving consent.
    mount();
    await screen.findByRole("heading", { level: 1, name: "I. INTRODUCTION" });

    fireEvent.click(
      screen.getByLabelText(/Allow this document to be sent to an AI service/)
    );
    expect(await screen.findByRole("button", { name: /Start tagging/ })).toBeTruthy();
    expect(api.setResearchConsent).toHaveBeenCalledWith(7, true);
  });

  it("says plainly that withdrawing consent deleted the tags", async () => {
    api.getResearchDocument.mockResolvedValue({ ...DOCUMENT, tagging_consent: true });
    api.setResearchConsent.mockResolvedValue({
      enabled: false,
      total: 3,
      message: "Tagging is off: you have not given consent for this document.",
    });
    mount();
    await screen.findByRole("heading", { level: 1, name: "I. INTRODUCTION" });

    fireEvent.click(
      screen.getByLabelText(/Allow this document to be sent to an AI service/)
    );
    expect(await screen.findByText(/tags for this document have been deleted/)).toBeTruthy();
  });
});

describe("key points", () => {
  it("are not shown at all when the feature is off", async () => {
    mount();
    await screen.findByRole("heading", { level: 1, name: "I. INTRODUCTION" });
    expect(screen.queryByText(/Key points/)).toBeNull();
  });

  it("are labelled as machine-generated", async () => {
    api.readResearchSection.mockResolvedValue(
      READ({
        key_points: { status: "done", text: "Sessions lengthened.\nComprehension held.", model: "m" },
      })
    );
    mount();
    await screen.findByRole("heading", { level: 1, name: "I. INTRODUCTION" });
    expect(screen.getByText("machine-generated")).toBeTruthy();
    expect(screen.getByText("Sessions lengthened.")).toBeTruthy();
  });

  it("show nothing but an explanation when the call failed", async () => {
    api.readResearchSection.mockResolvedValue(
      READ({ key_points: { status: "failed", text: "", model: "" } })
    );
    mount();
    await screen.findByRole("heading", { level: 1, name: "I. INTRODUCTION" });
    expect(screen.getByText(/Read the section itself rather than a summary/)).toBeTruthy();
  });
});

describe("honesty about the extraction", () => {
  it("lists what could not be handled", async () => {
    mount();
    await screen.findByRole("heading", { level: 1, name: "I. INTRODUCTION" });
    expect(screen.getByText(/pages are multi-column/)).toBeTruthy();
  });

  it("shows the captions it held back", async () => {
    mount();
    await screen.findByRole("heading", { level: 1, name: "I. INTRODUCTION" });
    expect(screen.getByText(/Fig. 1. Mean active session length/)).toBeTruthy();
  });
});

describe("citing a document with gaps in its metadata", () => {
  const incomplete = { ...DOCUMENT, authors: "", year: null, needs_review: ["authors", "year"] };

  it("asks for the missing fields by name", async () => {
    api.getResearchDocument.mockResolvedValue(incomplete);
    mount();
    await screen.findByRole("heading", { level: 1, name: "I. INTRODUCTION" });
    const warning = screen.getByText(/before citing/);
    expect(warning.textContent).toContain("authors");
    expect(warning.textContent).toContain("year");
  });

  it("says nothing when the document has everything", async () => {
    mount();
    await screen.findByRole("heading", { level: 1, name: "I. INTRODUCTION" });
    expect(screen.queryByText(/before citing/)).toBeNull();
  });

  it("marks a guessed field as needing review", async () => {
    api.getResearchDocument.mockResolvedValue({ ...DOCUMENT, unverified: ["year"] });
    mount();
    await screen.findByRole("heading", { level: 1, name: "I. INTRODUCTION" });
    expect(screen.getByText(/before citing/).textContent).toContain("year");
  });

  it("offers the undated switch when editing, and sends it", async () => {
    api.getResearchDocument.mockResolvedValue(incomplete);
    api.updateResearchMetadata.mockResolvedValue(incomplete);
    mount();
    await screen.findByRole("heading", { level: 1, name: "I. INTRODUCTION" });

    fireEvent.click(screen.getByRole("button", { name: "Edit details" }));
    fireEvent.click(screen.getByLabelText(/This document has no date/));
    fireEvent.click(screen.getByRole("button", { name: "Save" }));

    await waitFor(() =>
      expect(api.updateResearchMetadata).toHaveBeenCalledWith(
        7,
        expect.objectContaining({ no_date: true })
      )
    );
  });
});
