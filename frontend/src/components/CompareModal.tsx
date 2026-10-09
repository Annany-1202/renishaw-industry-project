import React from 'react';
import { X, CheckCircle, AlertTriangle, Layers } from 'lucide-react';
import { ProductMatch } from '../types';

interface CompareModalProps {
  products: ProductMatch[];
  onClose: () => void;
  onSelectProduct: (p: ProductMatch) => void;
}

export const CompareModal: React.FC<CompareModalProps> = ({ products, onClose, onSelectProduct }) => {
  if (products.length === 0) return null;

  const attributes = [
    { label: 'Match Class', key: 'match_class' },
    { label: 'Score', key: 'score' },
    { label: 'Thread Interface', key: 'thread' },
    { label: 'Category', key: 'category' },
    { label: 'Ball Material', key: 'ball_material' },
    { label: 'Ball Diameter (mm)', key: 'ball_diameter_mm' },
    { label: 'Overall Length (mm)', key: 'overall_length_mm' },
    { label: 'EWL (mm)', key: 'effective_working_length_mm' },
    { label: 'Stem Material', key: 'stem_material' },
    { label: 'Stem Diameter (mm)', key: 'stem_diameter_mm' },
    { label: 'Weight (g)', key: 'weight_g' },
    { label: 'Source Document', key: 'source_pdf' },
    { label: 'Page', key: 'source_page' }
  ];

  return (
    <div className="fixed inset-0 z-50 bg-black/60 backdrop-blur-xs flex items-center justify-center p-4">
      <div className="bg-white dark:bg-neutral-900 rounded-xl shadow-2xl border border-notion-borderLight dark:border-notion-borderDark w-full max-w-5xl max-h-[85vh] flex flex-col overflow-hidden animate-in fade-in zoom-in-95 duration-150">
        <div className="flex items-center justify-between p-4 border-b border-notion-borderLight dark:border-notion-borderDark">
          <div className="flex items-center space-x-2">
            <Layers size={18} className="text-neutral-700 dark:text-neutral-300" />
            <h3 className="font-semibold text-base text-neutral-900 dark:text-white">
              Product Comparison ({products.length} selected)
            </h3>
          </div>
          <button
            onClick={onClose}
            className="p-1 rounded hover:bg-neutral-100 dark:hover:bg-neutral-800 text-neutral-400"
          >
            <X size={18} />
          </button>
        </div>

        <div className="flex-1 overflow-auto p-4">
          <table className="w-full text-left text-xs border-collapse">
            <thead>
              <tr className="border-b border-neutral-200 dark:border-neutral-800">
                <th className="p-3 font-semibold text-neutral-400 w-44">Part Number</th>
                {products.map((p) => (
                  <th key={p.id} className="p-3 font-mono font-bold text-sm text-neutral-900 dark:text-white min-w-[180px]">
                    <div className="flex flex-col space-y-1">
                      <span>{p.part_number}</span>
                      <button
                        onClick={() => { onSelectProduct(p); onClose(); }}
                        className="text-[11px] font-normal text-blue-600 dark:text-blue-400 hover:underline text-left"
                      >
                        View Full Specs
                      </button>
                    </div>
                  </th>
                ))}
              </tr>
            </thead>
            <tbody className="divide-y divide-neutral-100 dark:divide-neutral-800/60">
              {attributes.map((attr) => (
                <tr key={attr.key} className="hover:bg-neutral-50 dark:hover:bg-neutral-800/20">
                  <td className="p-3 font-medium text-neutral-500 dark:text-neutral-400">
                    {attr.label}
                  </td>
                  {products.map((p) => {
                    const val = (p as any)[attr.key];
                    if (attr.key === 'match_class') {
                      return (
                        <td key={p.id} className="p-3">
                          {val === 'EXACT_MATCH' ? (
                            <span className="px-2 py-0.5 rounded bg-emerald-100 dark:bg-emerald-950 text-emerald-800 dark:text-emerald-300 font-semibold text-[10px]">
                              Exact Match
                            </span>
                          ) : (
                            <span className="px-2 py-0.5 rounded bg-amber-100 dark:bg-amber-950 text-amber-800 dark:text-amber-300 font-semibold text-[10px]">
                              Alternative
                            </span>
                          )}
                        </td>
                      );
                    }
                    if (attr.key === 'score') {
                      return (
                        <td key={p.id} className="p-3 font-mono font-semibold">
                          {p.score.toFixed(1)} / 100
                        </td>
                      );
                    }
                    return (
                      <td key={p.id} className="p-3 font-mono text-neutral-800 dark:text-neutral-200">
                        {val !== null && val !== undefined ? String(val) : '-'}
                      </td>
                    );
                  })}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
};
