import React, { useState } from 'react';
import { X, Plus } from 'lucide-react';

export interface KeywordEditorProps {
  keywords: string[];
  onChange: (keywords: string[]) => void;
  label?: string;
}

export const KeywordEditor: React.FC<KeywordEditorProps> = ({
  keywords,
  onChange,
  label = '监控关键词',
}) => {
  const [inputText, setInputText] = useState('');

  const handleAdd = () => {
    if (!inputText.trim()) return;
    const splitWords = inputText
      .replace(/[,，\n\r\t]+/g, ' ')
      .split(' ')
      .map((w) => w.trim())
      .filter(Boolean);
    if (splitWords.length === 0) return;

    const seen = new Set(keywords);
    const added: string[] = [];
    for (const w of splitWords) {
      if (!seen.has(w)) {
        seen.add(w);
        added.push(w);
      } 
    }
    if (added.length > 0) {
      onChange([...keywords, ...added]);
    }
    setInputText('');
  };

  const handleRemove = (wordToRemove: string) => {
    onChange(keywords.filter((w) => w !== wordToRemove));
  };

  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '8px' }}>
        <label style={{ fontSize: '13px', fontWeight: 600, color: '#334155' }}>
          {label} <span style={{ fontWeight: 400, color: '#64748b' }}>({keywords.length} 个)</span>
        </label>
        {keywords.length > 0 && (
          <button
            type="button"
            onClick={() => onChange([])}
            style={{ fontSize: '12px', color: '#f53f3f', background: 'none', border: 'none', cursor: 'pointer' }}
          >
            清空所有
          </button>
        )}
      </div>

      {/* 关键词标签列表 */}
      <div
        style={{
          maxHeight: '150px',
          overflowY: 'auto',
          padding: '8px',
          background: '#f8fafc',
          border: '1px solid #e2e8f0',
          borderRadius: '6px',
          display: 'flex',
          flexWrap: 'wrap',
          gap: '6px',
          marginBottom: '10px',
        }}
      >
        {keywords.length === 0 ? (
          <span style={{ fontSize: '12px', color: '#94a3b8', padding: '4px' }}>暂无监控关键词，请在下方添加</span>
        ) : (
          keywords.map((kw) => (
            <span
              key={kw}
              style={{
                display: 'inline-flex',
                alignItems: 'center',
                gap: '4px',
                padding: '3px 8px',
                fontSize: '12px',
                background: '#ffffff',
                border: '1px solid #cbd5e1',
                borderRadius: '4px',
                color: '#1e293b',
              }}
            >
              <span>{kw}</span>
              <button
                type="button"
                onClick={() => handleRemove(kw)}
                style={{
                  background: 'none',
                  border: 'none',
                  color: '#94a3b8',
                  cursor: 'pointer',
                  padding: 0,
                  display: 'flex',
                  alignItems: 'center',
                }}
                title={`删除 ${kw}`}
              >
                <X size={13} style={{ color: '#ef4444' }} />
              </button>
            </span>
          ))
        )}
      </div>

      {/* 批量添加关键词输入框 */}
      <div style={{ display: 'flex', gap: '8px' }}>
        <input
          type="text"
          placeholder="输入新关键词，多个词可用空格、逗号分隔..."
          value={inputText}
          onChange={(e) => setInputText(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === 'Enter') {
              e.preventDefault();
              handleAdd();
            }
          }}
          style={{
            flex: 1,
            height: '34px',
            padding: '0 10px',
            fontSize: '13px',
            border: '1px solid #cbd5e1',
            borderRadius: '6px',
            outline: 'none',
          }}
        />
        <button
          type="button"
          onClick={handleAdd}
          style={{
            padding: '0 12px',
            height: '34px',
            fontSize: '13px',
            fontWeight: 500,
            background: '#ffffff',
            border: '1px solid #cbd5e1',
            borderRadius: '6px',
            cursor: 'pointer',
            display: 'inline-flex',
            alignItems: 'center',
            gap: '4px',
            color: '#1e293b',
          }}
        >
          <Plus size={14} /> 添加词
        </button>
      </div>
    </div>
  );
};
