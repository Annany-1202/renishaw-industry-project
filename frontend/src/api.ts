import {
  SearchResponse,
  DocumentInfo,
  DocumentDetail,
  DeletionPreview,
  SettingsConfig,
  SettingsPatch,
  HealthStatus,
  ParsedQuery
} from './types';

const API_BASE = '/api';

export class ApiError extends Error {
  status: number;
  body: any;
  constructor(message: string, status: number, body: any) {
    super(message);
    this.status = status;
    this.body = body;
  }
}

async function request<T>(path: string, init?: RequestInit, fallback = 'The request failed'): Promise<T> {
  let res: Response;
  try {
    res = await fetch(`${API_BASE}${path}`, init);
  } catch {
    throw new ApiError('The local server is not reachable. Check that the application is still running.', 0, null);
  }
  const body = await res.json().catch(() => null);
  if (!res.ok) {
    const detail = body?.detail;
    const message = typeof detail === 'string' ? detail : Array.isArray(detail) && detail[0]?.msg ? detail[0].msg : fallback;
    throw new ApiError(message, res.status, body);
  }
  return body as T;
}

const json = (method: string, payload: unknown): RequestInit => ({
  method,
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify(payload)
});

export const fetchHealth = () => request<HealthStatus>('/health', undefined, 'Health check failed');

export function executeSearch(
  query: string,
  clarificationAnswer?: string,
  previousQuery?: ParsedQuery,
  manualOverrides?: Record<string, unknown>
): Promise<SearchResponse> {
  return request<SearchResponse>(
    '/search',
    json('POST', {
      query,
      clarification_answer: clarificationAnswer || null,
      previous_query: previousQuery || null,
      manual_overrides: manualOverrides || null
    }),
    'The search could not be completed'
  );
}

export const fetchDocuments = () => request<DocumentInfo[]>('/documents', undefined, 'Could not load the document list');
export const fetchDocument = (id: string) =>
  request<DocumentDetail>(`/documents/${encodeURIComponent(id)}`, undefined, 'Could not load the document');
export const fetchDeletionPreview = (id: string) =>
  request<DeletionPreview>(`/documents/${encodeURIComponent(id)}/deletion-preview`, undefined, 'Could not load the deletion preview');

export function uploadDocument(file: File): Promise<{ id: string; filename: string; status: string }> {
  const formData = new FormData();
  formData.append('file', file);
  return request('/documents', { method: 'POST', body: formData }, 'The upload failed');
}

export const deleteDocument = (id: string) =>
  request<any>(`/documents/${encodeURIComponent(id)}`, { method: 'DELETE' }, 'The document could not be deleted');
export const retryDocument = (id: string) =>
  request<any>(`/documents/${encodeURIComponent(id)}/retry`, { method: 'POST' }, 'The retry could not be started');
export const reportUrl = (id: string, kind: 'report' | 'images' | 'review' = 'report') =>
  `${API_BASE}/documents/${encodeURIComponent(id)}/report?kind=${kind}`;

export const fetchSettings = () => request<SettingsConfig>('/settings', undefined, 'Could not load the settings');
export const updateSettings = (patch: SettingsPatch) =>
  request<SettingsConfig>('/settings', json('PATCH', patch), 'The settings were not saved');
export const resetSettings = () => request<SettingsConfig>('/settings/reset', { method: 'POST' }, 'The settings were not reset');

export const triggerReconcile = () => request<any>('/admin/reconcile', { method: 'POST' }, 'Reconciliation failed');
export const triggerReindex = () => request<any>('/admin/reindex', { method: 'POST' }, 'Reindexing failed');
export const restoreDefaults = () => request<{ queued: string[] }>('/admin/restore-defaults', { method: 'POST' }, 'Could not restore the supplied catalogues');
