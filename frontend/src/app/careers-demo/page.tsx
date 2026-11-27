'use client';

import { useEffect, useState } from 'react';
import { Alert, Box, Button, Card, CardContent, Checkbox, CircularProgress, Container, FormControlLabel, Stack, TextField, Typography } from '@mui/material';
import { useI18n } from '@/i18n/I18nProvider';
import { newPoolToken, newRequestId } from '@/lib/browserIds';

type Job = { position_id: string; position_code: string; title: string; org_unit: string | null; work_location: string | null; work_mode: string | null; application_deadline_at: string; description: string; can_apply: boolean };

export default function CareersDemo() {
  const { dateLocale } = useI18n();
  const [jobs, setJobs] = useState<Job[]>([]);
  const [job, setJob] = useState<Job | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [success, setSuccess] = useState('');
  const [busy, setBusy] = useState(false);
  const [requestId, setRequestId] = useState('');
  const [poolToken, setPoolToken] = useState('');
  const [savedToken, setSavedToken] = useState('');
  const [withdrawToken, setWithdrawToken] = useState('');
  useEffect(() => {
    fetch('/v1/careers-demo/jobs', { cache: 'no-store' }).then(async res => {
      if (!res.ok) throw new Error();
      setJobs(await res.json());
    }).catch(() => setError('Cổng demo chưa được bật hoặc không khả dụng.')).finally(() => setLoading(false));
  }, []);
  const apply = async (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!job || busy) return;
    setError(''); setSuccess(''); setBusy(true);
    try {
      const data = new FormData(event.currentTarget);
      data.set('request_id', requestId);
      if (data.has('pool_opt_in')) { data.set('pool_opt_in', 'true'); data.set('pool_token', poolToken); }
      const res = await fetch(`/v1/careers-demo/jobs/${job.position_id}/apply`, { method: 'POST', body: data });
      const result = await res.json();
      if (!res.ok) throw new Error(result.detail || 'Không thể gửi hồ sơ demo.');
      setSuccess('Đã nhận hồ sơ tổng hợp. HR có thể kiểm tra tại vị trí tương ứng.');
      setSavedToken(data.has('pool_opt_in') ? poolToken : '');
      setJob(null); setRequestId('');
    } catch (err) { setError(err instanceof Error ? err.message : 'Không thể gửi hồ sơ demo.'); }
    finally { setBusy(false); }
  };
  const withdraw = async (event: React.FormEvent) => {
    event.preventDefault(); setError(''); setSuccess('');
    try {
      const res = await fetch('/v1/careers-demo/pool/withdraw', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ token: withdrawToken.trim() }) });
      if (!res.ok) throw new Error('Mã demo không hợp lệ hoặc dịch vụ không khả dụng.');
      setSuccess('Nếu mã demo hợp lệ, lựa chọn đã được rút.'); setWithdrawToken(''); setSavedToken('');
    } catch (err) { setError(err instanceof Error ? err.message : 'Không thể rút lựa chọn.'); }
  };
  return <Container maxWidth="md" sx={{ py: 5 }}>
    <Typography variant="h1" sx={{ fontSize: 30, mb: 2 }}>Vị trí đang tuyển dụng — DEMO</Typography>
    <Alert severity="warning" sx={{ mb: 2 }}>Chỉ dùng dữ liệu tổng hợp, không gửi CV hoặc thông tin cá nhân thật. Cổng chưa dành cho vận hành công khai.</Alert>
    {error && <Alert severity="error" sx={{ mb: 2 }}>{error}</Alert>}
    {success && <Alert severity="success" sx={{ mb: 2 }}>{success}</Alert>}
    {savedToken && <Alert severity="info" sx={{ mb: 2 }}>Mã rút lựa chọn demo (hãy sao chép ngay; chỉ hiển thị trong phiên này): <Box component="code" sx={{ overflowWrap: 'anywhere' }}>{savedToken}</Box></Alert>}
    {loading ? <CircularProgress /> : jobs.length === 0 ? <Typography>Không có vị trí còn hạn trong demo.</Typography> : <Stack spacing={2}>
      {jobs.map(item => <Card variant="outlined" key={item.position_id}><CardContent>
        <Typography variant="h2" sx={{ fontSize: 21 }}>{item.title}</Typography>
        <Typography>{item.position_code} · {item.org_unit || '—'} · {item.work_location || '—'} · {item.work_mode || '—'}</Typography>
        <Typography>Hạn: {new Date(item.application_deadline_at).toLocaleString(dateLocale)}</Typography>
        <Typography component="p" sx={{ whiteSpace: 'pre-wrap', my: 2 }}>{item.description}</Typography>
        <Button variant="contained" disabled={!item.can_apply || busy} onClick={() => {
          // Trang demo cũng chạy trên HTTP ở VPS: `crypto.randomUUID` vắng mặt ở đó.
          const requestIdValue = newRequestId();
          const poolTokenValue = newPoolToken();
          if (!requestIdValue || !poolTokenValue) { setError('Trình duyệt này quá cũ để gửi hồ sơ an toàn. Hãy dùng trình duyệt mới hơn.'); return; }
          setJob(item); setRequestId(requestIdValue); setPoolToken(poolTokenValue);
          setSavedToken(''); setError(''); setSuccess('');
        }}>Ứng tuyển demo</Button>
        {!item.can_apply && <Typography variant="caption" display="block">Chưa thể nộp: rubric của JD hiện tại chưa được duyệt.</Typography>}
      </CardContent></Card>)}
    </Stack>}
    {job && <Box component="form" onSubmit={apply} sx={{ mt: 4 }}><Stack spacing={2}>
      <Typography variant="h2" sx={{ fontSize: 23 }}>Ứng tuyển demo: {job.title}</Typography>
      <TextField name="name" label="Họ tên tổng hợp" required inputProps={{ maxLength: 200 }} />
      <TextField name="email" type="email" label="Email tổng hợp" required inputProps={{ maxLength: 254 }} />
      <TextField name="phone" label="Điện thoại tổng hợp (tùy chọn)" inputProps={{ maxLength: 50 }} />
      <label>CV tổng hợp PDF hoặc DOCX, tối đa 10 MB <input name="cv" type="file" accept=".pdf,.docx" required /></label>
      <FormControlLabel control={<Checkbox name="pool_opt_in" />} label="Tôi chọn tham gia Talent Pool DEMO trong 7 ngày (chỉ hồ sơ giả). Không bắt buộc để nộp đơn." />
      <Alert severity="info">Đồng ý demo là riêng biệt, không gia hạn lưu trữ. Có thể rút bằng mã demo; nội dung này chưa phải thông báo dữ liệu được duyệt.</Alert>
      <Stack direction="row" spacing={1}><Button type="submit" variant="contained" disabled={busy}>Gửi hồ sơ demo</Button><Button type="button" disabled={busy} onClick={() => setJob(null)}>Hủy</Button></Stack>
    </Stack></Box>}
    <Box component="form" onSubmit={withdraw} sx={{ mt: 5 }}><Stack spacing={2}>
      <Typography variant="h2" sx={{ fontSize: 21 }}>Rút lựa chọn Talent Pool demo</Typography>
      <TextField label="Mã demo" value={withdrawToken} onChange={e => setWithdrawToken(e.target.value)} required inputProps={{ maxLength: 64 }} />
      <Button type="submit" variant="outlined">Rút lựa chọn</Button>
    </Stack></Box>
  </Container>;
}
