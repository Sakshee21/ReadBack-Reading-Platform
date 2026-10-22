import { useState } from "react";
import { uploadResearchDocument } from "../api";
import ResearchMetadataForm from "./ResearchMetadataForm";

const BLANK = { title: "", authors: "", year: "", venue: "", doi: "" };

/**
 * Upload a paper or textbook PDF.
 *
 * Metadata typed here wins over whatever the document says about itself, so
 * someone who already knows the citation can put it in up front. Anything left
 * blank is read from the document and can be corrected afterwards.
 */
export default function UploadResearchDialog({ open, onClose, onUploaded }) {
  const [file, setFile] = useState(null);
  const [docKind, setDocKind] = useState("");
  const [meta, setMeta] = useState(BLANK);
  const [consent, setConsent] = useState(false);
  const [progress, setProgress] = useState(0);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  if (!open) return null;

  function reset() {
    setFile(null);
    setDocKind("");
    setMeta(BLANK);
    setConsent(false);
    setProgress(0);
    setBusy(false);
    setError("");
  }

  async function submit(event) {
    event.preventDefault();
    if (!file) {
      setError("Choose a PDF first.");
      return;
    }
    setBusy(true);
    setError("");
    try {
      const document = await uploadResearchDocument({
        file,
        docKind: docKind || undefined,
        title: meta.title || undefined,
        authors: meta.authors || undefined,
        year: meta.year === "" ? undefined : meta.year,
        venue: meta.venue || undefined,
        doi: meta.doi || undefined,
        taggingConsent: consent,
        onProgress: setProgress,
      });
      reset();
      onUploaded?.(document);
      onClose?.();
    } catch (err) {
      setError(err.message || "Upload failed.");
      setBusy(false);
    }
  }

  return (
    <div className="modal-backdrop" role="dialog" aria-modal="true" aria-label="Add a research document">
      <form className="modal-card research-upload" onSubmit={submit}>
        <h2>Add a research document</h2>
        <p className="modal-note">
          PDF only, with a real text layer. Scanned pages are refused — there is no OCR.
          Two-column papers are read column by column.
        </p>

        <label className="research-field">
          <span className="research-field-label">PDF file</span>
          <input
            type="file"
            accept="application/pdf,.pdf"
            disabled={busy}
            onChange={(e) => setFile(e.target.files?.[0] ?? null)}
          />
        </label>

        <fieldset className="research-kind" disabled={busy}>
          <legend>What is it?</legend>
          {[
            ["", "Work it out from the document"],
            ["paper", "A paper"],
            ["textbook", "A textbook or book"],
          ].map(([value, label]) => (
            <label key={value || "auto"}>
              <input
                type="radio"
                name="doc_kind"
                value={value}
                checked={docKind === value}
                onChange={() => setDocKind(value)}
              />
              {label}
            </label>
          ))}
        </fieldset>

        <details className="research-metadata-details">
          <summary>Citation details (optional)</summary>
          <p className="modal-note">
            Leave these blank to use what the document says. Whatever you type here wins.
          </p>
          <ResearchMetadataForm
            values={meta}
            onChange={setMeta}
            disabled={busy}
            showMissing={false}
          />
        </details>

        <label className="research-consent">
          <input
            type="checkbox"
            checked={consent}
            disabled={busy}
            onChange={(e) => setConsent(e.target.checked)}
          />
          <span>
            Allow this document to be sent to an AI service to tag sections and summarise
            them. Off by default; you can change it later, and switching it off deletes
            whatever was produced.
          </span>
        </label>

        {busy && (
          <div className="progress-bar" aria-label="Upload progress">
            <div className="fill" style={{ width: `${Math.round(progress * 100)}%` }} />
          </div>
        )}
        {error && <p className="form-error">{error}</p>}

        <div className="modal-actions">
          <button type="button" className="btn-secondary" onClick={onClose} disabled={busy}>
            Cancel
          </button>
          <button type="submit" className="btn-primary" disabled={busy}>
            {busy ? "Uploading…" : "Upload"}
          </button>
        </div>
      </form>
    </div>
  );
}
