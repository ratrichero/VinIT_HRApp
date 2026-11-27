'use client';

import { useCallback, useEffect, useMemo, useState } from 'react';
import { careersFailure } from '@/lib/syntheticIntake';
import { filterJobs } from '@/lib/careersFilter';
import { newPoolToken, newRequestId } from '@/lib/browserIds';
import { useI18n } from '@/i18n/I18nProvider';
import LanguageSwitcher from '@/i18n/LanguageSwitcher';
import { Alert, Box, Button, Card, CardContent, Checkbox, CircularProgress, Container, FormControlLabel, Stack, TextField, Typography } from '@mui/material';

type Job = {
  position_id: string; position_code: string; title: string; org_unit: string | null;
  work_location: string | null; work_mode: string | null; employment_type: string | null;
  job_family: string | null; application_deadline_at: string; description: string | null;
  can_apply_test: boolean; accepting_applications: boolean;
};
type JobPage = { items: Job[]; next_cursor: string | null; accepting_applications?: boolean; reason?: string };
type Filters = { employment_types: { value: string; count: number }[]; job_families: { value: string; count: number }[] };

/**
 * Trang tuyển dụng công khai.
 *
 * Ba quyết định bố cục, theo yêu cầu và theo mẫu tham khảo của VinUni:
 *
 * 1. **Danh sách dòng, không phải thẻ to.** Ảnh tham khảo cho thấy mỗi tin là
 *    một dòng ngắn (vị trí · địa điểm · hạn · nút). Nhìn được nhiều tin hơn trên
 *    một màn hình, đúng thứ ứng viên cần: quét nhanh để chọn.
 * 2. **Bấm vào tin mới ra form ứng tuyển**, không phải nút trên từng dòng và
 *    không phải form luôn mở. Tránh trường hợp bấm nhầm dòng mà đã gửi hồ sơ.
 * 3. **Tin không nhận được hồ sơ thì không hiện.** Việc lọc nằm ở máy chủ
 *    (`/v1/careers/jobs`), không phải ở đây: ẩn bằng giao diện thì vẫn còn đó
 *    một trang có tin mà bấm vào không nộp được.
 */
export default function CareersPage() {
  const { t, dateLocale } = useI18n();
  const [jobs, setJobs] = useState<Job[]>([]);
  const [filters, setFilters] = useState<Filters>({ employment_types: [], job_families: [] });
  const [cursor, setCursor] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [reason, setReason] = useState('');
  const [typeFilter, setTypeFilter] = useState('');
  const [familyFilter, setFamilyFilter] = useState('');
  const [familyQuery, setFamilyQuery] = useState('');
  // Chưa tick câu đồng ý mà đã bấm Gửi: hiện lời nhắc thay vì để nút im lặng.
  const [consentMissing, setConsentMissing] = useState(false);
  // Tìm theo chức danh, ngay trên danh sách đã tải. Không gọi API: số tin còn
  // hạn đủ nhỏ để lọc tại chỗ, và lọc tại chỗ thì gõ tới đâu thấy tới đó.
  const [titleQuery, setTitleQuery] = useState('');
  const [job, setJob] = useState<Job | null>(null);
  const [busy, setBusy] = useState(false);
  const [requestId, setRequestId] = useState('');
  const [poolToken, setPoolToken] = useState('');
  const [optedIn, setOptedIn] = useState(false);
  const [savedToken, setSavedToken] = useState('');
  const [success, setSuccess] = useState('');
  // Tên tệp đã chọn, để người nộp bằng điện thoại thấy mình đã chọn đúng CV.
  const [cvName, setCvName] = useState('');

  const load = useCallback(async (next: string | null, signal?: AbortSignal) => {
    setLoading(true); setError('');
    try {
      const params = new URLSearchParams();
      if (next) params.set('cursor', next);
      if (typeFilter) params.set('employment_type', typeFilter);
      if (familyFilter) params.set('job_family', familyFilter);
      const query = params.toString() ? `?${params}` : '';
      const res = await fetch(`/v1/careers/jobs${query}`, { cache: 'no-store', signal });
      if (!res.ok) throw new Error('Không thể tải danh sách vị trí. Vui lòng thử lại sau.');
      const page: JobPage = await res.json();
      setReason(page.reason || '');
      setJobs(previous => next ? [...previous, ...page.items.filter(item => !previous.some(existing => existing.position_id === item.position_id))] : page.items);
      setCursor(page.next_cursor);
    } catch (err) {
      if (!signal?.aborted) setError(err instanceof Error ? err.message : 'Không thể tải danh sách vị trí.');
    } finally { if (!signal?.aborted) setLoading(false); }
  }, [typeFilter, familyFilter]);

  useEffect(() => {
    const controller = new AbortController();
    void load(null, controller.signal);
    return () => controller.abort();
  }, [load]);

  useEffect(() => {
    const controller = new AbortController();
    fetch('/v1/careers/filters', { cache: 'no-store', signal: controller.signal })
      .then(res => res.ok ? res.json() : null)
      .then(data => { if (data) setFilters(data); })
      .catch(() => { /* Bộ lọc không tải được thì vẫn xem được danh sách. */ });
    return () => controller.abort();
  }, []);

  const familyOptions = useMemo(() => {
    const needle = familyQuery.trim().toLowerCase();
    return filters.job_families.filter(item => !needle || item.value.toLowerCase().includes(needle));
  }, [filters.job_families, familyQuery]);

  // Logic lọc nằm ở lib/careersFilter.ts để test được mà không cần render React.
  const visibleJobs = useMemo(() => filterJobs(jobs, titleQuery), [jobs, titleQuery]);

  const toggleType = (value: string) => {
    setTypeFilter(previous => previous === value ? '' : value);
    setJob(null);
  };
  const toggleFamily = (value: string) => {
    setFamilyFilter(previous => previous === value ? '' : value);
    setJob(null);
  };

  const selectJob = (selected: Job) => {
    // `crypto.randomUUID()` chỉ có trong secure context; mở trang qua
    // `http://<ip-vps>:3005` thì nó vắng mặt, dù `crypto.getRandomValues()` —
    // nguồn ngẫu nhiên mật mã học của cùng trình duyệt — vẫn chạy bình thường.
    // Chặn ở đây từng làm cả form ứng tuyển không mở được trên VPS chưa có
    // HTTPS, trong khi không có gì thực sự thiếu. Xem `lib/browserIds.ts`.
    const requestIdValue = newRequestId();
    const poolTokenValue = newPoolToken();
    if (!requestIdValue || !poolTokenValue) {
      // Chỉ còn lại trình duyệt không có nguồn ngẫu nhiên nào. Câu báo không
      // được đổ cho HTTPS nữa — nói đúng thứ cần nói.
      setError('Trình duyệt này quá cũ để gửi hồ sơ an toàn. Hãy dùng trình duyệt mới hơn.'); return;
    }
    setRequestId(requestIdValue);
    setPoolToken(poolTokenValue);
    setJob(selected); setOptedIn(false); setConsentMissing(false); setSavedToken(''); setError(''); setSuccess(''); setCvName('');
    // Đưa form vào tầm nhìn: trên trang dài, bấm vào tin ở cuối danh sách mà
    // form mở ở đầu trang thì người dùng tưởng nút không có tác dụng.
    if (typeof window !== 'undefined') window.setTimeout(() => {
      document.getElementById('careers-apply-form')?.scrollIntoView({ behavior: 'smooth', block: 'start' });
    }, 50);
  };

  const apply = async (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!job || busy) return;
    // required trên input tệp ẩn làm trình duyệt báo lỗi không thể focus, nên kiểm tra ở đây.
    const form = event.currentTarget;
    const file = (form.elements.namedItem('cv') as HTMLInputElement | null)?.files?.[0];
    if (!file) { setError('Hãy chọn tệp CV trước khi gửi hồ sơ.'); return; }
    // Câu đồng ý là bắt buộc. `required` trên checkbox đã chặn phần lớn trường
    // hợp, nhưng thông báo của trình duyệt nằm ngoài tầm nhìn khi form dài;
    // kiểm ở đây để lời nhắc hiện ngay trên nút.
    if (!optedIn) { setConsentMissing(true); return; }
    setConsentMissing(false);
    setBusy(true); setError(''); setSuccess('');
    try {
      const data = new FormData(form);
      data.set('request_id', requestId);
      data.set('pool_opt_in', optedIn ? 'true' : 'false');
      data.set('pool_token', optedIn ? poolToken : '');
      const res = await fetch(`/v1/careers/jobs/${job.position_id}/apply`, { method: 'POST', body: data, cache: 'no-store' });
      if (!res.ok) {
        const result = await res.json().catch(() => ({}));
        setError(careersFailure(res.status, result.detail));
        return;
      }
      setSuccess('Đã tiếp nhận hồ sơ; CV sẽ được xử lý và chấm điểm theo bộ tiêu chí của vị trí. Gửi lại cùng yêu cầu không tạo thêm hồ sơ.'); setSavedToken(optedIn ? poolToken : ''); setJob(null); setCvName('');
    } catch { setError(careersFailure(null, null)); }
    finally { setBusy(false); }
  };

  const formatDeadline = (value: string) =>
    new Date(value).toLocaleDateString(dateLocale, { day: '2-digit', month: '2-digit', year: 'numeric' });

  return <Container maxWidth="lg" sx={{ py: { xs: 2.5, md: 4 } }}>
    <Stack direction="row" alignItems="center" justifyContent="space-between" spacing={2} sx={{ mb: 1 }}>
      <Typography variant="h1" sx={{ fontSize: { xs: 24, md: 30 }, lineHeight: 1.2 }}>{t('Vị trí đang tuyển dụng')}</Typography>
      <LanguageSwitcher />
    </Stack>
    <Typography variant="body2" color="text.secondary" sx={{ mb: 3 }}>
      {t('Chọn một vị trí để xem mô tả công việc và nộp hồ sơ.')}
    </Typography>
    <TextField
      fullWidth size="small" value={titleQuery} onChange={event => setTitleQuery(event.target.value)}
      placeholder={t('Tìm theo chức danh hoặc địa điểm...')}
      inputProps={{ 'aria-label': t('Tìm việc làm'), maxLength: 120 }}
      sx={{ mb: 2 }}
    />

    {error && <Alert severity="error" sx={{ mb: 2 }} action={!job ? <Button color="inherit" onClick={() => void load(null)}>{t('Thử lại')}</Button> : undefined}>{t(error)}</Alert>}
    {success && <Alert severity="success" sx={{ mb: 2 }}>{t(success)}</Alert>}
    {savedToken && <Alert severity="info" sx={{ mb: 2 }}>
      <Typography variant="body2">{t('Mã rút lựa chọn thử nghiệm:')} <Box component="code" sx={{ overflowWrap: 'anywhere' }}>{savedToken}</Box></Typography>
      <Typography variant="body2">{t('Lưu mã và dùng tại /pool-withdraw.')}</Typography>
    </Alert>}

    {/*
      Thanh danh mục, theo mẫu VinUni. Mỗi mục nối vào bộ lọc `employment_type`
      có thật — không phải link chết. Nhưng danh mục phổ biến (Toàn thời gian,
      Thực tập...) thường chưa có tin nào mang nhãn đó: cột `employment_type`
      của vị trí hay bỏ trống. Nên chỉ hiện mục khi bộ lọc đang thật sự có
      người chọn được; không bày ra một hàng tab bấm vào là rỗng.
    */}
    <Box component="nav" aria-label={t('Danh mục việc làm')} sx={{
      display: 'flex', flexWrap: 'wrap', alignItems: 'center', gap: 0.5,
      backgroundColor: '#0A2B57', borderRadius: 1, px: 1, py: 0.5, mb: 3,
    }}>
      <Button onClick={() => { setTypeFilter(''); setJob(null); }} sx={{
        color: '#FFFFFF', minHeight: 40, textTransform: 'none', fontWeight: typeFilter ? 400 : 700,
        textDecoration: typeFilter ? 'none' : 'underline', textUnderlineOffset: 4,
        '&:hover': { backgroundColor: 'rgba(255,255,255,0.12)' },
      }}>{t('Tất cả')}</Button>
      {filters.employment_types.map(item => <Button
        key={item.value}
        onClick={() => toggleType(item.value)}
        aria-pressed={typeFilter === item.value}
        sx={{
          color: '#FFFFFF', minHeight: 40, textTransform: 'none',
          fontWeight: typeFilter === item.value ? 700 : 400,
          textDecoration: typeFilter === item.value ? 'underline' : 'none', textUnderlineOffset: 4,
          '&:hover': { backgroundColor: 'rgba(255,255,255,0.12)' },
        }}
      >{item.value} ({item.count})</Button>)}
      {/* Không có loại nào để chọn: nói ra, thay vì để thanh nav trống trơn
          khiến ứng viên tưởng trang hỏng. */}
      {!filters.employment_types.length && <Typography variant="body2" sx={{ color: 'rgba(255,255,255,0.75)', px: 1 }}>
        {t('Chưa có tin nào được gắn loại việc làm.')}
      </Typography>}
    </Box>

    <Box sx={{ display: 'grid', gap: { xs: 2, md: 3 }, gridTemplateColumns: { xs: '1fr', md: '260px 1fr' }, alignItems: 'start' }}>
      {/* Cột lọc: chỉ hiện giá trị đang có tin thật, để không có bộ lọc bấm vào ra rỗng. */}
      {filters.job_families.length > 0 && <Box component="aside" aria-label={t('Bộ lọc')} sx={{ p: 2, backgroundColor: '#F7F9FC', borderRadius: 1 }}>
        {/* "Loại việc làm" đã chuyển lên thanh nav phía trên. Để cả hai thì cùng
            một bộ lọc nằm hai chỗ, bấm bên này trông như bên kia không ăn. */}
        {filters.job_families.length > 0 && <>
          <Typography sx={{ fontWeight: 700, color: '#8A1538', mb: 1 }}>{t('Ngành / Lĩnh vực')}</Typography>
          <TextField size="small" fullWidth placeholder={t('Lọc ngành...')} value={familyQuery} onChange={event => setFamilyQuery(event.target.value)} sx={{ mb: 1 }} inputProps={{ 'aria-label': t('Lọc ngành') }} />
          <Stack spacing={0.5}>
            {familyOptions.map(item => <FormControlLabel
              key={item.value}
              control={<Checkbox size="small" checked={familyFilter === item.value} onChange={() => toggleFamily(item.value)} inputProps={{ 'aria-label': item.value }} />}
              label={<Typography variant="body2">{item.value} ({item.count})</Typography>}
            />)}
          </Stack>
          {!familyOptions.length && <Typography variant="caption" color="text.secondary">{t('Không có ngành khớp.')}</Typography>}
        </>}
      </Box>}

      <Box>
        <Typography variant="h2" sx={{ fontSize: { xs: 18, md: 20 }, color: '#8A1538', fontWeight: 700, mb: 2 }}>{t('Tất cả vị trí đang mở')}</Typography>
        {loading && <CircularProgress aria-label={t('Đang tải')} />}
        {!loading && !error && jobs.length > 0 && !visibleJobs.length && <Typography sx={{ mb: 2 }}>
          {t('Không có vị trí nào khớp từ khóa.')}
        </Typography>}
        {!loading && !error && !jobs.length && <Typography>
          {reason === 'INTAKE_NOT_OPEN'
            ? t('Hiện chưa mở nhận hồ sơ. Danh sách vị trí sẽ xuất hiện khi HR mở nhận hồ sơ.')
            : t('Hiện chưa có vị trí còn hạn.')}
        </Typography>}

        {/* Danh sách dòng. Bấm cả dòng, không chỉ nút — vùng bấm rộng hơn, đỡ trượt. */}
        <Box component="ul" sx={{ listStyle: 'none', p: 0, m: 0 }}>
          {visibleJobs.map(item => <Box component="li" key={item.position_id}>
            <Box
              role="button"
              tabIndex={0}
              aria-label={t('Xem chi tiết {0}', item.title)}
              onClick={() => selectJob(item)}
              onKeyDown={event => { if (event.key === 'Enter' || event.key === ' ') { event.preventDefault(); selectJob(item); } }}
              sx={{
                display: 'grid', gap: 1, alignItems: 'center', py: 1.75, px: 0.5,
                gridTemplateColumns: { xs: '1fr auto', md: '1.6fr 1fr 1fr auto' },
                borderBottom: '1px solid #D6DEEA', cursor: 'pointer',
                '&:hover': { backgroundColor: '#F7F9FC' },
                '&:focus-visible': { outline: '2px solid #0A2B57', outlineOffset: 2 },
              }}
            >
              <Typography sx={{ fontWeight: 700, color: '#0A2B57' }}>{item.title}</Typography>
              <Typography variant="body2" color="text.secondary">{item.work_location || item.org_unit || ''}</Typography>
              <Typography variant="body2" color="text.secondary">{t('Hạn')}: {formatDeadline(item.application_deadline_at)}</Typography>
              <Button
                variant="contained"
                size="small"
                sx={{ minHeight: 40, backgroundColor: '#A6192E', '&:hover': { backgroundColor: '#8A1538' } }}
                onClick={event => { event.stopPropagation(); selectJob(item); }}
              >
                {t('Xem chi tiết')}
              </Button>
            </Box>
          </Box>)}
        </Box>
        {cursor && !loading && !error && <Button sx={{ mt: 2, minHeight: 44 }} variant="outlined" onClick={() => void load(cursor)}>{t('Xem thêm')}</Button>}
      </Box>
    </Box>

    {/* Form chỉ hiện sau khi chọn một tin. */}
    {job && <Card variant="outlined" sx={{ mt: 4, borderColor: '#D6DEEA' }} id="careers-apply-form" data-testid="careers-apply-form"><CardContent>
      <Stack direction="row" justifyContent="space-between" alignItems="flex-start" spacing={2} sx={{ mb: 1 }}>
        <Box>
          <Typography variant="h2" sx={{ fontSize: { xs: 20, md: 23 }, lineHeight: 1.3 }}>{job.title}</Typography>
          <Typography variant="body2" color="text.secondary">{[job.position_code, job.org_unit, job.work_location, job.work_mode, job.employment_type].filter(Boolean).join(' · ')}</Typography>
          <Typography variant="body2" color="text.secondary">{t('Hạn')}: {formatDeadline(job.application_deadline_at)}</Typography>
        </Box>
        <Button onClick={() => { setJob(null); setCvName(''); }} sx={{ minHeight: 40 }}>{t('Đóng')}</Button>
      </Stack>
      {job.description && <Box sx={{ my: 2, p: 2, backgroundColor: '#F7F9FC', borderRadius: 1 }}>
        <Typography component="p" sx={{ whiteSpace: 'pre-wrap' }}>{job.description}</Typography>
      </Box>}
      <Box component="form" onSubmit={apply} noValidate>
        <Stack spacing={2}>
          <Typography variant="h3" sx={{ fontSize: { xs: 17, md: 19 }, fontWeight: 700 }}>{t('Nộp hồ sơ cho vị trí này')}</Typography>
          <TextField disabled={busy} name="name" label={t('Tên ứng viên')} required fullWidth autoComplete="name" inputProps={{ maxLength: 200 }} />
          <TextField disabled={busy} name="email" type="email" label={t('Email')} required fullWidth autoComplete="email" inputProps={{ maxLength: 254 }} />
          <TextField disabled={busy} name="phone" type="tel" label={t('Điện thoại')} fullWidth autoComplete="tel" inputProps={{ maxLength: 50 }} />
          {/* Chọn tệp bằng nút lớn thay vì input mặc định của trình duyệt: trên điện
              thoại ô file gốc bé, khó bấm và không hiện tên tệp đã chọn. */}
          <Box>
            <Typography variant="body2" sx={{ mb: 1, fontWeight: 600 }}>{t('CV PDF hoặc DOCX, tối đa 10 MB')}</Typography>
            <Stack direction={{ xs: 'column', sm: 'row' }} spacing={1} alignItems={{ xs: 'stretch', sm: 'center' }}>
              <Button component="label" variant="outlined" disabled={busy} sx={{ minHeight: 44 }} data-testid="careers-cv-pick">
                {t('Chọn tệp CV')}
                <input
                  hidden
                  name="cv"
                  type="file"
                  accept=".pdf,.docx"
                  disabled={busy}
                  data-testid="careers-cv-input"
                  onChange={event => setCvName(event.target.files?.[0]?.name || '')}
                />
              </Button>
              <Typography variant="body2" color="text.secondary" sx={{ overflowWrap: 'anywhere' }} data-testid="careers-cv-name">
                {cvName || t('Chưa chọn tệp nào.')}
              </Typography>
            </Stack>
          </Box>
          {/* Một câu, BẮT BUỘC: đồng ý nộp hồ sơ và đồng ý việc lưu hồ sơ 12 tháng
              là một hành động, không tách được — nộp hồ sơ mà không được giữ hồ sơ
              thì không tuyển được. Trước đây câu này nói về Talent Pool 7 ngày và
              là tuỳ chọn, trong khi khối bên dưới lại là lựa chọn tái sử dụng hồ sơ;
              gộp hai chỗ làm một để ứng viên chỉ phải trả lời một lần. */}
          <FormControlLabel
            control={<Checkbox disabled={busy} checked={optedIn} onChange={e => setOptedIn(e.target.checked)} required />}
            label={<Typography variant="body2">
              {t('Tôi đồng ý nộp hồ sơ và đồng ý để VinCareer lưu giữ hồ sơ trong 12 tháng kể từ ngày nộp, phục vụ các nhu cầu tuyển dụng của VinCareer. Tôi có thể yêu cầu rút lại sự đồng ý này bất cứ lúc nào bằng mã rút hiển thị sau khi gửi.')}
            </Typography>}
          />
          {consentMissing && <Alert severity="info" sx={{ mb: 1 }}>
            {t('Bạn cần đọc và đồng ý câu trên trước khi gửi hồ sơ.')}
          </Alert>}
          {optedIn && <Alert severity="info" sx={{ overflowWrap: 'anywhere' }}>
            <Typography variant="body2">{t('Mã rút lựa chọn (sao chép trước khi gửi; nếu mất kết nối hãy giữ nguyên form để thử lại):')} <Box component="code" sx={{ overflowWrap: 'anywhere' }}>{poolToken}</Box></Typography>
            <Typography variant="body2">{t('Dùng tại /pool-withdraw; rút không tự xóa hồ sơ ứng tuyển.')}</Typography>
          </Alert>}
          <Typography variant="body2">{t('Nếu gặp lỗi sau khi gửi, giữ nguyên form và mã rút để thử lại. Một yêu cầu mới có thể tạo thêm hồ sơ; hệ thống chưa tự phát hiện mọi hồ sơ trùng.')}</Typography>
          <Stack direction={{ xs: 'column', sm: 'row' }} spacing={1}>
            <Button type="submit" variant="contained" disabled={busy} sx={{ minHeight: 44 }}>{t('Gửi hồ sơ')}</Button>
            <Button type="button" disabled={busy} onClick={() => { setJob(null); setCvName(''); }} sx={{ minHeight: 44 }}>{t('Hủy')}</Button>
          </Stack>
        </Stack>
      </Box>
    </CardContent></Card>}
  </Container>;
}
