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
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  Paper,
  CircularProgress,
  Alert,
  Chip,
  LinearProgress,
  FormControl,
  InputLabel,
  Select,
  MenuItem,
  OutlinedInput,
  InputAdornment,
  IconButton,
  Tooltip,
  Stack,
  Link as MuiLink,
  TextField,
  Snackbar,
} from '@mui/material';
import SearchIcon from '@mui/icons-material/Search';
import RefreshIcon from '@mui/icons-material/Refresh';
import VisibilityIcon from '@mui/icons-material/Visibility';
import SortIcon from '@mui/icons-material/Sort';
import BookmarkAddOutlinedIcon from '@mui/icons-material/BookmarkAddOutlined';
import ArrowBackIcon from '@mui/icons-material/ArrowBack';
import ErrorOutlineIcon from '@mui/icons-material/ErrorOutline';
import PlaylistAddCheckIcon from '@mui/icons-material/PlaylistAddCheck';
import ShareIcon from '@mui/icons-material/Share';
import ExpandMoreIcon from '@mui/icons-material/ExpandMore';
import ExpandLessIcon from '@mui/icons-material/ExpandLess';
import Checkbox from '@mui/material/Checkbox';
import Dialog from '@mui/material/Dialog';
import DialogTitle from '@mui/material/DialogTitle';
import DialogContent from '@mui/material/DialogContent';
import DialogActions from '@mui/material/DialogActions';
import DialogContentText from '@mui/material/DialogContentText';
import FormControlLabel from '@mui/material/FormControlLabel';
import Switch from '@mui/material/Switch';
import Autocomplete from '@mui/material/Autocomplete';
import { useEffect, useState, useCallback, useRef } from 'react';
import { useParams } from 'next/navigation';
import Link from 'next/link';
import { assessmentsApi, operationsApi, applicationsApi, shortlistApi, positionsApi, type DuplicateSignal } from '@/lib/api';
import StatusBadge from '@/components/common/StatusBadge';
import QueueFilterChips from '@/components/applicants/QueueFilterChips';
import OperationProgressPanel from '@/components/workflow/OperationProgressPanel';
import {
  applicantQueueCounts,
  filterAndSortApplicantItems,
  isApplicantQueue,
  isApplicantSort,
  storeApplicantNavigation,
  type ApplicantQueue,
  type ApplicantSort,
} from '@/lib/applicantReview';
import type { RankingItem, UserSummary } from '@/types';
import { APPLICATION_STATUSES, isApplicationStatus } from '@/lib/applicationStatus';

const inScreening = (status?: string) => ['NEW', 'IN_REVIEW', 'SHORTLIST'].includes(status || '');

const OUTCOME_META: Record<string, { label: string; color: string }> = {
  STRONG_MATCH: { label: 'Đáp ứng tốt', color: '#067647' },
  MATCH: { label: 'Đáp ứng', color: '#0A2B57' },
  UNCLEAR: { label: 'Chưa rõ', color: '#B54708' },
  NO_MATCH: { label: 'Chưa đáp ứng', color: '#C72127' },
};

/** A score is only final once every rubric weight has clear evidence. */
const isPartialScore = (item: RankingItem) =>
  item.matching_score != null && item.evidence_coverage != null && item.evidence_coverage < 1;

export default function ApplicantsRankingPage() {
  const { t } = useI18n();
  const params = useParams();
  const positionId = params.id as string;

  const [duplicateSignals, setDuplicateSignals] = useState<DuplicateSignal[] | null>(null);
  const [duplicateError, setDuplicateError] = useState<string | null>(null);
  const [duplicateLoading, setDuplicateLoading] = useState(false);
  const loadDuplicates = async () => {
    setDuplicateLoading(true);
    setDuplicateError(null);
    try {
      const response = await positionsApi.getDuplicateSignals(positionId);
      setDuplicateSignals(response.data);
    } catch (err: any) {
      setDuplicateSignals(null);
      setDuplicateError(err.response?.data?.detail || t("Không thể tải cảnh báo trùng"));
    } finally { setDuplicateLoading(false); }
  };

  const [rankingItems, setRankingItems] = useState<RankingItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [assessing, setAssessing] = useState(false);
  const [operationStatus, setOperationStatus] = useState<import('@/types').OperationStatus | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [rankingError, setRankingError] = useState<string | null>(null);
  const [shareError, setShareError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [queue, setQueue] = useState<ApplicantQueue>('ALL');
  const [sort, setSort] = useState<ApplicantSort>('REVIEW_PRIORITY');
  const [searchQuery, setSearchQuery] = useState('');
  const pollTimerRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const urlInitializedRef = useRef(false);

  // Shortlist share dialog state
  const [shareDialogOpen, setShareDialogOpen] = useState(false);
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());
  const [shareRecipient, setShareRecipient] = useState<UserSummary | null>(null);
  const [shareRecipientQuery, setShareRecipientQuery] = useState('');
  const [shareRecipientOptions, setShareRecipientOptions] = useState<UserSummary[]>([]);
  const [shareAllowCv, setShareAllowCv] = useState(false);
  const [shareSubmitting, setShareSubmitting] = useState(false);
  const [expandedIds, setExpandedIds] = useState<Set<string>>(new Set());

  const toggleExpanded = (appId: string) => {
    setExpandedIds(prev => {
      const next = new Set(prev);
      if (next.has(appId)) next.delete(appId);
      else next.add(appId);
      return next;
    });
  };

  const renderCriterionBreakdown = (item: RankingItem) => {
    const results = item.criterion_results || [];
    if (!results.length) {
      return <Typography variant="body2" color="text.secondary">{t("Chưa có kết quả theo tiêu chí. Hãy chạy đánh giá để xem chi tiết.")}</Typography>;
    }
    return (
      <Box sx={{ display: 'grid', gap: 0.75 }}>
        {results.map(result => {
          const meta = OUTCOME_META[result.outcome] || OUTCOME_META.UNCLEAR;
          return (
            <Box key={result.criterion_id} sx={{ display: 'flex', alignItems: 'center', gap: 1, flexWrap: 'wrap' }}>
              <Typography variant="body2" fontWeight={600} sx={{ minWidth: 180, flex: '1 1 180px' }}>{result.criterion_name}</Typography>
              <Chip size="small" label={t(result.category === 'MUST_HAVE' ? "Bắt buộc" : "Ưu tiên")} sx={{ height: 20, fontSize: 10, backgroundColor: result.category === 'MUST_HAVE' ? '#FDF2F2' : '#E8F1FC', color: result.category === 'MUST_HAVE' ? '#941616' : '#0A2B57', fontWeight: 600 }} />
              <Typography variant="caption" color="text.secondary">{t("Trọng số {0}%", result.effective_weight ?? '—')}</Typography>
              <Chip size="small" variant="outlined" label={t(meta.label)} sx={{ height: 22, fontSize: 11, fontWeight: 700, color: meta.color, borderColor: meta.color }} />
              <Typography variant="body2" fontWeight={700} sx={{ color: meta.color, minWidth: 44 }}>{result.score == null ? '—' : `${result.score}%`}</Typography>
              {(result.outcome === 'UNCLEAR' || result.requires_verification) && (
                <Typography variant="caption" sx={{ color: '#B54708' }}>{t("Cần HR xác minh")}</Typography>
              )}
            </Box>
          );
        })}
        {isPartialScore(item) && (
          <Typography variant="caption" sx={{ color: '#B54708', mt: 0.5 }}>
            {t("Điểm một phần: chỉ tính trên {0}% trọng số tiêu chí đã có bằng chứng, chưa phải điểm cuối.", Math.round((item.evidence_coverage ?? 0) * 100))}
          </Typography>
        )}
      </Box>
    );
  };

  const loadRanking = useCallback(async () => {
    try {
      const [rankRes, appsRes] = await Promise.all([
        assessmentsApi.getLatestRanking(positionId),
        applicationsApi.listAll(positionId),
      ]);
      const ranks: RankingItem[] = rankRes.data || [];
      const apps: any[] = appsRes;

      // Merge ranking with application flags
      const appMap = new Map<string, any>();
      apps.forEach((a: any) => appMap.set(a.application_id, a));
      const merged = ranks.filter((r: RankingItem) => inScreening(appMap.get(r.application_id)?.application_status)).map((r: RankingItem) => {
        const a = appMap.get(r.application_id) || {};
        return {
          ...r,
          file_processing_status: a.file_processing_status,
          file_error: a.file_error,
          has_duplicate_warning: a.has_duplicate_warning,
          application_status: a.application_status,
          is_shortlisted: a.application_status === 'SHORTLIST',
          created_at: a.created_at,
        };
      });

      // Add unassessed applications to list (if they exist in apps response but not ranks)
      const rankedIds = new Set(merged.map(r => r.application_id));
      apps.forEach((a: any) => {
        if (!rankedIds.has(a.application_id)) {
          const identity = a.identity;
          let name = t("Chưa trích xuất tên");
          if (Array.isArray(identity) && identity[0]) name = identity[0].display_name || name;
          else if (identity && typeof identity === 'object') name = identity.display_name || name;
          merged.push({
            application_id: a.application_id,
            candidate_name: name,
            rank_number: null,
            matching_status: 'NOT_ASSESSED' as const,
            matching_score: null,
            evidence_coverage: null,
            needs_verification: false,
            has_mismatch: false,
            file_processing_status: a.file_processing_status,
            file_error: a.file_error,
            has_duplicate_warning: a.has_duplicate_warning,
            application_status: a.application_status,
            is_shortlisted: a.application_status === 'SHORTLIST',
            created_at: a.created_at,
          });
        }
      });

      setRankingError(null);
      setRankingItems(merged);
    } catch (err: any) {
      setRankingError(err.response?.data?.detail || t("Không thể tải bảng xếp hạng"));
    } finally {
      setLoading(false);
    }
  }, [positionId, t]);

  // Stop polling helper
  const stopPolling = useCallback(() => {
    if (pollTimerRef.current) {
      clearInterval(pollTimerRef.current);
      pollTimerRef.current = null;
    }
  }, []);

  // Poll operation status
  const pollOperation = useCallback((operationId: string) => {
    stopPolling();
    pollTimerRef.current = setInterval(async () => {
      try {
        const res = await operationsApi.getStatus(operationId);
        const data = res.data;
        setOperationStatus(data);
        if (data.status === 'COMPLETED' || data.status === 'FAILED') {
          stopPolling();
          setAssessing(false);
          if (data.status === 'COMPLETED') {
            await loadRanking();
            setNotice(data.progress?.failed ? t("Hoàn tất với {0} tệp cần kiểm tra.", data.progress.failed) : t("Đã cập nhật kết quả xếp hạng."));
          } else {
            setError(t("Đánh giá thất bại: {0}", data.error_message ? localizeServerMessage(data.error_message) : t("Lỗi không xác định")));
          }
        }
      } catch (e) {
        setError(t("Không thể cập nhật tiến trình. Hệ thống sẽ thử lại."));
      }
    }, 2000);
  }, [loadRanking, stopPolling, t]);

  useEffect(() => {
    let mounted = true;
    loadRanking();
    operationsApi.getActiveForPosition(positionId).then(res => {
      if (mounted && res.data) { setAssessing(true); setOperationStatus(res.data); pollOperation(res.data.operation_id); }
    }).catch(() => { if (mounted) setError(t("Không thể tải tiến trình đang xử lý.")); });
    return () => { mounted = false; stopPolling(); };
  }, [loadRanking, stopPolling, pollOperation, positionId, t]);

  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const queueParam = params.get('queue');
    const sortParam = params.get('sort');
    if (isApplicantQueue(queueParam)) setQueue(queueParam);
    if (isApplicantSort(sortParam)) setSort(sortParam);
    if (params.get('q')) setSearchQuery(params.get('q') || '');
    urlInitializedRef.current = true;
  }, []);

  useEffect(() => {
    if (!urlInitializedRef.current) return;
    const params = new URLSearchParams();
    if (queue !== 'ALL') params.set('queue', queue);
    if (sort !== 'REVIEW_PRIORITY') params.set('sort', sort);
    if (searchQuery.trim()) params.set('q', searchQuery.trim());
    const query = params.toString();
    window.history.replaceState(null, '', `${window.location.pathname}${query ? `?${query}` : ''}`);
  }, [queue, sort, searchQuery]);

  const handleRunAssessment = async () => {
    try {
      setAssessing(true);
      setError(null);
      const res = await assessmentsApi.runForPosition(positionId);
      if (String(res.data.status).toUpperCase() === 'COMPLETED') {
        setAssessing(false); setNotice(res.data.message || t("Không có hồ sơ cần đánh giá."));
        await loadRanking();
      } else {
        const opId = res.data.operation_id;
        setOperationStatus({ operation_id: opId, status: 'PENDING', progress: undefined });
        pollOperation(opId);
      }
    } catch (err: any) {
      setError(err.response?.data?.detail || t("Không thể chạy đánh giá"));
      setAssessing(false);
    }
  };

  // Only assigned, active Hiring Managers can be recipients.
  useEffect(() => {
    if (!shareDialogOpen) return;
    shortlistApi.getPotentialRecipients(positionId).then(res => setShareRecipientOptions(res.data || []))
      .catch(() => setShareError(t("Không thể tải danh sách Hiring Manager.")));
  }, [shareDialogOpen, positionId, t]);

  const handleToggleSelect = (appId: string) => {
    setSelectedIds(prev => {
      const next = new Set(prev);
      if (next.has(appId)) next.delete(appId);
      else next.add(appId);
      return next;
    });
  };

  const handleSelectAllVisible = () => {
    const visibleIds = filteredItems.filter(i => i.is_shortlisted).map(i => i.application_id);
    const allSelected = visibleIds.every(id => selectedIds.has(id));
    setSelectedIds(prev => {
      const next = new Set(prev);
      if (allSelected) visibleIds.forEach(id => next.delete(id));
      else visibleIds.forEach(id => next.add(id));
      return next;
    });
  };

  const handleOpenShare = () => {
    // Preserve an explicit selection; otherwise pre-select visible shortlist items.
    if (selectedIds.size === 0) {
      const shortlisted = rankingItems.filter(i => i.is_shortlisted).map(i => i.application_id);
      setSelectedIds(new Set(shortlisted));
    }
    setShareError(null);
    setShareDialogOpen(true);
  };

  const handleShareSubmit = async () => {
    if (!shareRecipient || selectedIds.size === 0) return;
    try {
      setShareSubmitting(true); setShareError(null);
      await shortlistApi.create({
        position_id: positionId,
        shared_with_user_id: shareRecipient.user_id,
        application_ids: Array.from(selectedIds),
        note: '',
        allow_cv_view: shareAllowCv,
      });
      setShareDialogOpen(false);
      setShareRecipient(null);
      setShareRecipientQuery('');
      setSelectedIds(new Set());
      setShareAllowCv(false);
      setNotice(t("Đã chia sẻ shortlist. Hiring Manager có thể xem trong mục Shortlist."));
    } catch (err: any) {
      setShareError(err.response?.data?.detail || t("Không thể chia sẻ shortlist"));
    } finally {
      setShareSubmitting(false);
    }
  };

  const handleToggleShortlist = async (appId: string, currentlyShortlisted: boolean) => {
    const newStatus = currentlyShortlisted ? 'IN_REVIEW' : 'SHORTLIST';
    try {
      await applicationsApi.updateStatus(appId, newStatus);
      await loadRanking();
    } catch (err: any) {
      setError(err.response?.data?.detail || t("Không thể cập nhật trạng thái"));
    }
  };

  const queueCounts = applicantQueueCounts(rankingItems);
  const filteredItems = filterAndSortApplicantItems(rankingItems, queue, searchQuery, sort);

  const storeNavigationContext = () => {
    storeApplicantNavigation({
      positionId,
      queue,
      sort,
      search: searchQuery,
      applicationIds: filteredItems.map(item => item.application_id),
      storedAt: Date.now(),
    });
  };

  const getMatchingStatusBadge = (item: RankingItem) => {
    if (!inScreening(item.application_status)) return <StatusBadge type="app-new" label={t("Ngoài sàng lọc")} />;
    if (item.matching_status === 'NOT_ASSESSED') return <StatusBadge type="app-new" label={t("Chưa có trong xếp hạng")} />;
    if (item.has_mismatch) {
      return <StatusBadge type="match-mismatch" label={t("Có dấu hiệu miss-match")} />;
    }
    if (item.needs_verification) {
      return <StatusBadge type="match-verify" label={t("Cần HR xác minh")} />;
    }
    return <StatusBadge type="match-meets" label={t("Đáp ứng bắt buộc")} />;
  };

  const getScoreColor = (score: number | null) => {
    if (score === null || score === undefined) return 'text.disabled';
    if (score >= 80) return '#067647';
    if (score >= 60) return '#0A2B57';
    return '#B54708';
  };

  const assessedCount = rankingItems.filter(i => i.matching_status && i.matching_status !== 'NOT_ASSESSED').length;
  const totalApplications = rankingItems.length;

  if (loading) {
    return (
      <Box sx={{ display: 'flex', justifyContent: 'center', mt: 10 }}>
        <CircularProgress color="secondary" />
      </Box>
    );
  }

  return (
    <Box>
      <Button component={Link} href={`/positions/${positionId}`} startIcon={<ArrowBackIcon />} sx={{ mb: 1 }}>{t("Quay lại vị trí")}</Button>
      <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', flexWrap: 'wrap', gap: 2, mb: 3 }}>
        <Box>
          <Typography variant="h2" sx={{ fontSize: 22, color: '#0A2B57', mb: 0.5 }}>{t("Danh sách ưu tiên rà soát ứng viên")}</Typography>
          <Typography variant="body2" color="text.secondary">{t("Xếp hạng sàng lọc theo phiên bản tiêu chí mới nhất đã duyệt; số thứ hạng là tại lần chạy gần nhất.")}</Typography>
        </Box>
        <Box sx={{ display: 'flex', gap: 2, flexWrap: 'wrap' }}>
          <Button
            variant="outlined"
            startIcon={<RefreshIcon />}
            onClick={loadRanking}
            sx={{ borderColor: '#0A2B57', color: '#0A2B57' }}
          >{t("Làm mới")}</Button>
          <Button
            variant="outlined"
            startIcon={<ShareIcon />}
            onClick={handleOpenShare}
            sx={{ borderColor: '#0A2B57', color: '#0A2B57' }}
          >{t("Chia sẻ Shortlist")}</Button>
          <Button
            variant="contained"
            color="secondary"
            startIcon={assessing ? <CircularProgress size={18} color="inherit" /> : <PlaylistAddCheckIcon />}
            onClick={handleRunAssessment}
            disabled={assessing}
          >
            {assessing ? t("Đang đánh giá...") : t("Chạy đánh giá & xếp hạng")}
          </Button>
        </Box>
      </Box>

      {error && (
        <Alert severity="error" sx={{ mb: 3 }} onClose={() => setError(null)}>
          {t(error)}
        </Alert>
      )}

      {/* Operation progress */}
      {operationStatus && operationStatus.status && operationStatus.status !== 'COMPLETED' && operationStatus.status !== 'FAILED' && (
        <OperationProgressPanel operation={operationStatus} />
      )}

      {rankingError && <Alert severity="error" sx={{ mb: 3 }} action={<Button color="inherit" onClick={loadRanking}>{t("Thử lại")}</Button>}>{t(rankingError)}</Alert>}
      {!rankingError && <>
      {/* Summary cards */}
      <Stack direction="row" spacing={2} useFlexGap sx={{ mb: 3, flexWrap: 'wrap' }}>
        <Card sx={{ minWidth: 140, flex: '1 1 140px' }}>
          <CardContent sx={{ py: 2, '&:last-child': { pb: 2 } }}>
            <Typography variant="caption" color="text.secondary">{t("Tổng hồ sơ")}</Typography>
            <Typography variant="h4" sx={{ fontSize: 24, fontWeight: 'bold', color: '#0A2B57' }}>{totalApplications}</Typography>
          </CardContent>
        </Card>
        <Card sx={{ minWidth: 140, flex: '1 1 140px' }}>
          <CardContent sx={{ py: 2, '&:last-child': { pb: 2 } }}>
            <Typography variant="caption" color="text.secondary">{t("Có trong xếp hạng")}</Typography>
            <Typography variant="h4" sx={{ fontSize: 24, fontWeight: 'bold', color: '#067647' }}>{assessedCount}</Typography>
          </CardContent>
        </Card>
        <Card sx={{ minWidth: 140, flex: '1 1 140px', border: queueCounts.NEEDS_VERIFICATION > 0 ? '1px solid #FEDF89' : undefined }}>
          <CardContent sx={{ py: 2, '&:last-child': { pb: 2 } }}>
            <Typography variant="caption" color="text.secondary">{t("Cần HR xác minh")}</Typography>
            <Typography variant="h4" sx={{ fontSize: 24, fontWeight: 'bold', color: queueCounts.NEEDS_VERIFICATION > 0 ? '#B54708' : '#667085' }}>
              {queueCounts.NEEDS_VERIFICATION}
            </Typography>
          </CardContent>
        </Card>
        {queueCounts.DUPLICATE > 0 && (
          <Card sx={{ minWidth: 140, flex: '1 1 140px', border: '1px solid #FECDCA' }}>
            <CardContent sx={{ py: 2, '&:last-child': { pb: 2 } }}>
              <Typography variant="caption" color="text.secondary">{t("Cảnh báo trùng lặp")}</Typography>
              <Typography variant="h4" sx={{ fontSize: 24, fontWeight: 'bold', color: '#C72127' }}>
                {queueCounts.DUPLICATE}
              </Typography>
            </CardContent>
          </Card>
        )}
      </Stack>

      {/* Review queues and filters */}
      <QueueFilterChips value={queue} counts={queueCounts} onChange={setQueue} />
      <Box sx={{ display: 'flex', gap: 2, mb: 3, alignItems: 'center', flexWrap: 'wrap' }}>
        <OutlinedInput
          placeholder={t("Tìm kiếm theo tên ứng viên...")}
          startAdornment={
            <InputAdornment position="start">
              <SearchIcon sx={{ color: '#A09F9C' }} />
            </InputAdornment>
          }
          value={searchQuery}
          onChange={(e) => setSearchQuery(e.target.value)}
          sx={{
            maxWidth: 350,
            borderRadius: '30px',
            backgroundColor: '#F3EEEE',
            '&.Mui-focused': { backgroundColor: '#FFFFFF' }
          }}
          size="small"
          inputProps={{ 'aria-label': t("Tìm kiếm theo tên ứng viên...") }}
        />
        <FormControl size="small" sx={{ minWidth: 230 }}>
          <InputLabel id="applicant-sort-label">{t("Sắp xếp danh sách")}</InputLabel>
          <Select
            labelId="applicant-sort-label"
            value={sort}
            label={t("Sắp xếp danh sách")}
            onChange={(e) => setSort(e.target.value as ApplicantSort)}
            startAdornment={<SortIcon fontSize="small" sx={{ mr: 0.5, color: 'text.secondary' }} />}
          >
            <MenuItem value="REVIEW_PRIORITY">{t("Ưu tiên rà soát")}</MenuItem>
            <MenuItem value="RANK">{t("Thứ hạng")}</MenuItem>
            <MenuItem value="SCORE_DESC">{t("Điểm matching cao nhất")}</MenuItem>
            <MenuItem value="COVERAGE_ASC">{t("Độ phủ thấp trước")}</MenuItem>
            <MenuItem value="NEWEST">{t("Mới nhất")}</MenuItem>
          </Select>
        </FormControl>
        <Typography variant="caption" color="text.secondary">{t("Đang hiển thị {0} hồ sơ trong hàng đợi.", filteredItems.length)}</Typography>
      </Box>

      {selectedIds.size > 0 && (
        <Box sx={{ position: 'sticky', top: { xs: 72, md: 76 }, zIndex: 4, mb: 3, p: 1.5, border: '1px solid #B9CBE2', borderRadius: 2, backgroundColor: '#EFF8FF', display: 'flex', alignItems: 'center', gap: 1.5, flexWrap: 'wrap' }}>
          <Typography variant="body2" fontWeight={700}>{t("Đã chọn {0} hồ sơ shortlist", selectedIds.size)}</Typography>
          <Box sx={{ flex: 1 }} />
          <Button size="small" onClick={() => setSelectedIds(new Set())}>{t("Bỏ chọn")}</Button>
          <Button size="small" variant="contained" color="secondary" startIcon={<ShareIcon />} onClick={handleOpenShare}>{t("Chia sẻ Shortlist")}</Button>
        </Box>
      )}

      <Alert severity="info" sx={{ mb: 3 }}>
        {t("Cách đọc danh sách: điểm một phần chỉ tính trên phần trọng số đã có bằng chứng (cột Độ phủ), chưa phải điểm cuối. Ô chọn ở đầu mỗi dòng chỉ dùng để chọn hồ sơ đã Shortlist khi chia sẻ cho Hiring Manager. Mở rộng từng dòng để xem kết quả theo từng tiêu chí.")}
      </Alert>

      {/* Cards keep the primary actions visible on narrow screens. */}
      <Box sx={{ display: { xs: 'grid', md: 'none' }, gap: 2 }}>
        {filteredItems.length === 0 ? (
          <Paper sx={{ p: 4, textAlign: 'center', color: 'text.secondary' }}>
            {rankingItems.length === 0 ? t("Chưa có hồ sơ nào. Tải CV lên để bắt đầu.") : t("Không có hồ sơ nào phù hợp bộ lọc.")}
          </Paper>
        ) : filteredItems.map(item => (
          <Card key={item.application_id} sx={{ border: '1px solid #E9EEF4' }}>
            <CardContent>
              <Box sx={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', gap: 1 }}>
                <Box><Typography variant="subtitle1" fontWeight={700} color="#0A2B57">{item.candidate_name || t("Chưa trích xuất tên")}</Typography>
                  <Typography variant="caption" color="text.secondary">{t("Thứ hạng: ")}{item.rank_number ?? '—'} · {item.application_status && isApplicationStatus(item.application_status) ? t(APPLICATION_STATUSES[item.application_status].label) : t("Chưa rõ trạng thái")}</Typography></Box>
                {getMatchingStatusBadge(item)}
              </Box>
              <Box sx={{ display: 'flex', gap: 1, flexWrap: 'wrap', mt: 1.5 }}>
                {item.file_processing_status === 'NEEDS_HR_REVIEW' && <Chip size="small" color="error" variant="outlined" label={t("Cần HR xử lý CV")} />}
                {item.has_duplicate_warning && <Chip size="small" color="warning" variant="outlined" label={t("Hồ sơ trùng lặp")} />}
                {item.evidence_coverage != null && item.evidence_coverage < 0.7 && <Chip size="small" color="warning" variant="outlined" label={t("Độ phủ thấp — cần xác minh")} />}
              </Box>
              <Typography variant="body2" sx={{ mt: 1.5 }}>{t("Điểm: ")}<strong>{item.matching_score == null ? '—' : `${item.matching_score}%`}</strong>{isPartialScore(item) && <Chip size="small" label={t("một phần")} sx={{ height: 20, fontSize: 10, ml: 0.5, backgroundColor: '#FFFAEB', color: '#B54708', fontWeight: 700 }} />}{t("· Độ phủ: ")}<strong>{item.evidence_coverage == null ? '—' : `${Math.round(item.evidence_coverage * 100)}%`}</strong></Typography>
              <Button size="small" onClick={() => toggleExpanded(item.application_id)} endIcon={expandedIds.has(item.application_id) ? <ExpandLessIcon fontSize="small" /> : <ExpandMoreIcon fontSize="small" />} sx={{ mt: 0.5, px: 0.5 }}>{t("Chi tiết tiêu chí")}</Button>
              {expandedIds.has(item.application_id) && <Box sx={{ mt: 1 }}>{renderCriterionBreakdown(item)}</Box>}
              {item.is_shortlisted && <FormControlLabel sx={{ display: 'flex', mt: 0.5 }} control={<Checkbox checked={selectedIds.has(item.application_id)} onChange={() => handleToggleSelect(item.application_id)} />} label={t("Chọn để chia sẻ")} />}
              {!item.is_shortlisted && <Typography variant="caption" color="text.secondary" sx={{ display: 'block', mt: 0.5 }}>{t("Chuyển hồ sơ sang Shortlist để chọn chia sẻ cho Hiring Manager.")}</Typography>}
              <Box sx={{ display: 'flex', gap: 1, flexWrap: 'wrap', mt: 1.5 }}>
                <Button component={Link} href={`/positions/${positionId}/applicants/${item.application_id}`} onClick={storeNavigationContext} variant="outlined" size="small">{t("Xem chi tiết")}</Button>
                {(item.is_shortlisted || item.application_status === 'IN_REVIEW') && <Button size="small" onClick={() => handleToggleShortlist(item.application_id, !!item.is_shortlisted)}>{item.is_shortlisted ? t("Bỏ shortlist") : t("Thêm vào shortlist")}</Button>}
              </Box>
            </CardContent>
          </Card>
        ))}
      </Box>
      {/* Ranking Table */}
      <TableContainer component={Paper} sx={{ display: { xs: 'none', md: 'block' }, borderRadius: 2, boxShadow: '0 1px 3px rgba(0,0,0,0.05)', maxHeight: '72vh' }}>
        <Table stickyHeader aria-label={t("Danh sách ưu tiên ứng viên")}>
          <TableHead>
            <TableRow>
              <TableCell padding="checkbox" width="40">
                <Tooltip title={t("Chọn tất cả hồ sơ Shortlist đang hiển thị để chia sẻ")}>
                  <span>
                    <Checkbox
                      inputProps={{ 'aria-label': t("Chọn tất cả hồ sơ shortlist đang hiển thị") }}
                      checked={filteredItems.filter(i => i.is_shortlisted).length > 0 && filteredItems.filter(i => i.is_shortlisted).every(i => selectedIds.has(i.application_id))}
                      indeterminate={selectedIds.size > 0 && !filteredItems.filter(i => i.is_shortlisted).every(i => selectedIds.has(i.application_id))}
                      onChange={handleSelectAllVisible}
                      disabled={filteredItems.filter(i => i.is_shortlisted).length === 0}
                    />
                  </span>
                </Tooltip>
              </TableCell>
              <TableCell width="70">{t("Thứ hạng")}</TableCell>
              <TableCell>{t("Ứng viên")}</TableCell>
              <TableCell width="170">{t("Nhóm matching")}</TableCell>
              <TableCell width="110" align="center">{t("Điểm")}</TableCell>
              <TableCell width="160">{t("Độ phủ")}</TableCell>
              <TableCell width="100" align="center">Shortlist</TableCell>
              <TableCell width="100" align="right">Xem</TableCell>
            </TableRow>
          </TableHead>
          <TableBody>
            {filteredItems.length === 0 ? (
              <TableRow>
                <TableCell colSpan={8} align="center" sx={{ py: 8, color: 'text.secondary' }}>
                  {rankingItems.length === 0
                    ? t("Chưa có hồ sơ nào được đánh giá. Tải CV lên và nhấn \"Chạy đánh giá & xếp hạng\" để xem danh sách.")
                    : t("Không có hồ sơ nào phù hợp bộ lọc.")}
                </TableCell>
              </TableRow>
            ) : (
              filteredItems.map((item) => (
                <React.Fragment key={item.application_id}>
                <TableRow hover selected={selectedIds.has(item.application_id)}>
                  <TableCell padding="checkbox">
                    <Tooltip title={item.is_shortlisted ? t("Chọn hồ sơ để chia sẻ shortlist") : t("Chỉ chọn được hồ sơ đã Shortlist để chia sẻ cho Hiring Manager")}>
                      <span>
                        <Checkbox
                          inputProps={{ 'aria-label': t("Chọn hồ sơ {0} để chia sẻ", item.candidate_name || t("ứng viên")) }}
                          checked={selectedIds.has(item.application_id)}
                          disabled={!item.is_shortlisted}
                          onChange={() => handleToggleSelect(item.application_id)}
                        />
                      </span>
                    </Tooltip>
                  </TableCell>
                  <TableCell>
                    <Typography
                      variant="h4"
                      sx={{
                        fontSize: 20,
                        fontWeight: 'bold',
                        color: item.rank_number ? '#0A2B57' : 'text.disabled',
                      }}
                    >
                      {item.rank_number ?? '—'}
                    </Typography>
                  </TableCell>
                  <TableCell>
                    <Typography variant="body2" fontWeight={500}>
                      {item.candidate_name || t("Chưa trích xuất tên")}
                    </Typography>
                    <Box sx={{ display: 'flex', gap: 0.5, mt: 0.5, flexWrap: 'wrap' }}>
                      {item.application_status && isApplicationStatus(item.application_status) && <Chip label={t(APPLICATION_STATUSES[item.application_status].label)} size="small" sx={{ height: 20, fontSize: 10 }} />}
                      {item.file_processing_status === 'NEEDS_HR_REVIEW' && (
                        <Chip
                          label={t("Cần HR xử lý CV")}
                          size="small"
                          icon={<ErrorOutlineIcon fontSize="small" />}
                          sx={{ height: 20, fontSize: 10, backgroundColor: '#FECDCA', color: '#B42318' }}
                        />
                      )}
                      {item.has_duplicate_warning && (
                        <Chip
                          label={t("Hồ sơ trùng lặp")}
                          size="small"
                          icon={<ErrorOutlineIcon fontSize="small" />}
                          sx={{ height: 20, fontSize: 10, backgroundColor: '#FEF0C7', color: '#B54708' }}
                        />
                      )}
                      {item.evidence_coverage != null && item.evidence_coverage < 0.7 && (
                        <Chip
                          label={t("Chưa đủ dữ liệu để xếp hạng ổn định")}
                          size="small"
                          icon={<ErrorOutlineIcon fontSize="small" />}
                          sx={{ height: 20, fontSize: 10, backgroundColor: '#FFFAEB', color: '#B54708' }}
                        />
                      )}
                      {item.file_processing_status === 'PROCESSING' && (
                        <Chip label={t("Đang xử lý")} size="small" sx={{ height: 20, fontSize: 10 }} />
                      )}
                    </Box>
                  </TableCell>
                  <TableCell>{getMatchingStatusBadge(item)}</TableCell>
                  <TableCell align="center">
                    {item.matching_score === null || item.matching_score === undefined ? (
                      <Typography variant="h4" sx={{ fontSize: 20, fontWeight: 'bold', color: 'text.disabled' }}>—</Typography>
                    ) : (
                      <Tooltip title={isPartialScore(item)
                        ? t("Điểm một phần: chỉ tính trên {0}% trọng số tiêu chí đã có bằng chứng, chưa phải điểm cuối.", Math.round((item.evidence_coverage ?? 0) * 100))
                        : t("Điểm cuối: đã tính trên toàn bộ trọng số tiêu chí.")}>
                        <Box>
                          <Typography
                            variant="h4"
                            sx={{
                              fontSize: 20,
                              fontWeight: 'bold',
                              color: isPartialScore(item) ? '#B54708' : getScoreColor(item.matching_score),
                            }}
                          >
                            {`${item.matching_score}%`}
                          </Typography>
                          {isPartialScore(item) && (
                            <Typography variant="caption" sx={{ display: 'block', color: '#B54708', fontWeight: 700 }}>{t("một phần")}</Typography>
                          )}
                        </Box>
                      </Tooltip>
                    )}
                  </TableCell>
                  <TableCell>
                    <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                      <Box sx={{ flex: 1 }}>
                        <LinearProgress
                          variant="determinate"
                          value={Math.round((item.evidence_coverage ?? 0) * 100)}
                          sx={{
                            height: 8,
                            borderRadius: 4,
                            backgroundColor: '#F2F4F7',
                            '& .MuiLinearProgress-bar': {
                              backgroundColor:
                                (item.evidence_coverage ?? 0) >= 0.7 ? '#067647'
                                : (item.evidence_coverage ?? 0) >= 0.5 ? '#B54708'
                                : '#C72127',
                              borderRadius: 4,
                            },
                          }}
                        />
                      </Box>
                      <Typography variant="caption" sx={{ minWidth: 36, textAlign: 'right' }}>
                        {item.evidence_coverage !== null && item.evidence_coverage !== undefined
                          ? `${Math.round(item.evidence_coverage * 100)}%`
                          : '—'}
                      </Typography>
                    </Box>
                  </TableCell>
                  <TableCell align="center">
                    <Tooltip title={item.is_shortlisted ? t("Bỏ shortlist") : item.application_status === 'IN_REVIEW' ? t("Thêm vào Shortlist") : t("Chuyển hồ sơ sang Đang xem trước khi shortlist")}>
                      <span><IconButton
                        color={item.is_shortlisted ? "secondary" : "default"}
                        onClick={(e) => {
                          e.preventDefault();
                          handleToggleShortlist(item.application_id, !!item.is_shortlisted);
                        }}
                        size="small"
                        aria-label={item.is_shortlisted ? t("Bỏ shortlist") : t("Thêm vào shortlist")}
                        disabled={!item.is_shortlisted && item.application_status !== 'IN_REVIEW'}
                      >
                        <BookmarkAddOutlinedIcon fontSize="small" />
                      </IconButton></span>
                    </Tooltip>
                  </TableCell>
                  <TableCell align="right">
                    <Tooltip title={expandedIds.has(item.application_id) ? t("Thu gọn chi tiết tiêu chí") : t("Xem kết quả theo từng tiêu chí")}>
                      <IconButton
                        onClick={() => toggleExpanded(item.application_id)}
                        aria-label={t("Chi tiết tiêu chí của {0}", item.candidate_name || t("ứng viên"))}
                        aria-expanded={expandedIds.has(item.application_id)}
                        size="small"
                        sx={{ color: '#0A2B57' }}
                      >
                        {expandedIds.has(item.application_id) ? <ExpandLessIcon /> : <ExpandMoreIcon />}
                      </IconButton>
                    </Tooltip>
                    <Tooltip title={t("Xem chi tiết & đối chiếu bằng chứng")}>
                      <IconButton
                        component={Link}
                        href={`/positions/${positionId}/applicants/${item.application_id}`}
                        onClick={storeNavigationContext}
                        aria-label={t("Xem chi tiết hồ sơ {0}", item.candidate_name || t("ứng viên"))}
                        sx={{ color: '#0A2B57' }}
                      >
                        <VisibilityIcon />
                      </IconButton>
                    </Tooltip>
                  </TableCell>
                </TableRow>
                {expandedIds.has(item.application_id) && (
                  <TableRow>
                    <TableCell colSpan={8} sx={{ backgroundColor: '#F9FAFB', py: 2 }}>
                      {renderCriterionBreakdown(item)}
                      <Button
                        component={Link}
                        href={`/positions/${positionId}/applicants/${item.application_id}`}
                        onClick={storeNavigationContext}
                        size="small"
                        sx={{ mt: 1.5 }}
                      >
                        {t("Mở hồ sơ để đối chiếu bằng chứng")}
                      </Button>
                    </TableCell>
                  </TableRow>
                )}
                </React.Fragment>
              ))
            )}
          </TableBody>
        </Table>
      </TableContainer>
      </>}

      <Card sx={{ mt: 3 }}>
        <CardContent>
          <Stack direction="row" spacing={2} alignItems="center" flexWrap="wrap">
            <Typography variant="h6">{t("Cặp cảnh báo trùng hồ sơ")}</Typography>
            <Button onClick={loadDuplicates} disabled={duplicateLoading}>
              {duplicateLoading ? t("Đang tải...") : t("Tải cảnh báo trùng")}
            </Button>
          </Stack>
          <Typography variant="body2" color="text.secondary" sx={{ my: 1 }}>
            {t("Chỉ xem tín hiệu đã ghi nhận trong vị trí này; tín hiệu có thể cũ và không xác nhận hai hồ sơ là trùng.")}
          </Typography>
          {duplicateError && <Alert severity="error">{t(duplicateError)}</Alert>}
          {duplicateSignals && duplicateSignals.length === 0 && <Typography>{t("Chưa có cảnh báo trùng.")}</Typography>}
          {duplicateSignals?.map(signal => (
            <Box key={signal.signal_id} sx={{ borderTop: '1px solid #eee', py: 1.5 }}>
              <Stack direction="row" spacing={1} flexWrap="wrap" alignItems="center">
                <MuiLink component={Link} href={`/positions/${positionId}/applicants/${signal.application_id_1}`}>
                  {signal.candidate_name_1 || signal.application_id_1}
                </MuiLink>
                <Typography>↔</Typography>
                <MuiLink component={Link} href={`/positions/${positionId}/applicants/${signal.application_id_2}`}>
                  {signal.candidate_name_2 || signal.application_id_2}
                </MuiLink>
              </Stack>
              <Typography variant="body2" color="text.secondary">
                {signal.signal_type} · {t("Độ tin cậy")} {Math.round(Number(signal.confidence) * 100)}% · {signal.review_status}
              </Typography>
            </Box>
          ))}
        </CardContent>
      </Card>

      {/* Shortlist Share Dialog */}
      <Dialog open={shareDialogOpen} onClose={() => !shareSubmitting && setShareDialogOpen(false)} maxWidth="sm" fullWidth>
        <DialogTitle>{t("Chia sẻ Shortlist cho Hiring Manager")}</DialogTitle>
        <DialogContent>
          <DialogContentText sx={{ mb: 2 }}>{t("Chọn Hiring Manager phụ trách và hồ sơ đang ở trạng thái Shortlist. Người nhận có thể xem trong mục Shortlist.")}</DialogContentText>
          {shareError && <Alert severity="error" sx={{ mb: 2 }}>{t(shareError)}</Alert>}
          <Autocomplete
            noOptionsText={t("Chưa có Hiring Manager được phân công")}
            options={shareRecipientOptions}
            getOptionLabel={(opt: any) => opt.display_name || ''}
            isOptionEqualToValue={(opt: any, val: any) => opt.user_id === val?.user_id}
            inputValue={shareRecipientQuery}
            onInputChange={(_, val) => setShareRecipientQuery(val)}
            value={shareRecipient}
            onChange={(_, val) => setShareRecipient(val as UserSummary | null)}
            renderInput={(params) => (
              <TextField
                {...params}
                label={t("Chọn người nhận (gõ tên để tìm)")}
                margin="normal"
                fullWidth
                required
              />
            )}
          />
          <Box sx={{ mt: 2 }}>
            <Typography variant="subtitle2" sx={{ mb: 1 }}>{t("              Ứng viên được chia sẻ (")}{selectedIds.size})
            </Typography>
            <Box sx={{ maxHeight: 220, overflowY: 'auto', border: '1px solid #F2F4F7', borderRadius: 1, p: 1 }}>
              {rankingItems.filter(i => selectedIds.has(i.application_id)).map(i => (
                <Box key={i.application_id} sx={{
                  display: 'flex',
                  justifyContent: 'space-between',
                  alignItems: 'center',
                  py: 0.75,
                  px: 1,
                  borderRadius: 1,
                  '&:hover': { backgroundColor: '#F9FAFB' }
                }}>
                  <Typography variant="body2">{i.candidate_name}</Typography>
                  <Chip
                    size="small"
                    label={i.matching_status === 'MEETS_MANDATORY' ? t("Đáp ứng") : t("Cần xem xét")}
                    color={i.matching_status === 'MEETS_MANDATORY' ? 'success' : 'warning'}
                  />
                </Box>
              ))}
              {selectedIds.size === 0 && (
                <Typography variant="caption" color="text.secondary">{t("Chưa chọn ứng viên nào. Hãy đánh dấu vào ô chọn ứng viên shortlist.")}</Typography>
              )}
            </Box>
            <FormControlLabel
              control={
                <Switch
                  checked={shareAllowCv}
                  onChange={(e) => setShareAllowCv(e.target.checked)}
                />
              }
              label={t("Cho phép người nhận xem và tải CV gốc")}
              sx={{ mt: 2 }}
            />
          </Box>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setShareDialogOpen(false)} disabled={shareSubmitting}>{t("Hủy")}</Button>
          <Button
            variant="contained"
            color="secondary"
            onClick={handleShareSubmit}
            disabled={!shareRecipient || selectedIds.size === 0 || shareSubmitting}
          >
            {shareSubmitting ? t("Đang gửi...") : t("Chia sẻ")}
          </Button>
        </DialogActions>
      </Dialog>
      <Snackbar open={!!notice} autoHideDuration={5000} onClose={() => setNotice(null)} message={notice ? t(notice) : ""} />
    </Box>
  );
}
