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
    // Light-theme chips: deepened text on tinted backgrounds for contrast.
    switch (variant) {
      case 'nominal':
        return {
          bg: 'bg-emerald-50',
          border: 'border-emerald-200',
          text: 'text-emerald-700',
          dot: 'bg-emerald-500',
        };
      case 'info':
        return {
          bg: 'bg-sky-50',
          border: 'border-sky-200',
          text: 'text-sky-700',
          dot: 'bg-sky-500',
        };
      case 'warning':
        return {
          bg: 'bg-amber-50',
          border: 'border-amber-200',
          text: 'text-amber-700',
          dot: 'bg-amber-500',
        };
      case 'critical':
        return {
          bg: 'bg-rose-50',
          border: 'border-rose-200',
          text: 'text-rose-700',
          dot: 'bg-rose-500',
        };
      case 'extremeMet':
        return {
          bg: 'bg-cyan-50',
          border: 'border-cyan-200',
          text: 'text-cyan-700',
          dot: 'bg-cyan-500',
        };
      case 'neutral':
      default:
        return {
          bg: 'bg-slate-100',
          border: 'border-slate-200',
          text: 'text-slate-600',
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
