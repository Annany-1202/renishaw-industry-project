import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { X, Image as ImageIcon, List, ChevronLeft, ChevronRight, ChevronDown, Search, Link2, Loader2, AlertTriangle, FileText } from 'lucide-react';
import { DocumentImage, DocumentImages, DocumentInfo, DocumentPart, DocumentParts } from '../types';
import { fetchDocumentImages, fetchDocumentParts } from '../api';

export type GalleryTab = 'images' | 'parts';

interface DocumentGalleryProps {
  document: DocumentInfo;
  initialTab?: GalleryTab;
  onClose: () => void;
}

const IMAGE_BATCH = 60;
const PART_PAGE = 50;

const show = (v: unknown, unit?: string) => (v === null || v === undefined || v === '' ? '—' : `${v}${unit ? ` ${unit}` : ''}`);

const specRows = (p: DocumentPart): [string, string][] => [
  ['Product type', `${p.category}${p.stylus_type && p.stylus_type !== p.category ? ` (${p.stylus_type.replace(/_/g, ' ')})` : ''}`],
  ['Thread', show(p.thread)],
  ['Ball / tip material', show(p.ball_material)],
  ['Ball / tip diameter', show(p.ball_diameter_mm, 'mm')],
  ['Stem / body material', show(p.stem_material)],
  ['Stem diameter', show(p.stem_diameter_mm, 'mm')],
  ['Overall length', show(p.overall_length_mm, 'mm')],
  ['Effective working length', show(p.effective_working_length_mm, 'mm')],
  ['Mass', show(p.weight_g, 'g')],
  ['Manufacturer', show(p.manufacturer)]
];

const Thumb: React.FC<{ src: string; alt: string; className?: string }> = ({ src, alt, className }) => {
  const [failed, setFailed] = useState(false);
  if (failed) {
    return (
      <div className={`flex items-center justify-center bg-neutral-100 dark:bg-neutral-800 text-neutral-400 ${className || ''}`}>
        <ImageIcon size={18} />
      </div>
    );
  }
  return <img src={src} alt={alt} loading="lazy" onError={() => setFailed(true)} className={`object-contain bg-white ${className || ''}`} />;
};

export const DocumentGallery: React.FC<DocumentGalleryProps> = ({ document, initialTab = 'images', onClose }) => {
  const [tab, setTab] = useState<GalleryTab>(initialTab);

  // --- images ---
  const [images, setImages] = useState<DocumentImages | null>(null);
  const [imageError, setImageError] = useState<string | null>(null);
  const [typeFilter, setTypeFilter] = useState('');
  const [pageFilter, setPageFilter] = useState('');
  const [linkedOnly, setLinkedOnly] = useState(false);
  const [visible, setVisible] = useState(IMAGE_BATCH);
  const [open, setOpen] = useState<number | null>(null);

  // --- parts ---
  const [parts, setParts] = useState<DocumentParts | null>(null);
  const [partError, setPartError] = useState<string | null>(null);
  const [partsLoading, setPartsLoading] = useState(false);
  const [query, setQuery] = useState('');
  const [debounced, setDebounced] = useState('');
  const [category, setCategory] = useState('');
  const [expanded, setExpanded] = useState<string | null>(null);
  // Whole-document counts; the server returns them unaffected by the filters.
  const categories = parts?.categories || {};

  useEffect(() => {
    let live = true;
    fetchDocumentImages(document.id)
      .then((r) => live && setImages(r))
      .catch((e) => live && setImageError(e.message));
    return () => {
      live = false;
    };
  }, [document.id]);

  useEffect(() => {
    const timer = window.setTimeout(() => setDebounced(query.trim()), 250);
    return () => window.clearTimeout(timer);
  }, [query]);

  const partsSeq = useRef(0);
  const loadParts = useCallback(
    async (offset: number) => {
      const seq = ++partsSeq.current;
      setPartsLoading(true);
      setPartError(null);
      try {
        const page = await fetchDocumentParts(document.id, { q: debounced, category, offset, limit: PART_PAGE });
        if (seq !== partsSeq.current) return; // the filter changed meanwhile
        setParts((prev) => (offset > 0 && prev ? { ...page, parts: [...prev.parts, ...page.parts] } : page));
      } catch (e: any) {
        if (seq === partsSeq.current) setPartError(e.message);
      } finally {
        if (seq === partsSeq.current) setPartsLoading(false);
      }
    },
    [document.id, debounced, category]
  );

  useEffect(() => {
    if (tab === 'parts') loadParts(0);
  }, [tab, loadParts]);

  const filtered = useMemo(() => {
    if (!images) return [];
    const page = parseInt(pageFilter, 10);
    return images.images.filter(
      (img) =>
        (!typeFilter || img.image_type === typeFilter) &&
        (!pageFilter || Number.isNaN(page) || img.page_number === page) &&
        (!linkedOnly || img.associated_parts.length > 0)
    );
  }, [images, typeFilter, pageFilter, linkedOnly]);

  useEffect(() => setVisible(IMAGE_BATCH), [typeFilter, pageFilter, linkedOnly]);

  const step = useCallback(
    (delta: number) => {
      if (open === null || !filtered.length) return;
      setOpen((open + delta + filtered.length) % filtered.length);
    },
    [open, filtered.length]
  );

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const target = e.target as HTMLElement | null;
      if (target && ['INPUT', 'TEXTAREA', 'SELECT'].includes(target.tagName)) return;
      if (e.key === 'Escape') {
        if (open !== null) setOpen(null);
        else onClose();
      } else if (open !== null && e.key === 'ArrowRight') step(1);
      else if (open !== null && e.key === 'ArrowLeft') step(-1);
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [open, onClose, step]);

  const showPart = (partNumber: string) => {
    setOpen(null);
    setCategory('');
    setQuery(partNumber);
    setDebounced(partNumber);
    setExpanded(null);
    setTab('parts');
  };

  const current: DocumentImage | null = open !== null ? filtered[open] ?? null : null;

  const tabButton = (key: GalleryTab, icon: React.ReactNode, label: string) => (
    <button
      role="tab"
      aria-selected={tab === key}
      onClick={() => setTab(key)}
      className={`inline-flex items-center space-x-1.5 px-3 py-1.5 rounded-lg text-xs font-medium transition-colors ${
        tab === key
          ? 'bg-neutral-900 dark:bg-neutral-100 text-white dark:text-neutral-900'
          : 'text-neutral-600 dark:text-neutral-300 hover:bg-neutral-100 dark:hover:bg-neutral-800'
      }`}
    >
      {icon}
      <span>{label}</span>
    </button>
  );

  return (
    <div role="dialog" aria-modal="true" aria-label={`Contents of ${document.filename}`} className="fixed inset-0 z-50 bg-black/50 flex items-center justify-center p-4" onClick={onClose}>
      <div
        className="w-full max-w-6xl h-[90vh] rounded-xl bg-white dark:bg-neutral-900 border border-notion-borderLight dark:border-notion-borderDark flex flex-col overflow-hidden"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center gap-3 p-4 border-b border-notion-borderLight dark:border-notion-borderDark shrink-0">
          <FileText size={18} className="text-neutral-400 shrink-0" />
          <div className="min-w-0 flex-1">
            <h3 className="text-sm font-semibold text-neutral-900 dark:text-white truncate" title={document.filename}>{document.filename}</h3>
            <p className="text-[11px] text-notion-mutedLight dark:text-notion-mutedDark">
              {document.page_count} pages · {document.product_count} parts · {document.image_count} images
            </p>
          </div>
          <div role="tablist" className="flex items-center gap-1">
            {tabButton('images', <ImageIcon size={13} />, `Images (${images?.total ?? document.image_count})`)}
            {tabButton('parts', <List size={13} />, `All parts (${document.product_count})`)}
          </div>
          <button onClick={onClose} aria-label="Close" className="p-1 rounded hover:bg-neutral-100 dark:hover:bg-neutral-800 text-neutral-500">
            <X size={18} />
          </button>
        </div>

        {tab === 'images' && (
          <div className="flex-1 flex flex-col min-h-0">
            <div className="flex flex-wrap items-center gap-2 px-4 py-2.5 border-b border-notion-borderLight dark:border-notion-borderDark text-xs shrink-0">
              <select
                value={typeFilter}
                onChange={(e) => setTypeFilter(e.target.value)}
                aria-label="Image type"
                className="px-2 py-1 rounded border border-neutral-300 dark:border-neutral-700 bg-white dark:bg-neutral-900"
              >
                <option value="">All types</option>
                {Object.entries(images?.image_types || {}).map(([t, n]) => (
                  <option key={t} value={t}>
                    {t} ({n})
                  </option>
                ))}
              </select>
              <input
                type="number"
                min={1}
                value={pageFilter}
                onChange={(e) => setPageFilter(e.target.value)}
                placeholder="Page"
                aria-label="Page number"
                className="w-20 px-2 py-1 rounded border border-neutral-300 dark:border-neutral-700 bg-white dark:bg-neutral-900"
              />
              <label className="inline-flex items-center space-x-1.5 text-neutral-600 dark:text-neutral-300">
                <input type="checkbox" checked={linkedOnly} onChange={(e) => setLinkedOnly(e.target.checked)} />
                <span>Linked to a part only</span>
              </label>
              <span className="ml-auto text-neutral-500">
                {images ? `${filtered.length} of ${images.total} images · ${images.linked_images} linked to parts` : ''}
              </span>
            </div>
            <div className="flex-1 overflow-y-auto p-4">
              {imageError && <p className="text-xs text-red-700 dark:text-red-300">{imageError}</p>}
              {!images && !imageError && (
                <p className="text-xs text-neutral-500 flex items-center space-x-1.5">
                  <Loader2 size={13} className="animate-spin" />
                  <span>Loading images…</span>
                </p>
              )}
              {images && filtered.length === 0 && (
                <p className="text-xs text-neutral-500 text-center p-8">
                  {images.total === 0 ? 'No images were extracted from this document.' : 'No image matches these filters.'}
                </p>
              )}
              <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5 gap-3">
                {filtered.slice(0, visible).map((img, i) => (
                  <button
                    key={img.image_id}
                    onClick={() => setOpen(i)}
                    className="text-left rounded-lg border border-notion-borderLight dark:border-notion-borderDark overflow-hidden hover:ring-2 hover:ring-neutral-400 dark:hover:ring-neutral-600 transition"
                    aria-label={`Image on page ${img.page_number}`}
                  >
                    <Thumb src={img.image_url} alt={img.description || `Page ${img.page_number}`} className="w-full h-32" />
                    <div className="p-2 space-y-1 border-t border-notion-borderLight dark:border-notion-borderDark">
                      <div className="flex items-center justify-between text-[11px]">
                        <span className="font-medium text-neutral-800 dark:text-neutral-200">Page {img.page_number}</span>
                        <span className="px-1.5 py-0.5 rounded bg-neutral-100 dark:bg-neutral-800 text-neutral-500">{img.image_type}</span>
                      </div>
                      <div className="text-[10px] font-mono text-neutral-500 truncate" title={img.associated_parts.map((p) => p.part_number).join(', ')}>
                        {img.associated_parts.length
                          ? img.associated_parts.slice(0, 2).map((p) => p.part_number).join(', ') +
                            (img.associated_parts.length > 2 ? ` +${img.associated_parts.length - 2}` : '')
                          : 'No linked part'}
                      </div>
                    </div>
                  </button>
                ))}
              </div>
              {filtered.length > visible && (
                <div className="text-center pt-4">
                  <button onClick={() => setVisible(visible + IMAGE_BATCH)} className="px-3 py-1.5 rounded-lg border border-neutral-300 dark:border-neutral-700 text-xs">
                    Show more ({filtered.length - visible} remaining)
                  </button>
                </div>
              )}
            </div>
          </div>
        )}

        {tab === 'parts' && (
          <div className="flex-1 flex flex-col min-h-0">
            <div className="flex flex-wrap items-center gap-2 px-4 py-2.5 border-b border-notion-borderLight dark:border-notion-borderDark text-xs shrink-0">
              <div className="flex items-center border border-neutral-300 dark:border-neutral-700 rounded px-2 flex-1 min-w-[12rem]">
                <Search size={13} className="text-neutral-400" />
                <input
                  type="text"
                  value={query}
                  maxLength={100}
                  onChange={(e) => setQuery(e.target.value)}
                  placeholder="Filter by part number or description"
                  aria-label="Filter parts"
                  className="w-full px-2 py-1 bg-transparent focus:outline-none"
                />
              </div>
              <select
                value={category}
                onChange={(e) => setCategory(e.target.value)}
                aria-label="Product type"
                className="px-2 py-1 rounded border border-neutral-300 dark:border-neutral-700 bg-white dark:bg-neutral-900"
              >
                <option value="">All product types</option>
                {Object.entries(categories).map(([c, n]) => (
                  <option key={c} value={c}>
                    {c} ({n})
                  </option>
                ))}
              </select>
              <span className="ml-auto text-neutral-500">{parts ? `${parts.parts.length} of ${parts.total} parts` : ''}</span>
            </div>
            <div className="flex-1 overflow-y-auto p-4 space-y-2">
              {partError && <p className="text-xs text-red-700 dark:text-red-300">{partError}</p>}
              {parts && parts.total === 0 && !partsLoading && (
                <p className="text-xs text-neutral-500 text-center p-8">
                  {debounced || category ? 'No part matches these filters.' : 'No parts were extracted from this document.'}
                </p>
              )}
              {parts?.parts.map((p) => {
                const isOpen = expanded === p.id;
                return (
                  <div key={p.id} className="rounded-lg border border-notion-borderLight dark:border-notion-borderDark">
                    <button
                      onClick={() => setExpanded(isOpen ? null : p.id)}
                      aria-expanded={isOpen}
                      className="w-full flex items-center gap-3 p-2.5 text-left hover:bg-neutral-50 dark:hover:bg-neutral-800/40"
                    >
                      {isOpen ? <ChevronDown size={14} className="text-neutral-400 shrink-0" /> : <ChevronRight size={14} className="text-neutral-400 shrink-0" />}
                      {p.images[0] ? (
                        <Thumb src={p.images[0].image_url} alt={p.part_number} className="w-14 h-14 rounded border border-neutral-200 dark:border-neutral-800 shrink-0" />
                      ) : (
                        <div className="w-14 h-14 rounded border border-dashed border-neutral-300 dark:border-neutral-700 flex items-center justify-center text-neutral-300 shrink-0">
                          <ImageIcon size={16} />
                        </div>
                      )}
                      <div className="min-w-0 flex-1">
                        <div className="flex items-center gap-2">
                          <span className="font-mono text-sm font-semibold text-neutral-900 dark:text-white">{p.part_number}</span>
                          <span className="text-[10px] px-1.5 py-0.5 rounded bg-neutral-100 dark:bg-neutral-800 text-neutral-500">{p.category}</span>
                          {p.validation_status !== 'validated' && (
                            <span className="text-[10px] px-1.5 py-0.5 rounded bg-orange-100 dark:bg-orange-950 text-orange-800 dark:text-orange-300">needs review</span>
                          )}
                        </div>
                        <p className="text-xs text-neutral-600 dark:text-neutral-300 truncate" title={p.product_name}>{p.product_name}</p>
                        <p className="text-[11px] text-neutral-500">
                          {[p.thread, p.ball_diameter_mm != null ? `Ø${p.ball_diameter_mm} mm` : null, p.ball_material, p.overall_length_mm != null ? `L ${p.overall_length_mm} mm` : null]
                            .filter(Boolean)
                            .join(' · ') || 'No dimensions stated'}
                          {` · page ${p.source_page}`}
                        </p>
                      </div>
                    </button>
                    {isOpen && (
                      <div className="border-t border-notion-borderLight dark:border-notion-borderDark p-3 grid md:grid-cols-2 gap-4 text-xs">
                        <div className="space-y-3">
                          {p.alt_part_number && <p className="font-mono text-neutral-500">Also listed as: {p.alt_part_number}</p>}
                          {p.description && p.description !== p.product_name && <p className="text-neutral-500">{p.description}</p>}
                          <dl className="grid grid-cols-2 gap-x-3 gap-y-1">
                            {specRows(p).map(([label, value]) => (
                              <React.Fragment key={label}>
                                <dt className="text-neutral-500">{label}</dt>
                                <dd className="font-medium text-neutral-900 dark:text-neutral-100">{value}</dd>
                              </React.Fragment>
                            ))}
                          </dl>
                          <div className="p-2 rounded bg-neutral-50 dark:bg-neutral-800/40 border border-neutral-200/60 dark:border-neutral-800 text-[11px] text-neutral-600 dark:text-neutral-300 space-y-0.5">
                            <div className="font-semibold">Source</div>
                            <div>{p.source_pdf}, page {p.source_page}</div>
                            {p.source_table && <div>Table: {p.source_table}</div>}
                            <div>
                              Extraction: {p.validation_status}
                              {p.extraction_confidence < 1 ? ` (confidence ${(p.extraction_confidence * 100).toFixed(0)}%)` : ''}
                            </div>
                            {p.review_reason && (
                              <div className="flex items-start space-x-1 text-orange-800 dark:text-orange-300">
                                <AlertTriangle size={11} className="shrink-0 mt-0.5" />
                                <span>{p.review_reason}</span>
                              </div>
                            )}
                          </div>
                        </div>
                        <div className="space-y-2">
                          <div className="font-semibold text-neutral-700 dark:text-neutral-200">Images ({p.images.length})</div>
                          {p.images.length === 0 && <p className="text-neutral-500">No image is associated with this part in the document.</p>}
                          <div className="grid grid-cols-2 gap-2">
                            {p.images.map((img) => (
                              <a key={img.image_id} href={img.image_url} target="_blank" rel="noreferrer" className="block rounded border border-neutral-200 dark:border-neutral-800 overflow-hidden">
                                <Thumb src={img.image_url} alt={`${p.part_number}, page ${img.page_number}`} className="w-full h-28" />
                                <div className="p-1.5 text-[10px] text-neutral-500 space-y-0.5">
                                  <div>
                                    Page {img.page_number} · {img.image_type} · {img.association_status}
                                  </div>
                                  {img.association_basis && <div className="truncate" title={img.association_basis}>{img.association_basis}</div>}
                                </div>
                              </a>
                            ))}
                          </div>
                        </div>
                      </div>
                    )}
                  </div>
                );
              })}
              {partsLoading && (
                <p className="text-xs text-neutral-500 flex items-center space-x-1.5">
                  <Loader2 size={13} className="animate-spin" />
                  <span>Loading parts…</span>
                </p>
              )}
              {parts && !partsLoading && parts.parts.length < parts.total && (
                <div className="text-center pt-2">
                  <button onClick={() => loadParts(parts.parts.length)} className="px-3 py-1.5 rounded-lg border border-neutral-300 dark:border-neutral-700 text-xs">
                    Load more ({parts.total - parts.parts.length} remaining)
                  </button>
                </div>
              )}
            </div>
          </div>
        )}
      </div>

      {current && (
        <div
          role="dialog"
          aria-modal="true"
          aria-label={`Image on page ${current.page_number}`}
          className="fixed inset-0 z-[60] bg-black/80 flex items-center justify-center p-4"
          onClick={(e) => {
            e.stopPropagation();
            setOpen(null);
          }}
        >
          <div className="w-full max-w-4xl max-h-[92vh] rounded-xl bg-white dark:bg-neutral-900 flex flex-col md:flex-row overflow-hidden" onClick={(e) => e.stopPropagation()}>
            <div className="relative flex-1 bg-white flex items-center justify-center min-h-[18rem]">
              <img src={current.image_url} alt={current.description || ''} className="max-h-[80vh] max-w-full object-contain" />
              {filtered.length > 1 && (
                <>
                  <button onClick={() => step(-1)} aria-label="Previous image" className="absolute left-2 top-1/2 -translate-y-1/2 p-1.5 rounded-full bg-black/40 text-white">
                    <ChevronLeft size={18} />
                  </button>
                  <button onClick={() => step(1)} aria-label="Next image" className="absolute right-2 top-1/2 -translate-y-1/2 p-1.5 rounded-full bg-black/40 text-white">
                    <ChevronRight size={18} />
                  </button>
                </>
              )}
            </div>
            <div className="w-full md:w-80 p-4 space-y-3 text-xs overflow-y-auto border-t md:border-t-0 md:border-l border-notion-borderLight dark:border-notion-borderDark">
              <div className="flex items-center justify-between">
                <span className="text-neutral-500">
                  {(open ?? 0) + 1} / {filtered.length}
                </span>
                <button onClick={() => setOpen(null)} aria-label="Close image" className="p-1 rounded hover:bg-neutral-100 dark:hover:bg-neutral-800 text-neutral-500">
                  <X size={16} />
                </button>
              </div>
              <dl className="grid grid-cols-[auto,1fr] gap-x-3 gap-y-1">
                <dt className="text-neutral-500">Source</dt>
                <dd className="break-all">{current.source_pdf}</dd>
                <dt className="text-neutral-500">Page</dt>
                <dd>{current.page_number}</dd>
                <dt className="text-neutral-500">Type</dt>
                <dd>{current.image_type}</dd>
              </dl>
              {current.description && <p className="text-neutral-600 dark:text-neutral-300">{current.description}</p>}
              <div className="space-y-1.5">
                <div className="font-semibold text-neutral-700 dark:text-neutral-200 flex items-center space-x-1">
                  <Link2 size={12} />
                  <span>Associated parts ({current.associated_parts.length})</span>
                </div>
                {current.associated_parts.length === 0 && <p className="text-neutral-500">This image is not linked to a part number.</p>}
                {current.associated_parts.map((link) => (
                  <button
                    key={link.product_id}
                    onClick={() => showPart(link.part_number)}
                    className="w-full text-left p-2 rounded border border-neutral-200 dark:border-neutral-800 hover:bg-neutral-50 dark:hover:bg-neutral-800/40"
                  >
                    <div className="flex items-center justify-between">
                      <span className="font-mono font-semibold">{link.part_number}</span>
                      <span className="text-[10px] text-neutral-500">{link.association_status}</span>
                    </div>
                    <div className="text-[11px] text-neutral-500 truncate" title={link.product_name}>{link.product_name}</div>
                    {link.association_basis && <div className="text-[10px] text-neutral-400 mt-0.5">{link.association_basis}</div>}
                  </button>
                ))}
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};
