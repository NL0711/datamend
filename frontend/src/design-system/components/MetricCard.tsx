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
      className={`bg-[#152033] border border-[#263B5E] rounded-xl p-4.5 shadow-lg hover:border-[#38BDF8]/50 hover:bg-[#1A2840] transition-all flex flex-col justify-between ${
        onClick ? 'cursor-pointer' : ''
      } ${className}`}
    >
      <div>
        <div className="flex items-center justify-between gap-2 mb-2">
          <span className="text-[11px] font-semibold uppercase tracking-wider text-slate-300 font-mono">
            {label}
          </span>
          <div className="flex items-center gap-2">
            {badge}
            {icon && <div className="text-slate-300 p-1.5 bg-[#10192A] rounded-lg border border-[#263B5E]/60">{icon}</div>}
          </div>
        </div>

        <div className="mt-1 flex items-baseline gap-2">
          <span className="text-2xl sm:text-3xl font-bold font-mono text-white tracking-tight">
            {value}
          </span>
          {unit && (
            <span className="text-xs sm:text-sm font-semibold font-mono text-slate-300">
              {unit}
            </span>
          )}
          {delta && (
            <span
              className={`ml-auto text-[11px] font-mono font-semibold px-2 py-0.5 rounded ${
                delta.isNeutral
                  ? 'bg-[#10192A] text-slate-300 border border-[#263B5E]'
                  : delta.isPositive
                  ? 'bg-emerald-500/15 text-emerald-300 border border-emerald-500/30'
                  : 'bg-rose-500/15 text-rose-300 border border-rose-500/30'
              }`}
            >
              {delta.value}
            </span>
          )}
        </div>

        {sublabel && (
          <div className="mt-1 text-xs text-slate-400 font-medium">{sublabel}</div>
        )}
      </div>

      {(footerLeft || footerRight) && (
        <div className="mt-3.5 pt-2.5 border-t border-white/[0.08] flex items-center justify-between text-xs text-slate-400 font-mono">
          <div>{footerLeft}</div>
          <div>{footerRight}</div>
        </div>
      )}
    </div>
  );
};
