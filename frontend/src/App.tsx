import React, { useState, useEffect, useCallback, useRef } from 'react';
import { Sidebar } from './components/Sidebar';
import { Header } from './components/Header';
import { CommandPalette } from './components/CommandPalette';
import { SearchPage } from './components/SearchPage';
import { DocumentsPage } from './components/DocumentsPage';
import { SettingsPage } from './components/SettingsPage';
import { SidePeek } from './components/SidePeek';
import { CompareModal } from './components/CompareModal';
import { executeSearch, fetchDocuments, fetchHealth } from './api';
import { SearchResponse, ProductMatch, DocumentInfo, HealthStatus, ParsedQuery } from './types';

const IN_FLIGHT = ['Uploaded', 'Queued', 'Processing', 'Deleting'];

export const App: React.FC = () => {
  const [activeTab, setActiveTab] = useState<'search' | 'documents' | 'settings'>('search');
  const [sidebarCollapsed, setSidebarCollapsed] = useState<boolean>(false);
  const [isDark, setIsDark] = useState<boolean>(() => {
    const saved = localStorage.getItem('theme');
    if (saved) return saved === 'dark';
    return window.matchMedia('(prefers-color-scheme: dark)').matches;
  });

  const [commandPaletteOpen, setCommandPaletteOpen] = useState<boolean>(false);
  const [queryInput, setQueryInput] = useState<string>('');
  const [searchResponse, setSearchResponse] = useState<SearchResponse | null>(null);
  const [searchLoading, setSearchLoading] = useState<boolean>(false);
  const [searchError, setSearchError] = useState<string | null>(null);
  const searchSeq = useRef(0);

  const [selectedProductForPeek, setSelectedProductForPeek] = useState<ProductMatch | null>(null);
  const [selectedCompare, setSelectedCompare] = useState<ProductMatch[]>([]);
  const [compareModalOpen, setCompareModalOpen] = useState<boolean>(false);

  const [documents, setDocuments] = useState<DocumentInfo[]>([]);
  const [documentsError, setDocumentsError] = useState<string | null>(null);
  const [health, setHealth] = useState<HealthStatus | null>(null);

  useEffect(() => {
    document.documentElement.classList.toggle('dark', isDark);
    localStorage.setItem('theme', isDark ? 'dark' : 'light');
  }, [isDark]);

  const refreshDocuments = useCallback(async () => {
    try {
      setDocuments(await fetchDocuments());
      setDocumentsError(null);
    } catch (e: any) {
      setDocumentsError(e.message);
    }
  }, []);

  const refreshHealth = useCallback(async () => {
    setHealth(await fetchHealth().catch(() => null));
  }, []);

  const refreshAll = useCallback(async () => {
    await Promise.all([refreshDocuments(), refreshHealth()]);
  }, [refreshDocuments, refreshHealth]);

  useEffect(() => {
    refreshAll();
  }, [refreshAll]);

  // While a document is being ingested or deleted, poll so its status updates without a manual refresh.
  const busy = documents.some((d) => IN_FLIGHT.includes(d.status));
  useEffect(() => {
    if (!busy) return;
    const timer = window.setInterval(refreshDocuments, 1500);
    return () => window.clearInterval(timer);
  }, [busy, refreshDocuments]);
  const wasBusy = useRef(false);
  useEffect(() => {
    if (wasBusy.current && !busy) refreshHealth();
    wasBusy.current = busy;
  }, [busy, refreshHealth]);

  const handleSearch = async (
    query: string,
    clarificationAnswer?: string,
    prevQuery?: ParsedQuery,
    overrides?: Record<string, unknown>
  ) => {
    const seq = ++searchSeq.current;
    setSearchLoading(true);
    setSearchError(null);
    setSelectedCompare([]);
    setSelectedProductForPeek(null);
    try {
      const res = await executeSearch(query, clarificationAnswer, prevQuery, overrides);
      if (seq !== searchSeq.current) return; // a newer search was started
      setSearchResponse(res);
    } catch (err: any) {
      if (seq !== searchSeq.current) return;
      setSearchError(err.message || 'The search could not be completed');
    } finally {
      if (seq === searchSeq.current) setSearchLoading(false);
    }
  };

  const toggleTheme = () => setIsDark(!isDark);

  return (
    <div className="flex h-screen w-screen overflow-hidden bg-notion-light dark:bg-notion-dark text-notion-textLight dark:text-notion-textDark font-sans">
      <Sidebar
        activeTab={activeTab}
        setActiveTab={setActiveTab}
        collapsed={sidebarCollapsed}
        setCollapsed={setSidebarCollapsed}
        isDark={isDark}
        toggleTheme={toggleTheme}
        documents={documents}
        onOpenCommandPalette={() => setCommandPaletteOpen(true)}
      />

      <div className="flex-1 flex flex-col min-w-0 h-screen overflow-hidden">
        <Header
          activeTab={activeTab}
          health={health}
          onOpenCommandPalette={() => setCommandPaletteOpen(true)}
          isDark={isDark}
          toggleTheme={toggleTheme}
        />

        <main className="flex-1 overflow-y-auto">
          {activeTab === 'search' && (
            <SearchPage
              onSearch={handleSearch}
              searchResponse={searchResponse}
              loading={searchLoading}
              error={searchError}
              health={health}
              onSelectProduct={(p) => setSelectedProductForPeek(p)}
              selectedCompare={selectedCompare}
              setSelectedCompare={setSelectedCompare}
              onOpenCompare={() => setCompareModalOpen(true)}
              queryInput={queryInput}
              setQueryInput={setQueryInput}
            />
          )}

          {activeTab === 'documents' && (
            <DocumentsPage documents={documents} loadError={documentsError} refreshDocuments={refreshAll} />
          )}

          {activeTab === 'settings' && <SettingsPage health={health} refreshHealth={refreshAll} />}
        </main>
      </div>

      <SidePeek product={selectedProductForPeek} onClose={() => setSelectedProductForPeek(null)} />

      {compareModalOpen && (
        <CompareModal
          products={selectedCompare}
          onClose={() => setCompareModalOpen(false)}
          onSelectProduct={(p) => setSelectedProductForPeek(p)}
        />
      )}

      <CommandPalette
        open={commandPaletteOpen}
        setOpen={setCommandPaletteOpen}
        setActiveTab={setActiveTab}
        toggleTheme={toggleTheme}
        isDark={isDark}
        onExecutePresetQuery={(q) => {
          setQueryInput(q);
          setActiveTab('search');
          handleSearch(q);
        }}
      />
    </div>
  );
};
