import React, { useState } from 'react';
import { Lock, Key, Eye, EyeOff, ShieldAlert } from 'lucide-react';
import { fetchJson } from '@/shared/api/client';
import { useToast } from '@/shared/components/Toast';

export interface SimplePromoGatekeeperProps {
  onUnlocked: () => void;
}

export const SimplePromoGatekeeper: React.FC<SimplePromoGatekeeperProps> = ({ onUnlocked }) => {
  const { showSuccess, showError } = useToast();
  const [password, setPassword] = useState('');
  const [showPassword, setShowPassword] = useState(false);
  const [loading, setLoading] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!password.trim()) {
      showError('请输入管理口令');
      return;
    }
    setLoading(true);
    try {
      const res: any = await fetchJson('/api/simple-promo/auth/verify', {
        method: 'POST',
        body: JSON.stringify({ password: password.trim() }),
      });
      if (res.token) {
        sessionStorage.setItem('simple_promo_token', res.token);
      }
      showSuccess('身份验证成功，已进入管理工作台');
      onUnlocked();
    } catch (err: any) {
      showError(err.message || '口令错误，请重试');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div
      style={{
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        minHeight: '65vh',
      }}
    >
      <div
        className="card"
        style={{
          width: '460px',
          maxWidth: '92vw',
          padding: '36px 32px',
          borderRadius: '16px',
          boxShadow: '0 20px 25px -5px rgba(0, 0, 0, 0.08), 0 8px 10px -6px rgba(0, 0, 0, 0.04)',
          textAlign: 'center',
          backgroundColor: '#ffffff',
          border: '1px solid #e2e8f0',
        }}
      >
        <div
          style={{
            width: '56px',
            height: '56px',
            borderRadius: '50%',
            backgroundColor: 'var(--primary-light)',
            color: 'var(--primary)',
            display: 'inline-flex',
            alignItems: 'center',
            justifyContent: 'center',
            marginBottom: '16px',
          }}
        >
          <Lock size={28} />
        </div>

        <h2 style={{ fontSize: '18px', fontWeight: 600, color: '#0f172a', marginBottom: '8px' }}>
          管理工作台
        </h2>
        <p style={{ fontSize: '13px', color: '#64748b', lineHeight: 1.6, marginBottom: '24px' }}>
          此板块为私密管理区域，包含简单投老笔记批量暂停与各板块任务清理。
          <br />
          请输入管理员口令解锁进入。
        </p>

        <form onSubmit={handleSubmit}>
          <div style={{ marginBottom: '20px', textAlign: 'left' }}>
            <label
              style={{
                display: 'block',
                fontSize: '13px',
                fontWeight: 500,
                color: '#334155',
                marginBottom: '6px',
              }}
            >
              管理员访问口令
            </label>
            <div style={{ position: 'relative' }}>
              <input
                type={showPassword ? 'text' : 'password'}
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                placeholder="请输入管理访问口令"
                autoFocus
                style={{
                  width: '100%',
                  padding: '10px 40px 10px 36px',
                  borderRadius: '8px',
                  border: '1px solid #cbd5e1',
                  fontSize: '14px',
                  outline: 'none',
                  backgroundColor: '#ffffff',
                }}
              />
              <Key
                size={16}
                style={{
                  position: 'absolute',
                  left: '12px',
                  top: '50%',
                  transform: 'translateY(-50%)',
                  color: '#94a3b8',
                }}
              />
              <button
                type="button"
                onClick={() => setShowPassword(!showPassword)}
                title={showPassword ? '隐藏口令' : '显示口令'}
                style={{
                  position: 'absolute',
                  right: '12px',
                  top: '50%',
                  transform: 'translateY(-50%)',
                  background: 'none',
                  border: 'none',
                  cursor: 'pointer',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  color: '#64748b',
                  padding: '2px',
                  userSelect: 'none',
                }}
              >
                {showPassword ? <EyeOff size={16} /> : <Eye size={16} />}
              </button>
            </div>
          </div>

          <button
            type="submit"
            disabled={loading}
            style={{
              width: '100%',
              padding: '10px',
              borderRadius: '8px',
              backgroundColor: 'var(--primary)',
              color: '#ffffff',
              border: 'none',
              cursor: loading ? 'not-allowed' : 'pointer',
              fontSize: '14px',
              fontWeight: 600,
              boxShadow: '0 2px 4px rgba(239, 43, 58, 0.25)',
            }}
          >
            {loading ? '正在验证...' : '验证并进入控制台'}
          </button>
        </form>
      </div>
    </div>
  );
};
