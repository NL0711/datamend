import React from 'react';

export interface MetricCardProps {
  label: string;
  value: string | number;
  unit?: string;
  sublabel?: string;
  delta?: {
    value: string;
    isPositive?: boolean;
    isNeutral?: boolean;
  };
  icon?: React.ReactNode;
  badge?: React.ReactNode;
  footerLeft?: React.ReactNode;
  footerRight?: React.ReactNode;
  className?: string;
  onClick?: () => void;
}

export const MetricCard: React.FC<MetricCardProps> = ({
  label,
  value,
  unit,
  sublabel,
  delta,
  icon,
  badge,
  footerLeft,
  footerRight,
  className = '',
  onClick,
}) => {
  return (
    <div
      onClick={onClick}
      className={`bg-[#FFFFFF] border border-[#D3DCE7] rounded-xl p-4.5 shadow-md hover:border-sky-400 hover:bg-[#F8FAFC] hover:shadow-xl transition-all flex flex-col justify-between ${
        onClick ? 'cursor-pointer' : ''
      } ${className}`}
    >
      <div>
        <div className="flex items-center justify-between gap-2 mb-2">
          <span className="text-[11px] font-semibold uppercase tracking-wider text-slate-600 font-mono">
            {label}
          </span>
          <div className="flex items-center gap-2">
            {badge}
            {icon && <div className="text-slate-600 p-1.5 bg-[#F4F6FA] rounded-lg border border-[#D3DCE7]/60">{icon}</div>}
          </div>
        </div>

        <div className="mt-1 flex items-baseline gap-2">
          <span className="text-2xl sm:text-3xl font-bold font-mono text-slate-900 tracking-tight">
            {value}
          </span>
          {unit && (
            <span className="text-xs sm:text-sm font-semibold font-mono text-slate-600">
              {unit}
            </span>
          )}
          {delta && (
            <span
              className={`ml-auto text-[11px] font-mono font-semibold px-2 py-0.5 rounded ${
                delta.isNeutral
                  ? 'bg-[#F4F6FA] text-slate-600 border border-[#D3DCE7]'
                  : delta.isPositive
                  ? 'bg-emerald-500/15 text-emerald-700 border border-emerald-500/30'
                  : 'bg-rose-500/15 text-rose-700 border border-rose-500/30'
              }`}
            >
              {delta.value}
            </span>
          )}
        </div>

        {sublabel && (
          <div className="mt-1 text-xs text-slate-500 font-medium">{sublabel}</div>
        )}
      </div>

      {(footerLeft || footerRight) && (
        <div className="mt-3.5 pt-2.5 border-t border-slate-200 flex items-center justify-between text-xs text-slate-500 font-mono">
          <div>{footerLeft}</div>
          <div>{footerRight}</div>
        </div>
      )}
    </div>
  );
};
