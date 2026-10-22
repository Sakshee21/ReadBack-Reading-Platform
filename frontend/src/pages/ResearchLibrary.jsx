import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api, researchExportUrl } from "../api";
import Icon from "../components/Icon";
import SettingsPanel from "../components/SettingsPanel";
import UploadResearchDialog from "../components/UploadResearchDialog";

const KIND_LABEL = { paper: "Paper", textbook: "Textbook" };

/**
 * The research library: this reader's own papers and textbooks.
 *
 * Deliberately plain. None of the reading-habit mechanics belong here - no
 * streak, no nudge, no progress ring - because none of them should apply to
 * reading for study.
 */
export default function ResearchLibrary() {
  const [documents, setDocuments] = useState([]);
  const [loading, setLoading] = useState(true);
  const [uploadOpen, setUploadOpen] = useState(false);
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [confirmDelete, setConfirmDelete] = useState(null);
  const [error, setError] = useState("");

  const load = useCallback(async () => {
    try {
      setDocuments(await api.listResearch());
      setError("");
    } catch (err) {
      setError(err.message || "Could not load your research documents.");
    }
  }, []);

  useEffect(() => {
    let cancelled = false;
    load().then(() => !cancelled && setLoading(false));
    return () => {
      cancelled = true;
    };
  }, [load]);

  // A document converts in the background, so poll while any is still working.
  useEffect(() => {
    if (!documents.some((d) => d.status === "processing")) return undefined;
    const timer = setInterval(load, 1500);
    return () => clearInterval(timer);
  }, [documents, load]);

  async function remove(id) {
    try {
      await api.deleteResearchDocument(id);
      setConfirmDelete(null);
      await load();
    } catch (err) {
      setError(err.message || "Could not delete that document.");
    }
  }

  if (loading) return <div className="page-loading">Loading your research documents...</div>;

  return (
    <div className="research-page">
      <div className="library-header">
        <div>
          <h1>Research</h1>
          <p className="research-subtitle">
            Papers and textbooks, read by section. Private to you, and kept out of the
            reading pilot.
          </p>
        </div>
        <div className="research-header-actions">
          <Link to="/library" className="btn-secondary">
            <Icon name="library" />
            Reading library
          </Link>
          <button className="btn-secondary" onClick={() => setUploadOpen(true)}>
            <Icon name="upload" />
            Add a document
          </button>
          <button className="btn-secondary" onClick={() => setSettingsOpen(true)}>
            <Icon name="settings" />
            Settings
          </button>
        </div>
      </div>

      {error && <p className="form-error">{error}</p>}

      {documents.length === 0 ? (
        <div className="research-empty">
          <h2>Nothing here yet</h2>
          <p>
            Add a paper or a textbook as a PDF. Sections, references and citation details
            are read out of the document; you can correct any of them afterwards.
          </p>
          <button className="btn-primary" onClick={() => setUploadOpen(true)}>
            Add your first document
          </button>
        </div>
      ) : (
        <>
          <div className="research-grid">
            {documents.map((doc) => {
              const ready = doc.status === "ready";
              return (
                <div key={doc.id} className="research-card-wrap">
                  {ready ? (
                    <Link to={`/research/${doc.id}`} className="research-card">
                      <DocumentCard doc={doc} />
                    </Link>
                  ) : (
                    <div className="research-card is-unready">
                      <DocumentCard doc={doc} />
                    </div>
                  )}
                  <button
                    className="research-delete"
                    aria-label={`Delete ${doc.title}`}
                    onClick={() => setConfirmDelete(doc)}
                  >
                    Delete
                  </button>
                </div>
              );
            })}
          </div>

          <p className="research-export">
            <a href={researchExportUrl()}>Export your sections and tags as CSV</a> — your own
            documents only. Research documents are not in the pilot exports.
          </p>
        </>
      )}

      {confirmDelete && (
        <div className="modal-backdrop" role="dialog" aria-modal="true">
          <div className="modal-card">
            <h2>Delete this document?</h2>
            <p>
              <strong>{confirmDelete.title}</strong> and its highlights, notes and tags are
              deleted for good.
            </p>
            <div className="modal-actions">
              <button className="btn-secondary" onClick={() => setConfirmDelete(null)}>
                Keep it
              </button>
              <button className="btn-danger" onClick={() => remove(confirmDelete.id)}>
                Delete
              </button>
            </div>
          </div>
        </div>
      )}

      <UploadResearchDialog
        open={uploadOpen}
        onClose={() => setUploadOpen(false)}
        onUploaded={load}
      />
      <SettingsPanel open={settingsOpen} onClose={() => setSettingsOpen(false)} />
    </div>
  );
}

function DocumentCard({ doc }) {
  return (
    <>
      <div className="research-card-top">
        <span className="research-kind-badge">{KIND_LABEL[doc.doc_kind] || "Document"}</span>
        {doc.tagging_consent && <span className="research-tag-badge">AI tagging on</span>}
      </div>
      <h3>{doc.title}</h3>
      <p className="author">{doc.authors || "Author not found"}</p>
      <p className="research-card-meta">
        {[
          doc.year || "No year",
          doc.venue,
          doc.page_count ? `${doc.page_count} pages` : null,
          doc.section_count ? `${doc.section_count} sections` : null,
        ]
          .filter(Boolean)
          .join(" · ")}
      </p>
      {doc.status !== "ready" && (
        <div className={`book-state ${doc.status}`}>
          {doc.status === "processing"
            ? "Converting…"
            : doc.failure_reason || "Conversion failed"}
        </div>
      )}
    </>
  );
}
