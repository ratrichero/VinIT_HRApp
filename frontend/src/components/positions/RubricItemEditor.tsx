'use client';

import { useState } from 'react';
import {
  Box, Button, Checkbox, Chip, Collapse, Divider, FormControlLabel, IconButton, MenuItem,
  Stack, TextField, Tooltip, Typography,
} from '@mui/material';
import HelpOutlineIcon from '@mui/icons-material/HelpOutline';
import ExpandMoreIcon from '@mui/icons-material/ExpandMore';
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
 * Loại tiêu chí — chính là ``requirement_spec.kind`` bên backend.
 *
 * Đây là thứ duy nhất trong ``requirement_spec`` mà HR cần chọn, vì nó quyết
 * định máy so kiểu gì: đếm số năm, so bằng cấp, đối chiếu ngoại ngữ, hay dò
 * thuật ngữ. Các trường còn lại (``terms``, ``min_years``, …) máy tự suy ra từ
 * tên + mô tả + từ khoá, nên không đưa ra cho HR sửa.
 */
const SPEC_KINDS = ['SKILL', 'YEARS', 'DEGREE', 'CERTIFICATION', 'LANGUAGE'] as const;
type SpecKind = (typeof SPEC_KINDS)[number];

/** Nhãn người đọc được cho từng loại. Không hiện mã ``SKILL``/``YEARS`` ra. */
const KIND_LABEL: Record<SpecKind, string> = {
  SKILL: 'Kỹ năng hoặc công nghệ',
  YEARS: 'Số năm kinh nghiệm',
  DEGREE: 'Bằng cấp',
  CERTIFICATION: 'Chứng chỉ',
  LANGUAGE: 'Ngoại ngữ',
};

/**
 * ``requirement_spec`` lưu dạng JSONB tự do. Form này chỉ sửa ``kind`` và giữ
 * nguyên phần còn lại, nên phải đọc được cả spec do AI sinh, spec cũ nhiều
 * khoá, và spec hỏng — không được để một khoá lạ làm trắng cả form.
 */
function specKindOf(spec: Record<string, unknown> | null): SpecKind {
  const raw = typeof spec?.kind === 'string' ? spec.kind.toUpperCase() : '';
  return (SPEC_KINDS as readonly string[]).includes(raw) ? (raw as SpecKind) : 'SKILL';
}

/**
 * Một tiêu chí trong cột của nó.
 *
 * Nguyên tắc hiển thị: **HR chỉ thấy thứ HR hiểu.** Ba trường máy tự suy ra
 * (``requirement_spec`` phần chi tiết, trọng số đã tính, từ khoá đã tách) không
 * bày ra thành ô nhập; chúng nằm trong khối "Tuỳ chọn nâng cao" đóng sẵn.
 *
 * Trước đây ô ``Requirement spec (JSON)`` bắt HR gõ JSON tay. Backend suy spec
 * từ tên + mô tả + từ khoá, nên bắt gõ JSON là vừa thừa vừa nguy hiểm: gõ sai
 * một dấu phẩy là không lưu được, mà gõ đúng thì cũng chỉ lặp lại thứ máy đã
 * suy ra.
 */
export default function RubricItemEditor({
  item,
  index,
  keywords,
  canEdit,
  onChange,
  onKeywordsChange,
  onRemove,
  onMove,
}: {
  item: RubricItem;
  index: number;
  keywords: string;
  canEdit: boolean;
  onChange: (patch: Partial<RubricItem>) => void;
  onKeywordsChange: (value: string) => void;
  onRemove: () => void;
  onMove: (direction: -1 | 1) => void;
}) {
  const { t } = useI18n();
  const [advanced, setAdvanced] = useState(false);
  const kind = specKindOf(item.requirement_spec);
  const keywordList = keywords.split(',').map(k => k.trim()).filter(Boolean);

  /** Đổi loại tiêu chí: giữ nguyên mọi khoá khác trong spec. */
  const changeKind = (next: SpecKind) => {
    const base = item.requirement_spec && typeof item.requirement_spec === 'object' ? item.requirement_spec : {};
    onChange({ requirement_spec: { ...base, kind: next } });
  };

  return (
    <Box sx={{ py: 1.5 }}>
      {/* ─── Dòng 1: số thứ tự + tên tiêu chí ─────────────────────────────── */}
      <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, mb: 1 }}>
        <Typography variant="body2" fontWeight={700} sx={{ flexShrink: 0, width: 20, color: 'text.secondary' }}>
          {index + 1}.
        </Typography>
        <TextField
          size="small"
          fullWidth
          label={t('Tên tiêu chí')}
          placeholder={t('Ví dụ: Kinh nghiệm phát triển API')}
          value={item.name}
          disabled={!canEdit}
          onChange={e => onChange({ name: e.target.value })}
        />
      </Box>

      {/* ─── Dòng 2: mô tả — đủ rộng, không bị ép cạnh ô khác ──────────────── */}
      <Box sx={{ pl: '28px', mb: 1.25 }}>
        <TextField
          size="small"
          fullWidth
          label={t('Mô tả tiêu chí')}
          placeholder={t('Viết như giải thích cho đồng nghiệp: tiêu chí này đạt khi nào?')}
          multiline
          minRows={2}
          value={item.description}
          disabled={!canEdit}
          onChange={e => onChange({ description: e.target.value })}
          helperText={t('Máy đọc tên và mô tả để tự suy ra cách so khớp. Không cần điền gì thêm.')}
          FormHelperTextProps={{ sx: { mx: 0 } }}
        />
      </Box>

      {/* ─── Dòng 3: trọng số + loại tiêu chí. Hai ô cùng bề rộng, thẳng hàng ─ */}
      <Box
        sx={{
          pl: '28px',
          display: 'grid',
          gap: 1.25,
          gridTemplateColumns: { xs: '1fr', sm: '130px minmax(0, 240px)' },
          alignItems: 'start',
          mb: 1.25,
        }}
      >
        <TextField
          size="small"
          type="number"
          label={t('Trọng số (%)')}
          value={item.weight_in_group}
          disabled={!canEdit}
          onChange={e => onChange({ weight_in_group: e.target.value })}
          inputProps={{ min: 0, max: 100, step: 5 }}
        />
        <TextField
          select
          size="small"
          label={t('Cách máy so khớp')}
          value={kind}
          disabled={!canEdit}
          onChange={e => changeKind(e.target.value as SpecKind)}
          helperText={t('Chọn kiểu bằng chứng cần tìm trong CV.')}
          FormHelperTextProps={{ sx: { mx: 0 } }}
        >
          {SPEC_KINDS.map(k => <MenuItem key={k} value={k}>{t(KIND_LABEL[k])}</MenuItem>)}
        </TextField>
      </Box>

      {/* ─── Dòng 4: từ khoá. Nhãn gọn, hướng dẫn nằm trong tooltip ─────────── */}
      <Box sx={{ pl: '28px', mb: 1 }}>
        <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.5, mb: 0.25 }}>
          <Typography variant="caption" sx={{ fontWeight: 600, color: 'text.secondary' }}>
            {t('Từ khoá bằng chứng')}
          </Typography>
          <Tooltip
            arrow
            title={t('Máy dò các từ này trong CV. Cách nhau bằng dấu phẩy, ví dụ: Python, FastAPI, PostgreSQL. Càng cụ thể càng tốt — tránh từ chung như "kinh nghiệm".')}
          >
            <IconButton size="small" sx={{ p: 0.25 }} aria-label={t('Từ khoá bằng chứng là gì?')}>
              <HelpOutlineIcon sx={{ fontSize: 15, color: 'text.disabled' }} />
            </IconButton>
          </Tooltip>
        </Box>
        <TextField
          size="small"
          fullWidth
          placeholder={t('Python, FastAPI, PostgreSQL')}
          value={keywords}
          disabled={!canEdit}
          onChange={e => onKeywordsChange(e.target.value)}
        />
        {/* Xem lại từ khoá đã tách: gõ thừa dấu phẩy hay dấu cách vẫn thấy đúng
            những gì máy sẽ dùng, không phải đoán. */}
        {keywordList.length > 0 && (
          <Stack direction="row" spacing={0.5} sx={{ flexWrap: 'wrap', gap: 0.5, mt: 0.75 }}>
            {keywordList.map(k => (
              <Chip key={k} size="small" label={k} sx={{ height: 20, fontSize: 11, backgroundColor: '#EEF3F9' }} />
            ))}
          </Stack>
        )}
      </Box>

      {/* ─── Bộ nút ────────────────────────────────────────────────────────── */}
      {canEdit && (
        <>
          <Divider sx={{ ml: '28px', mb: 0.5 }} />
          <Box sx={{ pl: '28px', display: 'flex', alignItems: 'center', gap: 0.5, flexWrap: 'wrap' }}>
            <Button size="small" onClick={() => onMove(-1)} disabled={index === 0}>{t('Lên')}</Button>
            <Button size="small" onClick={() => onMove(1)}>{t('Xuống')}</Button>
            <Button size="small" color="error" onClick={onRemove}>{t('Xoá tiêu chí')}</Button>
            <Button
              size="small"
              onClick={() => setAdvanced(v => !v)}
              endIcon={<ExpandMoreIcon sx={{ fontSize: 16, transform: advanced ? 'rotate(180deg)' : 'none', transition: 'transform .2s' }} />}
              sx={{ ml: 'auto', color: 'text.secondary' }}
            >
              {t('Tuỳ chọn nâng cao')}
            </Button>
          </Box>

          {/* Đóng sẵn: phần lớn rubric không cần tới. Chỉ mở khi HR muốn dặn
              người đọc bằng chứng cách tìm — nội dung này hiện ở trang chấm
              điểm để người đọc bằng chứng biết cần tìm gì trong CV. */}
          <Collapse in={advanced}>
            <Box sx={{ pl: '28px', pt: 1 }}>
              <TextField
                size="small"
                fullWidth
                multiline
                minRows={2}
                label={t('Dặn người đọc bằng chứng')}
                placeholder={t('Ví dụ: tìm tên dự án và số năm trong phần kinh nghiệm, không cộng trùng các giai đoạn chồng lấp.')}
                value={item.evidence_guidance || ''}
                disabled={!canEdit}
                onChange={e => onChange({ evidence_guidance: e.target.value || null })}
                helperText={t('Hiện ở trang chấm điểm để người đọc biết cần tìm gì. Không ảnh hưởng điểm số.')}
                FormHelperTextProps={{ sx: { mx: 0 } }}
              />
            </Box>
          </Collapse>
        </>
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
