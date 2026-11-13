'use client';

import { useEffect, useState } from 'react';
import { Alert, Autocomplete, Box, Button, Checkbox, CircularProgress, Dialog, DialogActions, DialogContent, DialogTitle, FormControlLabel, TextField, Typography } from '@mui/material';
import { positionsApi, usersApi } from '@/lib/api';
import { useI18n } from '@/i18n/I18nProvider';

type Person = { user_id: string; display_name: string; account_status?: string; version?: string };

export default function HiringManagerChange({ positionId, onChanged }: { positionId: string; onChanged: () => Promise<void> }) {
  const { t } = useI18n();
  const [open, setOpen] = useState(false);
  const [current, setCurrent] = useState<Person[] | null>(null);
  const [options, setOptions] = useState<Person[]>([]);
  const [selected, setSelected] = useState<Person | null>(null);
  const [search, setSearch] = useState('');
  const [loading, setLoading] = useState(false);
  const [searching, setSearching] = useState(false);
  const [saving, setSaving] = useState(false);
  const [confirmed, setConfirmed] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<'changed' | 'unchanged' | null>(null);

  useEffect(() => {
    if (!open) return;
    let live = true;
    setLoading(true); setCurrent(null); setError(null); setSelected(null); setSearch(''); setConfirmed(false);
    positionsApi.getHiringManagers(positionId).then(res => { if (live) setCurrent(res.data); })
      .catch(err => { if (live) setError(typeof err.response?.data?.detail === 'string' ? t(err.response.data.detail) : t("Không thể tải Hiring Manager hiện tại.")); })
      .finally(() => { if (live) setLoading(false); });
    return () => { live = false; };
  }, [open, positionId, t]);

  useEffect(() => {
    if (!open) return;
    let live = true;
    setSearching(true);
    const timer = window.setTimeout(() => {
      usersApi.list({ role: 'HIRING_MANAGER', search: search.trim() || undefined })
        .then(res => { if (live) setOptions(res.data || []); })
        .catch(() => { if (live) { setOptions([]); setError(t("Không thể tải danh sách Hiring Manager.")); } })
        .finally(() => { if (live) setSearching(false); });
    }, 200);
    return () => { live = false; window.clearTimeout(timer); };
  }, [open, search, t]);

  const submit = async () => {
    if (!selected || current === null || !confirmed || saving) return;
    setSaving(true); setError(null);
    try {
      const result = await positionsApi.changeHiringManager(positionId, selected.user_id, current.map(person => person.version || ''));
      setOpen(false); setSuccess(result.data.changed ? 'changed' : 'unchanged');
      await onChanged();
    } catch (err: any) {
      if (err.response?.status === 409) setCurrent(null);
      const detail = err.response?.data?.detail;
      setError((typeof detail === 'string' ? t(detail) : t("Không thể đổi Hiring Manager. Vui lòng thử lại.")) + (err.response?.status === 409 ? ` ${t("Đóng và mở lại hộp thoại để tải dữ liệu mới.")}` : ''));
    } finally { setSaving(false); }
  };
  return <Box>
    <Button variant="outlined" onClick={() => { setSuccess(null); setOpen(true); }}>{t("Đổi Hiring Manager")}</Button>
    {success && <Alert severity="success" onClose={() => setSuccess(null)} sx={{ mt: 1 }}>{success === 'changed' ? t("Đã cập nhật Hiring Manager. Hãy chia sẻ shortlist mới nếu cần.") : t("Hiring Manager không thay đổi; các shortlist hiện tại vẫn giữ nguyên.")}</Alert>}
    <Dialog open={open} onClose={() => !saving && setOpen(false)} maxWidth="sm" fullWidth>
      <DialogTitle>{t("Đổi Hiring Manager")}</DialogTitle>
      <DialogContent>
        <Alert severity="warning" sx={{ mb: 2 }}>{t("Shortlist đang chia sẻ cho HM cũ sẽ bị thu hồi; phản hồi và lịch sử được giữ. HM mới không tự nhận shortlist: HR cần chia sẻ lại. Các quyền khác được cấp riêng không tự thu hồi.")}</Alert>
        <Typography variant="body2" sx={{ mb: 2 }}>{t("Hiring Manager hiện tại")}: {loading ? '…' : current === null ? '—' : current.length ? current.map(person => person.display_name).join(', ') : t("Chưa có")}</Typography>
        <Autocomplete options={options} value={selected} loading={searching} inputValue={search} onInputChange={(_, value) => setSearch(value)}
          onChange={(_, value) => setSelected(value)} getOptionLabel={option => option.display_name || ''} isOptionEqualToValue={(a, b) => a.user_id === b.user_id}
          noOptionsText={t("Không tìm thấy Hiring Manager đang hoạt động")}
          renderInput={params => <TextField {...params} label={t("Hiring Manager mới")} placeholder={t("Nhập tên để tìm")} margin="dense" InputProps={{ ...params.InputProps, endAdornment: <>{searching && <CircularProgress size={18} />}{params.InputProps.endAdornment}</> }} />} />
        <Typography variant="caption" color="text.secondary">{t("Chỉ chọn tài khoản HM đang hoạt động, khác HR phụ trách. Tiêu chí đã duyệt và lịch sử phê duyệt không thay đổi.")}</Typography>
        <FormControlLabel control={<Checkbox checked={confirmed} onChange={e => setConfirmed(e.target.checked)} />} label={t("Tôi hiểu các shortlist cũ sẽ bị thu hồi và cần chia sẻ lại.")} sx={{ mt: 1 }} />
        {error && <Alert severity="error" sx={{ mt: 1 }}>{error}</Alert>}
      </DialogContent>
      <DialogActions><Button disabled={saving} onClick={() => setOpen(false)}>{t("Hủy")}</Button><Button variant="contained" disabled={saving || loading || !current || !selected || !confirmed} onClick={submit}>{saving ? t("Đang lưu…") : t("Xác nhận đổi")}</Button></DialogActions>
    </Dialog>
  </Box>;
}
