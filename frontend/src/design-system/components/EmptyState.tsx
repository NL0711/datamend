import React from 'react';
import { ShieldCheck } from 'lucide-react';

export interface EmptyStateProps {
  title: string;
  description: string;
  icon?: React.ReactNode;
  actionLabel?: string;
  onAction?: () => void;
  className?: string;
}

export const EmptyState: React.FC<EmptyStateProps> = ({
  title,
  description,
  icon,
  actionLabel,
  onAction,
  className = '',
}) => {
  return (
    <div
      className={`p-8 sm:p-12 text-center border border-dashed border-[#263B5E] rounded-xl bg-[#152033]/60 flex flex-col items-center justify-center ${className}`}
    >
      <div className="p-3 bg-[#1B2A44] border border-[#263B5E] rounded-xl text-slate-300 mb-3.5 shadow-inner">
        {icon || <ShieldCheck className="w-6 h-6 text-emerald-400" />}
      </div>
      <h4 className="text-sm font-bold text-white mb-1 font-mono">{title}</h4>
      <p className="text-xs text-slate-300 max-w-md leading-relaxed font-sans">{description}</p>
      {actionLabel && onAction && (
        <button
          onClick={onAction}
          className="mt-4 px-3.5 py-1.5 bg-[#1B2A44] hover:bg-[#233656] text-slate-200 text-xs font-semibold rounded-lg border border-[#263B5E] transition-colors font-mono"
        >
          {actionLabel}
        </button>
      )}
    </div>
  );
};
