import React from 'react';
import { Layers, Activity, Sun, Moon } from 'lucide-react';
import { HealthStatus } from '../types';

interface HeaderProps {
  activeTab: string;
  health: HealthStatus | null;
  onOpenCommandPalette: () => void;
  isDark: boolean;
  toggleTheme: () => void;
}

export const Header: React.FC<HeaderProps> = ({
  activeTab,
  health,
  onOpenCommandPalette,
  isDark,
  toggleTheme
}) => {
  const getTabTitle = () => {
    switch (activeTab) {
      case 'search': return 'Catalogue Search';
      case 'documents': return 'Document Management';
      case 'settings': return 'System Settings';
      default: return 'Renishaw Product Retrieval';
    }
  };

  const isHealthy = health?.status === 'healthy';

  return (
    <header className="h-14 border-b border-notion-borderLight dark:border-notion-borderDark bg-notion-light/80 dark:bg-notion-dark/80 backdrop-blur flex items-center justify-between px-6 shrink-0 z-10">
      {/* Breadcrumbs */}
      <div className="flex items-center space-x-2 text-sm">
        <span className="text-notion-mutedLight dark:text-notion-mutedDark">Renishaw Project</span>
        <span className="text-notion-mutedLight dark:text-notion-mutedDark">/</span>
        <span className="font-medium text-notion-textLight dark:text-notion-textDark">{getTabTitle()}</span>
      </div>

      {/* Quick Action & Health Indicator */}
      <div className="flex items-center space-x-3">
        <button
          onClick={onOpenCommandPalette}
          className="flex items-center space-x-2 px-2.5 py-1 rounded-md text-xs border border-notion-borderLight dark:border-notion-borderDark text-notion-mutedLight dark:text-notion-mutedDark hover:bg-notion-hoverLight dark:hover:bg-notion-hoverDark transition-colors"
        >
          <Layers size={13} />
          <span>Search or jump to...</span>
          <kbd className="px-1 py-0.5 rounded bg-neutral-100 dark:bg-neutral-800 text-[10px]">Ctrl+K</kbd>
        </button>

        {health && (
          <div
            className={`flex items-center space-x-1.5 px-2 py-0.5 rounded-full text-xs font-medium border ${
              isHealthy
                ? 'bg-emerald-50 dark:bg-emerald-950/40 text-emerald-700 dark:text-emerald-400 border-emerald-200 dark:border-emerald-800'
                : 'bg-amber-50 dark:bg-amber-950/40 text-amber-700 dark:text-amber-400 border-amber-200 dark:border-amber-800'
            }`}
            title={`Ollama: ${health.ollama.ollama_reachable ? 'Connected' : 'Offline'} | DB: ${health.database.connected ? 'Connected' : 'Error'} | Vectors: ${health.vector_index.item_count}`}
          >
            <Activity size={12} className={isHealthy ? 'text-emerald-500' : 'text-amber-500 animate-pulse'} />
            <span className="capitalize">{health.status}</span>
          </div>
        )}

        <button
          onClick={toggleTheme}
          className="p-1.5 rounded hover:bg-notion-hoverLight dark:hover:bg-notion-hoverDark text-notion-mutedLight dark:text-notion-mutedDark"
          title="Toggle theme"
        >
          {isDark ? <Sun size={15} className="text-amber-400" /> : <Moon size={15} />}
        </button>
      </div>
    </header>
  );
};
