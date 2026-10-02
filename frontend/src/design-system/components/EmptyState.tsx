import React from 'react';

export interface EmptyStateProps {
  title: string;
  description: string;
  actionLabel?: string;
  onAction?: () => void;
  className?: string;
}

export const EmptyState: React.FC<EmptyStateProps> = ({
  title,
  description,
  actionLabel,
  onAction,
  className = '',
}) => {
  return (
    <div
      className={`p-8 sm:p-12 text-center border border-dashed border-[#D3DCE7] rounded-xl bg-[#FFFFFF]/60 flex flex-col items-center justify-center ${className}`}
    >
      <h4 className="text-sm font-bold text-slate-900 mb-1 font-mono">{title}</h4>
      <p className="text-xs text-slate-600 max-w-md leading-relaxed font-sans">{description}</p>
      {actionLabel && onAction && (
        <button
          onClick={onAction}
          className="mt-4 px-3.5 py-1.5 bg-[#EDF1F7] hover:bg-[#E2E8F2] text-slate-700 text-xs font-semibold rounded-lg border border-[#D3DCE7] transition-colors font-mono"
        >
          {actionLabel}
        </button>
      )}
    </div>
  );
};
