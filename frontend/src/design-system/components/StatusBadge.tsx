import React from 'react';

export type StatusBadgeVariant =
  | 'nominal'
  | 'info'
  | 'warning'
  | 'critical'
  | 'extremeMet'
  | 'neutral';

export interface StatusBadgeProps {
  label: string;
  variant?: StatusBadgeVariant;
  size?: 'sm' | 'md';
  pulse?: boolean;
  icon?: React.ReactNode;
  className?: string;
}

export const StatusBadge: React.FC<StatusBadgeProps> = ({
  label,
  variant = 'nominal',
  size = 'md',
  pulse = false,
  icon,
  className = '',
}) => {
  const getStyles = (): { bg: string; border: string; text: string; dot: string } => {
    switch (variant) {
      case 'nominal':
        return {
          bg: 'bg-emerald-500/10',
          border: 'border-emerald-500/30',
          text: 'text-emerald-400',
          dot: 'bg-emerald-400',
        };
      case 'info':
        return {
          bg: 'bg-sky-500/10',
          border: 'border-sky-500/30',
          text: 'text-sky-400',
          dot: 'bg-sky-400',
        };
      case 'warning':
        return {
          bg: 'bg-amber-500/10',
          border: 'border-amber-500/35',
          text: 'text-amber-400',
          dot: 'bg-amber-400',
        };
      case 'critical':
        return {
          bg: 'bg-rose-500/15',
          border: 'border-rose-500/40',
          text: 'text-rose-400',
          dot: 'bg-rose-400',
        };
      case 'extremeMet':
        return {
          bg: 'bg-cyan-500/15',
          border: 'border-cyan-500/40',
          text: 'text-cyan-300',
          dot: 'bg-cyan-400',
        };
      case 'neutral':
      default:
        return {
          bg: 'bg-slate-800/60',
          border: 'border-slate-700/60',
          text: 'text-slate-300',
          dot: 'bg-slate-400',
        };
    }
  };

  const styles = getStyles();
  const sizeClasses =
    size === 'sm'
      ? 'px-2 py-0.5 text-[10px] gap-1'
      : 'px-2.5 py-1 text-xs gap-1.5 font-semibold';

  return (
    <span
      className={`inline-flex items-center rounded-md border font-mono tracking-tight transition-colors ${styles.bg} ${styles.border} ${styles.text} ${sizeClasses} ${className}`}
    >
      {pulse && (
        <span
          className={`w-1.5 h-1.5 rounded-full ${styles.dot} animate-pulse shrink-0`}
          aria-hidden="true"
        />
      )}
      {icon && <span className="shrink-0">{icon}</span>}
      <span>{label}</span>
    </span>
  );
};
