export type MatchStatus = 'MATCH' | 'DIFFERS' | 'UNKNOWN' | 'NOT_APPLICABLE';
export type MatchClass = 'EXACT_MATCH' | 'ALTERNATIVE' | 'NO_MATCH';
export type Outcome =
  | 'exact' | 'alternative' | 'no_match' | 'insufficient_evidence' | 'irrelevant' | 'conflict' | 'clarification';

export interface AttributeComparison {
  attribute_name: string;
  label: string;
  requested_value: string | number | null;
  product_value: string | number | null;
  unit?: string | null;
  status: MatchStatus;
  is_hard: boolean;
  weight: number;
  score: number;
  difference_description?: string | null;
  note?: string | null;
}

export interface ImageInfo {
  image_id: string;
  document_id: string;
  source_pdf: string;
  page_number: number;
  image_url: string;
  image_type: string;
  association_status: string;
  association_basis?: string | null;
  description?: string | null;
  label?: string | null;
}

export interface SourceReference {
  document_id: string;
  source_pdf: string;
  source_page: number;
  source_table?: string | null;
  validation_status: string;
  record_id: string;
}

export interface ProductMatch {
  id: string;
  document_id: string;
  manufacturer?: string | null;
  part_number: string;
  alt_part_number?: string | null;
  product_name: string;
  description?: string | null;
  category: string;
  stylus_type?: string | null;
  thread?: string | null;
  ball_material?: string | null;
  ball_diameter_mm?: number | null;
  stem_material?: string | null;
  stem_diameter_mm?: number | null;
  overall_length_mm?: number | null;
  effective_working_length_mm?: number | null;
  weight_g?: number | null;
  extra_attributes: Record<string, unknown>;
  source_pdf: string;
  source_page: number;
  source_table?: string | null;
  sources: SourceReference[];
  validation_status: string;
  review_reason?: string | null;
  match_class: MatchClass;
  score: number;
  attribute_comparisons: AttributeComparison[];
  matching_attributes: string[];
  differing_attributes: string[];
  missing_attributes: string[];
  explanation: string;
  explanation_source: 'template' | 'llm';
  images: ImageInfo[];
  image_note?: string | null;
}

export interface RequestedAttribute {
  name: string;
  value: string | number | null;
  unit?: string | null;
  original_text?: string | null;
  is_hard_constraint: boolean;
  source: 'query' | 'clarification' | 'llm' | 'inferred' | 'manual';
  note?: string | null;
}

export interface ParsedQuery {
  original_query: string;
  category?: string | null;
  stylus_type?: string | null;
  thread?: string | null;
  secondary_thread?: string | null;
  ball_material?: string | null;
  ball_diameter_mm?: number | null;
  stem_material?: string | null;
  stem_diameter_mm?: number | null;
  overall_length_mm?: number | null;
  effective_working_length_mm?: number | null;
  part_number?: string | null;
  hard_constraints: string[];
  flexible_preferences: string[];
  requested_attributes: RequestedAttribute[];
  assumptions: string[];
  unparsed_terms: string[];
  probe_model?: string | null;
  llm_used: boolean;
  interpreter: string;
  [key: string]: unknown;
}

export interface SearchResponse {
  search_id: string;
  query: string;
  interpreted_query: ParsedQuery;
  result_class: MatchClass;
  outcome: Outcome;
  message?: string | null;
  total_found: number;
  results: ProductMatch[];
  clarification?: { type?: string | null; question?: string | null; options?: string[] } | null;
  diagnostics: Record<string, unknown>;
  score_note: string;
  execution_time_ms: number;
}

export type DocumentStatus = 'Uploaded' | 'Queued' | 'Processing' | 'Ready' | 'Failed' | 'Deleting';

export interface DocumentInfo {
  id: string;
  filename: string;
  file_hash: string;
  file_size: number;
  page_count: number;
  status: DocumentStatus;
  error_message?: string | null;
  is_builtin: boolean;
  embedding_model?: string | null;
  embedded_count: number;
  created_at: string;
  updated_at: string;
  product_count: number;
  review_count: number;
  image_count: number;
}

export interface DocumentDetail extends DocumentInfo {
  ingestion_report?: Record<string, any> | null;
  events: { event: string; detail: string; created_at: string }[];
}

export interface DeletionPreview {
  document_id: string;
  filename: string;
  will_remove: {
    products: number;
    images: number;
    product_image_links: number;
    embeddings: number;
    source_file: number;
    shared_part_numbers_kept_in_other_documents: number;
  };
}

export interface SettingsConfig {
  app_name: string;
  version: string;
  llm_model: string;
  embedding_model: string;
  ollama_base_url: string;
  min_alternative_score: number;
  max_results: number;
  llm_temperature: number;
  llm_mode: 'auto' | 'always' | 'off';
  llm_explanations: boolean;
  embeddings_enabled: boolean;
  max_upload_size_mb: number;
  weights: Record<string, number>;
  tolerances: Record<string, number>;
}

export type SettingsPatch = Partial<Pick<SettingsConfig,
  'min_alternative_score' | 'max_results' | 'llm_temperature' | 'llm_mode' | 'llm_explanations' | 'weights' | 'tolerances'>>;

export interface HealthStatus {
  status: 'healthy' | 'degraded' | 'unavailable';
  search_available: boolean;
  notes: string[];
  app_version: string;
  llm_mode: string;
  ollama: {
    ollama_reachable: boolean;
    llm_model: string;
    llm_model_available: boolean;
    embedding_model: string;
    embedding_model_available: boolean;
    models_found: string[];
    error?: string | null;
  };
  database: {
    connected: boolean;
    product_count: number;
    document_count: number;
    ready_document_count?: number;
    schema_version?: number;
    error?: string;
  };
  vector_index: {
    ready: boolean;
    item_count: number;
    expected_count?: number;
    in_sync?: boolean;
    disabled?: boolean;
    error?: string;
  };
}
