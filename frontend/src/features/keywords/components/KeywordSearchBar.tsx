import React from 'react';
import { Search, Plus, X, Calendar } from 'lucide-react';
import { Button } from '@/shared/components/Button';

export interface KeywordSearchBarProps {
  inputWord: string;
  setInputWord: (val: string) => void;
  selectedWords: string[];
  onAddWords: (text: string) => void;
  onRemoveWord: (word: string) => void;
  onClearWords: () => void;
  startDate: string;
  setStartDate: (val: string) => void;
  endDate: string;
  setEndDate: (val: string) => void;
  maxEndDate: string;
  isAfterNoon: boolean;
  onPresetDays: (days: number) => void;
  onSearch: () => void;
  isSearching: boolean;
}

export const KeywordSearchBar: React.FC<KeywordSearchBarProps> = ({
  inputWord,
  setInputWord,
  selectedWords,
  onAddWords,
  onRemoveWord,
  onClearWords,
  startDate,
  setStartDate,
  endDate,
  setEndDate,
  maxEndDate,
  isAfterNoon,
  onPresetDays,
  onSearch,
  isSearching,
}) => {
  return (
    <div
      style={{
        backgroundColor: '#ffffff',
        borderRadius: '12px',
        padding: '20px',
        border: '1px solid #e2e8f0',
        display: 'flex',
        flexDirection: 'column',
        gap: '16px',
      }}
    >
      <div style={{ display: 'flex', gap: '14px', alignItems: 'flex-start', flexWrap: 'wrap' }}>
        {/* 输入与 Chips 区 */}
        <div style={{ flex: 1, minWidth: '320px', display: 'flex', flexDirection: 'column', gap: '8px' }}>
          <div style={{ display: 'flex', gap: '8px' }}>
            <input
              type="text"
              placeholder="输入关键词（支持空格、回车或逗号分隔批量粘贴添加）"
              value={inputWord}
              onChange={(e) => setInputWord(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === 'Enter') {
                  e.preventDefault();
                  if (inputWord.trim()) onAddWords(inputWord);
                }
              }}
              onPaste={(e) => {
                const pasteText = e.clipboardData.getData('text');
                if (pasteText && (pasteText.includes(' ') || pasteText.includes(',') || pasteText.includes('\n'))) {
                  e.preventDefault();
                  onAddWords(pasteText);
                }
              }}
              style={{
                flex: 1,
                padding: '9px 14px',
                borderRadius: '6px',
                border: '1px solid #cbd5e1',
                fontSize: '14px',
                outline: 'none',
              }}
            />
            <Button
              variant="secondary"
              type="button"
              onClick={() => {
                if (inputWord.trim()) onAddWords(inputWord);
              }}
            >
              <Plus size={16} /> 添加
            </Button>
          </div>

          {/* Chips 列表 */}
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: '6px', minHeight: '32px', alignItems: 'center' }}>
            {selectedWords.map((w) => (
              <span
                key={w}
                style={{
                  display: 'inline-flex',
                  alignItems: 'center',
                  gap: '4px',
                  padding: '4px 10px',
                  borderRadius: '9999px',
                  fontSize: '12px',
                  fontWeight: 500,
                  backgroundColor: '#f1f5f9',
                  color: '#334155',
                  border: '1px solid #e2e8f0',
                }}
              >
                {w}
                <button
                  type="button"
                  onClick={() => onRemoveWord(w)}
                  style={{ background: 'none', border: 'none', cursor: 'pointer', color: '#94a3b8', display: 'flex' }}
                  aria-label={`移除 ${w}`}
                >
                  <X size={13} />
                </button>
              </span>
            ))}
            {selectedWords.length > 0 && (
              <button
                type="button"
                onClick={onClearWords}
                style={{
                  fontSize: '12px',
                  color: '#94a3b8',
                  background: 'none',
                  border: 'none',
                  cursor: 'pointer',
                  padding: '4px 8px',
                }}
              >
                清空 ({selectedWords.length})
              </button>
            )}
          </div>
        </div>

        {/* 日期选择区 */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: '8px', minWidth: '320px' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
            <input
              type="date"
              value={startDate}
              max={endDate}
              onChange={(e) => setStartDate(e.target.value)}
              style={{ padding: '8px 10px', borderRadius: '6px', border: '1px solid #cbd5e1', fontSize: '13px' }}
            />
            <span style={{ color: '#94a3b8' }}>至</span>
            <input
              type="date"
              value={endDate}
              max={maxEndDate}
              onChange={(e) => setEndDate(e.target.value)}
              style={{ padding: '8px 10px', borderRadius: '6px', border: '1px solid #cbd5e1', fontSize: '13px' }}
            />
          </div>
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
            <div style={{ display: 'flex', gap: '6px' }}>
              <Button size="sm" variant="ghost" onClick={() => onPresetDays(7)}>
                近7天
              </Button>
              <Button size="sm" variant="ghost" onClick={() => onPresetDays(30)}>
                近30天
              </Button>
              <Button size="sm" variant="ghost" onClick={() => onPresetDays(90)}>
                近90天
              </Button>
            </div>
            <span style={{ fontSize: '11px', color: '#ea580c', fontWeight: 500 }}>
              {isAfterNoon ? '今日 12:00 起支持 T-1 数据' : '中午 12:00 前支持 T-2 数据'}
            </span>
          </div>
        </div>

        {/* 查询按钮 */}
        <Button
          size="lg"
          variant="primary"
          onClick={onSearch}
          loading={isSearching}
          disabled={selectedWords.length === 0}
          style={{ height: '42px', padding: '0 22px' }}
        >
          <Search size={16} /> 查询数据
        </Button>
      </div>
    </div>
  );
};

