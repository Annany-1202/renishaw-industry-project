import React, { useEffect, useState } from 'react';
import {
  Search,
  CheckCircle,
  AlertTriangle,
  HelpCircle,
  Image as ImageIcon,
  Layers,
  Lock,
  Unlock,
  X,
  Ban,
  SearchX,
  ShieldQuestion,
  Info,
  Filter
} from 'lucide-react';
import { SearchResponse, ProductMatch, ParsedQuery, HealthStatus } from '../types';

interface SearchPageProps {
  onSearch: (q: string, clarificationAnswer?: string, prevQuery?: ParsedQuery, overrides?: Record<string, unknown>) => void;
  searchResponse: SearchResponse | null;
  loading: boolean;
  error: string | null;
  health: HealthStatus | null;
  onSelectProduct: (p: ProductMatch) => void;
  selectedCompare: ProductMatch[];
  setSelectedCompare: React.Dispatch<React.SetStateAction<ProductMatch[]>>;
  onOpenCompare: () => void;
  queryInput: string;
  setQueryInput: (q: string) => void;
}

const PRESET_QUERIES = [
  'M2 stylus with 2 mm ruby ball, 20 mm long',
  'M5 stylus with 0.08 inch ruby ball',
  'M3 extension 50 mm long',
  'Stylus for TP20 with 3 mm ruby ball',
  'M2 stylus 2.2 mm ruby ball 20 mm long',
  'M3 to M2 adaptor',
  'Stylus for my probe'
];

const MAX_COMPARE = 5;

// Attributes shown as editable chips: field -> [label, unit]
const CHIP_FIELDS: Record<string, [string, string]> = {
  category: ['Product type', ''],
  stylus_type: ['Type', ''],
  thread: ['Thread', ''],
  secondary_thread: ['Second thread', ''],
  ball_material: ['Ball material', ''],
  ball_diameter_mm: ['Ball diameter', 'mm'],
  stem_material: ['Stem material', ''],
  stem_diameter_mm: ['Stem diameter', 'mm'],
  overall_length_mm: ['Overall length', 'mm'],
  effective_working_length_mm: ['Working length', 'mm']
};

const fmt = (v: number | null | undefined, unit = 'mm') => (v === null || v === undefined ? '—' : `${v} ${unit}`);

export const SearchPage: React.FC<SearchPageProps> = ({
  onSearch,
  searchResponse,
  loading,
  error,
  health,
  onSelectProduct,
  selectedCompare,
  setSelectedCompare,
  onOpenCompare,
  queryInput,
  setQueryInput
}) => {
  const [clarificationInput, setClarificationInput] = useState<string>('');
  const [editing, setEditing] = useState<{ field: string; value: string } | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  useEffect(() => {
    setEditing(null);
    setClarificationInput('');
    setNotice(null);
  }, [searchResponse?.search_id]);

  const parsed = searchResponse?.interpreted_query;
  // Refinements always belong to the request that produced the current response.
  const baseQuery = parsed?.original_query || queryInput;

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (queryInput.trim() && !loading) onSearch(queryInput.trim());
  };

  const submitClarification = (answer: string) => {
    if (parsed && answer.trim() && !loading) onSearch(baseQuery, answer.trim(), parsed);
  };

  const applyOverride = (overrides: Record<string, unknown>) => {
    if (parsed && !loading) onSearch(baseQuery, undefined, parsed, overrides);
  };

  const toggleHard = (field: string) => {
    if (!parsed) return;
    const hard = parsed.hard_constraints.includes(field)
      ? parsed.hard_constraints.filter((h) => h !== field)
      : [...parsed.hard_constraints, field];
    applyOverride({ hard_constraints: hard, flexible_preferences: parsed.flexible_preferences.filter((f) => f !== field) });
  };

  const commitEdit = () => {
    if (!editing) return;
    const value = editing.value.trim();
    setEditing(null);
    if (parsed && String(parsed[editing.field] ?? '') !== value) applyOverride({ [editing.field]: value || null });
  };

  const toggleCompare = (prod: ProductMatch) => {
    setNotice(null);
    if (selectedCompare.some((p) => p.id === prod.id)) {
      setSelectedCompare(selectedCompare.filter((p) => p.id !== prod.id));
    } else if (selectedCompare.length >= MAX_COMPARE) {
      setNotice(`At most ${MAX_COMPARE} products can be compared at once.`);
    } else {
      setSelectedCompare([...selectedCompare, prod]);
    }
  };

  const renderProductCard = (product: ProductMatch) => {
    const isSelected = selectedCompare.some((p) => p.id === product.id);
    const hasImage = product.images.length > 0;
    const exact = product.match_class === 'EXACT_MATCH';

    return (
      <div
        key={product.id}
        className={`rounded-xl border p-4 bg-white dark:bg-neutral-900 transition-all hover:shadow-md ${
          exact
            ? 'border-emerald-200 dark:border-emerald-800/60 hover:border-emerald-400'
            : 'border-neutral-200 dark:border-neutral-800 hover:border-neutral-400'
        }`}
      >
        <div className="flex items-start justify-between gap-4">
          <div className="flex-1 min-w-0">
            <div className="flex flex-wrap items-center gap-2">
              <span className="font-mono font-bold text-base text-neutral-900 dark:text-neutral-100">{product.part_number}</span>
              {exact ? (
                <span className="inline-flex items-center space-x-1 px-2 py-0.5 rounded-full text-[11px] font-semibold bg-emerald-100 dark:bg-emerald-950 text-emerald-800 dark:text-emerald-300">
                  <CheckCircle size={11} />
                  <span>Exact catalogue match</span>
                </span>
              ) : (
                <span
                  className="inline-flex items-center space-x-1 px-2 py-0.5 rounded-full text-[11px] font-semibold bg-amber-100 dark:bg-amber-950 text-amber-800 dark:text-amber-300"
                  title="Internal ranking score, not a probability or a suitability rating"
                >
                  <AlertTriangle size={11} />
                  <span>Ranked alternative · score {product.score.toFixed(0)}/100</span>
                </span>
              )}
              {product.validation_status !== 'validated' && (
                <span
                  className="px-2 py-0.5 rounded-full text-[11px] font-semibold bg-orange-100 dark:bg-orange-950 text-orange-800 dark:text-orange-300"
                  title={product.review_reason || 'This catalogue record is flagged for review'}
                >
                  Record needs review
                </span>
              )}
            </div>

            <p className="text-xs text-neutral-600 dark:text-neutral-400 mt-1 line-clamp-1">
              {product.product_name}
              <span className="text-neutral-400"> · {product.category}{product.stylus_type && product.stylus_type !== product.category ? ` (${product.stylus_type.replace('_', ' ')})` : ''}</span>
            </p>

            <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 mt-3 pt-3 border-t border-neutral-100 dark:border-neutral-800/60 text-xs">
              <div>
                <span className="text-[10px] text-notion-mutedLight dark:text-notion-mutedDark block">Thread</span>
                <span className="font-semibold text-neutral-800 dark:text-neutral-200">{product.thread || '—'}</span>
              </div>
              <div>
                <span className="text-[10px] text-notion-mutedLight dark:text-notion-mutedDark block">Ball diameter</span>
                <span className="font-semibold text-neutral-800 dark:text-neutral-200">{fmt(product.ball_diameter_mm)}</span>
              </div>
              <div>
                <span className="text-[10px] text-notion-mutedLight dark:text-notion-mutedDark block">Length</span>
                <span className="font-semibold text-neutral-800 dark:text-neutral-200">{fmt(product.overall_length_mm)}</span>
              </div>
              <div>
                <span className="text-[10px] text-notion-mutedLight dark:text-notion-mutedDark block">Ball / stem material</span>
                <span className="font-semibold text-neutral-800 dark:text-neutral-200 truncate block">
                  {[product.ball_material, product.stem_material].filter(Boolean).join(' / ') || '—'}
                </span>
              </div>
            </div>

            {!exact && product.differing_attributes.concat(product.missing_attributes).length > 0 && (
              <ul className="mt-2 text-[11px] text-amber-800 dark:text-amber-300 list-disc pl-4 space-y-0.5">
                {product.differing_attributes.concat(product.missing_attributes).map((d, i) => (
                  <li key={i}>{d}</li>
                ))}
              </ul>
            )}

            <div className="mt-3 text-[11px] text-neutral-500 dark:text-neutral-400 flex items-center justify-between gap-3">
              <span className="truncate" title={product.sources.map((s) => `${s.source_pdf}, p. ${s.source_page}`).join('\n')}>
                Source: {product.source_pdf}, p. {product.source_page}
                {product.sources.length > 1 ? ` (+${product.sources.length - 1} more source${product.sources.length > 2 ? 's' : ''})` : ''}
              </span>
              <span className={`inline-flex items-center space-x-1 shrink-0 ${hasImage ? 'text-emerald-600 dark:text-emerald-400 font-medium' : ''}`}>
                <ImageIcon size={12} />
                <span>{hasImage ? `${product.images.length} verified image${product.images.length === 1 ? '' : 's'}` : 'No associated image'}</span>
              </span>
            </div>
          </div>

          <div className="flex flex-col items-end space-y-2 shrink-0">
            {hasImage ? (
              <button
                type="button"
                className="relative w-16 h-16 rounded-lg border border-neutral-200 dark:border-neutral-800 bg-white p-1 flex items-center justify-center hover:border-neutral-400"
                onClick={() => onSelectProduct(product)}
                aria-label={`Open details and images of ${product.part_number}`}
              >
                <img src={product.images[0].image_url} alt={`${product.part_number} catalogue illustration`} className="max-h-full max-w-full object-contain" />
                {product.images[0].label && (
                  <span className="absolute -top-1.5 -right-1.5 px-1 rounded bg-amber-500 text-white text-[8px] font-bold">ALT</span>
                )}
              </button>
            ) : (
              <div
                className="w-16 h-16 rounded-lg border border-dashed border-neutral-200 dark:border-neutral-800 flex items-center justify-center text-neutral-300 dark:text-neutral-700"
                title={product.image_note || 'No associated image available'}
              >
                <ImageIcon size={18} />
              </div>
            )}

            <div className="flex items-center space-x-2 pt-1">
              <label className="flex items-center space-x-1 text-[11px] text-notion-mutedLight dark:text-notion-mutedDark cursor-pointer select-none">
                <input type="checkbox" checked={isSelected} onChange={() => toggleCompare(product)} className="rounded focus:ring-0" />
                <span>Compare</span>
              </label>
              <button
                onClick={() => onSelectProduct(product)}
                className="px-2 py-1 rounded text-xs bg-neutral-100 dark:bg-neutral-800 hover:bg-neutral-200 dark:hover:bg-neutral-700 font-medium text-neutral-800 dark:text-neutral-200 transition-colors"
              >
                Details
              </button>
            </div>
          </div>
        </div>
      </div>
    );
  };

  const chips = parsed
    ? Object.keys(CHIP_FIELDS).filter((f) => parsed[f] !== null && parsed[f] !== undefined && parsed[f] !== '')
    : [];
  const outcome = searchResponse?.outcome;
  const asksUser = outcome === 'clarification' || outcome === 'conflict';
  const history = (parsed?.clarification_history as string[] | undefined) || [];
  const answeredSteps = history.filter((h) => !h.startsWith('NARROW:')).length;
  const followUp = searchResponse?.follow_up;

  const renderFollowUp = () =>
    followUp && (
      <div className="p-3 rounded-xl border border-neutral-200 dark:border-neutral-800 bg-neutral-50 dark:bg-neutral-900/40 space-y-2">
        <div className="flex items-start space-x-2">
          <Filter size={14} className="text-neutral-500 shrink-0 mt-0.5" />
          <p className="text-xs text-neutral-700 dark:text-neutral-300">
            <span className="font-semibold">Narrow down: </span>
            {followUp.question}
          </p>
        </div>
        <div className="flex flex-wrap gap-1.5">
          {followUp.options.map((opt, i) => (
            <button
              key={opt}
              disabled={loading}
              onClick={() => submitClarification(opt)}
              className="inline-flex items-center space-x-1.5 px-2.5 py-1 rounded-lg text-xs bg-white dark:bg-neutral-800 border border-neutral-300 dark:border-neutral-700 hover:bg-neutral-100 dark:hover:bg-neutral-700 disabled:opacity-50 transition-colors"
            >
              <span>{opt}</span>
              {followUp.option_counts[i] !== undefined && <span className="text-[10px] text-neutral-500">{followUp.option_counts[i]}</span>}
            </button>
          ))}
        </div>
      </div>
    );

  return (
    <div className="max-w-4xl mx-auto px-6 py-8 space-y-8">
      <div className="space-y-3">
        <form onSubmit={handleSubmit}>
          <div className="flex items-center border border-notion-borderLight dark:border-notion-borderDark rounded-xl bg-white dark:bg-neutral-900 focus-within:ring-2 focus-within:ring-neutral-400 dark:focus-within:ring-neutral-600 transition-all">
            <Search size={18} className="ml-4 text-notion-mutedLight dark:text-notion-mutedDark shrink-0" />
            <input
              type="text"
              value={queryInput}
              maxLength={1000}
              onChange={(e) => setQueryInput(e.target.value)}
              placeholder="Describe the component, e.g. M2 stylus with 2 mm ruby ball, 20 mm long"
              aria-label="Product description"
              className="w-full py-3.5 px-3 bg-transparent text-sm text-neutral-900 dark:text-white placeholder:text-neutral-400 focus:outline-none"
            />
            <button
              type="submit"
              disabled={loading || !queryInput.trim()}
              className="mr-2 px-4 py-1.5 rounded-lg bg-neutral-900 dark:bg-neutral-100 text-white dark:text-neutral-900 text-xs font-semibold hover:bg-neutral-800 dark:hover:bg-neutral-200 disabled:opacity-40 transition-colors shrink-0"
            >
              {loading ? 'Searching…' : 'Search'}
            </button>
          </div>
        </form>

        <div className="flex flex-wrap items-center gap-1.5 text-xs">
          <span className="text-notion-mutedLight dark:text-notion-mutedDark font-medium mr-1">Examples:</span>
          {PRESET_QUERIES.map((preset) => (
            <button
              key={preset}
              disabled={loading}
              onClick={() => {
                setQueryInput(preset);
                onSearch(preset);
              }}
              className="px-2.5 py-1 rounded-full border border-notion-borderLight dark:border-notion-borderDark hover:bg-notion-hoverLight dark:hover:bg-notion-hoverDark text-[11px] transition-colors disabled:opacity-50"
            >
              {preset}
            </button>
          ))}
        </div>

        {health && health.database.connected && (health.database.ready_document_count ?? 0) === 0 && (
          <div className="flex items-start space-x-2 p-3 rounded-lg border border-amber-200 dark:border-amber-900 bg-amber-50 dark:bg-amber-950/30 text-xs text-amber-900 dark:text-amber-200">
            <Info size={14} className="shrink-0 mt-0.5" />
            <span>No catalogue is ready yet. Documents may still be processing; see the Documents page.</span>
          </div>
        )}
      </div>

      {selectedCompare.length > 0 && (
        <div className="fixed bottom-6 left-1/2 -translate-x-1/2 z-30 bg-neutral-900 dark:bg-white text-white dark:text-neutral-900 px-4 py-2.5 rounded-full shadow-xl flex items-center space-x-3 text-xs font-medium">
          <Layers size={14} />
          <span>{selectedCompare.length} selected</span>
          <button
            onClick={onOpenCompare}
            disabled={selectedCompare.length < 2}
            className="px-3 py-1 rounded-full bg-emerald-500 hover:bg-emerald-600 text-white font-semibold transition-colors disabled:opacity-50"
          >
            Compare
          </button>
          <button onClick={() => setSelectedCompare([])} className="opacity-70 hover:opacity-100">
            Clear
          </button>
        </div>
      )}

      {notice && (
        <div role="status" className="p-2.5 rounded-lg border border-neutral-200 dark:border-neutral-700 bg-neutral-50 dark:bg-neutral-900 text-xs">
          {notice}
        </div>
      )}

      {error && !loading && (
        <div role="alert" className="flex items-start space-x-2 p-3.5 rounded-xl border border-red-200 dark:border-red-900 bg-red-50 dark:bg-red-950/30 text-xs text-red-800 dark:text-red-200">
          <AlertTriangle size={15} className="shrink-0 mt-0.5" />
          <div>
            <p className="font-semibold">The search did not complete</p>
            <p className="mt-0.5">{error}</p>
          </div>
        </div>
      )}

      {loading && (
        <div className="space-y-4 animate-pulse" aria-busy="true" aria-label="Searching">
          <div className="h-4 bg-neutral-200 dark:bg-neutral-800 rounded w-1/4" />
          <div className="h-28 bg-neutral-100 dark:bg-neutral-800/60 rounded-xl" />
          <div className="h-28 bg-neutral-100 dark:bg-neutral-800/60 rounded-xl" />
        </div>
      )}

      {!loading && !error && searchResponse && parsed && (
        <div className="space-y-6">
          {/* What the system understood (editable) */}
          {outcome !== 'irrelevant' && (
            <div className="p-3.5 rounded-xl border border-notion-borderLight dark:border-notion-borderDark bg-neutral-50/70 dark:bg-neutral-900/40 space-y-2">
              <div className="flex items-center justify-between text-xs text-notion-mutedLight dark:text-notion-mutedDark">
                <span className="font-semibold uppercase tracking-wider text-[10px]">How your request was read</span>
                <span className="text-[11px]">
                  {parsed.llm_used ? 'rules + local language model' : parsed.interpreter === 'manual' ? 'edited manually' : 'rules'} ·{' '}
                  {Math.round(searchResponse.execution_time_ms)} ms
                </span>
              </div>
              <p className="text-[11px] text-neutral-500 dark:text-neutral-400 italic truncate" title={parsed.original_query}>
                “{parsed.original_query}”
              </p>
              {chips.length === 0 && <p className="text-xs text-neutral-500">No attributes were recognised.</p>}
              <div className="flex flex-wrap gap-1.5 pt-1">
                {chips.map((field) => {
                  const [label, unit] = CHIP_FIELDS[field];
                  const hard = parsed.hard_constraints.includes(field);
                  const attr = parsed.requested_attributes.find((a) => a.name === field);
                  const isEditing = editing?.field === field;
                  return (
                    <span
                      key={field}
                      className={`inline-flex items-center rounded-md text-xs font-medium border overflow-hidden ${
                        hard
                          ? 'bg-neutral-900 text-white dark:bg-white dark:text-neutral-900 border-transparent'
                          : 'bg-white dark:bg-neutral-800 border-neutral-300 dark:border-neutral-700'
                      }`}
                    >
                      {isEditing ? (
                        <input
                          autoFocus
                          value={editing.value}
                          onChange={(e) => setEditing({ field, value: e.target.value })}
                          onBlur={commitEdit}
                          onKeyDown={(e) => {
                            if (e.key === 'Enter') commitEdit();
                            if (e.key === 'Escape') setEditing(null);
                          }}
                          aria-label={`Edit ${label}`}
                          className="w-28 px-2 py-1 bg-white text-neutral-900 focus:outline-none"
                        />
                      ) : (
                        <button
                          className="px-2.5 py-1 hover:underline"
                          title={[attr?.original_text ? `You typed: ${attr.original_text}` : '', attr?.note || '', 'Click to edit'].filter(Boolean).join(' · ')}
                          onClick={() => setEditing({ field, value: String(parsed[field]) })}
                        >
                          {label}: {String(parsed[field])}{unit ? ` ${unit}` : ''}
                        </button>
                      )}
                      <button
                        onClick={() => toggleHard(field)}
                        className="px-1.5 py-1 border-l border-current/20 opacity-80 hover:opacity-100 inline-flex items-center space-x-1"
                        title={hard ? 'Mandatory: never relaxed. Click to make it flexible.' : 'Flexible: used for ranking. Click to make it mandatory.'}
                        aria-label={`${label} is ${hard ? 'mandatory' : 'flexible'}; toggle`}
                      >
                        {hard ? <Lock size={11} /> : <Unlock size={11} />}
                        <span className="text-[10px]">{hard ? 'must' : 'flexible'}</span>
                      </button>
                      <button
                        onClick={() => applyOverride({ [field]: null })}
                        className="px-1.5 py-1 border-l border-current/20 opacity-70 hover:opacity-100"
                        title={`Remove ${label}`}
                        aria-label={`Remove ${label}`}
                      >
                        <X size={11} />
                      </button>
                    </span>
                  );
                })}
              </div>
              {parsed.assumptions.length > 0 && (
                <ul className="pt-1 text-[11px] text-neutral-500 dark:text-neutral-400 list-disc pl-4 space-y-0.5">
                  {parsed.assumptions.map((a, i) => (
                    <li key={i}>{a}</li>
                  ))}
                </ul>
              )}
              {parsed.unparsed_terms.length > 0 && (
                <p className="text-[11px] text-neutral-500 dark:text-neutral-400">
                  Not used: {parsed.unparsed_terms.join(', ')}
                </p>
              )}
            </div>
          )}

          {/* Clarification / conflict */}
          {asksUser && searchResponse.clarification && (
            <div className="p-4 rounded-xl border border-blue-200 dark:border-blue-900/60 bg-blue-50/60 dark:bg-blue-950/20 space-y-3">
              <div className="flex items-start space-x-2.5">
                <HelpCircle size={18} className="text-blue-600 dark:text-blue-400 shrink-0 mt-0.5" />
                <div className="space-y-1">
                  <h4 className="text-sm font-semibold text-blue-950 dark:text-blue-200">
                    {outcome === 'conflict' ? 'Your request contains conflicting requirements' : 'One detail is needed'}
                    {outcome !== 'conflict' && answeredSteps > 0 && (
                      <span className="ml-2 text-[11px] font-normal text-blue-700 dark:text-blue-300">question {answeredSteps + 1}</span>
                    )}
                  </h4>
                  <p className="text-xs text-blue-800 dark:text-blue-300 leading-relaxed">{searchResponse.clarification.question}</p>
                </div>
              </div>
              {(searchResponse.clarification.options || []).length > 0 && (
                <div className="flex flex-wrap gap-1.5">
                  {searchResponse.clarification.options!.map((opt) => (
                    <button
                      key={opt}
                      onClick={() => submitClarification(opt)}
                      className="px-2.5 py-1 rounded-lg text-xs font-medium bg-white dark:bg-neutral-800 border border-blue-300 dark:border-blue-800 hover:bg-blue-100 dark:hover:bg-blue-900/40 text-blue-900 dark:text-blue-200 transition-colors"
                    >
                      {opt}
                    </button>
                  ))}
                </div>
              )}
              <div className="flex space-x-2">
                <input
                  type="text"
                  value={clarificationInput}
                  maxLength={1000}
                  onChange={(e) => setClarificationInput(e.target.value)}
                  placeholder="Type your answer, e.g. M2, 20 mm long"
                  aria-label="Clarification answer"
                  className="flex-1 px-3 py-1.5 rounded-lg border border-blue-300 dark:border-blue-800 bg-white dark:bg-neutral-900 text-xs text-neutral-900 dark:text-white focus:outline-none"
                  onKeyDown={(e) => {
                    if (e.key === 'Enter') submitClarification(clarificationInput);
                  }}
                />
                <button
                  onClick={() => submitClarification(clarificationInput)}
                  disabled={!clarificationInput.trim()}
                  className="px-3 py-1.5 rounded-lg bg-blue-600 hover:bg-blue-700 text-white text-xs font-medium disabled:opacity-50 transition-colors"
                >
                  Refine search
                </button>
              </div>
            </div>
          )}

          {outcome === 'exact' && (
            <div className="space-y-3">
              <div className="flex items-center space-x-2">
                <CheckCircle size={16} className="text-emerald-500" />
                <h3 className="text-sm font-semibold text-neutral-900 dark:text-white">
                  Exact match{searchResponse.total_found === 1 ? '' : 'es'} ({searchResponse.results.length}
                  {searchResponse.total_found > searchResponse.results.length ? ` of ${searchResponse.total_found}` : ''})
                </h3>
              </div>
              <p className="text-xs text-neutral-500 dark:text-neutral-400">{searchResponse.message}</p>
              {renderFollowUp()}
              <div className="space-y-3">{searchResponse.results.map(renderProductCard)}</div>
            </div>
          )}

          {outcome === 'alternative' && (
            <div className="space-y-3">
              <div className="flex items-center space-x-2">
                <AlertTriangle size={16} className="text-amber-500" />
                <h3 className="text-sm font-semibold text-neutral-900 dark:text-white">
                  Related alternatives ({searchResponse.results.length}
                  {searchResponse.total_found > searchResponse.results.length ? ` of ${searchResponse.total_found}` : ''}) — no exact match
                </h3>
              </div>
              <p className="text-xs text-neutral-500 dark:text-neutral-400">{searchResponse.message}</p>
              <p className="text-[11px] text-neutral-400">{searchResponse.score_note}</p>
              {renderFollowUp()}
              <div className="space-y-3">{searchResponse.results.map(renderProductCard)}</div>
            </div>
          )}

          {outcome === 'no_match' && (
            <div className="p-8 text-center rounded-xl border border-dashed border-neutral-300 dark:border-neutral-700 bg-neutral-50 dark:bg-neutral-900/30 space-y-2">
              <SearchX size={24} className="mx-auto text-neutral-400" />
              <h3 className="text-sm font-semibold text-neutral-800 dark:text-neutral-200">No suitable product found</h3>
              <p className="text-xs text-neutral-500 dark:text-neutral-400 max-w-lg mx-auto">{searchResponse.message}</p>
              <p className="text-[11px] text-neutral-400 max-w-lg mx-auto">
                Nothing is shown rather than an unrelated product. You can make a requirement flexible or remove it above.
              </p>
            </div>
          )}

          {outcome === 'insufficient_evidence' && (
            <div className="p-8 text-center rounded-xl border border-dashed border-amber-300 dark:border-amber-800 bg-amber-50/50 dark:bg-amber-950/20 space-y-2">
              <ShieldQuestion size={24} className="mx-auto text-amber-500" />
              <h3 className="text-sm font-semibold text-neutral-800 dark:text-neutral-200">Insufficient evidence</h3>
              <p className="text-xs text-neutral-600 dark:text-neutral-300 max-w-lg mx-auto">{searchResponse.message}</p>
            </div>
          )}

          {outcome === 'irrelevant' && (
            <div className="p-8 text-center rounded-xl border border-dashed border-neutral-300 dark:border-neutral-700 bg-neutral-50 dark:bg-neutral-900/30 space-y-2">
              <Ban size={24} className="mx-auto text-neutral-400" />
              <h3 className="text-sm font-semibold text-neutral-800 dark:text-neutral-200">Outside the catalogue</h3>
              <p className="text-xs text-neutral-500 dark:text-neutral-400 max-w-lg mx-auto">{searchResponse.message}</p>
            </div>
          )}
        </div>
      )}
    </div>
  );
};
