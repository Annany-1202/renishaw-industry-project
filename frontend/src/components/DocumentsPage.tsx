import React, { useRef, useState } from 'react';
import { UploadCloud, FileText, Trash2, RotateCcw, CheckCircle, AlertTriangle, Loader2, Download, X, ChevronDown, ChevronRight } from 'lucide-react';
import { DocumentInfo, DocumentDetail, DeletionPreview } from '../types';
import { ApiError, deleteDocument, fetchDeletionPreview, fetchDocument, reportUrl, retryDocument, uploadDocument } from '../api';

interface DocumentsPageProps {
  documents: DocumentInfo[];
  loadError: string | null;
  refreshDocuments: () => Promise<void> | void;
}

type Notice = { kind: 'ok' | 'error'; text: string };

const STATUS_STYLE: Record<string, string> = {
  Ready: 'bg-emerald-100 dark:bg-emerald-950 text-emerald-800 dark:text-emerald-300',
  Failed: 'bg-red-100 dark:bg-red-950 text-red-800 dark:text-red-300',
  Deleting: 'bg-orange-100 dark:bg-orange-950 text-orange-800 dark:text-orange-300'
};
const BUSY = ['Uploaded', 'Queued', 'Processing'];

const size = (bytes: number) => (bytes > 1 << 20 ? `${(bytes / (1 << 20)).toFixed(1)} MB` : `${Math.max(1, Math.round(bytes / 1024))} KB`);

export const DocumentsPage: React.FC<DocumentsPageProps> = ({ documents, loadError, refreshDocuments }) => {
  const [dragging, setDragging] = useState(false);
  const [uploading, setUploading] = useState<string | null>(null);
  const [notice, setNotice] = useState<Notice | null>(null);
  const [confirm, setConfirm] = useState<DeletionPreview | null>(null);
  const [working, setWorking] = useState<string | null>(null);
  const [expanded, setExpanded] = useState<string | null>(null);
  const [detail, setDetail] = useState<DocumentDetail | null>(null);
  const fileInput = useRef<HTMLInputElement>(null);

  const upload = async (files: FileList | File[] | null) => {
    const list = Array.from(files || []);
    if (!list.length) return;
    setNotice(null);
    const messages: string[] = [];
    let failed = false;
    for (const file of list) {
      if (!file.name.toLowerCase().endsWith('.pdf')) {
        messages.push(`${file.name}: only PDF files are supported.`);
        failed = true;
        continue;
      }
      setUploading(file.name);
      try {
        await uploadDocument(file);
        messages.push(`${file.name}: uploaded, processing started.`);
      } catch (e: any) {
        failed = true;
        messages.push(`${file.name}: ${e.message}`);
      }
    }
    setUploading(null);
    setNotice({ kind: failed ? 'error' : 'ok', text: messages.join(' ') });
    if (fileInput.current) fileInput.current.value = '';
    await refreshDocuments();
  };

  const askDelete = async (doc: DocumentInfo) => {
    setNotice(null);
    try {
      setConfirm(await fetchDeletionPreview(doc.id));
    } catch (e: any) {
      setNotice({ kind: 'error', text: e.message });
    }
  };

  const doDelete = async () => {
    if (!confirm) return;
    const target = confirm;
    setConfirm(null);
    setWorking(target.document_id);
    try {
      const report = await deleteDocument(target.document_id);
      const r = report.removed || {};
      setNotice({
        kind: 'ok',
        text: `Deleted ${target.filename}: ${r.products ?? 0} products, ${r.images ?? 0} images, ${r.embeddings ?? 0} index entries and the stored PDF were removed and verified.`
      });
      if (expanded === target.document_id) setExpanded(null);
    } catch (e: any) {
      const step = e instanceof ApiError ? e.body?.report?.failed_step : null;
      setNotice({ kind: 'error', text: `${e.message}${step ? ` (failed step: ${step})` : ''}` });
    } finally {
      setWorking(null);
      await refreshDocuments();
    }
  };

  const retry = async (doc: DocumentInfo) => {
    setNotice(null);
    setWorking(doc.id);
    try {
      await retryDocument(doc.id);
    } catch (e: any) {
      setNotice({ kind: 'error', text: e.message });
    } finally {
      setWorking(null);
      await refreshDocuments();
    }
  };

  const toggleDetail = async (doc: DocumentInfo) => {
    if (expanded === doc.id) {
      setExpanded(null);
      return;
    }
    setExpanded(doc.id);
    setDetail(null);
    try {
      setDetail(await fetchDocument(doc.id));
    } catch (e: any) {
      setNotice({ kind: 'error', text: e.message });
    }
  };

  return (
    <div className="max-w-4xl mx-auto px-6 py-8 space-y-6">
      <div>
        <h2 className="text-lg font-semibold text-neutral-900 dark:text-white">Catalogue documents</h2>
        <p className="text-xs text-notion-mutedLight dark:text-notion-mutedDark mt-1">
          Only documents with status Ready are searched. Deleting a document removes its products, images, index entries and stored file.
        </p>
      </div>

      <div
        onDragOver={(e) => {
          e.preventDefault();
          setDragging(true);
        }}
        onDragLeave={() => setDragging(false)}
        onDrop={(e) => {
          e.preventDefault();
          setDragging(false);
          upload(e.dataTransfer.files);
        }}
        className={`rounded-xl border-2 border-dashed p-8 text-center transition-colors ${
          dragging ? 'border-neutral-900 dark:border-white bg-neutral-100 dark:bg-neutral-800' : 'border-neutral-300 dark:border-neutral-700 bg-neutral-50 dark:bg-neutral-900/40'
        }`}
      >
        <UploadCloud size={26} className="mx-auto text-neutral-400 mb-2" />
        <p className="text-sm font-medium text-neutral-800 dark:text-neutral-200">
          {uploading ? `Uploading ${uploading}…` : 'Drop a PDF catalogue here'}
        </p>
        <p className="text-xs text-neutral-500 mt-1">or</p>
        <input ref={fileInput} id="pdf-upload" type="file" accept="application/pdf,.pdf" multiple className="sr-only" onChange={(e) => upload(e.target.files)} />
        <label
          htmlFor="pdf-upload"
          className={`inline-block mt-2 px-3 py-1.5 rounded-lg bg-neutral-900 dark:bg-neutral-100 text-white dark:text-neutral-900 text-xs font-semibold cursor-pointer ${uploading ? 'opacity-50 pointer-events-none' : ''}`}
        >
          Choose PDF
        </label>
      </div>

      {(notice || loadError) && (
        <div
          role={notice?.kind === 'ok' ? 'status' : 'alert'}
          className={`flex items-start justify-between gap-3 p-3 rounded-lg border text-xs ${
            notice?.kind === 'ok'
              ? 'border-emerald-200 dark:border-emerald-900 bg-emerald-50 dark:bg-emerald-950/30 text-emerald-900 dark:text-emerald-200'
              : 'border-red-200 dark:border-red-900 bg-red-50 dark:bg-red-950/30 text-red-800 dark:text-red-200'
          }`}
        >
          <span>{notice?.text || loadError}</span>
          {notice && (
            <button aria-label="Dismiss" onClick={() => setNotice(null)}>
              <X size={13} />
            </button>
          )}
        </div>
      )}

      <div className="space-y-2">
        {documents.length === 0 && !loadError && (
          <p className="text-xs text-neutral-500 p-6 text-center border border-dashed border-neutral-300 dark:border-neutral-700 rounded-xl">
            No documents yet. Upload a PDF catalogue, or restore the supplied catalogues from Settings.
          </p>
        )}
        {documents.map((doc) => {
          const busy = BUSY.includes(doc.status) || working === doc.id;
          const open = expanded === doc.id;
          const report = open && detail?.id === doc.id ? detail.ingestion_report : null;
          return (
            <div key={doc.id} className="rounded-xl border border-notion-borderLight dark:border-notion-borderDark bg-white dark:bg-neutral-900">
              <div className="flex items-center gap-3 p-3.5">
                <button onClick={() => toggleDetail(doc)} aria-expanded={open} aria-label={`${open ? 'Hide' : 'Show'} details of ${doc.filename}`} className="text-neutral-400 hover:text-neutral-700 dark:hover:text-neutral-200">
                  {open ? <ChevronDown size={16} /> : <ChevronRight size={16} />}
                </button>
                <FileText size={18} className="text-neutral-400 shrink-0" />
                <div className="min-w-0 flex-1">
                  <div className="flex items-center gap-2">
                    <span className="text-sm font-medium text-neutral-900 dark:text-neutral-100 truncate" title={doc.filename}>{doc.filename}</span>
                    {doc.is_builtin && <span className="text-[10px] px-1.5 py-0.5 rounded bg-neutral-100 dark:bg-neutral-800 text-neutral-500 shrink-0">supplied</span>}
                  </div>
                  <div className="text-[11px] text-notion-mutedLight dark:text-notion-mutedDark mt-0.5">
                    {size(doc.file_size)}
                    {doc.page_count ? ` · ${doc.page_count} pages` : ''}
                    {doc.status === 'Ready' ? ` · ${doc.product_count} products · ${doc.image_count} images` : ''}
                    {doc.status === 'Ready' && doc.review_count > 0 ? ` · ${doc.review_count} flagged for review` : ''}
                  </div>
                  {doc.error_message && (
                    <div className="text-[11px] text-red-700 dark:text-red-300 mt-1 flex items-start space-x-1">
                      <AlertTriangle size={11} className="shrink-0 mt-0.5" />
                      <span>{doc.error_message}</span>
                    </div>
                  )}
                </div>
                <span className={`inline-flex items-center space-x-1 px-2 py-0.5 rounded-full text-[11px] font-semibold shrink-0 ${STATUS_STYLE[doc.status] || 'bg-blue-100 dark:bg-blue-950 text-blue-800 dark:text-blue-300'}`}>
                  {doc.status === 'Ready' ? <CheckCircle size={11} /> : doc.status === 'Failed' ? <AlertTriangle size={11} /> : <Loader2 size={11} className="animate-spin" />}
                  <span>{doc.status}</span>
                </span>
                {doc.status === 'Failed' && (
                  <button onClick={() => retry(doc)} disabled={busy} title="Retry ingestion" aria-label={`Retry ${doc.filename}`} className="p-1.5 rounded hover:bg-neutral-100 dark:hover:bg-neutral-800 text-neutral-500 disabled:opacity-40">
                    <RotateCcw size={15} />
                  </button>
                )}
                <button
                  onClick={() => askDelete(doc)}
                  disabled={busy}
                  title={doc.status === 'Deleting' ? 'Finish the interrupted deletion' : 'Delete document'}
                  aria-label={`Delete ${doc.filename}`}
                  className="p-1.5 rounded hover:bg-red-50 dark:hover:bg-red-950/40 text-neutral-500 hover:text-red-600 disabled:opacity-40"
                >
                  <Trash2 size={15} />
                </button>
              </div>

              {open && (
                <div className="border-t border-notion-borderLight dark:border-notion-borderDark p-3.5 text-xs space-y-3">
                  {!detail || detail.id !== doc.id ? (
                    <p className="text-neutral-500">Loading…</p>
                  ) : (
                    <>
                      {report ? (
                        <>
                          <dl className="grid grid-cols-2 sm:grid-cols-4 gap-2">
                            {[
                              ['Rows read', report.rows_extracted],
                              ['Products stored', report.products_extracted],
                              ['Flagged for review', report.rows_needs_review],
                              ['Rows rejected', report.rows_rejected],
                              ['Images extracted', report.images_extracted],
                              ['Images verified', report.images_verified],
                              ['Products without image', report.products_without_image],
                              ['Index entries', detail.embedded_count]
                            ].map(([label, value]) => (
                              <div key={label as string} className="p-2 rounded bg-neutral-50 dark:bg-neutral-800/40 border border-neutral-200/60 dark:border-neutral-800">
                                <dt className="text-[10px] text-notion-mutedLight dark:text-notion-mutedDark">{label}</dt>
                                <dd className="font-semibold">{value ?? '—'}</dd>
                              </div>
                            ))}
                          </dl>
                          <p className="text-neutral-500">Search index: {report.embeddings || 'not built'}</p>
                          {(report.exceptions || []).length > 0 && (
                            <ul className="list-disc pl-4 text-amber-700 dark:text-amber-300">
                              {report.exceptions.slice(0, 8).map((x: string, i: number) => <li key={i}>{x}</li>)}
                            </ul>
                          )}
                          <div className="flex flex-wrap gap-2">
                            {([['report', 'Ingestion report (JSON)'], ['review', 'Rows needing review (CSV)'], ['images', 'Image associations (CSV)']] as const).map(([kind, label]) => (
                              <a key={kind} href={reportUrl(doc.id, kind)} className="inline-flex items-center space-x-1 px-2 py-1 rounded border border-neutral-300 dark:border-neutral-700 hover:bg-neutral-100 dark:hover:bg-neutral-800">
                                <Download size={12} />
                                <span>{label}</span>
                              </a>
                            ))}
                          </div>
                        </>
                      ) : (
                        <p className="text-neutral-500">No ingestion report is available for this document.</p>
                      )}
                      <details>
                        <summary className="cursor-pointer text-neutral-500">History</summary>
                        <ul className="mt-1 space-y-0.5 text-[11px] text-neutral-500">
                          {detail.events.map((e, i) => (
                            <li key={i}>
                              {e.created_at} · {e.event}
                              {e.detail ? ` · ${e.detail}` : ''}
                            </li>
                          ))}
                        </ul>
                      </details>
                    </>
                  )}
                </div>
              )}
            </div>
          );
        })}
      </div>

      {confirm && (
        <div role="dialog" aria-modal="true" aria-label="Confirm deletion" className="fixed inset-0 z-50 bg-black/50 flex items-center justify-center p-4" onClick={() => setConfirm(null)}>
          <div className="w-full max-w-md rounded-xl bg-white dark:bg-neutral-900 border border-notion-borderLight dark:border-notion-borderDark p-5 space-y-3" onClick={(e) => e.stopPropagation()}>
            <h3 className="text-sm font-semibold text-neutral-900 dark:text-white">Delete this document?</h3>
            <p className="text-xs text-neutral-600 dark:text-neutral-300 break-all">{confirm.filename}</p>
            <ul className="text-xs text-neutral-600 dark:text-neutral-300 list-disc pl-4 space-y-0.5">
              <li>{confirm.will_remove.products} product records</li>
              <li>{confirm.will_remove.images} images and {confirm.will_remove.product_image_links} image links</li>
              <li>{confirm.will_remove.embeddings} search-index entries</li>
              <li>the stored PDF and its reports</li>
            </ul>
            {confirm.will_remove.shared_part_numbers_kept_in_other_documents > 0 && (
              <p className="text-xs text-neutral-500">
                {confirm.will_remove.shared_part_numbers_kept_in_other_documents} of its part numbers also appear in another document and stay searchable from there.
              </p>
            )}
            <p className="text-xs text-neutral-500">This cannot be undone; the PDF would have to be uploaded again.</p>
            <div className="flex justify-end space-x-2 pt-1">
              <button autoFocus onClick={() => setConfirm(null)} className="px-3 py-1.5 rounded-lg border border-neutral-300 dark:border-neutral-700 text-xs">
                Cancel
              </button>
              <button onClick={doDelete} className="px-3 py-1.5 rounded-lg bg-red-600 hover:bg-red-700 text-white text-xs font-semibold">
                Delete document
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};
