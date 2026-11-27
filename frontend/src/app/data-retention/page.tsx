'use client';

import { Fragment, useCallback, useEffect, useState } from 'react';
import {
  Alert, Box, Button, Chip, CircularProgress, Dialog, DialogActions, DialogContent,
  DialogContentText, DialogTitle, FormControl, InputLabel, MenuItem, Paper, Select,
  Stack, Table, TableBody, TableCell, TableContainer, TableHead, TableRow, Typography,
} from '@mui/material';
import { useI18n } from '@/i18n/I18nProvider';
import { applicationsApi, positionsApi, retentionApi } from '@/lib/api';
import { APPLICATION_STATUSES, type ApplicationStatus } from '@/lib/applicationStatus';
import {
  canCancelRetentionCase,
  canConfirmRetentionCase,
  hasApplicationTimeline,
  retentionDate,
  retentionExecutionLabel,
  retentionStatusLabel,
  summarizeRetentionCases,
  type RetentionCase,
} from '@/lib/retention';

type Position = { position_id: string; position_code?: string; title: string; status?: string };

type StatusEvent = {
  event_id: string;
  previous_status: string | null;
  new_status: string;
  reason: string | null;
  note: string | null;
  changed_at: string | null;
  changed_by_name: string | null;
};

type TimelineState = { state: 'loading' | 'ready' | 'error'; events?: StatusEvent[]; message?: string };

const shortId = (value: string | null | undefined) => (value ? `${value.slice(0, 8)}…` : '—');

export default function DataRetentionPage() {
  const { t, dateLocale } = useI18n();
  const [positions, setPositions] = useState<Position[]>([]);
  const [positionId, setPositionId] = useState('');
  const [positionsError, setPositionsError] = useState('');
  const [cases, setCases] = useState<RetentionCase[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const [generateOpen, setGenerateOpen] = useState(false);
  const [generating, setGenerating] = useState(false);
  const [pendingAction, setPendingAction] = useState<{ kind: 'confirm' | 'cancel'; item: RetentionCase } | null>(null);
  const [acting, setActing] = useState(false);
  const [timelines, setTimelines] = useState<Record<string, TimelineState>>({});

  useEffect(() => {
    let active = true;
    positionsApi.listAll()
      .then(list => {
        if (!active) return;
        const items: Position[] = Array.isArray(list) ? list : [];
        setPositions(items);
        // Vị trí đã đóng là nơi có thể có trường hợp đến hạn; chọn sẵn để HR không phải dò.
        const firstClosed = items.find(item => item.status === 'CLOSED');
        if (items.length) setPositionId((firstClosed || items[0]).position_id);
      })
      .catch(() => { if (active) setPositionsError(t('Không tải được danh sách vị trí.')); });
    return () => { active = false; };
  }, [t]);

  const loadCases = useCallback(async (id: string) => {
    if (!id) { setCases([]); return; }
    setLoading(true); setError('');
    try {
      const response = await retentionApi.listCases(id);
      setCases(Array.isArray(response.data) ? response.data : []);
    } catch (err: any) {
      setCases([]);
      setError(err.response?.status === 403
        ? t('Bạn không có quyền xem dữ liệu lưu trữ của vị trí này.')
        : (err.response?.data?.detail || t('Không tải được danh sách trường hợp lưu trữ.')));
    } finally {
      setLoading(false);
    }
  }, [t]);

  useEffect(() => {
    setTimelines({});
    setNotice('');
    void loadCases(positionId);
  }, [positionId, loadCases]);

  const generate = async () => {
    if (!positionId || generating) return;
    setGenerating(true); setError(''); setNotice('');
    try {
      const response = await retentionApi.generateCases(positionId);
      const result = response.data || {};
      const created = Number(result.created_count || 0);
      setGenerateOpen(false);
      setNotice(created > 0
        ? t('Đã tạo {0} trường hợp lưu trữ, hạn xoá {1}.', created, retentionDate(result.due_date, dateLocale))
        : t('Chưa tạo trường hợp nào: vị trí chưa đóng, chưa quá hạn lưu trữ, hoặc mọi hồ sơ đã có trường hợp đang mở.'));
      await loadCases(positionId);
    } catch (err: any) {
      setError(err.response?.data?.detail || t('Không tạo được trường hợp lưu trữ.'));
    } finally {
      setGenerating(false);
    }
  };

  const runAction = async () => {
    if (!pendingAction || acting) return;
    const { kind, item } = pendingAction;
    setActing(true); setError(''); setNotice('');
    try {
      const response = kind === 'confirm'
        ? await retentionApi.confirmCase(item.retention_case_id)
        : await retentionApi.cancelCase(item.retention_case_id);
      const updated: RetentionCase | undefined = response.data;
      if (updated?.retention_case_id) {
        setCases(previous => previous.map(row => (row.retention_case_id === updated.retention_case_id ? { ...row, ...updated } : row)));
      } else {
        await loadCases(positionId);
      }
      setNotice(kind === 'confirm'
        ? t('Đã xác nhận trường hợp {0}; trường hợp vào hàng đợi xoá, dữ liệu chưa bị xoá ngay.', shortId(item.application_opaque_id))
        : t('Đã huỷ trường hợp {0}; hồ sơ vẫn được giữ.', shortId(item.application_opaque_id)));
      setPendingAction(null);
    } catch (err: any) {
      setError(err.response?.data?.detail || t('Không cập nhật được trường hợp lưu trữ.'));
    } finally {
      setActing(false);
    }
  };

  const toggleTimeline = async (item: RetentionCase) => {
    const current = timelines[item.retention_case_id];
    if (current && current.state !== 'error') {
      setTimelines(previous => {
        const next = { ...previous };
        delete next[item.retention_case_id];
        return next;
      });
      return;
    }
    if (!item.application_id) return;
    setTimelines(previous => ({ ...previous, [item.retention_case_id]: { state: 'loading' } }));
    try {
      const response = await applicationsApi.getStatusEvents(item.application_id);
      setTimelines(previous => ({
        ...previous,
        [item.retention_case_id]: { state: 'ready', events: Array.isArray(response.data) ? response.data : [] },
      }));
    } catch (err: any) {
      setTimelines(previous => ({
        ...previous,
        [item.retention_case_id]: {
          state: 'error',
          message: err.response?.status === 403
            ? t('Chỉ HR phụ trách mới xem được lịch sử quyết định của hồ sơ này.')
            : (err.response?.data?.detail || t('Không tải được timeline của hồ sơ.')),
        },
      }));
    }
  };

  const summary = summarizeRetentionCases(cases);
  const selectedPosition = positions.find(item => item.position_id === positionId);
  const statusLabel = (status: string) => t(APPLICATION_STATUSES[status as ApplicationStatus]?.label || status);
  const statusTone = (status: string) => (
    status === 'PENDING' ? { bg: '#FFFAEB', color: '#B54708' }
      : status === 'SCHEDULED_FOR_DELETION' ? { bg: '#EFF8FF', color: '#175CD3' }
        : status === 'DELETED' ? { bg: '#F2F4F7', color: '#344054' }
          : { bg: '#ECFDF3', color: '#067647' }
  );

  return (
    <Box>
      <Typography variant="h1" sx={{ fontSize: { xs: 24, md: 28 }, color: '#0A2B57', mb: 0.5 }}>{t('Dữ liệu & lưu trữ')}</Typography>
      <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
        {t('Xem và xác nhận việc xoá dữ liệu hồ sơ theo chính sách lưu trữ. Không có xoá tự động: mỗi trường hợp phải được người có quyền xác nhận.')}
      </Typography>

      <Paper variant="outlined" sx={{ p: 2, mb: 2 }}>
        <Stack direction={{ xs: 'column', sm: 'row' }} spacing={2} alignItems={{ xs: 'stretch', sm: 'center' }}>
          <FormControl size="small" sx={{ minWidth: 280, flex: 1 }} disabled={!positions.length}>
            <InputLabel id="retention-position-label">{t('Vị trí')}</InputLabel>
            <Select
              labelId="retention-position-label"
              label={t('Vị trí')}
              value={positionId}
              onChange={event => setPositionId(event.target.value)}
              inputProps={{ 'data-testid': 'retention-position-select' }}
            >
              {positions.map(item => (
                <MenuItem key={item.position_id} value={item.position_id}>
                  {[item.position_code, item.title, item.status === 'CLOSED' ? t('Đã đóng') : null].filter(Boolean).join(' · ')}
                </MenuItem>
              ))}
            </Select>
          </FormControl>
          <Button
            variant="outlined"
            onClick={() => setGenerateOpen(true)}
            disabled={!positionId || loading}
            sx={{ minHeight: 44 }}
            data-testid="retention-generate-open"
          >
            {t('Tạo trường hợp lưu trữ')}
          </Button>
        </Stack>
      </Paper>

      {positionsError && <Alert severity="error" sx={{ mb: 2 }}>{positionsError}</Alert>}
      {error && <Alert severity="error" sx={{ mb: 2 }} action={<Button color="inherit" onClick={() => void loadCases(positionId)}>{t('Thử lại')}</Button>}>{error}</Alert>}
      {notice && <Alert severity="success" sx={{ mb: 2 }} onClose={() => setNotice('')} data-testid="retention-notice">{notice}</Alert>}

      {!positions.length && !positionsError && <Alert severity="info">{t('Chưa có vị trí nào để xem dữ liệu lưu trữ.')}</Alert>}
      {selectedPosition && (
        <Typography variant="body2" color="text.secondary" sx={{ mb: 1.5 }} data-testid="retention-summary">
          {t('Tổng {0} trường hợp · {1} đến hạn · {2} chờ xác nhận · {3} đã lên lịch xoá · {4} đã huỷ.', summary.total, summary.due, summary.pending, summary.scheduled, summary.cancelled)}
        </Typography>
      )}

      {loading ? (
        <Box sx={{ display: 'flex', alignItems: 'center', gap: 1.5, py: 4 }}><CircularProgress size={22} /><Typography variant="body2" color="text.secondary">{t('Đang tải…')}</Typography></Box>
      ) : positionId && !error && cases.length === 0 ? (
        <Paper variant="outlined" sx={{ p: 4, textAlign: 'center', color: 'text.secondary' }}>{t('Không có trường hợp lưu trữ nào cho vị trí này.')}</Paper>
      ) : cases.length > 0 ? (
        <Paper variant="outlined">
          <TableContainer>
            <Table size="small" aria-label={t('Danh sách trường hợp lưu trữ')}>
              <TableHead>
                <TableRow>
                  <TableCell>{t('Mã ẩn danh')}</TableCell>
                  <TableCell>{t('Hạn xoá')}</TableCell>
                  <TableCell>{t('Trạng thái')}</TableCell>
                  <TableCell>{t('Thực thi')}</TableCell>
                  <TableCell>{t('Xác nhận lúc')}</TableCell>
                  <TableCell align="right">{t('Hành động')}</TableCell>
                </TableRow>
              </TableHead>
              <TableBody>
                {cases.map(item => {
                  const tone = statusTone(item.status);
                  const timeline = timelines[item.retention_case_id];
                  const timelineOpen = Boolean(timeline);
                  return (
                    <Fragment key={item.retention_case_id}>
                      <TableRow hover data-testid={`retention-case-${item.retention_case_id}`}>
                        <TableCell>
                          <Stack direction="row" spacing={0.5} alignItems="center" flexWrap="wrap">
                            <Typography variant="body2" sx={{ fontFamily: 'monospace' }}>{shortId(item.application_opaque_id)}</Typography>
                            {item.is_due && <Chip size="small" label={t('Đến hạn')} sx={{ height: 20, fontSize: 10, backgroundColor: '#FDF2F2', color: '#B42318', fontWeight: 700 }} />}
                          </Stack>
                          <Typography variant="caption" color="text.secondary">{t('Chính sách phiên bản {0}', item.policy_version || '—')}</Typography>
                        </TableCell>
                        <TableCell><Typography variant="body2">{retentionDate(item.due_date, dateLocale)}</Typography></TableCell>
                        <TableCell>
                          <Chip size="small" label={t(retentionStatusLabel(item.status))} data-testid={`retention-status-${item.retention_case_id}`}
                            sx={{ height: 22, fontSize: 11, fontWeight: 700, backgroundColor: tone.bg, color: tone.color }} />
                        </TableCell>
                        <TableCell><Typography variant="body2">{t(retentionExecutionLabel(item.execution_status))}</Typography></TableCell>
                        <TableCell><Typography variant="body2">{retentionDate(item.confirmed_at, dateLocale)}</Typography></TableCell>
                        <TableCell align="right">
                          <Stack direction="row" spacing={1} justifyContent="flex-end" flexWrap="wrap">
                            <Button size="small" onClick={() => void toggleTimeline(item)} data-testid={`retention-timeline-${item.retention_case_id}`}
                              disabled={!hasApplicationTimeline(item)} title={hasApplicationTimeline(item) ? undefined : t('Hồ sơ đã bị xoá; không còn timeline quyết định.')}>
                              {timelineOpen ? t('Ẩn timeline') : t('Timeline')}
                            </Button>
                            <Button size="small" variant="outlined" color="error" disabled={!canConfirmRetentionCase(item)}
                              onClick={() => setPendingAction({ kind: 'confirm', item })} data-testid={`retention-confirm-${item.retention_case_id}`}>
                              {t('Xác nhận')}
                            </Button>
                            <Button size="small" disabled={!canCancelRetentionCase(item)}
                              onClick={() => setPendingAction({ kind: 'cancel', item })} data-testid={`retention-cancel-${item.retention_case_id}`}>
                              {t('Hủy')}
                            </Button>
                          </Stack>
                        </TableCell>
                      </TableRow>
                      {timelineOpen && (
                        <TableRow>
                          <TableCell colSpan={6} sx={{ backgroundColor: '#F8FAFC' }}>
                            {timeline.state === 'loading' && <Typography variant="body2" color="text.secondary">{t('Đang tải timeline…')}</Typography>}
                            {timeline.state === 'error' && <Alert severity="warning">{timeline.message}</Alert>}
                            {timeline.state === 'ready' && (
                              (timeline.events || []).length === 0
                                ? <Typography variant="body2" color="text.secondary">{t('Chưa có sự kiện quyết định nào cho hồ sơ này.')}</Typography>
                                : <Stack spacing={1} data-testid={`retention-timeline-list-${item.retention_case_id}`}>
                                  {(timeline.events || []).map(event => (
                                    <Box key={event.event_id} sx={{ borderLeft: '3px solid #B9CBE2', pl: 1.5 }}>
                                      <Typography variant="body2">
                                        {statusLabel(event.previous_status || '')} → <strong>{statusLabel(event.new_status)}</strong>
                                      </Typography>
                                      <Typography variant="caption" color="text.secondary">
                                        {retentionDate(event.changed_at, dateLocale)} · {event.changed_by_name || t('Không rõ người thay đổi')}
                                      </Typography>
                                      {event.reason && <Typography variant="caption" sx={{ display: 'block' }}>{t('Lý do: {0}', event.reason)}</Typography>}
                                      {event.note && <Typography variant="caption" sx={{ display: 'block' }}>{t('Ghi chú: {0}', event.note)}</Typography>}
                                    </Box>
                                  ))}
                                </Stack>
                            )}
                          </TableCell>
                        </TableRow>
                      )}
                    </Fragment>
                  );
                })}
              </TableBody>
            </Table>
          </TableContainer>
        </Paper>
      ) : null}

      <Dialog open={generateOpen} onClose={() => (generating ? undefined : setGenerateOpen(false))} maxWidth="sm" fullWidth data-testid="retention-generate-dialog">
        <DialogTitle>{t('Tạo trường hợp lưu trữ')}</DialogTitle>
        <DialogContent dividers>
          <DialogContentText>
            {t('Hệ thống chỉ tạo trường hợp cho vị trí đã đóng và đã quá thời hạn lưu trữ. Mỗi hồ sơ chưa có trường hợp đang mở sẽ nhận một trường hợp ở trạng thái Chờ xác nhận; bước này chưa xoá dữ liệu.')}
          </DialogContentText>
        </DialogContent>
        <DialogActions sx={{ p: 2 }}>
          <Button onClick={() => setGenerateOpen(false)} disabled={generating} sx={{ minHeight: 44 }}>{t('Hủy')}</Button>
          <Button variant="contained" color="secondary" onClick={() => void generate()} disabled={generating} sx={{ minHeight: 44 }} data-testid="retention-generate-confirm">
            {generating ? t('Đang tạo…') : t('Tạo trường hợp')}
          </Button>
        </DialogActions>
      </Dialog>

      <Dialog open={Boolean(pendingAction)} onClose={() => (acting ? undefined : setPendingAction(null))} maxWidth="sm" fullWidth data-testid="retention-action-dialog">
        <DialogTitle>{pendingAction?.kind === 'confirm' ? t('Xác nhận xoá dữ liệu hồ sơ này?') : t('Huỷ trường hợp lưu trữ này?')}</DialogTitle>
        <DialogContent dividers>
          <DialogContentText>
            {pendingAction?.kind === 'confirm'
              ? t('Trường hợp {0} sẽ vào hàng đợi xoá theo chính sách lưu trữ. Dữ liệu chưa bị xoá ngay; bước thực thi do quy trình riêng đảm nhiệm.', shortId(pendingAction.item.application_opaque_id))
              : t('Trường hợp {0} sẽ không bị xoá và hồ sơ vẫn được giữ theo chính sách hiện hành.', shortId(pendingAction?.item.application_opaque_id))}
          </DialogContentText>
        </DialogContent>
        <DialogActions sx={{ p: 2 }}>
          <Button onClick={() => setPendingAction(null)} disabled={acting} sx={{ minHeight: 44 }}>{t('Đóng')}</Button>
          <Button variant="contained" color={pendingAction?.kind === 'confirm' ? 'error' : 'primary'} onClick={() => void runAction()} disabled={acting}
            sx={{ minHeight: 44 }} data-testid="retention-action-confirm">
            {acting ? t('Đang cập nhật…') : pendingAction?.kind === 'confirm' ? t('Xác nhận') : t('Huỷ trường hợp')}
          </Button>
        </DialogActions>
      </Dialog>
    </Box>
  );
}
