'use client';

import { useCallback, useEffect, useRef, useState } from 'react';
import { Alert, Box, Button, Card, CardContent, Chip, CircularProgress, FormControl, Grid, InputLabel, MenuItem, Select, Table, TableBody, TableCell, TableContainer, TableHead, TableRow, Typography } from '@mui/material';
import RefreshIcon from '@mui/icons-material/Refresh';
import { useI18n } from '@/i18n/I18nProvider';
import { adminApi } from '@/lib/api';
import { formatUsd } from '@/lib/llmCost';

type Amount = number | string | null;
type Summary = { attempts: number; http_ok: number; http_failed: number; errors_observed: number; priced_attempts: number; unpriced_attempts: number; input_known_attempts: number; output_known_attempts: number; input_tokens: number | null; output_tokens: number | null; latency_samples: number; avg_latency_ms: number | null; p95_latency_ms: number | null; estimated_usd: Amount };
type Day = { day: string; attempts: number; http_failed: number; unpriced_attempts: number; estimated_usd: Amount };
type Model = { config_id: string | null; provider: string; provider_name: string | null; model_name: string; returned_model: string | null; attempts: number; http_failed: number; unpriced_attempts: number; estimated_usd: Amount };
type Attempt = { attempt_id: string; created_at: string; provider: string; provider_name: string | null; model_name: string; returned_model: string | null; task_name: string; http_success: boolean; http_status: number | null; failure_category: string | null; duration_ms: number | null; input_tokens: number | null; output_tokens: number | null; estimated_cost_usd: Amount; input_price_per_million_usd: Amount; output_price_per_million_usd: Amount };
type Dashboard = { summary: Summary; daily: Day[]; models: Model[]; events: Attempt[] };

export default function LlmOperations() {
  const { t, dateLocale } = useI18n();
  const [days, setDays] = useState(30);
  const [offset, setOffset] = useState(0);
  const [data, setData] = useState<Dashboard | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);
  const limit = 25;
  const request = useRef(0);
  const load = useCallback(async () => {
    const id = ++request.current;
    setLoading(true); setError(false);
    try { const response = await adminApi.getLlmOperations({ days, limit, offset }); if (request.current === id) setData(response.data); }
    catch { if (request.current === id) { setError(true); setData(null); } }
    finally { if (request.current === id) setLoading(false); }
  }, [days, offset]);
  useEffect(() => { const counter = request; load(); return () => { counter.current++; }; }, [load]);
  const nf = (value: number | null | undefined) => value == null ? '—' : new Intl.NumberFormat(dateLocale).format(value);
  const max = Math.max(1, ...(data?.daily || []).map(item => item.attempts));
  const s = data?.summary;
  return <Box>
    <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: 2, mb: 2 }}>
      <Box><Typography variant="h4">{t("Vận hành LLM")}</Typography><Typography variant="body2" color="text.secondary">{t("Tổng hợp lượt gọi HTTP và chi phí ước tính")}</Typography></Box>
      <Box sx={{ display: 'flex', gap: 1, alignItems: 'center' }}><FormControl size="small" sx={{ minWidth: 150 }}><InputLabel id="llm-days-label">{t("Khoảng thời gian")}</InputLabel><Select labelId="llm-days-label" label={t("Khoảng thời gian")} value={days} onChange={e => { setDays(Number(e.target.value)); setOffset(0); }}><MenuItem value={7}>{t("7 ngày qua")}</MenuItem><MenuItem value={30}>{t("30 ngày qua")}</MenuItem><MenuItem value={90}>{t("90 ngày qua")}</MenuItem></Select></FormControl><Button variant="outlined" startIcon={<RefreshIcon />} onClick={load} disabled={loading}>{t("Làm mới")}</Button></Box>
    </Box>
    <Alert severity="info" sx={{ mb: 2 }}>{t("Mỗi lượt là một lần thử HTTP, bao gồm retry/fallback; không phải số tác vụ thành công. Dữ liệu best-effort có thể thiếu; không bao gồm test kết nối, BGE hay reranker. Chi phí ước tính không phải hóa đơn.")}</Alert>
    {error && <Alert severity="error" sx={{ mb: 2 }}>{t("Không thể tải dữ liệu vận hành LLM.")}</Alert>}
    {loading && <Box sx={{ textAlign: 'center', py: 5 }}><CircularProgress /></Box>}
    {!loading && s && <>
      <Grid container spacing={2} sx={{ mb: 2 }}>
        {[
          { label: t("Lượt thử HTTP"), value: nf(s.attempts), note: `${t("HTTP không thành công")}: ${nf(s.http_failed)}` },
          { label: t("Chi phí ước tính"), value: formatUsd(s.estimated_usd), note: `${t("Chưa tính được")}: ${nf(s.unpriced_attempts)} / ${nf(s.attempts)}` },
          { label: t("Token đầu vào / đầu ra"), value: `${nf(s.input_tokens)} / ${nf(s.output_tokens)}`, note: `${t("Có token đầu vào / đầu ra")}: ${nf(s.input_known_attempts)} / ${nf(s.output_known_attempts)}` },
          { label: t("Độ trễ HTTP p95"), value: s.p95_latency_ms == null ? '—' : `${Math.round(s.p95_latency_ms)} ms`, note: `${t("Số mẫu độ trễ")}: ${nf(s.latency_samples)}` },
        ].map(item => <Grid item xs={12} sm={6} lg={3} key={item.label}><Card variant="outlined" sx={{ height: '100%' }}><CardContent><Typography variant="caption" color="text.secondary">{item.label}</Typography><Typography variant="h5" sx={{ my: 1, wordBreak: 'break-word' }}>{item.value}</Typography><Typography variant="caption" color="text.secondary">{item.note}</Typography></CardContent></Card></Grid>)}
      </Grid>
      <Grid container spacing={2} sx={{ mb: 2 }}>
        <Grid item xs={12} md={7}><Card variant="outlined" sx={{ height: '100%' }}><CardContent>
          <Typography variant="h6">{t("Lượt gọi theo ngày (UTC)")}</Typography><Typography variant="caption" color="text.secondary">{t("Theo thời gian ghi nhận; ngày không có dữ liệu không hiển thị.")}</Typography>
          {data.daily.length ? <Box sx={{ display: 'flex', alignItems: 'flex-end', gap: 0.8, overflowX: 'auto', height: 165, mt: 2, pb: 1 }} aria-label={t("Biểu đồ lượt gọi theo ngày")}>
            {data.daily.map(day => <Box key={day.day} sx={{ minWidth: 36, textAlign: 'center' }} title={`${day.day}: ${day.attempts}`}><Typography variant="caption">{day.attempts}</Typography><Box sx={{ height: Math.max(3, 105 * day.attempts / max), bgcolor: 'primary.main', borderRadius: '5px 5px 0 0', mx: 0.5 }} /><Typography variant="caption" color="text.secondary">{day.day.slice(5)}</Typography></Box>)}
          </Box> : <Typography variant="body2" color="text.secondary" sx={{ py: 5 }}>{t("Chưa có lượt ghi nhận trong khoảng này.")}</Typography>}
        </CardContent></Card></Grid>
        <Grid item xs={12} md={5}><Card variant="outlined" sx={{ height: '100%' }}><CardContent><Typography variant="h6">{t("Theo model và nhà cung cấp")}</Typography><Typography variant="caption" color="text.secondary">{t("Tối đa 20 nhóm có nhiều lượt nhất; model trả về có thể không xác định.")}</Typography>
          {data.models.length ? data.models.map((model, index) => <Box key={`${model.config_id || 'env'}-${model.returned_model || 'unknown'}-${index}`} sx={{ mt: 1.5, borderBottom: '1px solid', borderColor: 'divider', pb: 1 }}><Typography variant="body2" fontWeight={600}>{model.provider_name || model.provider} · {model.model_name}</Typography><Typography variant="caption" color="text.secondary" display="block">{t("Model trả về")}: {model.returned_model || '—'} · {nf(model.attempts)} {t("lượt")} · {formatUsd(model.estimated_usd)} · {t("Chưa tính được")}: {nf(model.unpriced_attempts)}</Typography></Box>) : <Typography variant="body2" color="text.secondary" sx={{ py: 5 }}>{t("Chưa có lượt ghi nhận trong khoảng này.")}</Typography>}
        </CardContent></Card></Grid>
      </Grid>
      <Card variant="outlined" sx={{ mb: 2 }}><CardContent><Typography variant="h6">{t("Chi phí ước tính theo ngày (UTC)")}</Typography><Typography variant="caption" color="text.secondary">{t("Chỉ gồm lượt tính được; số lượt chưa tính được hiển thị bên cạnh. Dấu gạch ngang nghĩa là không biết.")}</Typography>
        {data.daily.length ? <Box sx={{ mt: 1, maxHeight: 240, overflowY: 'auto' }}>{data.daily.map(day => { const peak = Math.max(0, ...data.daily.map(d => Number(d.estimated_usd || 0))); const cost = day.estimated_usd == null ? null : Number(day.estimated_usd); return <Box key={day.day} sx={{ display: 'flex', alignItems: 'center', gap: 1, my: 0.5 }}><Typography variant="caption" sx={{ minWidth: 78 }}>{day.day}</Typography><Box sx={{ flex: 1, bgcolor: 'action.hover', height: 10, borderRadius: 1 }}><Box sx={{ bgcolor: 'secondary.main', width: cost == null || peak === 0 ? '0%' : `${Math.max(1, 100 * cost / peak)}%`, height: 10, borderRadius: 1 }} /></Box><Typography variant="caption" sx={{ minWidth: 130 }}>{formatUsd(day.estimated_usd)} · {t("Chưa tính được")}: {day.unpriced_attempts}</Typography></Box>; })}</Box> : <Typography variant="body2" sx={{ py: 2 }}>{t("Chưa có lượt ghi nhận trong khoảng này.")}</Typography>}
      </CardContent></Card>
      <Card variant="outlined"><CardContent><Typography variant="h6">{t("Nhật ký lượt thử gần đây")}</Typography><Typography variant="caption" color="text.secondary">{t("Không chứa prompt, CV/JD, nội dung phản hồi hoặc khóa. Model trả về, mã HTTP và độ trễ của dữ liệu cũ có thể không có.")}</Typography>
        <TableContainer sx={{ mt: 1 }}><Table size="small" aria-label={t("Nhật ký lượt thử gần đây")}><TableHead><TableRow>{[t("Thời gian"), t("Nhà cung cấp / model"), t("Tác vụ"), t("HTTP / lỗi"), t("Độ trễ"), t("Token vào / ra"), t("Giá USD / 1 triệu token (vào / ra)"), t("Chi phí ước tính")].map(label => <TableCell key={label}>{label}</TableCell>)}</TableRow></TableHead><TableBody>
          {data.events.map(item => <TableRow key={item.attempt_id}><TableCell sx={{ whiteSpace: 'nowrap' }}>{new Date(item.created_at).toLocaleString(dateLocale)}</TableCell><TableCell><Typography variant="body2">{item.provider_name || item.provider} · {item.model_name}</Typography><Typography variant="caption" color="text.secondary">{t("Model trả về")}: {item.returned_model || '—'}</Typography></TableCell><TableCell>{item.task_name}</TableCell><TableCell><Chip size="small" color={item.http_success ? 'success' : 'warning'} label={item.http_status ?? (item.http_success ? 'HTTP OK' : t("Không rõ"))} />{item.failure_category && <Typography variant="caption" display="block">{item.failure_category}</Typography>}</TableCell><TableCell>{item.duration_ms == null ? '—' : `${nf(item.duration_ms)} ms`}</TableCell><TableCell>{nf(item.input_tokens)} / {nf(item.output_tokens)}</TableCell><TableCell>{formatUsd(item.input_price_per_million_usd)} / {formatUsd(item.output_price_per_million_usd)}</TableCell><TableCell>{formatUsd(item.estimated_cost_usd)}</TableCell></TableRow>)}
          {!data.events.length && <TableRow><TableCell colSpan={8}>{t("Chưa có lượt ghi nhận trong khoảng này.")}</TableCell></TableRow>}
        </TableBody></Table></TableContainer>
        <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mt: 2 }}><Typography variant="caption">{t("Bắt đầu từ lượt")}: {offset + (data.events.length ? 1 : 0)}</Typography><Box><Button disabled={offset === 0 || loading} onClick={() => setOffset(Math.max(0, offset - limit))}>{t("Trước")}</Button><Button disabled={data.events.length < limit || offset + limit > 10000 || loading} onClick={() => setOffset(offset + limit)}>{t("Tiếp")}</Button></Box></Box>
      </CardContent></Card>
    </>}
  </Box>;
}
