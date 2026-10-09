import React, { useEffect } from 'react';
import { Command } from 'cmdk';
import { Search, FileText, Settings, Moon, Sun, RefreshCw, X } from 'lucide-react';

interface CommandPaletteProps {
  open: boolean;
  setOpen: (open: boolean) => void;
  setActiveTab: (tab: 'search' | 'documents' | 'settings') => void;
  toggleTheme: () => void;
  isDark: boolean;
  onExecutePresetQuery: (q: string) => void;
}

export const CommandPalette: React.FC<CommandPaletteProps> = ({
  open,
  setOpen,
  setActiveTab,
  toggleTheme,
  isDark,
  onExecutePresetQuery
}) => {
  useEffect(() => {
    const down = (e: KeyboardEvent) => {
      if (e.key === 'k' && (e.metaKey || e.ctrlKey)) {
        e.preventDefault();
        setOpen(!open);
      }
      if (e.key === 'Escape' && open) {
        setOpen(false);
      }
    };
    document.addEventListener('keydown', down);
    return () => document.removeEventListener('keydown', down);
  }, [open, setOpen]);

  if (!open) return null;

  return (
    <div className="fixed inset-0 z-50 bg-black/50 backdrop-blur-xs flex items-start justify-center pt-24">
      <div className="relative w-full max-w-lg bg-white dark:bg-neutral-900 rounded-xl shadow-2xl border border-notion-borderLight dark:border-notion-borderDark overflow-hidden animate-in fade-in zoom-in-95 duration-100">
        <Command label="Global Command Menu">
          <div className="flex items-center px-3 border-b border-notion-borderLight dark:border-notion-borderDark">
            <Search size={16} className="text-notion-mutedLight dark:text-notion-mutedDark mr-2" />
            <Command.Input
              placeholder="Type a command or jump to..."
              className="w-full py-3 bg-transparent text-sm text-neutral-900 dark:text-neutral-100 focus:outline-none placeholder:text-neutral-400"
              autoFocus
            />
            <button
              onClick={() => setOpen(false)}
              className="p-1 rounded hover:bg-neutral-100 dark:hover:bg-neutral-800 text-neutral-400"
            >
              <X size={15} />
            </button>
          </div>

          <Command.List className="max-h-72 overflow-y-auto p-2 text-sm">
            <Command.Empty className="p-4 text-center text-xs text-neutral-400">
              No matching commands found.
            </Command.Empty>

            <Command.Group heading="Navigation" className="text-xs font-semibold text-neutral-400 px-2 py-1">
              <Command.Item
                onSelect={() => { setActiveTab('search'); setOpen(false); }}
                className="flex items-center space-x-2.5 px-2.5 py-2 rounded-lg cursor-pointer hover:bg-neutral-100 dark:hover:bg-neutral-800 text-neutral-800 dark:text-neutral-200"
              >
                <Search size={15} />
                <span>Go to Search</span>
              </Command.Item>
              <Command.Item
                onSelect={() => { setActiveTab('documents'); setOpen(false); }}
                className="flex items-center space-x-2.5 px-2.5 py-2 rounded-lg cursor-pointer hover:bg-neutral-100 dark:hover:bg-neutral-800 text-neutral-800 dark:text-neutral-200"
              >
                <FileText size={15} />
                <span>Manage Documents & Upload</span>
              </Command.Item>
              <Command.Item
                onSelect={() => { setActiveTab('settings'); setOpen(false); }}
                className="flex items-center space-x-2.5 px-2.5 py-2 rounded-lg cursor-pointer hover:bg-neutral-100 dark:hover:bg-neutral-800 text-neutral-800 dark:text-neutral-200"
              >
                <Settings size={15} />
                <span>System Settings & Weights</span>
              </Command.Item>
            </Command.Group>

            <Command.Group heading="Sample Metrology Searches" className="text-xs font-semibold text-neutral-400 px-2 py-1 mt-2">
              <Command.Item
                onSelect={() => {
                  onExecutePresetQuery("M2 stylus with 2 mm ruby ball, 20 mm long");
                  setOpen(false);
                }}
                className="flex items-center space-x-2.5 px-2.5 py-2 rounded-lg cursor-pointer hover:bg-neutral-100 dark:hover:bg-neutral-800 text-neutral-800 dark:text-neutral-200"
              >
                <Search size={14} className="text-emerald-500" />
                <span>M2 stylus with 2 mm ruby ball, 20 mm long</span>
              </Command.Item>
              <Command.Item
                onSelect={() => {
                  onExecutePresetQuery("M3 extension 50 mm long");
                  setOpen(false);
                }}
                className="flex items-center space-x-2.5 px-2.5 py-2 rounded-lg cursor-pointer hover:bg-neutral-100 dark:hover:bg-neutral-800 text-neutral-800 dark:text-neutral-200"
              >
                <Search size={14} className="text-emerald-500" />
                <span>M3 extension 50 mm long</span>
              </Command.Item>
              <Command.Item
                onSelect={() => {
                  onExecutePresetQuery("M5 stylus with 0.08 inch ruby ball");
                  setOpen(false);
                }}
                className="flex items-center space-x-2.5 px-2.5 py-2 rounded-lg cursor-pointer hover:bg-neutral-100 dark:hover:bg-neutral-800 text-neutral-800 dark:text-neutral-200"
              >
                <Search size={14} className="text-emerald-500" />
                <span>M5 stylus with 0.08 inch ruby ball (inch conversion)</span>
              </Command.Item>
            </Command.Group>

            <Command.Group heading="Theme" className="text-xs font-semibold text-neutral-400 px-2 py-1 mt-2">
              <Command.Item
                onSelect={() => { toggleTheme(); setOpen(false); }}
                className="flex items-center space-x-2.5 px-2.5 py-2 rounded-lg cursor-pointer hover:bg-neutral-100 dark:hover:bg-neutral-800 text-neutral-800 dark:text-neutral-200"
              >
                {isDark ? <Sun size={15} /> : <Moon size={15} />}
                <span>Toggle {isDark ? "Light" : "Dark"} Mode</span>
              </Command.Item>
            </Command.Group>
          </Command.List>
        </Command>
      </div>
    </div>
  );
};
