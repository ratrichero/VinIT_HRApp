'use client';

import { useI18n } from '@/i18n/I18nProvider';
import { localizeServerMessage } from '@/i18n/serverMessages';

import * as React from 'react';
import {
  Box,
  Typography,
  Button,
  Card,
  CardContent,
  Grid,
  CircularProgress,
  Alert,
  Divider,
  Paper,
  Chip,
  IconButton,
  Tooltip,
  Dialog,
  DialogTitle,
  DialogContent,
  DialogActions,
  TextField,
  MenuItem,
  Select,
  InputLabel,
  FormControl,
  Snackbar,
  Accordion,
  AccordionSummary,
  AccordionDetails,
} from '@mui/material';
import ArrowBackIcon from '@mui/icons-material/ArrowBack';
import GetAppIcon from '@mui/icons-material/GetApp';
import NavigateNextIcon from '@mui/icons-material/NavigateNext';
import NavigateBeforeIcon from '@mui/icons-material/NavigateBefore';
import ExpandMoreIcon from '@mui/icons-material/ExpandMore';
import ReplayIcon from '@mui/icons-material/Replay';
import { useCallback, useEffect, useRef, useState } from 'react';
import { useParams } from 'next/navigation';
import Link from 'next/link';
import { applicationsApi, operationsApi } from '@/lib/api';
import StatusBadge from '@/components/common/StatusBadge';
import StickyActionBar from '@/components/common/StickyActionBar';
import CandidateProfilePanel from '@/components/candidates/CandidateProfilePanel';
import EvidenceCard from '@/components/candidates/EvidenceCard';
import CVDocumentViewer from '@/components/candidates/CVDocumentViewer';
import HRNotesPanel from '@/components/candidates/HRNotesPanel';
import { readApplicantNavigation, type ApplicantNavigationContext } from '@/lib/applicantReview';
import type { ApplicationWithAssessment } from '@/types';
import { APPLICATION_STATUSES, APPLICATION_TRANSITIONS, isApplicationStatus } from '@/lib/applicationStatus';

interface StatusEvent {
  event_id: string;
  previous_status: string | null;
  new_status: string;
  reason: string | null;
  note: string | null;
  changed_at: string;
  changed_by_name: string | null;
}

export default function ApplicantDetailPage() {
  const { t, dateLocale, locale } = useI18n();
  const params = useParams();
  const positionId = params.id as string;
  const applicantId = params.applicantId as string;

  const [application, setApplication] = useState<ApplicationWithAssessment | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [statusDialogOpen, setStatusDialogOpen] = useState(false);
  const [newStatus, setNewStatus] = useState('');
  const [statusReason, setStatusReason] = useState('');
  const [statusNote, setStatusNote] = useState('');
  const [statusError, setStatusError] = useState<string | null>(null);
  const [statusSubmitting, setStatusSubmitting] = useState(false);
  const [success, setSuccess] = useState(false);
  const [reprocessing, setReprocessing] = useState(false);
  const [reprocessError, setReprocessError] = useState<string | null>(null);
  const [reprocessOperationId, setReprocessOperationId] = useState<string | null>(null);
  const [reprocessNotice, setReprocessNotice] = useState(false);
  const [history, setHistory] = useState<StatusEvent[]>([]);
  const [historyError, setHistoryError] = useState<string | null>(null);
  const [selectedPage, setSelectedPage] = useState(1);
  const [selectedEvidenceId, setSelectedEvidenceId] = useState<string | null>(null);
  const [navigationContext, setNavigationContext] = useState<ApplicantNavigationContext | null>(null);
  const [cvUrl, setCvUrl] = useState<string | null>(null);
  const [cvError, setCvError] = useState<string | null>(null);
  const [cvDownloading, setCvDownloading] = useState(false);
  const blobUrl = useRef<string | null>(null);
  const requestId = useRef(0);

  const loadData = useCallback(async (initial = false) => {
    const currentRequest = ++requestId.current;
    try {
      if (initial) setLoading(true);
      const res = await applicationsApi.getById(applicantId);
      if (currentRequest !== requestId.current) return;
      if (res.data.position_id !== positionId) throw new Error(t("Hồ sơ không thuộc vị trí này"));
      setApplication(res.data);
      setError(null);
      if (res.data.can_update_status) {
        applicationsApi.getStatusEvents(applicantId).then(events => {
          if (currentRequest === requestId.current) { setHistory(events.data || []); setHistoryError(null); }
        }).catch(() => { if (currentRequest === requestId.current) setHistoryError(t("Không thể tải lịch sử trạng thái.")); });
      } else { setHistory([]); setHistoryError(null); }
      if (res.data.can_view_cv) {
        try {
          const file = await applicationsApi.getCvBlob(applicantId);
          if (currentRequest !== requestId.current) return;
          if (blobUrl.current) { URL.revokeObjectURL(blobUrl.current); blobUrl.current = null; }
          setCvError(null);
          blobUrl.current = URL.createObjectURL(file.data);
          setCvUrl(blobUrl.current);
        } catch {
          if (currentRequest === requestId.current) { setCvUrl(null); setCvError(t("Không thể tải CV gốc. Vui lòng thử lại sau.")); }
        }
      } else {
        if (blobUrl.current) { URL.revokeObjectURL(blobUrl.current); blobUrl.current = null; }
        setCvUrl(null); setCvError(null);
      }
    } catch (err: any) {
      if (currentRequest === requestId.current) {
        if (err.response?.status === 403 || err.response?.status === 404) setApplication(null);
        setError(err.response?.data?.detail || t("Không thể tải thông tin hồ sơ"));
      }
    } finally { if (currentRequest === requestId.current) setLoading(false); }
  }, [applicantId, positionId, t]);

  useEffect(() => {
    loadData(true);
    return () => { requestId.current += 1; if (blobUrl.current) { URL.revokeObjectURL(blobUrl.current); blobUrl.current = null; } };
  }, [loadData]);

  useEffect(() => {
    setNavigationContext(readApplicantNavigation(positionId));
    setSelectedEvidenceId(null);
    setSelectedPage(1);
  }, [positionId, applicantId]);

  const handleDownloadCv = async () => {
    if (cvDownloading) return;
    setCvDownloading(true);
    try {
      // A download is a separate authorized/audited request, not the preview blob.
      const file = await applicationsApi.getCvBlob(applicantId);
      const url = URL.createObjectURL(file.data);
      const link = document.createElement('a');
      link.href = url;
      link.download = application?.documents?.[0]?.original_filename || 'cv';
      document.body.appendChild(link);
      link.click();
      link.remove();
      window.setTimeout(() => URL.revokeObjectURL(url), 1000);
      setCvError(null);
    } catch (err: any) {
      if (err.response?.status === 403 || err.response?.status === 404) {
        if (blobUrl.current) { URL.revokeObjectURL(blobUrl.current); blobUrl.current = null; }
        setCvUrl(null);
      }
      setCvError(t("Không thể tải CV gốc. Vui lòng thử lại sau."));
    } finally { setCvDownloading(false); }
  };

  const handleStatusUpdate = async () => {
    if (!newStatus || statusSubmitting) return;
    const rejected = newStatus.startsWith('REJECTED');
    if (rejected && !statusReason.trim()) { setStatusError(t("Vui lòng nhập lý do loại hồ sơ.")); return; }
    try {
      setStatusSubmitting(true); setStatusError(null);
      await applicationsApi.updateStatus(applicantId, newStatus, statusReason.trim() || undefined, statusNote.trim() || undefined);
      setStatusDialogOpen(false); setSuccess(true);
      await loadData();
    } catch (err: any) {
      setStatusError(err.response?.data?.detail || t("Cập nhật trạng thái không thành công"));
    } finally { setStatusSubmitting(false); }
  };

  const handleReprocess = async () => {
    if (reprocessing) return;
    try {
      setReprocessing(true);
      setReprocessError(null);
      const res = await applicationsApi.reprocess(applicantId);
      setReprocessOperationId(res.data.operation_id);
      setReprocessNotice(true);
    } catch (err: any) {
      setReprocessError(err.response?.data?.detail || t("Không thể đưa CV vào hàng đợi xử lý lại."));
      setReprocessing(false);
    }
  };

  useEffect(() => {
    if (!reprocessOperationId) return;
    const timer = setInterval(async () => {
      try {
        const res = await operationsApi.getStatus(reprocessOperationId);
        if (res.data.status === 'COMPLETED') {
          setReprocessOperationId(null);
          setReprocessing(false);
          await loadData();
        } else if (res.data.status === 'FAILED') {
          setReprocessOperationId(null);
          setReprocessing(false);
          setReprocessError(t("Không thể xử lý lại CV. Vui lòng kiểm tra và thử lại sau."));
        }
      } catch {
        // Keep polling; a transient status read must not cancel the job.
      }
    }, 3000);
    return () => clearInterval(timer);
  }, [reprocessOperationId, loadData, t]);

  const jumpToPage = (page: number) => { if (page >= 1) setSelectedPage(page); };

  if (loading) {
    return (
      <Box sx={{ display: 'flex', justifyContent: 'center', mt: 10 }}>
        <CircularProgress color="secondary" />
      </Box>
    );
  }

  if (!application) {
    return <Alert severity="error" action={<Button onClick={() => loadData(true)}>{t("Thử lại")}</Button>}>{t(error || "Không tìm thấy hồ sơ ứng viên")}</Alert>;
  }

  const assessment = application.latest_assessment;
  const criteriaResults = assessment?.criterion_results || [];
  const canViewEvidence = Boolean(application.can_view_assessment_evidence);
  const currentStatus = isApplicationStatus(application.application_status) ? application.application_status : null;
  const nextStatuses = currentStatus ? APPLICATION_TRANSITIONS[currentStatus] : [];
  const statusLabel = currentStatus ? APPLICATION_STATUSES[currentStatus] : null;
  const selectedLabel = isApplicationStatus(newStatus) ? t(APPLICATION_STATUSES[newStatus].label) : newStatus;
  const isPdf = application.documents?.[0]?.mime_type === 'application/pdf' || /\.pdf$/i.test(application.documents?.[0]?.original_filename || '');
  const navigationIndex = navigationContext?.applicationIds.indexOf(applicantId) ?? -1;
  const previousApplicantId = navigationIndex > 0 ? navigationContext?.applicationIds[navigationIndex - 1] : undefined;
  const nextApplicantId = navigationContext && navigationIndex >= 0 && navigationIndex < navigationContext.applicationIds.length - 1
    ? navigationContext.applicationIds[navigationIndex + 1]
    : undefined;
  const backSearch = new URLSearchParams();
  if (navigationContext) {
    if (navigationContext.queue !== 'ALL') backSearch.set('queue', navigationContext.queue);
    if (navigationContext.sort !== 'REVIEW_PRIORITY') backSearch.set('sort', navigationContext.sort);
    if (navigationContext.search.trim()) backSearch.set('q', navigationContext.search.trim());
  }
  const backHref = application.can_update_status
    ? `/positions/${positionId}/applicants${backSearch.toString() ? `?${backSearch.toString()}` : ''}`
    : '/shortlist';

  return (
    <Box>
      {/* Back button */}
      <Button
        component={Link}
        href={backHref}
        startIcon={<ArrowBackIcon />}
        sx={{ color: '#0A2B57', mb: 2 }}
      >
        {application.can_update_status ? t("Quay lại danh sách xếp hạng") : t("Quay lại shortlist")}
      </Button>

      <StickyActionBar>
        <Box sx={{ display: 'flex', alignItems: 'center', gap: 2, flexWrap: 'wrap' }}>
          <Box sx={{ minWidth: 220, flex: 1 }}>
            <Typography variant="body1" fontWeight={700} color="#0A2B57">{application.identity?.display_name || t("Hồ sơ ứng viên")}</Typography>
            <Typography variant="caption" color="text.secondary">
              {navigationIndex >= 0 && navigationContext
                ? t("Hồ sơ {0}/{1} trong hàng đợi đang xem", navigationIndex + 1, navigationContext.applicationIds.length)
                : t("Đang xem chi tiết hồ sơ")}
              {assessment?.matching_score != null ? ` · ${t("Điểm matching")} ${assessment.matching_score}%` : ''}
              {assessment?.evidence_coverage != null ? ` · ${t("Độ phủ bằng chứng")} ${Math.round(assessment.evidence_coverage * 100)}%` : ''}
            </Typography>
          </Box>
          {previousApplicantId ? (
            <Button component={Link} href={`/positions/${positionId}/applicants/${previousApplicantId}`} variant="outlined" size="small" startIcon={<NavigateBeforeIcon />}>{t("Hồ sơ trước")}</Button>
          ) : (
            <Button variant="outlined" size="small" startIcon={<NavigateBeforeIcon />} disabled>{t("Hồ sơ trước")}</Button>
          )}
          {nextApplicantId ? (
            <Button component={Link} href={`/positions/${positionId}/applicants/${nextApplicantId}`} variant="contained" color="secondary" size="small" endIcon={<NavigateNextIcon />}>{t("Hồ sơ tiếp theo")}</Button>
          ) : (
            <Button variant="outlined" size="small" endIcon={<NavigateNextIcon />} disabled>{t("Hồ sơ tiếp theo")}</Button>
          )}
        </Box>
      </StickyActionBar>

      {/* Warnings */}
      {(application.file_processing_status === 'NEEDS_HR_REVIEW' || application.has_duplicate_warning) && (
        <Alert
          severity="warning"
          sx={{ mb: 2, border: '1px solid #FEDF89' }}
        >
          {application.file_processing_status === 'NEEDS_HR_REVIEW' && (
            <>
              <Typography variant="body2">
                <strong>{t("CV cần được HR xem lại:")}</strong> {application.file_error ? localizeServerMessage(application.file_error, locale) : t("File CV có vấn đề (lỗi xử lý, định dạng quét/OCR cần thiết, hoặc bị mã hóa).")}
              </Typography>
              {application.can_update_status && (
                <Box sx={{ mt: 1, display: 'flex', gap: 1, alignItems: 'center', flexWrap: 'wrap' }}>
                  <Button size="small" variant="contained" color="warning" startIcon={<ReplayIcon />} disabled={reprocessing} onClick={handleReprocess}>
                    {reprocessing ? t("Đang xử lý lại…") : t("Xử lý lại CV")}
                  </Button>
                  {reprocessError && <Typography variant="body2" color="error">{reprocessError}</Typography>}
                </Box>
              )}
            </>
          )}
          {application.has_duplicate_warning && (
            <Typography variant="body2" sx={{ mt: application.file_processing_status === 'NEEDS_HR_REVIEW' ? 0.5 : 0 }}>
              <strong>{t("Cảnh báo trùng lặp:")}</strong> {t("Phát hiện hồ sơ có thể đã tồn tại trong hệ thống. Vui lòng kiểm tra lại trước khi đưa ra quyết định.")}</Typography>
          )}
        </Alert>
      )}

      {/* Applicant Header */}
      <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', gap: 2, flexWrap: 'wrap', mb: 2 }}>
        <Box>
          <Typography variant="h1" sx={{ fontSize: 24, color: '#0A2B57', mb: 0.5 }}>
            {application.identity?.display_name || t("Hồ sơ ứng viên")}
          </Typography>
          <Box sx={{ display: 'flex', gap: 2, alignItems: 'center', mt: 1, flexWrap: 'wrap' }}>
            <Typography variant="body2" color="text.secondary" fontFamily="monospace">
              ID: {application.application_id.slice(0, 8)}...
            </Typography>
            {application.file_processing_status === 'PROCESSING' && (
              <Chip label={t("Đang xử lý CV")} size="small" />
            )}
            {application.has_duplicate_warning && (
              <Chip label={t("Hồ sơ trùng lặp")} size="small" sx={{ backgroundColor: '#FEF0C7', color: '#B54708' }} />
            )}
            {assessment && (
              <>
                {assessment.matching_status === 'MEETS_MANDATORY' && (
                  <StatusBadge type="match-meets" label={t("Đáp ứng bắt buộc")} />
                )}
                {assessment.matching_status === 'NEEDS_HR_VERIFICATION' && (
                  <StatusBadge type="match-verify" label={t("Cần HR xác minh")} />
                )}
                {assessment.matching_status === 'POSSIBLE_MISMATCH' && (
                  <StatusBadge type="match-mismatch" label={t("Có dấu hiệu miss-match")} />
                )}
              </>
            )}
            {statusLabel && <StatusBadge type={statusLabel.badge} label={t(statusLabel.label)} />}
          </Box>
        </Box>

        <Box sx={{ display: 'flex', gap: 1, flexWrap: 'wrap' }}>
          <Button
            variant="outlined"
            startIcon={<GetAppIcon />}
            onClick={handleDownloadCv}
            disabled={!cvUrl || cvDownloading}
            sx={{ borderColor: '#0A2B57', color: '#0A2B57' }}
          >{t("Tải CV gốc")}</Button>
          {application.can_update_status && nextStatuses.length > 0 && (
            <FormControl size="small" sx={{ minWidth: 220 }}>
              <InputLabel id="application-status-label">{t("Cập nhật trạng thái")}</InputLabel>
              <Select
                labelId="application-status-label"
                value=""
                label={t("Cập nhật trạng thái")}
                onChange={(e) => {
                  if (e.target.value) {
                    setNewStatus(e.target.value);
                    setStatusReason(''); setStatusNote(''); setStatusError(null);
                    setStatusDialogOpen(true);
                  }
                }}
              >
                {nextStatuses.map(code => (
                  <MenuItem key={code} value={code}>{t(APPLICATION_STATUSES[code].label)}</MenuItem>
                ))}
              </Select>
            </FormControl>
          )}
          {application.can_update_status && currentStatus && nextStatuses.length === 0 && (
            <Chip label={t("Hồ sơ đã kết thúc")} size="small" color="default" />
          )}
        </Box>
      </Box>

      {cvError && <Alert severity="error" sx={{ mb: 2 }}>{t(cvError)}</Alert>}
      {assessment?.evidence_coverage != null && assessment.evidence_coverage < 0.7 && (
        <Alert severity="warning" sx={{ mb: 2 }}>{t("Chưa đủ dữ liệu để xếp hạng ổn định. Điểm chỉ mang tính tham khảo; HR cần kiểm tra bằng chứng trước khi quyết định.")}</Alert>
      )}

      {/* Score summary */}
      {assessment && (
        <Grid container spacing={2} sx={{ mb: 3 }}>
          <Grid item xs={12} sm={4}>
            <Card>
              <CardContent sx={{ textAlign: 'center' }}>
                <Typography variant="caption" color="text.secondary">{t("Điểm trên tiêu chí đã có bằng chứng")}</Typography>
                <Typography
                  variant="h3"
                  sx={{
                    fontSize: 32,
                    fontWeight: 'bold',
                    color: assessment.evidence_coverage != null && assessment.evidence_coverage < 0.7 ? '#B54708' :
                            assessment.matching_score != null && assessment.matching_score >= 80 ? '#067647' :
                            assessment.matching_score != null && assessment.matching_score >= 60 ? '#0A2B57' : '#B54708',
                    mt: 1,
                  }}
                >
                  {assessment.matching_score !== null ? `${assessment.matching_score}%` : '-'}
                </Typography>
              </CardContent>
            </Card>
          </Grid>
          <Grid item xs={12} sm={4}>
            <Card>
              <CardContent sx={{ textAlign: 'center' }}>
                <Typography variant="caption" color="text.secondary">{t("Độ phủ bằng chứng")}</Typography>
                <Typography
                  variant="h3"
                  sx={{
                    fontSize: 32,
                    fontWeight: 'bold',
                    color: (assessment.evidence_coverage || 0) >= 0.7 ? '#067647' : '#B54708',
                    mt: 1,
                  }}
                >
                  {assessment.evidence_coverage !== null ? `${Math.round(assessment.evidence_coverage * 100)}%` : '-'}
                </Typography>
                {assessment.evidence_coverage !== null && assessment.evidence_coverage < 0.7 && (
                  <Typography variant="caption" color="#B54708">{t("Chưa đủ dữ liệu để xếp hạng ổn định")}</Typography>
                )}
              </CardContent>
            </Card>
          </Grid>
          <Grid item xs={12} sm={4}>
            <Card>
              <CardContent sx={{ textAlign: 'center' }}>
                <Typography variant="caption" color="text.secondary">{t("Số tiêu chí đánh giá")}</Typography>
                <Typography variant="h3" sx={{ fontSize: 32, fontWeight: 'bold', color: '#0A2B57', mt: 1 }}>
                  {canViewEvidence ? criteriaResults.length : '—'}
                </Typography>
                <Typography variant="caption" color="text.secondary">
                  {canViewEvidence ? t("{0} đáp ứng, {1} chưa rõ", criteriaResults.filter(r => r.outcome === 'MATCH' || r.outcome === 'STRONG_MATCH').length, criteriaResults.filter(r => r.outcome === 'UNCLEAR').length) : t("Chỉ được phép xem tóm tắt")}
                </Typography>
              </CardContent>
            </Card>
          </Grid>
        </Grid>
      )}

      {error && (
        <Alert severity="error" sx={{ mb: 3 }} onClose={() => setError(null)}>
          {t(error)}
        </Alert>
      )}

      {/* Side-by-side layout: Evidence on left, CV on right */}
      <Grid container spacing={3}>
        {/* Left Column: Criteria Assessment & Evidence */}
        <Grid item xs={12} md={6}>
          <Typography variant="h4" sx={{ fontSize: 16, fontWeight: 600, color: '#0A2B57', mb: 2 }}>{t("Kết quả đánh giá theo tiêu chí")}</Typography>

          {criteriaResults.length === 0 ? (
            <Card>
              <CardContent sx={{ textAlign: 'center', py: 6, color: 'text.secondary' }}>{assessment && !canViewEvidence ? t("Bản đánh giá này chỉ được chia sẻ ở chế độ tóm tắt.") : t("Chưa có kết quả đánh giá cho hồ sơ này")}</CardContent>
            </Card>
          ) : (
            <Box sx={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
              {criteriaResults.map((result) => (
                <EvidenceCard
                  key={result.criterion_id}
                  result={result}
                  isPdf={isPdf}
                  hasCv={Boolean(cvUrl)}
                  selected={selectedEvidenceId === result.criterion_id}
                  onJumpToPage={(page, criterionId) => { setSelectedEvidenceId(criterionId); jumpToPage(page); }}
                />
              ))}
            </Box>
          )}
        </Grid>

        {/* Right Column: CV Viewer */}
        <Grid item xs={12} md={6}>
          <CVDocumentViewer
            cvUrl={cvUrl}
            cvError={cvError}
            isPdf={isPdf}
            canViewCv={Boolean(application.can_view_cv)}
            selectedPage={selectedPage}
            onPageChange={jumpToPage}
          />
        </Grid>
      </Grid>

      {application.can_view_cv && <CandidateProfilePanel key={applicantId} applicationId={applicantId} canEdit={!!application.can_update_status} onSaved={() => { loadData(); }} />}
      {application.can_manage_hr_notes && <HRNotesPanel key={applicantId} applicationId={applicantId} />}

      {application.can_update_status && (
        <Accordion disableGutters elevation={0} sx={{ mb: 3, border: '1px solid #E4E7EC', borderRadius: '8px !important', '&:before': { display: 'none' } }}>
          <AccordionSummary expandIcon={<ExpandMoreIcon />} aria-controls="status-history-content" id="status-history-header">
            <Typography fontWeight={600}>{t("Lịch sử trạng thái ")}{history.length > 0 && `(${history.length})`}</Typography>
          </AccordionSummary>
          <AccordionDetails id="status-history-content">
            {historyError ? <Alert severity="error">{t(historyError)}</Alert> : history.length === 0 ? (
              <Typography variant="body2" color="text.secondary">{t("Chưa có thay đổi trạng thái.")}</Typography>
            ) : history.map(event => (
              <Box key={event.event_id} sx={{ py: 1.5, borderTop: '1px solid #EDF1F5' }}>
                <Typography variant="body2" fontWeight={600}>
                  {event.previous_status && isApplicationStatus(event.previous_status) ? t(APPLICATION_STATUSES[event.previous_status].label) : event.previous_status || '—'} →{' '}
                  {isApplicationStatus(event.new_status) ? t(APPLICATION_STATUSES[event.new_status].label) : event.new_status}
                </Typography>
                <Typography variant="caption" color="text.secondary">{event.changed_by_name || 'HR'} · {new Date(event.changed_at).toLocaleString(dateLocale)}</Typography>
                {event.reason && <Typography variant="body2" sx={{ mt: 0.5, whiteSpace: 'pre-wrap' }}>{t("Lý do: ")}{event.reason}</Typography>}
                {event.note && <Typography variant="body2" color="text.secondary" sx={{ whiteSpace: 'pre-wrap' }}>{t("Ghi chú: ")}{event.note}</Typography>}
              </Box>
            ))}
          </AccordionDetails>
        </Accordion>
      )}

      {/* Status changes follow the server transition matrix. */}
      <Dialog open={statusDialogOpen} onClose={() => !statusSubmitting && setStatusDialogOpen(false)} maxWidth="sm" fullWidth>
        <DialogTitle>{t("Xác nhận chuyển sang: ")}{selectedLabel}</DialogTitle>
        <DialogContent dividers>
          <Typography variant="body2" sx={{ mb: 2 }}>{t("            Trạng thái hiện tại:")} <strong>{statusLabel ? t(statusLabel.label) : ""}</strong>{t(". Quyết định và lý do sẽ được lưu vào lịch sử hồ sơ.")}</Typography>
          {statusError && <Alert severity="error" sx={{ mb: 2 }}>{t(statusError)}</Alert>}
          {newStatus.startsWith('REJECTED') && (
            <TextField label={t("Lý do loại hồ sơ")} required fullWidth multiline minRows={2} value={statusReason}
              onChange={e => setStatusReason(e.target.value)} inputProps={{ maxLength: 1000 }} sx={{ mb: 2 }} />
          )}
          <TextField label={t("Ghi chú (tùy chọn)")} fullWidth multiline minRows={2} value={statusNote}
            onChange={e => setStatusNote(e.target.value)} inputProps={{ maxLength: 2000 }} />
        </DialogContent>
        <DialogActions sx={{ p: 2 }}>
          <Button onClick={() => setStatusDialogOpen(false)} disabled={statusSubmitting}>{t("Hủy")}</Button>
          <Button variant="contained" color={newStatus.startsWith('REJECTED') ? 'error' : 'secondary'}
            disabled={statusSubmitting || (newStatus.startsWith('REJECTED') && !statusReason.trim())} onClick={handleStatusUpdate}>
            {statusSubmitting ? t("Đang lưu…") : t("Xác nhận")}
          </Button>
        </DialogActions>
      </Dialog>
      <Snackbar open={success} autoHideDuration={4000} onClose={() => setSuccess(false)}
        message={t("Đã cập nhật trạng thái hồ sơ")} />
      <Snackbar open={reprocessNotice} autoHideDuration={4000} onClose={() => setReprocessNotice(false)}
        message={t("Đã đưa CV vào hàng đợi xử lý lại.")} />
    </Box>
  );
}
