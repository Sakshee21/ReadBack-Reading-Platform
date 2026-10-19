import { useEffect, useRef, useState } from "react";
import { api, logEvent, uploadBook } from "../api";

const ACCEPTED = ".txt,.epub,.pdf";
const MAX_MB = 10;
const POLL_MS = 1200;
const POLL_TIMEOUT_MS = 180000;

function formatOf(file) {
  return (file?.name || "").split(".").pop()?.toLowerCase() || "unknown";
}

/**
 * Upload a book and watch it convert.
 *
 * Conversion runs in a background task on the server, so after the upload
 * finishes we poll /status until the book is ready or failed.
 */
export default function UploadBookDialog({ open, onClose, onAdded }) {
  const [file, setFile] = useState(null);
  const [title, setTitle] = useState("");
  const [author, setAuthor] = useState("");
  const [themeConsent, setThemeConsent] = useState(false);
  const [phase, setPhase] = useState("idle"); // idle | uploading | processing | failed
  const [progress, setProgress] = useState(0);
  const [error, setError] = useState("");
  const [dragging, setDragging] = useState(false);
  const inputRef = useRef(null);
  const pollTimer = useRef(null);

  useEffect(() => {
    if (!open) return;
    setFile(null);
    setTitle("");
    setAuthor("");
    setThemeConsent(false);
    setPhase("idle");
    setProgress(0);
    setError("");
    return () => clearTimeout(pollTimer.current);
  }, [open]);

  if (!open) return null;

  function pick(selected) {
    setError("");
    if (!selected) return;
    if (selected.size > MAX_MB * 1024 * 1024) {
      setError(`That file is ${(selected.size / 1024 / 1024).toFixed(1)} MB. The limit is ${MAX_MB} MB.`);
      return;
    }
    setFile(selected);
    if (!title) setTitle(selected.name.replace(/\.[^.]+$/, "").replace(/[_-]+/g, " "));
  }

  function waitForConversion(bookId, startedAt) {
    pollTimer.current = setTimeout(async () => {
      try {
        const status = await api.getBookStatus(bookId);
        if (status.status === "ready") {
          logEvent("book_upload_completed", {
            bookId,
            word_count: status.total_word_count,
            chapter_count: status.chapter_count,
            session_count: status.micro_session_count,
            source_format: formatOf(file),
          });
          onAdded?.();
          onClose();
          return;
        }
        if (status.status === "failed") {
          setPhase("failed");
          setError(status.failure_reason || "Conversion failed.");
          logEvent("book_upload_failed", {
            bookId,
            reason_category: "conversion_failed",
            source_format: formatOf(file),
          });
          return;
        }
        if (Date.now() - startedAt > POLL_TIMEOUT_MS) {
          setPhase("failed");
          setError("Conversion is taking unusually long. Check your library in a moment.");
          return;
        }
        waitForConversion(bookId, startedAt);
      } catch (err) {
        setPhase("failed");
        setError(err.message || "Lost track of the conversion.");
      }
    }, POLL_MS);
  }

  async function handleUpload() {
    if (!file) return;
    setPhase("uploading");
    setError("");
    setProgress(0);
    logEvent("book_upload_started", { source_format: formatOf(file) });

    try {
      const created = await uploadBook({
        file,
        title: title.trim(),
        author: author.trim(),
        themeTaggingConsent: themeConsent,
        onProgress: setProgress,
      });
      setPhase("processing");
      waitForConversion(created.id, Date.now());
    } catch (err) {
      setPhase("failed");
      setError(err.message || "Upload failed.");
      logEvent("book_upload_failed", {
        reason_category: err.status === 413 ? "too_large" : "rejected",
        source_format: formatOf(file),
      });
    }
  }

  const busy = phase === "uploading" || phase === "processing";

  return (
    <div className="modal-overlay" onClick={busy ? undefined : onClose}>
      <div className="upload-card" onClick={(e) => e.stopPropagation()}>
        <div className="drawer-header">
          <h2>Add your own book</h2>
          <button className="icon-btn" onClick={onClose} disabled={busy}>
            Close
          </button>
        </div>

        <div className="upload-body">
          <div
            className={`dropzone ${dragging ? "dragging" : ""} ${file ? "has-file" : ""}`}
            onDragOver={(e) => {
              e.preventDefault();
              setDragging(true);
            }}
            onDragLeave={() => setDragging(false)}
            onDrop={(e) => {
              e.preventDefault();
              setDragging(false);
              pick(e.dataTransfer.files?.[0]);
            }}
            onClick={() => !busy && inputRef.current?.click()}
          >
            <input
              ref={inputRef}
              id="upload-file"
              type="file"
              accept={ACCEPTED}
              hidden
              onChange={(e) => pick(e.target.files?.[0])}
            />
            {file ? (
              <>
                <strong>{file.name}</strong>
                <span className="dropzone-hint">{(file.size / 1024 / 1024).toFixed(1)} MB</span>
              </>
            ) : (
              <>
                <strong>Drop a file here, or click to choose</strong>
                <span className="dropzone-hint">
                  .txt, .epub or .pdf &middot; up to {MAX_MB} MB &middot; PDFs need real text,
                  not scans
                </span>
              </>
            )}
          </div>

          <label className="upload-field">
            <span>Title</span>
            <input
              id="upload-title"
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              placeholder="Taken from the filename if left blank"
              disabled={busy}
            />
          </label>
          <label className="upload-field">
            <span>Author</span>
            <input
              id="upload-author"
              value={author}
              onChange={(e) => setAuthor(e.target.value)}
              placeholder="Unknown"
              disabled={busy}
            />
          </label>

          <label className="upload-consent">
            <input
              type="checkbox"
              checked={themeConsent}
              onChange={(e) => setThemeConsent(e.target.checked)}
              disabled={busy}
            />{" "}
            <span>
              Allow theme tagging. Your book's text will be sent to an AI service (OpenRouter's free
              models, which may log prompts and outputs) so passages can be labelled with themes.
              You can withdraw this later.
            </span>
          </label>

          {phase === "uploading" && (
            <div className="upload-status">
              <div className="progress-bar">
                <div className="fill" style={{ width: `${Math.round(progress * 100)}%` }} />
              </div>
              <span>Uploading… {Math.round(progress * 100)}%</span>
            </div>
          )}

          {phase === "processing" && (
            <div className="upload-status">
              <div className="progress-bar indeterminate">
                <div className="fill" style={{ width: "100%" }} />
              </div>
              <span>Converting into chapters and reading sessions…</span>
            </div>
          )}

          {error && <p className="settings-warning">{error}</p>}

          <p className="upload-notice">
            Only upload books you have the right to read. Uploaded books are private to you.
          </p>

          <button className="btn-primary" onClick={handleUpload} disabled={!file || busy}>
            {phase === "uploading" ? "Uploading…" : phase === "processing" ? "Converting…" : "Upload book"}
          </button>
        </div>
      </div>
    </div>
  );
}
