import React, { useState, useEffect } from 'react';
import { Activity, Sliders, RotateCcw, RefreshCw, CheckCircle, Database, Cpu, AlertTriangle, Wrench, Save } from 'lucide-react';
import { SettingsConfig, HealthStatus } from '../types';
import { fetchSettings, updateSettings, resetSettings, triggerReconcile, triggerReindex, restoreDefaults } from '../api';

interface SettingsPageProps {
  health: HealthStatus | null;
  refreshHealth: () => Promise<void> | void;
}

type Notice = { kind: 'ok' | 'error' | 'busy'; text: string };

const WEIGHT_LABELS: Record<string, string> = {
  thread: 'Thread / mounting interface',
  category: 'Product type and description',
  ball_diameter: 'Ball / tip diameter',
  overall_length: 'Overall length',
  stem_material: 'Stem material',
  ball_material: 'Ball material',
  other_dimensions: 'Other dimensions'
};
const TOLERANCE_LABELS: Record<string, string> = {
  ball_diameter: 'Ball diameter (mm)',
  overall_length: 'Overall length (mm)',
  stem_diameter: 'Stem diameter (mm)',
  effective_working_length: 'Working length (mm)',
  ball_diameter_rel: 'Ball diameter (fraction of request)',
  overall_length_rel: 'Overall length (fraction of request)',
  stem_diameter_rel: 'Stem diameter (fraction of request)',
  effective_working_length_rel: 'Working length (fraction of request)'
};

const Ok: React.FC<{ ok: boolean; yes: string; no: string }> = ({ ok, yes, no }) => (
  <span className={ok ? 'text-emerald-600 dark:text-emerald-400 font-semibold' : 'text-amber-600 dark:text-amber-400 font-semibold'}>{ok ? yes : no}</span>
);

export const SettingsPage: React.FC<SettingsPageProps> = ({ health, refreshHealth }) => {
  const [config, setConfig] = useState<SettingsConfig | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [notice, setNotice] = useState<Notice | null>(null);
  const [running, setRunning] = useState<string | null>(null);

  const load = async () => {
    try {
      setConfig(await fetchSettings());
      setLoadError(null);
    } catch (e: any) {
      setLoadError(e.message);
    }
  };

  useEffect(() => {
    load();
  }, []);

  const save = async () => {
    if (!config) return;
    setSaving(true);
    setNotice(null);
    try {
      setConfig(await updateSettings({
        min_alternative_score: config.min_alternative_score,
        max_results: config.max_results,
        llm_mode: config.llm_mode,
        weights: config.weights,
        tolerances: config.tolerances
      }));
      setNotice({ kind: 'ok', text: 'Settings saved. They apply to the next search and are kept after a restart.' });
    } catch (e: any) {
      setNotice({ kind: 'error', text: `Not saved: ${e.message}` });
    } finally {
      setSaving(false);
    }
  };

  const reset = async () => {
    setNotice(null);
    try {
      setConfig(await resetSettings());
      setNotice({ kind: 'ok', text: 'Settings were reset to the defaults.' });
    } catch (e: any) {
      setNotice({ kind: 'error', text: e.message });
    }
  };

  const run = async (name: string, busyText: string, action: () => Promise<string>) => {
    setRunning(name);
    setNotice({ kind: 'busy', text: busyText });
    try {
      setNotice({ kind: 'ok', text: await action() });
    } catch (e: any) {
      setNotice({ kind: 'error', text: e.message });
    } finally {
      setRunning(null);
      await refreshHealth();
    }
  };

  const number = (value: string, fallback: number) => {
    const n = Number(value);
    return value.trim() === '' || Number.isNaN(n) ? fallback : n;
  };

  if (loadError) {
    return (
      <div role="alert" className="max-w-4xl mx-auto px-6 py-8 text-xs text-red-700 dark:text-red-300">
        {loadError}{' '}
        <button className="underline" onClick={load}>Try again</button>
      </div>
    );
  }
  if (!config) return <div className="p-8 text-center text-xs text-neutral-400">Loading settings…</div>;

  const vec = health?.vector_index;

  return (
    <div className="max-w-4xl mx-auto px-6 py-8 space-y-8 text-xs">
      <div>
        <h2 className="text-lg font-semibold text-neutral-900 dark:text-white">Settings and system status</h2>
        <p className="text-notion-mutedLight dark:text-notion-mutedDark mt-1">
          Everything runs on this computer. {config.app_name} v{config.version}.
        </p>
      </div>

      {health && health.notes.length > 0 && (
        <div className="p-3 rounded-lg border border-amber-200 dark:border-amber-900 bg-amber-50 dark:bg-amber-950/30 text-amber-900 dark:text-amber-200 space-y-1">
          {health.notes.map((n, i) => (
            <div key={i} className="flex items-start space-x-1.5">
              <AlertTriangle size={13} className="shrink-0 mt-0.5" />
              <span>{n}</span>
            </div>
          ))}
          {health.search_available && <div className="text-amber-800/80 dark:text-amber-200/80">Structured search still works.</div>}
        </div>
      )}

      <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
        <div className="p-4 rounded-xl border border-notion-borderLight dark:border-notion-borderDark bg-white dark:bg-neutral-900 space-y-2">
          <div className="flex items-center space-x-2 font-semibold"><Cpu size={16} /><span>Local Ollama</span></div>
          <div className="space-y-1 text-neutral-600 dark:text-neutral-400">
            <p>Service: {health ? <Ok ok={health.ollama.ollama_reachable} yes="running" no="not reachable" /> : '—'}</p>
            <p className="break-all">LLM <span className="font-mono">{config.llm_model}</span>: {health ? <Ok ok={health.ollama.llm_model_available} yes="installed" no="missing" /> : '—'}</p>
            <p className="break-all">Embeddings <span className="font-mono">{config.embedding_model}</span>: {health ? <Ok ok={health.ollama.embedding_model_available} yes="installed" no="missing" /> : '—'}</p>
            <p className="font-mono text-[10px]">{config.ollama_base_url}</p>
          </div>
        </div>
        <div className="p-4 rounded-xl border border-notion-borderLight dark:border-notion-borderDark bg-white dark:bg-neutral-900 space-y-2">
          <div className="flex items-center space-x-2 font-semibold"><Database size={16} /><span>Catalogue database</span></div>
          <div className="space-y-1 text-neutral-600 dark:text-neutral-400">
            <p>Status: {health ? <Ok ok={health.database.connected} yes="connected" no="error" /> : '—'}</p>
            <p>Documents ready: {health?.database.ready_document_count ?? '—'} of {health?.database.document_count ?? '—'}</p>
            <p>Searchable products: {health?.database.product_count ?? '—'}</p>
          </div>
        </div>
        <div className="p-4 rounded-xl border border-notion-borderLight dark:border-notion-borderDark bg-white dark:bg-neutral-900 space-y-2">
          <div className="flex items-center space-x-2 font-semibold"><Activity size={16} /><span>Vector index</span></div>
          <div className="space-y-1 text-neutral-600 dark:text-neutral-400">
            {vec?.disabled ? (
              <p>Disabled in the configuration.</p>
            ) : (
              <>
                <p>Entries: {vec?.item_count ?? '—'} of {vec?.expected_count ?? '—'}</p>
                <p>State: {vec ? <Ok ok={!!vec.in_sync} yes="in sync" no="out of sync – run Reindex" /> : '—'}</p>
              </>
            )}
            <p className="text-[10px]">Used only to order otherwise equal results.</p>
          </div>
        </div>
      </div>

      {notice && (
        <div
          role={notice.kind === 'error' ? 'alert' : 'status'}
          className={`p-3 rounded-lg border ${
            notice.kind === 'error'
              ? 'border-red-200 dark:border-red-900 bg-red-50 dark:bg-red-950/30 text-red-800 dark:text-red-200'
              : notice.kind === 'ok'
                ? 'border-emerald-200 dark:border-emerald-900 bg-emerald-50 dark:bg-emerald-950/30 text-emerald-900 dark:text-emerald-200'
                : 'border-neutral-200 dark:border-neutral-700 bg-neutral-50 dark:bg-neutral-900'
          }`}
        >
          {notice.text}
        </div>
      )}

      <section className="p-4 rounded-xl border border-notion-borderLight dark:border-notion-borderDark bg-white dark:bg-neutral-900 space-y-4">
        <div className="flex items-center space-x-2 font-semibold text-sm"><Sliders size={16} /><span>Ranking</span></div>
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
          <label className="space-y-1 block">
            <span className="text-notion-mutedLight dark:text-notion-mutedDark">Minimum score for an alternative (0–100)</span>
            <input type="number" min={0} max={100} value={config.min_alternative_score}
              onChange={(e) => setConfig({ ...config, min_alternative_score: number(e.target.value, config.min_alternative_score) })}
              className="w-full px-2 py-1.5 rounded border border-neutral-300 dark:border-neutral-700 bg-transparent" />
          </label>
          <label className="space-y-1 block">
            <span className="text-notion-mutedLight dark:text-notion-mutedDark">Maximum results shown (1–20)</span>
            <input type="number" min={1} max={20} step={1} value={config.max_results}
              onChange={(e) => setConfig({ ...config, max_results: Math.round(number(e.target.value, config.max_results)) })}
              className="w-full px-2 py-1.5 rounded border border-neutral-300 dark:border-neutral-700 bg-transparent" />
          </label>
          <label className="space-y-1 block">
            <span className="text-notion-mutedLight dark:text-notion-mutedDark">Local language model</span>
            <select value={config.llm_mode} onChange={(e) => setConfig({ ...config, llm_mode: e.target.value as SettingsConfig['llm_mode'] })}
              className="w-full px-2 py-1.5 rounded border border-neutral-300 dark:border-neutral-700 bg-transparent dark:bg-neutral-900">
              <option value="auto">Only for wording the rules cannot read</option>
              <option value="always">For every query (slower)</option>
              <option value="off">Off (rules only, fastest)</option>
            </select>
          </label>
        </div>

        <div>
          <h4 className="font-semibold mb-2">Attribute weights</h4>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
            {Object.keys(config.weights).map((key) => (
              <label key={key} className="flex items-center justify-between gap-2">
                <span className="text-neutral-600 dark:text-neutral-400">{WEIGHT_LABELS[key] || key}</span>
                <input type="number" min={0} max={100} value={config.weights[key]}
                  onChange={(e) => setConfig({ ...config, weights: { ...config.weights, [key]: number(e.target.value, config.weights[key]) } })}
                  className="w-20 px-2 py-1 rounded border border-neutral-300 dark:border-neutral-700 bg-transparent text-right" />
              </label>
            ))}
          </div>
        </div>

        <div>
          <h4 className="font-semibold">Deviation scales</h4>
          <p className="text-notion-mutedLight dark:text-notion-mutedDark mb-2">
            How far a dimension may differ before it scores zero: the larger of the absolute value and the fraction of the requested value.
            These are ranking scales, not manufacturer tolerances.
          </p>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
            {Object.keys(config.tolerances).map((key) => (
              <label key={key} className="flex items-center justify-between gap-2">
                <span className="text-neutral-600 dark:text-neutral-400">{TOLERANCE_LABELS[key] || key}</span>
                <input type="number" min={0} step="any" value={config.tolerances[key]}
                  onChange={(e) => setConfig({ ...config, tolerances: { ...config.tolerances, [key]: number(e.target.value, config.tolerances[key]) } })}
                  className="w-20 px-2 py-1 rounded border border-neutral-300 dark:border-neutral-700 bg-transparent text-right" />
              </label>
            ))}
          </div>
        </div>

        <div className="flex items-center space-x-2 pt-1">
          <button onClick={save} disabled={saving} className="inline-flex items-center space-x-1.5 px-3 py-1.5 rounded-lg bg-neutral-900 dark:bg-neutral-100 text-white dark:text-neutral-900 font-semibold disabled:opacity-50">
            {saving ? <RefreshCw size={13} className="animate-spin" /> : <Save size={13} />}
            <span>{saving ? 'Saving…' : 'Save'}</span>
          </button>
          <button onClick={reset} disabled={saving} className="inline-flex items-center space-x-1.5 px-3 py-1.5 rounded-lg border border-neutral-300 dark:border-neutral-700">
            <RotateCcw size={13} />
            <span>Reset to defaults</span>
          </button>
        </div>
      </section>

      <section className="p-4 rounded-xl border border-notion-borderLight dark:border-notion-borderDark bg-white dark:bg-neutral-900 space-y-3">
        <div className="flex items-center space-x-2 font-semibold text-sm"><Wrench size={16} /><span>Maintenance</span></div>
        <div className="space-y-2">
          <div className="flex items-center justify-between gap-3">
            <span className="text-neutral-600 dark:text-neutral-400">Check the database, index and files against each other and remove anything left over from interrupted work.</span>
            <button disabled={!!running} onClick={() => run('reconcile', 'Reconciling…', async () => {
              const r = await triggerReconcile();
              const still = (r.deletions_still_failing || []).length;
              return `Reconciled: ${r.orphaned_vectors_removed} index entries, ${(r.orphaned_image_directories_cleaned || []).length} image folders, ` +
                `${r.orphaned_image_files_removed} image files and ${(r.orphaned_upload_files_removed || []).length} stored PDFs removed; ` +
                `${(r.deletions_resumed || []).length} interrupted deletions finished` + (still ? `; ${still} deletion(s) still failing` : '') + '.';
            })} className="shrink-0 inline-flex items-center space-x-1.5 px-3 py-1.5 rounded-lg border border-neutral-300 dark:border-neutral-700 disabled:opacity-50">
              <CheckCircle size={13} /><span>Reconcile</span>
            </button>
          </div>
          <div className="flex items-center justify-between gap-3">
            <span className="text-neutral-600 dark:text-neutral-400">Rebuild the vector index from the ready documents (needs the local embedding model; takes a few minutes).</span>
            <button disabled={!!running} onClick={() => run('reindex', 'Rebuilding the vector index…', async () => {
              const r = await triggerReindex();
              return `Reindexed ${r.indexed_items} products with ${r.embedding_model}.`;
            })} className="shrink-0 inline-flex items-center space-x-1.5 px-3 py-1.5 rounded-lg border border-neutral-300 dark:border-neutral-700 disabled:opacity-50">
              <RefreshCw size={13} className={running === 'reindex' ? 'animate-spin' : ''} /><span>Reindex</span>
            </button>
          </div>
          <div className="flex items-center justify-between gap-3">
            <span className="text-neutral-600 dark:text-neutral-400">Add the two supplied catalogues again if they were deleted.</span>
            <button disabled={!!running} onClick={() => run('restore', 'Restoring…', async () => {
              const r = await restoreDefaults();
              return r.queued.length ? `Queued ${r.queued.length} supplied catalogue(s) for processing; see the Documents page.` : 'Both supplied catalogues are already present.';
            })} className="shrink-0 inline-flex items-center space-x-1.5 px-3 py-1.5 rounded-lg border border-neutral-300 dark:border-neutral-700 disabled:opacity-50">
              <RotateCcw size={13} /><span>Restore supplied catalogues</span>
            </button>
          </div>
        </div>
      </section>
    </div>
  );
};
