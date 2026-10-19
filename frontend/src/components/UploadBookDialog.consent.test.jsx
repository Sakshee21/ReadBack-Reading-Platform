// @vitest-environment jsdom
import { describe, it, expect, afterEach, beforeEach, vi } from "vitest";
import { render, screen, fireEvent, cleanup, waitFor } from "@testing-library/react";
import UploadBookDialog from "./UploadBookDialog";

const upload = vi.fn();
vi.mock("../api", () => ({
  api: { getBookStatus: () => Promise.resolve({ status: "ready", total_word_count: 1, chapter_count: 1, micro_session_count: 1 }) },
  logEvent: () => {},
  uploadBook: (...a) => upload(...a),
}));

beforeEach(() => upload.mockReset().mockResolvedValue({ id: 9 }));
afterEach(cleanup);

function chooseFile() {
  const input = document.getElementById("upload-file");
  const file = new File(["hello"], "book.txt", { type: "text/plain" });
  fireEvent.change(input, { target: { files: [file] } });
}

describe("UploadBookDialog theme consent", () => {
  it("consent_is_unticked_by_default_and_names_the_risk", () => {
    render(<UploadBookDialog open onClose={() => {}} onAdded={() => {}} />);
    const box = screen.getByRole("checkbox", { name: /allow theme tagging/i });
    expect(box.checked).toBe(false);
    expect(screen.getByText(/sent to an ai service/i)).toBeTruthy();
    expect(screen.getByText(/may log prompts and outputs/i)).toBeTruthy();
  });

  it("not_ticked_sends_no_consent", async () => {
    render(<UploadBookDialog open onClose={() => {}} onAdded={() => {}} />);
    chooseFile();
    fireEvent.click(screen.getByRole("button", { name: "Upload book" }));
    await waitFor(() => expect(upload).toHaveBeenCalled());
    expect(upload.mock.calls[0][0].themeTaggingConsent).toBe(false);
  });

  it("ticked_sends_consent", async () => {
    render(<UploadBookDialog open onClose={() => {}} onAdded={() => {}} />);
    chooseFile();
    fireEvent.click(screen.getByRole("checkbox", { name: /allow theme tagging/i }));
    fireEvent.click(screen.getByRole("button", { name: "Upload book" }));
    await waitFor(() => expect(upload).toHaveBeenCalled());
    expect(upload.mock.calls[0][0].themeTaggingConsent).toBe(true);
  });

  it("consent_resets_each_time_the_dialog_opens", () => {
    const { rerender } = render(<UploadBookDialog open onClose={() => {}} onAdded={() => {}} />);
    fireEvent.click(screen.getByRole("checkbox", { name: /allow theme tagging/i }));
    rerender(<UploadBookDialog open={false} onClose={() => {}} onAdded={() => {}} />);
    rerender(<UploadBookDialog open onClose={() => {}} onAdded={() => {}} />);
    expect(screen.getByRole("checkbox", { name: /allow theme tagging/i }).checked).toBe(false);
  });
});
