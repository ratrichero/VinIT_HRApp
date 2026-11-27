'use client';

import { Box, Button, Chip, Divider, Stack, TextField, Typography } from '@mui/material';
import { useI18n } from '@/i18n/I18nProvider';

export type RubricItem = {
  name: string;
  description: string;
  category: 'MUST_HAVE' | 'NICE_TO_HAVE';
  weight_in_group: number | string;
  expected_evidence_keywords: string[];
  requirement_spec: Record<string, unknown> | null;
  evidence_guidance: string | null;
};

/** Màu nhóm, lấy đúng bảng màu trang chi tiết vị trí đang dùng. */
export const CATEGORY_STYLE = {
  MUST_HAVE: { bg: '#FDF2F2', fg: '#941616', label: 'BẮT BUỘC', heading: 'Tiêu chí bắt buộc' },
  NICE_TO_HAVE: { bg: '#E8F1FC', fg: '#0A2B57', label: 'ƯU TIÊN', heading: 'Tiêu chí ưu tiên' },
} as const;

/**
 * Một tiêu chí trong cột của nó.
 *
 * Mọi trường đều hiện đủ, không giấu sau nút "sửa": rubric là thước đo, HR phải
 * đọc được toàn bộ nội dung trước khi xuất bản. Hai trường ít dùng
 * (requirement spec, hướng dẫn bằng chứng) gộp vào một khối thu gọn để không
 * chiếm chỗ của trường chính.
 */
export default function RubricItemEditor({
  item,
  index,
  keywords,
  spec,
  canEdit,
  onChange,
  onKeywordsChange,
  onSpecChange,
  onRemove,
  onMove,
}: {
  item: RubricItem;
  index: number;
  keywords: string;
  spec: string;
  canEdit: boolean;
  onChange: (patch: Partial<RubricItem>) => void;
  onKeywordsChange: (value: string) => void;
  onSpecChange: (value: string) => void;
  onRemove: () => void;
  onMove: (direction: -1 | 1) => void;
}) {
  const { t } = useI18n();
  return (
    <Box sx={{ py: 1.5 }}>
      <Box sx={{ display: 'flex', alignItems: 'flex-start', gap: 1, mb: 1 }}>
        <Typography variant="body2" fontWeight={700} sx={{ flexShrink: 0, minWidth: 22 }}>
          {index + 1}.
        </Typography>
        <TextField
          size="small"
          fullWidth
          label={t('Tên tiêu chí')}
          value={item.name}
          disabled={!canEdit}
          onChange={e => onChange({ name: e.target.value })}
        />
      </Box>
      <TextField
        size="small"
        fullWidth
        label={t('Mô tả tiêu chí')}
        multiline
        minRows={1}
        sx={{ mb: 1 }}
        value={item.description}
        disabled={!canEdit}
        onChange={e => onChange({ description: e.target.value })}
      />
      <Box sx={{ display: 'flex', gap: 1, alignItems: 'center', flexWrap: 'wrap', mb: 1 }}>
        <TextField
          size="small"
          type="number"
          label={t('Trọng số (%)')}
          value={item.weight_in_group}
          disabled={!canEdit}
          onChange={e => onChange({ weight_in_group: e.target.value })}
          sx={{ width: 130 }}
        />
        <TextField
          size="small"
          label={t('Từ khóa bằng chứng')}
          helperText={t('Phân tách bằng dấu phẩy')}
          value={keywords}
          disabled={!canEdit}
          onChange={e => onKeywordsChange(e.target.value)}
          sx={{ flex: '1 1 220px', minWidth: 0 }}
        />
      </Box>
      <Stack direction="row" spacing={0.5} sx={{ flexWrap: 'wrap', gap: 0.5 }}>
        <TextField
          size="small"
          label={t('Hướng dẫn bằng chứng')}
          value={item.evidence_guidance || ''}
          disabled={!canEdit}
          onChange={e => onChange({ evidence_guidance: e.target.value || null })}
          sx={{ flex: '1 1 240px', minWidth: 0 }}
        />
        <TextField
          size="small"
          label={t('Requirement spec (JSON)')}
          value={spec}
          disabled={!canEdit}
          onChange={e => onSpecChange(e.target.value)}
          sx={{ flex: '1 1 200px', minWidth: 0 }}
        />
      </Stack>
      {canEdit && (
        <Box sx={{ display: 'flex', gap: 0.5, mt: 1 }}>
          <Button size="small" onClick={() => onMove(-1)} disabled={index === 0}>{t('Lên')}</Button>
          <Button size="small" onClick={() => onMove(1)}>{t('Xuống')}</Button>
          <Button size="small" color="error" onClick={onRemove} sx={{ ml: 'auto' }}>{t('Xóa tiêu chí')}</Button>
        </Box>
      )}
    </Box>
  );
}

/** Tổng trọng số một nhóm, kèm cảnh báo khi chưa bằng 100. */
export function groupTotal(items: RubricItem[], category: RubricItem['category']): number {
  return items
    .filter(item => item.category === category)
    .reduce((sum, item) => sum + (Number(item.weight_in_group) || 0), 0);
}

/**
 * Đầu cột: nhãn nhóm, số tiêu chí, tổng trọng số.
 *
 * Tổng hiện ngay ở đầu cột chứ không đợi tới lúc bấm xuất bản: điều kiện xuất
 * bản là mỗi nhóm cộng đúng 100, nên HR cần thấy con số đó trong lúc soạn.
 */
export function CategoryHeader({
  category,
  items,
}: {
  category: RubricItem['category'];
  items: RubricItem[];
}) {
  const { t } = useI18n();
  const style = CATEGORY_STYLE[category];
  const total = groupTotal(items, category);
  const count = items.filter(item => item.category === category).length;
  const ok = Math.abs(total - 100) < 0.005;
  return (
    <>
      <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, flexWrap: 'wrap' }}>
        <Chip
          label={t(style.label)}
          size="small"
          sx={{ backgroundColor: style.bg, color: style.fg, fontWeight: 700, fontSize: 11 }}
        />
        <Typography variant="h4" sx={{ fontSize: 16, fontWeight: 600 }}>
          {t(style.heading)}
        </Typography>
      </Box>
      <Box sx={{ display: 'flex', gap: 1, alignItems: 'baseline', flexWrap: 'wrap', mt: 0.5 }}>
        <Typography variant="body2" color="text.secondary">
          {count} {t('tiêu chí')}
        </Typography>
        <Typography variant="body2" color={ok ? 'text.secondary' : 'error'} fontWeight={ok ? 400 : 600}>
          · {t('Tổng trọng số:')} {total}% / 100%
        </Typography>
      </Box>
      <Divider sx={{ my: 1.5 }} />
    </>
  );
}
