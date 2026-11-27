'use client';

import { useState } from 'react';
import {
  Alert, Box, Button, Chip, Collapse, Divider, IconButton, MenuItem, Stack, TextField, Tooltip, Typography,
} from '@mui/material';
import HelpOutlineIcon from '@mui/icons-material/HelpOutline';
import ExpandMoreIcon from '@mui/icons-material/ExpandMore';
import { useI18n } from '@/i18n/I18nProvider';
import { rubricApi } from '@/lib/api';

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
 * Đây là thứ duy nhất HR cần *chọn*. Ngưỡng đi kèm (số năm, bậc bằng, mức
 * ngoại ngữ) thì HR chỉ *sửa lại* giá trị máy đã suy ra — cùng cách trang chi
 * tiết vị trí đang làm, để hai trang không dạy HR hai kiểu khác nhau.
 */
const SPEC_KINDS = ['SKILL', 'YEARS', 'DEGREE', 'CERTIFICATION', 'LANGUAGE'] as const;
type SpecKind = (typeof SPEC_KINDS)[number];

const KIND_LABEL: Record<SpecKind, string> = {
  SKILL: 'Kỹ năng hoặc công nghệ',
  YEARS: 'Số năm kinh nghiệm',
  DEGREE: 'Bằng cấp',
  CERTIFICATION: 'Chứng chỉ',
  LANGUAGE: 'Ngoại ngữ',
};

/** Đọc ``kind`` từ spec dạng JSONB tự do; spec hỏng thì coi như SKILL. */
function specKindOf(spec: Record<string, unknown> | null): SpecKind {
  const raw = typeof spec?.kind === 'string' ? spec.kind.toUpperCase() : '';
  return (SPEC_KINDS as readonly string[]).includes(raw) ? (raw as SpecKind) : 'SKILL';
}

function numberOf(value: unknown): string {
  return typeof value === 'number' && Number.isFinite(value) ? String(value) : '';
}

/**
 * Dựng spec gửi lên máy chủ từ thứ HR nhìn thấy.
 *
 * Vì sao phải dựng chứ không gửi nguyên ``item.requirement_spec``: khi HR vừa
 * bấm chọn loại trên một tiêu chí chưa có spec, object chỉ có ``{kind}`` —
 * schema từ chối spec không nói được gì (xem ``RequirementSpec.
 * reject_completely_empty_spec``). Nên luôn kèm ``terms`` lấy từ từ khoá, hoặc
 * từ tên tiêu chí nếu chưa có từ khoá nào.
 */
export function buildSpec(item: RubricItem, keywords: string): Record<string, unknown> | null {
  const base = item.requirement_spec && typeof item.requirement_spec === 'object' ? item.requirement_spec : null;
  const kind = specKindOf(base);
  const terms = keywords.split(',').map(k => k.trim()).filter(Boolean);
  const effectiveTerms = terms.length > 0 ? terms : (item.name.trim() ? [item.name.trim()] : []);

  // Chưa có spec và cũng không có gì để dò: gửi null để máy tự suy từ chữ,
  // thay vì gửi một spec rỗng mà schema sẽ từ chối.
  if (!base && effectiveTerms.length === 0) return null;
  if (!base) return { kind, terms: effectiveTerms };

  const spec: Record<string, unknown> = { ...base, kind };
  // ``terms`` trong spec là thứ máy thực sự dò. Giữ đồng bộ với ô từ khoá để
  // HR không phải sửa hai nơi cho cùng một danh sách.
  spec.terms = effectiveTerms;
  if (kind !== 'YEARS') spec.min_years = null;
  if (kind !== 'DEGREE') spec.required_degree_level = null;
  if (kind !== 'LANGUAGE') {
    spec.required_languages = [];
    spec.required_ielts = null;
    spec.required_toeic = null;
    spec.required_cefr = null;
    spec.required_language_rank = null;
  }
  return spec;
}

/**
 * Một tiêu chí trong cột của nó.
 *
 * Nguyên tắc hiển thị: **HR chỉ thấy thứ HR hiểu.**
 *
 * * ``requirement_spec`` không còn là ô JSON. HR chọn *loại* bằng nhãn đọc
 *   được, và chỉ khi loại đó cần ngưỡng thì ô ngưỡng mới hiện ra — kèm sẵn giá
 *   trị máy đã suy ra từ tên + mô tả, để HR sửa chứ không phải nghĩ.
 * * ``evidence_guidance`` thu vào "Tuỳ chọn nâng cao" đóng sẵn: engine chấm
 *   điểm không đọc trường này, nó chỉ hiện ở trang bằng chứng để người đọc biết
 *   cần tìm gì.
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
  const [resyncing, setResyncing] = useState(false);
  const [resyncError, setResyncError] = useState('');
  const spec = item.requirement_spec && typeof item.requirement_spec === 'object' ? item.requirement_spec : null;
  const kind = specKindOf(spec);
  const keywordList = keywords.split(',').map(k => k.trim()).filter(Boolean);

  /** Đổi một khoá trong spec, giữ nguyên phần còn lại. */
  const patchSpec = (patch: Record<string, unknown>) => {
    onChange({ requirement_spec: { ...(spec || {}), ...patch } });
  };

  /**
   * Hỏi máy xem nó sẽ so khớp tiêu chí này theo cách nào, rồi áp vào form.
   *
   * Chỉ chạy khi HR bấm — cố ý không tự động theo mỗi lần gõ. Spec đi thẳng vào
   * điểm số, nên nó chỉ được đổi khi có người chủ động quyết. Tự ghi đè sau
   * lưng nghĩa là sửa một câu mô tả có thể âm thầm đổi ngưỡng của tiêu chí đã
   * duyệt.
   */
  const resync = async (keepKind?: SpecKind) => {
    if (!canEdit || resyncing) return;
    setResyncing(true); setResyncError('');
    try {
      const { data } = await rubricApi.previewSpec({
        name: item.name.trim(),
        description: item.description.trim(),
        expected_evidence_keywords: keywordList,
      });
      const inferred = data.requirement_spec as Record<string, unknown>;
      // Giữ loại HR vừa chọn: máy có thể suy ra loại khác (ví dụ mô tả nêu cả
      // số năm lẫn bằng cấp), nhưng ý người dùng phải thắng.
      onChange({ requirement_spec: keepKind ? { ...inferred, kind: keepKind } : inferred });
    } catch (err: any) {
      setResyncError(err.response?.data?.detail || t('Không suy lại được.'));
    } finally {
      setResyncing(false);
    }
  };

  /**
   * Đổi loại tiêu chí.
   *
   * Vì sao phải hỏi máy chủ ngay tại đây: schema (cố ý, theo audit M1) từ chối
   * tiêu chí YEARS không có `min_years`, DEGREE không có bậc, LANGUAGE không có
   * mức. Nên nếu HR chọn YEARS trên một tiêu chí chưa có ngưỡng mà form gửi
   * thẳng `{kind:'YEARS'}` thì lần Lưu kế tiếp sẽ 422 — đúng lỗi đã xảy ra.
   *
   * Cách sửa: chọn loại xong thì hỏi máy nó suy ra ngưỡng gì từ tên + mô tả,
   * điền sẵn cho HR xem và sửa. HR vẫn là người quyết cuối; form chỉ không để
   * họ rơi vào trạng thái không lưu được.
   *
   * Nếu máy cũng không suy ra được (mô tả không nêu con số), ô ngưỡng hiện ra
   * trống kèm lời nhắc — vẫn không gửi lên được cho tới khi HR điền. Đó là hành
   * vi đúng: tiêu chí "số năm" mà không nêu số năm thì chưa phải tiêu chí.
   */
  const changeKind = async (next: SpecKind) => {
    const base: Record<string, unknown> = { ...(spec || {}), kind: next };
    if (next !== 'YEARS') base.min_years = null;
    if (next !== 'DEGREE') base.required_degree_level = null;
    if (next !== 'LANGUAGE') {
      base.required_languages = [];
      base.required_ielts = null;
      base.required_toeic = null;
      base.required_cefr = null;
      base.required_language_rank = null;
    }
    onChange({ requirement_spec: base });
    // Loại mới cần ngưỡng mà chưa có: mượn luôn đường suy luận của nút
    // "Suy lại", chỉ để điền sẵn — không ghi đè thứ HR đã nhập.
    const needsThreshold = (
      (next === 'YEARS' && base.min_years == null)
      || (next === 'DEGREE' && base.required_degree_level == null)
      || (next === 'LANGUAGE' && !(base.required_languages as string[] | undefined)?.length
          && base.required_ielts == null)
    );
    if (needsThreshold) await resync(next);
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

      {/* ─── Dòng 2: mô tả — một hàng riêng, đủ rộng ──────────────────────── */}
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
          helperText={t('Máy đọc tên và mô tả để tự suy ra cách so khớp.')}
          FormHelperTextProps={{ sx: { mx: 0 } }}
        />
      </Box>

      {/* ─── Dòng 3: trọng số + loại tiêu chí, thẳng hàng trên lưới ────────── */}
      <Box
        sx={{
          pl: '28px',
          display: 'grid',
          gap: 1.25,
          gridTemplateColumns: { xs: '1fr', sm: '130px minmax(0, 260px)' },
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
          InputLabelProps={{ shrink: true }}
          SelectProps={{
            MenuProps: { PaperProps: { sx: { '& .MuiMenuItem-root': { minHeight: 36 } } } },
          }}
        >
          {SPEC_KINDS.map(k => <MenuItem key={k} value={k}>{t(KIND_LABEL[k])}</MenuItem>)}
        </TextField>
      </Box>

      {/* ─── Dòng 4: ngưỡng — chỉ hiện khi loại cần, và chỉ hiện thứ liên quan ─ */}
      {canEdit && kind === 'YEARS' && (
        <Box sx={{ pl: '28px', mb: 1.25 }}>
          <TextField
            size="small"
            type="number"
            label={t('Số năm tối thiểu')}
            value={numberOf(spec?.min_years)}
            onChange={e => patchSpec({ min_years: e.target.value === '' ? null : Number(e.target.value) })}
            inputProps={{ min: 0, max: 80, step: 0.5 }}
            helperText={spec?.min_years == null
              ? t('Chưa có ngưỡng. Máy sẽ dò theo số năm ghi trong mô tả.')
              : undefined}
            FormHelperTextProps={{ sx: { mx: 0 } }}
            sx={{ width: { xs: '100%', sm: 220 } }}
          />
        </Box>
      )}

      {canEdit && kind === 'DEGREE' && (
        <Box sx={{ pl: '28px', mb: 1.25 }}>
          <TextField
            select
            size="small"
            label={t('Bậc bằng tối thiểu')}
            value={numberOf(spec?.required_degree_level)}
            onChange={e => patchSpec({ required_degree_level: e.target.value === '' ? null : Number(e.target.value) })}
            helperText={spec?.required_degree_level == null
              ? t('Chưa có ngưỡng. Để trống thì tiêu chí chỉ dò từ khoá.')
              : undefined}
            FormHelperTextProps={{ sx: { mx: 0 } }}
            sx={{ width: { xs: '100%', sm: 260 } }}
          >
            <MenuItem value="">{t('Chưa chọn')}</MenuItem>
            <MenuItem value={1}>{t('Trung học phổ thông')}</MenuItem>
            <MenuItem value={2}>{t('Cao đẳng')}</MenuItem>
            <MenuItem value={3}>{t('Đại học')}</MenuItem>
            <MenuItem value={4}>{t('Thạc sĩ')}</MenuItem>
            <MenuItem value={5}>{t('Tiến sĩ')}</MenuItem>
          </TextField>
        </Box>
      )}

      {canEdit && kind === 'LANGUAGE' && (
        <Box sx={{ pl: '28px', mb: 1.25, display: 'grid', gap: 1.25, gridTemplateColumns: { xs: '1fr', sm: '1fr 1fr' }, maxWidth: { sm: 520 } }}>
          <TextField
            size="small"
            label={t('Ngôn ngữ')}
            placeholder={t('Tiếng Anh, Tiếng Nhật')}
            value={Array.isArray(spec?.required_languages) ? (spec!.required_languages as string[]).join(', ') : ''}
            onChange={e => patchSpec({
              required_languages: e.target.value.split(',').map(v => v.trim()).filter(Boolean),
            })}
          />
          <TextField
            size="small"
            type="number"
            label={t('IELTS tối thiểu')}
            value={numberOf(spec?.required_ielts)}
            onChange={e => patchSpec({ required_ielts: e.target.value === '' ? null : Number(e.target.value) })}
            inputProps={{ min: 0, max: 9, step: 0.5 }}
          />
        </Box>
      )}

      {/* ─── Dòng 5: từ khoá — nhãn gọn, hướng dẫn trong tooltip ────────────── */}
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
            <Button size="small" onClick={() => void resync()} disabled={resyncing || !item.name.trim()}>
              {resyncing ? t('Đang suy lại…') : t('Suy lại từ tên + mô tả')}
            </Button>
            <Button
              size="small"
              onClick={() => setAdvanced(v => !v)}
              endIcon={<ExpandMoreIcon sx={{ fontSize: 16, transform: advanced ? 'rotate(180deg)' : 'none', transition: 'transform .2s' }} />}
              sx={{ ml: 'auto', color: 'text.secondary' }}
            >
              {t('Tuỳ chọn nâng cao')}
            </Button>
          </Box>

          {resyncError && (
            <Alert severity="error" sx={{ ml: '28px', mt: 0.5 }} onClose={() => setResyncError('')}>
              {resyncError}
            </Alert>
          )}

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
