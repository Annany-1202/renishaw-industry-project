import React, { useCallback, useEffect, useState } from 'react';
import { X, Image as ImageIcon, CheckCircle, AlertTriangle, ZoomIn, FileText, ChevronLeft, ChevronRight, Lock } from 'lucide-react';
import { ProductMatch, MatchStatus } from '../types';

interface SidePeekProps {
  product: ProductMatch | null;
  onClose: () => void;
}

const STATUS_STYLE: Record<MatchStatus, string> = {
  MATCH: 'bg-emerald-100 dark:bg-emerald-950 text-emerald-800 dark:text-emerald-300',
  DIFFERS: 'bg-amber-100 dark:bg-amber-950 text-amber-800 dark:text-amber-300',
  UNKNOWN: 'bg-neutral-200 dark:bg-neutral-800 text-neutral-700 dark:text-neutral-300',
  NOT_APPLICABLE: 'bg-neutral-100 dark:bg-neutral-800 text-neutral-500'
};
const STATUS_LABEL: Record<MatchStatus, string> = {
  MATCH: 'Match', DIFFERS: 'Differs', UNKNOWN: 'Not stated', NOT_APPLICABLE: 'n/a'
};

const show = (v: unknown, unit?: string | null) =>
  v === null || v === undefined || v === '' ? '—' : `${v}${unit ? ` ${unit}` : ''}`;

export const SidePeek: React.FC<SidePeekProps> = ({ product, onClose }) => {
  const [index, setIndex] = useState(0);
  const [lightbox, setLightbox] = useState(false);
  const [failed, setFailed] = useState<Record<string, boolean>>({});

  // A new product always starts at its first image.
  useEffect(() => {
    setIndex(0);
    setLightbox(false);
    setFailed({});
  }, [product?.id]);

  const count = product?.images.length ?? 0;
  const step = useCallback((delta: number) => {
    if (count > 1) setIndex((i) => (i + delta + count) % count);
  }, [count]);

  useEffect(() => {
    if (!product) return;
    const onKey = (e: KeyboardEvent) => {
      const target = e.target as HTMLElement | null;
      if (target && ['INPUT', 'TEXTAREA', 'SELECT'].includes(target.tagName)) return;
      if (e.key === 'Escape') {
        if (lightbox) setLightbox(false);
        else onClose();
      } else if (e.key === 'ArrowRight') step(1);
      else if (e.key === 'ArrowLeft') step(-1);
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [product, lightbox, onClose, step]);

  if (!product) return null;

  const exact = product.match_class === 'EXACT_MATCH';
  const image = product.images[Math.min(index, count - 1)];
  const specs: [string, string][] = [
    ['Product type', `${product.category}${product.stylus_type && product.stylus_type !== product.category ? ` (${product.stylus_type.replace('_', ' ')})` : ''}`],
    ['Thread', show(product.thread)],
    ['Ball / tip material', show(product.ball_material)],
    ['Ball / tip diameter', show(product.ball_diameter_mm, 'mm')],
    ['Stem / body material', show(product.stem_material)],
    ['Stem diameter', show(product.stem_diameter_mm, 'mm')],
    ['Overall length', show(product.overall_length_mm, 'mm')],
    ['Effective working length', show(product.effective_working_length_mm, 'mm')],
    ['Mass', show(product.weight_g, 'g')],
    ['Manufacturer', show(product.manufacturer)]
  ];

  return (
    <>
      <aside
        role="dialog"
        aria-label={`Details of ${product.part_number}`}
        className="fixed inset-y-0 right-0 z-40 w-full max-w-xl bg-white dark:bg-neutral-900 border-l border-notion-borderLight dark:border-notion-borderDark shadow-2xl flex flex-col overflow-hidden"
      >
        <div className="flex items-center justify-between p-4 border-b border-notion-borderLight dark:border-notion-borderDark shrink-0">
          {exact ? (
            <span className="inline-flex items-center space-x-1 px-2.5 py-1 rounded-full text-xs font-semibold bg-emerald-100 dark:bg-emerald-950/60 text-emerald-800 dark:text-emerald-300">
              <CheckCircle size={13} />
              <span>Exact catalogue match</span>
            </span>
          ) : (
            <span className="inline-flex items-center space-x-1 px-2.5 py-1 rounded-full text-xs font-semibold bg-amber-100 dark:bg-amber-950/60 text-amber-800 dark:text-amber-300">
              <AlertTriangle size={13} />
              <span>Ranked alternative · score {product.score.toFixed(0)}/100</span>
            </span>
          )}
          <button onClick={onClose} aria-label="Close details" className="p-1 rounded hover:bg-neutral-100 dark:hover:bg-neutral-800 text-neutral-500">
            <X size={18} />
          </button>
        </div>

        <div className="flex-1 overflow-y-auto p-6 space-y-6">
          <div>
            <h2 className="text-2xl font-bold tracking-tight text-neutral-900 dark:text-white font-mono">{product.part_number}</h2>
            {product.alt_part_number && (
              <p className="text-xs font-mono text-notion-mutedLight dark:text-notion-mutedDark mt-0.5">Also listed as: {product.alt_part_number}</p>
            )}
            <p className="text-sm text-neutral-700 dark:text-neutral-300 mt-2">{product.product_name}</p>
            {product.description && product.description !== product.product_name && (
              <p className="text-xs text-neutral-500 mt-1">{product.description}</p>
            )}
          </div>

          <div className={`p-3.5 rounded-lg border text-xs leading-relaxed ${
            exact
              ? 'bg-emerald-50/60 dark:bg-emerald-950/20 border-emerald-200 dark:border-emerald-800/60 text-emerald-900 dark:text-emerald-200'
              : 'bg-amber-50/60 dark:bg-amber-950/20 border-amber-200 dark:border-amber-800/60 text-amber-900 dark:text-amber-200'
          }`}>
            <div className="font-semibold mb-1">Why this result</div>
            {product.explanation}
          </div>

          {product.validation_status !== 'validated' && (
            <div className="p-3 rounded-lg border border-orange-200 dark:border-orange-900 bg-orange-50 dark:bg-orange-950/30 text-xs text-orange-900 dark:text-orange-200">
              <span className="font-semibold">This catalogue record is flagged for review.</span> {product.review_reason}
            </div>
          )}

          {/* Images */}
          <div className="space-y-3">
            <h3 className="text-xs font-semibold uppercase tracking-wider text-notion-mutedLight dark:text-notion-mutedDark flex items-center space-x-1.5">
              <ImageIcon size={14} />
              <span>Verified images ({count})</span>
            </h3>

            {image ? (
              <div className="space-y-2">
                <div className="relative rounded-lg border border-notion-borderLight dark:border-notion-borderDark bg-white p-2 flex items-center justify-center min-h-[200px]">
                  {failed[image.image_id] ? (
                    <p className="text-xs text-neutral-500">The image file could not be loaded.</p>
                  ) : (
                    <button onClick={() => setLightbox(true)} aria-label="Enlarge image" className="group">
                      <img
                        src={image.image_url}
                        alt={`${product.part_number}: ${image.image_type} from ${image.source_pdf}, page ${image.page_number}`}
                        onError={() => setFailed((f) => ({ ...f, [image.image_id]: true }))}
                        className="max-h-56 max-w-full object-contain"
                      />
                      <span className="absolute bottom-2 right-2 p-1.5 rounded-md bg-neutral-900/70 text-white opacity-0 group-hover:opacity-100 group-focus:opacity-100 transition-opacity">
                        <ZoomIn size={14} />
                      </span>
                    </button>
                  )}
                  {image.label && (
                    <span className="absolute top-2 left-2 px-1.5 py-0.5 rounded bg-amber-500 text-white text-[10px] font-bold uppercase">
                      {image.label}
                    </span>
                  )}
                  {count > 1 && (
                    <>
                      <button onClick={() => step(-1)} aria-label="Previous image" className="absolute left-1 top-1/2 -translate-y-1/2 p-1 rounded-full bg-neutral-900/60 text-white hover:bg-neutral-900">
                        <ChevronLeft size={16} />
                      </button>
                      <button onClick={() => step(1)} aria-label="Next image" className="absolute right-1 top-1/2 -translate-y-1/2 p-1 rounded-full bg-neutral-900/60 text-white hover:bg-neutral-900">
                        <ChevronRight size={16} />
                      </button>
                    </>
                  )}
                </div>

                <div className="text-[11px] text-notion-mutedLight dark:text-notion-mutedDark bg-neutral-50 dark:bg-neutral-800/40 p-2 rounded border border-neutral-200/60 dark:border-neutral-800 space-y-0.5">
                  <div className="flex items-center justify-between gap-2">
                    <span className="truncate">
                      {count > 1 ? `${index + 1} of ${count} · ` : ''}
                      <strong className="text-neutral-800 dark:text-neutral-200">{image.source_pdf}</strong>, page {image.page_number}
                    </span>
                    <span className="font-mono text-[10px] uppercase px-1 rounded bg-neutral-200 dark:bg-neutral-700 shrink-0">{image.image_type}</span>
                  </div>
                  {image.association_basis && <div>Linked to this part by: {image.association_basis}</div>}
                </div>

                {count > 1 && (
                  <div className="flex space-x-2 overflow-x-auto pb-1" role="tablist" aria-label="Product images">
                    {product.images.map((img, idx) => (
                      <button
                        key={img.image_id}
                        role="tab"
                        aria-selected={idx === index}
                        aria-label={`Image ${idx + 1}: ${img.source_pdf}, page ${img.page_number}`}
                        onClick={() => setIndex(idx)}
                        className={`h-16 w-16 shrink-0 rounded border p-1 bg-white flex items-center justify-center ${
                          idx === index ? 'border-neutral-900 dark:border-white ring-2 ring-neutral-400' : 'border-neutral-200 dark:border-neutral-700 opacity-60 hover:opacity-100'
                        }`}
                      >
                        <img src={img.image_url} alt="" className="max-h-full max-w-full object-contain" />
                      </button>
                    ))}
                  </div>
                )}
                {count > 1 && <p className="text-[10px] text-neutral-400">Use the ← → keys to move between images.</p>}
              </div>
            ) : (
              <div className="p-6 text-center rounded-lg border border-dashed border-neutral-300 dark:border-neutral-700 bg-neutral-50 dark:bg-neutral-900/50">
                <ImageIcon size={24} className="mx-auto text-neutral-400 mb-2 opacity-50" />
                <p className="text-xs font-medium text-neutral-700 dark:text-neutral-300">No associated image available</p>
                <p className="text-[11px] text-neutral-400 mt-1">{product.image_note}</p>
              </div>
            )}
          </div>

          {/* Requested vs catalogue */}
          {product.attribute_comparisons.length > 0 && (
            <div className="space-y-2">
              <h3 className="text-xs font-semibold uppercase tracking-wider text-notion-mutedLight dark:text-notion-mutedDark">
                Requested vs catalogue
              </h3>
              <div className="overflow-x-auto rounded-lg border border-neutral-200 dark:border-neutral-800">
                <table className="w-full text-xs">
                  <thead className="bg-neutral-50 dark:bg-neutral-800/50 text-left text-[10px] uppercase text-notion-mutedLight dark:text-notion-mutedDark">
                    <tr>
                      <th className="px-2.5 py-1.5 font-semibold">Attribute</th>
                      <th className="px-2.5 py-1.5 font-semibold">Requested</th>
                      <th className="px-2.5 py-1.5 font-semibold">Catalogue</th>
                      <th className="px-2.5 py-1.5 font-semibold">Result</th>
                    </tr>
                  </thead>
                  <tbody>
                    {product.attribute_comparisons.map((row) => (
                      <tr key={row.attribute_name} className="border-t border-neutral-100 dark:border-neutral-800 align-top">
                        <td className="px-2.5 py-1.5">
                          <span className="inline-flex items-center space-x-1">
                            <span>{row.label || row.attribute_name}</span>
                            {row.is_hard && (
                              <span title="Mandatory requirement" className="inline-flex items-center text-neutral-500">
                                <Lock size={10} />
                                <span className="sr-only">mandatory</span>
                              </span>
                            )}
                          </span>
                        </td>
                        <td className="px-2.5 py-1.5">{show(row.requested_value, row.unit)}</td>
                        <td className="px-2.5 py-1.5">
                          {show(row.product_value, row.unit)}
                          {row.note && <div className="text-[10px] text-neutral-500 mt-0.5">{row.note}</div>}
                        </td>
                        <td className="px-2.5 py-1.5">
                          <span className={`px-1.5 py-0.5 rounded text-[10px] font-semibold ${STATUS_STYLE[row.status]}`}>{STATUS_LABEL[row.status]}</span>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              <p className="text-[10px] text-neutral-400 flex items-center space-x-1">
                <Lock size={9} />
                <span>mandatory requirement · the score is an internal ranking value, not a suitability rating</span>
              </p>
            </div>
          )}

          <div className="space-y-2">
            <h3 className="text-xs font-semibold uppercase tracking-wider text-notion-mutedLight dark:text-notion-mutedDark">Catalogue specifications</h3>
            <dl className="grid grid-cols-2 gap-2 text-xs">
              {specs.map(([label, value]) => (
                <div key={label} className="p-2.5 rounded bg-neutral-50 dark:bg-neutral-800/40 border border-neutral-200/60 dark:border-neutral-800">
                  <dt className="text-notion-mutedLight dark:text-notion-mutedDark">{label}</dt>
                  <dd className="font-semibold text-neutral-800 dark:text-neutral-100 mt-0.5">{value}</dd>
                </div>
              ))}
            </dl>
          </div>

          <div className="space-y-2">
            <h3 className="text-xs font-semibold uppercase tracking-wider text-notion-mutedLight dark:text-notion-mutedDark flex items-center space-x-1.5">
              <FileText size={14} />
              <span>Sources ({product.sources.length})</span>
            </h3>
            <ul className="space-y-1.5 text-xs">
              {product.sources.map((s) => (
                <li key={s.record_id} className="p-2.5 rounded border border-neutral-200/60 dark:border-neutral-800 bg-neutral-50 dark:bg-neutral-800/40">
                  <div className="font-medium text-neutral-800 dark:text-neutral-100 break-all">{s.source_pdf}</div>
                  <div className="text-notion-mutedLight dark:text-notion-mutedDark mt-0.5">
                    Page {s.source_page}
                    {s.source_table ? ` · ${s.source_table}` : ''}
                    {s.validation_status !== 'validated' ? ' · flagged for review' : ''}
                    {s.record_id === product.id && product.sources.length > 1 ? ' · values shown are from this source' : ''}
                  </div>
                </li>
              ))}
            </ul>
          </div>
        </div>
      </aside>

      {lightbox && image && (
        <div
          role="dialog"
          aria-label="Enlarged image"
          className="fixed inset-0 z-50 bg-black/85 flex flex-col items-center justify-center p-6"
          onClick={() => setLightbox(false)}
        >
          <button aria-label="Close enlarged image" className="absolute top-4 right-4 p-2 rounded-full bg-white/10 text-white hover:bg-white/20">
            <X size={20} />
          </button>
          <img
            src={image.image_url}
            alt={`${product.part_number}: ${image.image_type}`}
            className="max-h-[80vh] max-w-[90vw] object-contain bg-white rounded p-3"
            onClick={(e) => e.stopPropagation()}
          />
          <p className="mt-3 text-xs text-white/90 text-center">
            {product.part_number}
            {image.label ? ` (${image.label})` : ''} · {image.source_pdf}, page {image.page_number} · {image.image_type}
            {count > 1 ? ` · ${index + 1} of ${count}` : ''}
          </p>
          {count > 1 && (
            <div className="mt-2 flex space-x-3" onClick={(e) => e.stopPropagation()}>
              <button onClick={() => step(-1)} aria-label="Previous image" className="p-2 rounded-full bg-white/10 text-white hover:bg-white/20">
                <ChevronLeft size={18} />
              </button>
              <button onClick={() => step(1)} aria-label="Next image" className="p-2 rounded-full bg-white/10 text-white hover:bg-white/20">
                <ChevronRight size={18} />
              </button>
            </div>
          )}
        </div>
      )}
    </>
  );
};
