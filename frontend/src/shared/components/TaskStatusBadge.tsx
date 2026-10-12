import React, { useState, useRef, useEffect } from 'react';
import { createPortal } from 'react-dom';
import { AlertCircle } from 'lucide-react';

interface TaskStatusBadgeProps {
  status: 'success' | 'failed' | 'running' | string;
  error?: string | null;
  style?: React.CSSProperties;
}

export const TaskStatusBadge: React.FC<TaskStatusBadgeProps> = ({ status, error, style }) => {
  const norm = (status || '').toLowerCase();
  const [isHovered, setIsHovered] = useState(false);
  const [coords, setCoords] = useState<{ top: number; left: number; placement: 'top' | 'bottom' } | null>(null);
  const badgeRef = useRef<HTMLSpanElement>(null);

  const isSuccess = norm === 'success';
  const isFailed = norm === 'failed';

  const updatePosition = () => {
    if (!badgeRef.current) return;
    const rect = badgeRef.current.getBoundingClientRect();
    const showBelow = rect.top < 150;
    const screenW = window.innerWidth;
    const left = Math.max(180, Math.min(screenW - 180, rect.left + rect.width / 2));
    setCoords({
      top: showBelow ? rect.bottom + 8 : rect.top - 8,
      left,
      placement: showBelow ? 'bottom' : 'top',
    });
  };

  const handleMouseEnter = () => {
    updatePosition();
    setIsHovered(true);
  };

  const handleMouseLeave = () => {
    setIsHovered(false);
  };

  useEffect(() => {
    if (isHovered) {
      const handleScroll = () => updatePosition();
      window.addEventListener('scroll', handleScroll, true);
      window.addEventListener('resize', handleScroll);
      return () => {
        window.removeEventListener('scroll', handleScroll, true);
        window.removeEventListener('resize', handleScroll);
      };
    }
  }, [isHovered]);

  if (isSuccess) {
    return (
      <span className="badge badge-success" style={{ marginTop: '2px', ...style }}>
        成功
      </span>
    );
  }

  if (isFailed) {
    const errorText = error || '任务执行失败，无详细错误信息';

    // 解析 JSON 响应中的中文错误提示和 traceId
    let summary = '';
    let traceId = '';
    const jsonMatch = errorText.match(/\{[\s\S]*"msg"\s*:\s*"([^"]+)"[\s\S]*\}/);
    if (jsonMatch) {
      try {
        const parsed = JSON.parse(jsonMatch[0]);
        if (parsed.msg) summary = parsed.msg;
        if (parsed.traceId) traceId = parsed.traceId;
      } catch {
        // 忽略解析异常
      }
    }

    return (
      <>
        <span
          ref={badgeRef}
          className="badge badge-danger"
          style={{
            marginTop: '2px',
            cursor: 'pointer',
            display: 'inline-flex',
            alignItems: 'center',
            gap: '3px',
            ...style,
          }}
          onMouseEnter={handleMouseEnter}
          onMouseLeave={handleMouseLeave}
        >
          <AlertCircle size={12} style={{ flexShrink: 0 }} />
          <span>失败</span>
        </span>

        {isHovered && coords && createPortal(
          <div
            style={{
              position: 'fixed',
              top: coords.top,
              left: coords.left,
              transform: coords.placement === 'bottom' ? 'translate(-50%, 0)' : 'translate(-50%, -100%)',
              zIndex: 999999,
              maxWidth: '460px',
              minWidth: '240px',
              padding: '12px 14px',
              background: '#0f172a',
              color: '#f8fafc',
              borderRadius: '8px',
              boxShadow: '0 20px 25px -5px rgba(0, 0, 0, 0.4), 0 8px 10px -6px rgba(0, 0, 0, 0.3)',
              border: '1px solid #334155',
              fontSize: '12px',
              lineHeight: '1.5',
              wordBreak: 'break-word',
              whiteSpace: 'pre-wrap',
              pointerEvents: 'none',
              animation: 'uiFadeUp 0.15s ease-out',
            }}
          >
            <div style={{ display: 'flex', alignItems: 'center', gap: '6px', fontWeight: 600, color: '#f87171', marginBottom: '6px' }}>
              <AlertCircle size={14} />
              <span>失败原因：{summary || '任务执行报错'}</span>
            </div>

            {traceId && (
              <div style={{ color: '#94a3b8', fontSize: '11px', marginBottom: '6px' }}>
                请求追踪 ID (traceId): <code style={{ color: '#cbd5e1' }}>{traceId}</code>
              </div>
            )}

            <div style={{ color: '#cbd5e1', fontSize: '11.5px', background: '#1e293b', padding: '6px 8px', borderRadius: '4px', border: '1px solid #334155' }}>
              {errorText}
            </div>

            {/* 气泡箭头 */}
            <div
              style={{
                position: 'absolute',
                left: '50%',
                transform: 'translateX(-50%)',
                width: 0,
                height: 0,
                borderLeft: '6px solid transparent',
                borderRight: '6px solid transparent',
                ...(coords.placement === 'bottom'
                  ? { bottom: '100%', borderBottom: '6px solid #0f172a' }
                  : { top: '100%', borderTop: '6px solid #0f172a' }),
              }}
            />
          </div>,
          document.body
        )}
      </>
    );
  }

  return (
    <span className="badge badge-gray" style={{ marginTop: '2px', ...style }}>
      {status || '-'}
    </span>
  );
};
