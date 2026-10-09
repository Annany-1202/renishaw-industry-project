import React from 'react';
import { Search, FileText, Settings, Database, Moon, Sun, ChevronLeft, ChevronRight, Layers } from 'lucide-react';
import { DocumentInfo } from '../types';

interface SidebarProps {
  activeTab: 'search' | 'documents' | 'settings';
  setActiveTab: (tab: 'search' | 'documents' | 'settings') => void;
  collapsed: boolean;
  setCollapsed: (collapsed: boolean) => void;
  isDark: boolean;
  toggleTheme: () => void;
  documents: DocumentInfo[];
  onOpenCommandPalette: () => void;
}

export const Sidebar: React.FC<SidebarProps> = ({
  activeTab,
  setActiveTab,
  collapsed,
  setCollapsed,
  isDark,
  toggleTheme,
  documents,
  onOpenCommandPalette
}) => {
  return (
    <aside
      className={`relative flex flex-col border-r border-notion-borderLight dark:border-notion-borderDark bg-notion-sidebarLight dark:bg-notion-sidebarDark transition-all duration-200 ${
        collapsed ? 'w-14' : 'w-64'
      } select-none shrink-0 h-screen`}
    >
      {/* Workspace Header */}
      <div className="flex items-center justify-between p-3 border-b border-notion-borderLight dark:border-notion-borderDark h-14">
        {!collapsed && (
          <div className="flex items-center space-x-2.5 overflow-hidden">
            <div className="w-6 h-6 rounded bg-neutral-900 dark:bg-neutral-100 flex items-center justify-center text-white dark:text-neutral-900 font-bold text-xs">
              R
            </div>
            <div className="flex flex-col">
              <span className="text-sm font-semibold truncate leading-tight">Renishaw Project</span>
              <span className="text-[10px] text-notion-mutedLight dark:text-notion-mutedDark">Technical Catalogue</span>
            </div>
          </div>
        )}
        <button
          onClick={() => setCollapsed(!collapsed)}
          className="p-1 rounded hover:bg-notion-hoverLight dark:hover:bg-notion-hoverDark text-notion-mutedLight dark:text-notion-mutedDark mx-auto"
          title={collapsed ? "Expand sidebar" : "Collapse sidebar"}
        >
          {collapsed ? <ChevronRight size={16} /> : <ChevronLeft size={16} />}
        </button>
      </div>

      {/* Navigation Links */}
      <div className="flex-1 py-3 px-2 space-y-1">
        <button
          onClick={() => setActiveTab('search')}
          className={`w-full flex items-center space-x-2.5 px-2.5 py-1.5 rounded-md text-sm transition-colors ${
            activeTab === 'search'
              ? 'bg-neutral-200/80 dark:bg-neutral-700/60 font-medium text-neutral-900 dark:text-white'
              : 'hover:bg-notion-hoverLight dark:hover:bg-notion-hoverDark text-notion-mutedLight dark:text-notion-mutedDark'
          }`}
          title="Search"
        >
          <Search size={16} className="shrink-0" />
          {!collapsed && <span>Search</span>}
        </button>

        <button
          onClick={() => setActiveTab('documents')}
          className={`w-full flex items-center space-x-2.5 px-2.5 py-1.5 rounded-md text-sm transition-colors ${
            activeTab === 'documents'
              ? 'bg-neutral-200/80 dark:bg-neutral-700/60 font-medium text-neutral-900 dark:text-white'
              : 'hover:bg-notion-hoverLight dark:hover:bg-notion-hoverDark text-notion-mutedLight dark:text-notion-mutedDark'
          }`}
          title="Documents"
        >
          <FileText size={16} className="shrink-0" />
          {!collapsed && (
            <div className="flex items-center justify-between flex-1">
              <span>Documents</span>
              <span className="text-xs px-1.5 py-0.5 rounded bg-neutral-200 dark:bg-neutral-800 text-neutral-600 dark:text-neutral-400">
                {documents.length}
              </span>
            </div>
          )}
        </button>

        <button
          onClick={() => setActiveTab('settings')}
          className={`w-full flex items-center space-x-2.5 px-2.5 py-1.5 rounded-md text-sm transition-colors ${
            activeTab === 'settings'
              ? 'bg-neutral-200/80 dark:bg-neutral-700/60 font-medium text-neutral-900 dark:text-white'
              : 'hover:bg-notion-hoverLight dark:hover:bg-notion-hoverDark text-notion-mutedLight dark:text-notion-mutedDark'
          }`}
          title="Settings"
        >
          <Settings size={16} className="shrink-0" />
          {!collapsed && <span>Settings</span>}
        </button>

        {/* Active Sources List */}
        {!collapsed && (
          <div className="pt-5 pb-1">
            <span className="px-2 text-[11px] font-medium uppercase tracking-wider text-notion-mutedLight dark:text-notion-mutedDark">
              Active Catalogues
            </span>
            <div className="mt-2 space-y-0.5">
              {documents.map((doc) => (
                <div
                  key={doc.id}
                  onClick={() => setActiveTab('documents')}
                  className="flex items-center space-x-2 px-2.5 py-1 rounded text-xs text-notion-textLight dark:text-notion-textDark hover:bg-notion-hoverLight dark:hover:bg-notion-hoverDark cursor-pointer truncate"
                  title={doc.filename}
                >
                  <span
                    className={`w-2 h-2 rounded-full shrink-0 ${
                      doc.status === 'Ready' ? 'bg-emerald-500' : 'bg-amber-500 animate-pulse'
                    }`}
                  />
                  <span className="truncate">{doc.filename}</span>
                </div>
              ))}
            </div>
          </div>
        )}
      </div>

      {/* Footer Actions */}
      <div className="p-2 border-t border-notion-borderLight dark:border-notion-borderDark space-y-1">
        <button
          onClick={onOpenCommandPalette}
          className="w-full flex items-center space-x-2.5 px-2.5 py-1.5 rounded-md text-xs text-notion-mutedLight dark:text-notion-mutedDark hover:bg-notion-hoverLight dark:hover:bg-notion-hoverDark"
          title="Command Palette (Ctrl+K)"
        >
          <Layers size={14} className="shrink-0" />
          {!collapsed && (
            <div className="flex items-center justify-between flex-1">
              <span>Quick Actions</span>
              <kbd className="px-1 py-0.5 rounded bg-neutral-200 dark:bg-neutral-800 text-[10px]">Ctrl+K</kbd>
            </div>
          )}
        </button>

        <button
          onClick={toggleTheme}
          className="w-full flex items-center space-x-2.5 px-2.5 py-1.5 rounded-md text-xs text-notion-mutedLight dark:text-notion-mutedDark hover:bg-notion-hoverLight dark:hover:bg-notion-hoverDark"
          title={isDark ? "Switch to light mode" : "Switch to dark mode"}
        >
          {isDark ? <Sun size={14} className="shrink-0 text-amber-400" /> : <Moon size={14} className="shrink-0" />}
          {!collapsed && <span>{isDark ? "Light Mode" : "Dark Mode"}</span>}
        </button>
      </div>
    </aside>
  );
};
