import React from 'react';
import { Loader2 } from 'lucide-react';

export interface ButtonProps extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: 'primary' | 'secondary' | 'danger' | 'ghost' | 'outline';
  size?: 'sm' | 'md' | 'lg';
  loading?: boolean;
}

export const Button: React.FC<ButtonProps> = ({
  children,
  variant = 'primary',
  size = 'md',
  loading = false,
  disabled,
  style,
  ...props
}) => {
  const baseStyle: React.CSSProperties = {
    display: 'inline-flex',
    alignItems: 'center',
    justifyContent: 'center',
    gap: '6px',
    fontWeight: 500,
    borderRadius: '6px',
    cursor: disabled || loading ? 'not-allowed' : 'pointer',
    opacity: disabled || loading ? 0.65 : 1,
    border: 'none',
    transition: 'all 0.15s ease',
    whiteSpace: 'nowrap',
    ...style,
  };

  const sizeStyle: Record<string, React.CSSProperties> = {
    sm: { padding: '6px 10px', fontSize: '13px' },
    md: { padding: '8px 14px', fontSize: '14px' },
    lg: { padding: '10px 18px', fontSize: '15px' },
  };

  const variantStyle: Record<string, React.CSSProperties> = {
    primary: { background: '#ea3445', color: '#ffffff' },
    secondary: { background: '#f1f5f9', color: '#334155', border: '1px solid #cbd5e1' },
    danger: { background: '#ef4444', color: '#ffffff' },
    ghost: { background: 'transparent', color: '#64748b' },
    outline: { background: '#ffffff', color: '#ea3445', border: '1px solid #ea3445' },
  };

  return (
    <button
      disabled={disabled || loading}
      style={{ ...baseStyle, ...sizeStyle[size], ...variantStyle[variant] }}
      {...props}
    >
      {loading && <Loader2 size={16} className="spin" style={{ animation: 'spin 1s linear infinite' }} />}
      {children}
    </button>
  );
};

