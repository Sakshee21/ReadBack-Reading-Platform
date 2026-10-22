import { useCallback, useEffect, useMemo, useState } from "react";
import { Link, useParams, useSearchParams } from "react-router-dom";
import { api } from "../api";
import { missingForCitation, researchCitation } from "../citations/research";
import HighlightableText from "../components/HighlightableText";
import Icon from "../components/Icon";
import ResearchMetadataForm from "../components/ResearchMetadataForm";
import SettingsPanel from "../components/SettingsPanel";
import { useBookHighlights } from "../highlights/useBookHighlights";

const KIND_LABEL = {
  abstract: "Abstract",
  body: "Section",
  references: "References",
  appendix: "Appendix",
  front_matter: "Title page",
};

/**
 * Reading a research document, by section.
 *
 * What is deliberately absent: no autoplay countdown, no next-up timer, no
 * cliffhanger break, no streak, no celebration, no imagine-this-scene prompt,
 * no puzzle break, and no reading-session logging. A paper is not a habit to
 * be scaffolded.
 *
 * What is kept: highlights with colours and comments, the notes page, copying
 * a citation (journal-article and textbook-chapter formats), and the
 * appearance themes.
 */
export default function ResearchReader() {
  const { documentId } = useParams();
  const [params, setParams] = useSearchParams();
  const id = Number(documentId);

  const [doc, setDoc] = useState(null);
  const [sectionId, setSectionId] = useState(null);
  const [reading, setReading] = useState(null);
  const [tagStatus, setTagStatus] = useState(null);
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [editingMeta, setEditingMeta] = useState(null);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");

  const loadDocument = useCallback(async () => {
    const detail = await api.getResearchDocument(id);
    setDoc(detail);
    return detail;
  }, [id]);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const detail = await loadDocument();
        if (cancelled) return;
        const wanted = Number(params.get("section"));
        const readable = detail.sections.filter((s) => s.readable);
        const chosen =
          detail.sections.find((s) => s.id === wanted) || readable[0] || detail.sections[0];
        setSectionId(chosen?.id ?? null);
      } catch (err) {
        if (!cancelled) setError(err.message || "Could not open that document.");
      }
    })();
    return () => {
      cancelled = true;
    };
    // params is read once, for a deep link; later changes come from setSectionId.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [loadDocument]);

  useEffect(() => {
    if (sectionId == null) return undefined;
    let cancelled = false;
    api
      .readResearchSection(id, sectionId)
      .then((body) => !cancelled && setReading(body))
      .catch((err) => !cancelled && setError(err.message || "Could not load that section."));
    return () => {
      cancelled = true;
    };
  }, [id, sectionId]);

  useEffect(() => {
    if (!doc) return;
    api
      .getResearchTagStatus(id)
      .then(setTagStatus)
      .catch(() => setTagStatus(null));
  }, [doc, id]);

  // Highlights are reloaded per section, keyed on its first chunk.
  const reloadKey = reading?.chunks?.[0]?.id ?? null;
  const { highlights, replaceForPart } = useBookHighlights(id, reloadKey);

  const locator = useMemo(
    () =>
      reading
        ? {
            title: reading.section.title,
            kind: reading.section.kind,
            index: reading.section.index,
          }
        : {},
    [reading]
  );

  // CiteControl calls cite(style, book, highlight); a research citation is
  // located by section, so the highlight argument is replaced by the locator.
  const cite = useCallback(
    (style, document) => researchCitation(style, document, locator),
    [locator]
  );
  // The fields a citation cannot be written without that are blank or still
  // only a guess. Shown in the panel and marked in the citation itself.
  const review = doc ? missingForCitation({ ...doc, authors: doc.authors }) : [];
  const linkTo = useCallback(
    () => `${window.location.origin}/research/${id}?section=${sectionId}`,
    [id, sectionId]
  );

  function goTo(nextSectionId) {
    setSectionId(nextSectionId);
    setParams({ section: String(nextSectionId) }, { replace: true });
    setReading(null);
    window.scrollTo({ top: 0 });
  }

  async function toggleConsent(next) {
    try {
      setTagStatus(await api.setResearchConsent(id, next));
      await loadDocument();
      setNotice(
        next
          ? "Tagging is on for this document."
          : "Tagging is off, and the tags for this document have been deleted."
      );
    } catch (err) {
      setError(err.message || "Could not change that setting.");
    }
  }

  async function startTagging() {
    try {
      setTagStatus(await api.queueResearchTags(id));
      setNotice("Tagging started. It runs in the background; reload to see new tags.");
    } catch (err) {
      setError(err.message || "Could not start tagging.");
    }
  }

  async function askKeyPoints() {
    try {
      await api.requestKeyPoints(id, sectionId);
      setNotice("Key points requested. They appear here once the model answers.");
    } catch (err) {
      setError(err.message || "Could not request key points.");
    }
  }

  async function saveMetadata(event) {
    event.preventDefault();
    try {
      await api.updateResearchMetadata(id, {
        ...editingMeta,
        year: editingMeta.year === "" ? null : editingMeta.year,
        no_date: Boolean(editingMeta.no_date),
      });
      setEditingMeta(null);
      await loadDocument();
      setNotice("Citation details saved.");
    } catch (err) {
      setError(err.message || "Could not save those details.");
    }
  }

  if (error && !doc) return <div className="page-loading">{error}</div>;
  if (!doc) return <div className="page-loading">Opening document...</div>;

  const section = reading?.section;
  const tagsByChunk = new Map((reading?.tags ?? []).map((t) => [t.micro_session_id, t.tags]));

  return (
    <div className="research-reader">
      <div className="research-topbar">
        <Link to="/research" className="btn-secondary">
          <Icon name="library" />
          Research
        </Link>
        <span className="research-topbar-title">{doc.title}</span>
        <div className="research-topbar-actions">
          <Link to={`/books/${id}/notes`} className="btn-secondary">
            <Icon name="notes" />
            Notes
          </Link>
          <button className="btn-secondary" onClick={() => setSettingsOpen(true)}>
            <Icon name="settings" />
            Settings
          </button>
        </div>
      </div>

      {notice && (
        <p className="research-notice" role="status">
          {notice}
        </p>
      )}
      {error && <p className="form-error">{error}</p>}

      <div className="research-layout">
        <nav className="research-sections" aria-label="Sections">
          <h2>Sections</h2>
          <ol>
            {doc.sections.map((s) => (
              <li key={s.id}>
                <button
                  className={`research-section-link${s.id === sectionId ? " is-current" : ""}${
                    s.readable ? "" : " is-aside"
                  }`}
                  onClick={() => goTo(s.id)}
                >
                  <span className="research-section-name">
                    {s.title || KIND_LABEL[s.kind] || "Untitled"}
                  </span>
                  <span className="research-section-meta">
                    {s.readable ? `${s.word_count.toLocaleString()} words` : KIND_LABEL[s.kind]}
                  </span>
                </button>
              </li>
            ))}
          </ol>

          <div className="research-aside-note">
            References and the title page are kept out of the reading flow, but you can
            open them here.
          </div>
        </nav>

        <main className="research-body">
          {!reading ? (
            <p className="page-loading">Loading section...</p>
          ) : (
            <>
              <header className="research-section-header">
                <p className="research-section-kind">{KIND_LABEL[section.kind] || section.kind}</p>
                <h1>{section.title || KIND_LABEL[section.kind] || "Untitled section"}</h1>
                <p className="research-section-stats">
                  {section.word_count.toLocaleString()} words
                  {section.readable ? "" : " · not part of the reading flow"}
                </p>
              </header>

              {reading.key_points && (
                <KeyPointsPanel
                  keyPoints={reading.key_points}
                  onRequest={askKeyPoints}
                  canRequest={section.readable && Boolean(tagStatus?.enabled)}
                />
              )}

              {reading.chunks.map((chunk) => (
                <article key={chunk.id || "whole"} className="research-chunk">
                  {chunk.id ? (
                    <HighlightableText
                      text={chunk.text}
                      bookId={id}
                      microSessionId={chunk.id}
                      enabled
                      highlights={highlights.filter((h) => h.micro_session_id === chunk.id)}
                      onChanged={(rows) => replaceForPart(chunk.id, rows)}
                      book={{ ...doc, author: doc.authors }}
                      cite={cite}
                      linkTo={linkTo}
                    />
                  ) : (
                    // A section stored whole (references, title page): readable,
                    // but with no chunk to anchor a highlight to.
                    <div className="research-plain-text">
                      {chunk.text.split("\n\n").map((para, i) => (
                        <p key={i}>{para}</p>
                      ))}
                    </div>
                  )}
                  {tagsByChunk.get(chunk.id)?.length > 0 && (
                    <ul className="research-chunk-tags" aria-label="Section tags">
                      {tagsByChunk.get(chunk.id).map((tag) => (
                        <li key={tag.tag} className="research-chunk-tag">
                          {tag.label}
                        </li>
                      ))}
                    </ul>
                  )}
                </article>
              ))}

              <nav className="research-section-nav" aria-label="Move between sections">
                <button
                  className="btn-secondary"
                  disabled={!reading.previous_section_id}
                  onClick={() => goTo(reading.previous_section_id)}
                >
                  Previous section
                </button>
                <button
                  className="btn-secondary"
                  disabled={!reading.next_section_id}
                  onClick={() => goTo(reading.next_section_id)}
                >
                  Next section
                </button>
              </nav>
            </>
          )}
        </main>

        <aside className="research-sidebar">
          <section className="research-panel">
            <h2>Citation details</h2>
            {review.length > 0 && (
              <p className="research-review-warning" role="status">
                Add {review.join(", ")} before citing. Until then a citation shows
                the gap as <code>[Author]</code> or <code>[Year]</code> rather than
                reading as though the document said so.
              </p>
            )}
            {editingMeta ? (
              <form onSubmit={saveMetadata}>
                <ResearchMetadataForm
                  values={editingMeta}
                  onChange={setEditingMeta}
                  needsReview={review}
                />
                <div className="modal-actions">
                  <button type="button" className="btn-secondary" onClick={() => setEditingMeta(null)}>
                    Cancel
                  </button>
                  <button type="submit" className="btn-primary">
                    Save
                  </button>
                </div>
              </form>
            ) : (
              <>
                <dl className="research-meta-list">
                  <dt>Authors</dt>
                  <dd>{doc.authors || <em>not found</em>}</dd>
                  <dt>Year</dt>
                  <dd>{doc.year || <em>not found</em>}</dd>
                  <dt>Venue</dt>
                  <dd>{doc.venue || <em>not found</em>}</dd>
                  <dt>DOI</dt>
                  <dd>{doc.doi || <em>not found</em>}</dd>
                </dl>
                <button
                  className="btn-secondary"
                  onClick={() =>
                    setEditingMeta({
                      title: doc.title ?? "",
                      authors: doc.authors ?? "",
                      year: doc.year ?? "",
                      venue: doc.venue ?? "",
                      doi: doc.doi ?? "",
                      no_date: Boolean(doc.no_date),
                    })
                  }
                >
                  Edit details
                </button>
                <p className="research-panel-note">
                  Blank fields are ones the document did not state. They are left empty
                  rather than guessed, because they go into citations.
                </p>
              </>
            )}
          </section>

          <section className="research-panel">
            <h2>Section tags</h2>
            <label className="research-consent">
              <input
                type="checkbox"
                checked={Boolean(doc.tagging_consent)}
                onChange={(e) => toggleConsent(e.target.checked)}
              />
              <span>Allow this document to be sent to an AI service</span>
            </label>
            {tagStatus && (
              <>
                <p className="research-tag-status" role="status">
                  {tagStatus.message}
                </p>
                {tagStatus.enabled && (
                  <>
                    <div className="progress-bar" aria-hidden="true">
                      <div
                        className="fill"
                        style={{
                          width: `${
                            tagStatus.total
                              ? Math.round((tagStatus.done / tagStatus.total) * 100)
                              : 0
                          }%`,
                        }}
                      />
                    </div>
                    <button className="btn-secondary" onClick={startTagging}>
                      {tagStatus.done ? "Tag what is left" : "Start tagging"}
                    </button>
                  </>
                )}
              </>
            )}
            <p className="research-panel-note">
              Tags label what a passage <em>does</em> — a claim, a method, a result — and
              are machine-generated.
            </p>
          </section>

          {doc.warnings?.length > 0 && (
            <section className="research-panel">
              <h2>What could not be handled</h2>
              <ul className="research-warnings">
                {doc.warnings.map((warning, i) => (
                  <li key={i}>{warning}</li>
                ))}
              </ul>
            </section>
          )}

          {doc.captions?.length > 0 && (
            <section className="research-panel">
              <h2>Figure and table captions</h2>
              <ul className="research-captions">
                {doc.captions.map((caption, i) => (
                  <li key={i}>{caption}</li>
                ))}
              </ul>
              <p className="research-panel-note">
                Kept aside so they do not read as part of a paragraph. The figures
                themselves are not shown.
              </p>
            </section>
          )}
        </aside>
      </div>

      <SettingsPanel open={settingsOpen} onClose={() => setSettingsOpen(false)} />
    </div>
  );
}

function KeyPointsPanel({ keyPoints, onRequest, canRequest }) {
  const points = (keyPoints.text || "").split("\n").filter(Boolean);
  return (
    <section className="research-key-points">
      <h2>
        Key points <span className="research-generated-badge">machine-generated</span>
      </h2>
      {keyPoints.status === "done" && points.length > 0 ? (
        <ul>
          {points.map((point, i) => (
            <li key={i}>{point}</li>
          ))}
        </ul>
      ) : keyPoints.status === "running" || keyPoints.status === "queued" ? (
        <p>Working on it…</p>
      ) : keyPoints.status === "failed" ? (
        <p>
          That did not work, so nothing is shown here. Read the section itself rather than
          a summary that might be wrong.
        </p>
      ) : (
        <p>
          No key points yet.
          {canRequest ? (
            <>
              {" "}
              <button className="btn-link" onClick={onRequest}>
                Generate them
              </button>
            </>
          ) : (
            " Turn on AI tagging for this document to generate them."
          )}
        </p>
      )}
    </section>
  );
}
