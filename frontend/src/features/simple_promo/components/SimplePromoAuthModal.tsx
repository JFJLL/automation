import React, { useState } from 'react';
import { Lock, ShieldCheck, Key, Eye, EyeOff } from 'lucide-react';
import { Dialog } from '@/shared/components/Dialog';
import { fetchJson } from '@/shared/api/client';
import { useToast } from '@/shared/components/Toast';

export interface SimplePromoAuthModalProps {
  isOpen: boolean;
  onClose: () => void;
  onSuccess: () => void;
}

export const SimplePromoAuthModal: React.FC<SimplePromoAuthModalProps> = ({
  isOpen,
  onClose,
  onSuccess,
}) => {
  const { showSuccess, showError } = useToast();
  const [password, setPassword] = useState('');
  const [showPassword, setShowPassword] = useState(false);
  const [loading, setLoading] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!password.trim()) {
      showError('请输入访问口令');
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
      showSuccess('板块已解锁');
      setPassword('');
      onSuccess();
      onClose();
    } catch (err: any) {
      showError(err.message || '口令错误，请重试');
    } finally {
      setLoading(false);
    }
  };

  return (
    <Dialog isOpen={isOpen} onClose={onClose} title="安全访问验证" width="440px">
      <div style={{ textAlign: 'center', marginBottom: '20px' }}>
        <div
          style={{
            width: '48px',
            height: '48px',
            borderRadius: '50%',
            backgroundColor: 'var(--primary-light)',
            color: 'var(--primary)',
            display: 'inline-flex',
            alignItems: 'center',
            justifyContent: 'center',
            marginBottom: '12px',
          }}
        >
          <Lock size={24} />
        </div>
        <h4 style={{ fontSize: '16px', fontWeight: 600, color: '#0f172a', marginBottom: '6px' }}>
          简单投暂停板块安全验证
        </h4>
        <p style={{ fontSize: '13px', color: '#64748b', lineHeight: 1.5 }}>
          由于暂停笔记投放涉及线上广告状态变更，需验证管理员安全口令后方可执行写操作。
        </p>
      </div>

      <form onSubmit={handleSubmit}>
        <div style={{ marginBottom: '20px' }}>
          <label
            style={{
              display: 'block',
              fontSize: '13px',
              fontWeight: 500,
              color: '#334155',
              marginBottom: '6px',
            }}
          >
            输入访问口令
          </label>
          <div style={{ position: 'relative' }}>
            <input
              type={showPassword ? 'text' : 'password'}
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              placeholder="请输入安全访问密码"
              autoFocus
              style={{
                width: '100%',
                padding: '9px 40px 9px 36px',
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
              title={showPassword ? '隐藏密码' : '显示密码'}
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

        <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '10px' }}>
          <button
            type="button"
            onClick={onClose}
            className="btn btn-secondary"
            style={{
              padding: '8px 16px',
              borderRadius: '6px',
              border: '1px solid #cbd5e1',
              backgroundColor: '#ffffff',
              cursor: 'pointer',
            }}
          >
            取消
          </button>
          <button
            type="submit"
            disabled={loading}
            className="btn btn-primary"
            style={{
              padding: '8px 20px',
              borderRadius: '6px',
              backgroundColor: 'var(--primary)',
              color: '#ffffff',
              border: 'none',
              cursor: 'pointer',
              fontWeight: 500,
            }}
          >
            {loading ? '验证中...' : '验证并解锁'}
          </button>
        </div>
      </form>
    </Dialog>
  );
};
