/**
 * Shown once conversion succeeds. Displays page statistics
 * and a download button for the generated DOCX.
 */
export default function DownloadCard({ result, onConvertAnother }) {
  return (
    <div className="download-card">
      <div className="download-card__icon">✓</div>
      <h2>Your document is ready</h2>

      <dl className="download-card__stats">
        <div>
          <dt>Total pages</dt>
          <dd>{result.totalPages}</dd>
        </div>
        <div>
          <dt>Digital text</dt>
          <dd>{result.digitalPages}</dd>
        </div>
        <div>
          <dt>OCR (scanned)</dt>
          <dd>{result.scannedPages}</dd>
        </div>
        <div>
          <dt>Mixed</dt>
          <dd>{result.mixedPages}</dd>
        </div>
      </dl>

        <a     
        href={result.downloadUrl}
        download
        className="download-card__button"
      >
        Download .docx
      </a>

      <button
        className="download-card__secondary"
        onClick={onConvertAnother}
      >
        Convert another file
      </button>
    </div>
  )
}