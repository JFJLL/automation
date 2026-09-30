import React from 'react';

export interface PlatformSelectorProps {
  platform: string;
  setPlatform: (val: string) => void;
  subAccountId: string;
  setSubAccountId: (val: string) => void;
  subaccounts: Array<{ id: string; name: string }>;
  disabled?: boolean;
}

export const PlatformSelector: React.FC<PlatformSelectorProps> = ({
  platform,
  setPlatform,
  subAccountId,
  setSubAccountId,
  subaccounts,
  disabled,
}) => {
  return (
    <div style={{ backgroundColor: '#ffffff', borderRadius: '12px', padding: '20px', border: '1px solid #e2e8f0' }}>
      <h3 style={{ fontSize: '15px', fontWeight: 600, color: '#0f172a', marginBottom: '14px' }}>
        1. 选择数据源平台
      </h3>
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: '14px' }}>
        {[
          { id: 'jzt', name: '京准通 (京东)', desc: '按达人/推广单元任务同步' },
          { id: 'taobao', name: '淘宝星河', desc: '红宝/星河内容与订单归因' },
          { id: 'juguang', name: '小红书聚光', desc: '支持多子账号广告报表' },
        ].map((p) => {
          const isSel = platform === p.id;
          return (
            <div
              key={p.id}
              onClick={() => !disabled && setPlatform(p.id)}
              style={{
                padding: '16px',
                borderRadius: '8px',
                cursor: disabled ? 'default' : 'pointer',
                border: '2px solid ' + (isSel ? '#ea3445' : '#e2e8f0'),
                backgroundColor: isSel ? '#fef2f2' : '#ffffff',
                transition: 'all 0.15s ease',
              }}
            >
              <div style={{ fontWeight: 600, fontSize: '15px', color: isSel ? '#ea3445' : '#0f172a' }}>
                {p.name}
              </div>
              <div style={{ fontSize: '12px', color: '#64748b', marginTop: '4px' }}>{p.desc}</div>
            </div>
          );
        })}
      </div>

      {platform === 'juguang' && (
        <div style={{ marginTop: '16px', display: 'flex', flexDirection: 'column', gap: '6px' }}>
          <label style={{ fontSize: '13px', fontWeight: 600, color: '#334155' }}>聚光子账号</label>
          <select
            value={subAccountId}
            onChange={(e) => setSubAccountId(e.target.value)}
            disabled={disabled}
            style={{
              padding: '8px 12px',
              borderRadius: '6px',
              border: '1px solid #cbd5e1',
              fontSize: '14px',
              maxWidth: '400px',
            }}
          >
            <option value="">默认主账号 / 全局凭据</option>
            {subaccounts.map((s) => (
              <option key={s.id} value={s.id}>
                {s.name} ({s.id})
              </option>
            ))}
          </select>
        </div>
      )}
    </div>
  );
};

