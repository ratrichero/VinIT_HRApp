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
} from '@mui/material';
import SearchIcon from '@mui/icons-material/Search';
import MoreVertIcon from '@mui/icons-material/MoreVert';
import InfoOutlinedIcon from '@mui/icons-material/InfoOutlined';
import ActionFeedback from '@/components/common/ActionFeedback';
import Menu from '@mui/material/Menu';
import Collapse from '@mui/material/Collapse';
import RefreshIcon from '@mui/icons-material/Refresh';
import VisibilityIcon from '@mui/icons-material/Visibility';
import SortIcon from '@mui/icons-material/Sort';
import BookmarkAddOutlinedIcon from '@mui/icons-material/BookmarkAddOutlined';
import ArrowBackIcon from '@mui/icons-material/ArrowBack';
import ErrorOutlineIcon from '@mui/icons-material/ErrorOutline';
import PlaylistAddCheckIcon from '@mui/icons-material/PlaylistAddCheck';
import PlayArrowIcon from '@mui/icons-material/PlayArrow';
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
import { assessmentsApi, operationsApi, applicationsApi, listAllApplications, shortlistApi, positionsApi, type DuplicateSignal } from '@/lib/api';
import { getCurrentUser } from '@/lib/meCache';
import { recordUxEvent } from '@/lib/uxMetrics';
import { APPLICANT_OWNERSHIP_LABELS } from '@/lib/applicantOwnershipLabels';
import { duplicateCompareHref } from '@/lib/duplicateCompare';
import CompareArrowsIcon from '@mui/icons-material/CompareArrows';
import ChecklistIcon from '@mui/icons-material/Checklist';
import {
  APPLICANT_OWNERSHIP_FILTERS,
  applicantOwnershipCounts,
  filterApplicantItemsByOwner,
  type ApplicantOwnership,
} from '@/lib/applicantOwnership';
import StatusBadge from '@/components/common/StatusBadge';
import QueueFilterChips from '@/components/applicants/QueueFilterChips';
import OperationProgressPanel from '@/components/workflow/OperationProgressPanel';
import {
  APPLICANT_CRITERION_OUTCOMES,
  APPLICANT_CRITERION_OUTCOME_LABELS,
  APPLICANT_QUEUE_LABELS,
  COVERAGE_THRESHOLD,
  hasApplicantCriteriaFilter,
  applicantProfileHref,
  applicantQueueCounts,
  applicantSearchParams,
  daysWaiting,
  filterAndSortApplicantItems,
  inScreening,
  isApplicantSort,
  isAssessed,
  needsVerification,
  normalizeApplicantQueue,
  readApplicantNavigation,
  storeApplicantNavigation,
  WAITING_ATTENTION_DAYS,
  windowApplicantItems,
  type ApplicantCriteriaFilter,
  type ApplicantCriterionOutcome,
  type ApplicantQueue,
  type ApplicantSort,
} from '@/lib/applicantReview';
import type { RankingItem, UserSummary } from '@/types';
import { APPLICATION_STATUSES, isApplicationStatus, type ApplicationStatus } from '@/lib/applicationStatus';
import {
  bulkRunProgress,
  bulkRunStorageKey,
  createBulkRun,
  hasUnfinishedRows,
  parseStoredBulkRun,
  retryFailed,
  stopPoint,
  toStoredBulkRun,
  type BulkRunRow,
  type BulkRowState,
  type StoredBulkRun,
} from '@/lib/bulkActionRun';

// Trạng thái của từng dòng trong biên bản lô.
const BULK_ROW_STATE: Record<BulkRowState, { label: string; bg: string; color: string }> = {
  pending: { label: 'Chờ xử lý', bg: '#F2F4F7', color: '#344054' },
  running: { label: 'Đang xử lý…', bg: '#EFF8FF', color: '#175CD3' },
  done: { label: 'Xong', bg: '#ECFDF3', color: '#067647' },
  failed: { label: 'Lỗi', bg: '#FDF2F2', color: '#B42318' },
  interrupted: { label: 'Chưa rõ kết quả', bg: '#FFFAEB', color: '#B54708' },
};

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
  const loadDuplicates = useCallback(async () => {
    setDuplicateLoading(true);
    setDuplicateError(null);
    try {
      const response = await positionsApi.getDuplicateSignals(positionId);
      // An unexpected payload must not take the whole ranking screen down: the
      // duplicate block is an enhancement, the list itself is the work.
      setDuplicateSignals(Array.isArray(response.data) ? response.data : []);
    } catch (err: any) {
      setDuplicateSignals(null);
      setDuplicateError(err.response?.data?.detail || t("Không thể tải cảnh báo trùng"));
    } finally { setDuplicateLoading(false); }
  }, [positionId, t]);

  const [rankingItems, setRankingItems] = useState<RankingItem[]>([]);
  const [loading, setLoading] = useState(true);
  // UX-R6-a: hai hành động phụ nằm trong menu để header chỉ còn một nút chính
  // và một nút phụ, giảm số đích nhấn ngang hàng với hành động chính.
  const [actionsMenuAnchor, setActionsMenuAnchor] = useState<null | HTMLElement>(null);
  // UX-R6-b: phần giải thích nghiệp vụ vẫn còn nguyên, chỉ thu gọn mặc định.
  const [showHowToRead, setShowHowToRead] = useState(false);
  const [assessing, setAssessing] = useState(false);
  const [operationStatus, setOperationStatus] = useState<import('@/types').OperationStatus | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [rankingError, setRankingError] = useState<string | null>(null);
  const [shareError, setShareError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [queue, setQueue] = useState<ApplicantQueue>('ALL');
  const [ownerFilter, setOwnerFilter] = useState<ApplicantOwnership>('ALL');
  const [currentUserId, setCurrentUserId] = useState<string | null>(null);
  const [sort, setSort] = useState<ApplicantSort>('RANK');
  const [searchQuery, setSearchQuery] = useState('');
  // Lọc theo bằng chứng: câu hỏi HR hỏi hằng ngày là "hồ sơ nào thiếu bằng chứng
  // cho tiêu chí này" và "hồ sơ nào chờ tôi xác minh quá 3 ngày".
  const [criterionId, setCriterionId] = useState('');
  const [criterionOutcome, setCriterionOutcome] = useState<ApplicantCriterionOutcome>('MISSING');
  const [verificationWaiting, setVerificationWaiting] = useState<'' | 'any' | '3' | '7'>('');
  const pollTimerRef = useRef<ReturnType<typeof setInterval> | null>(null);
  // Id của chính người đang xem, để "Của tôi" so đúng người. Chỉ dùng cho bộ
  // lọc hiển thị; quyền vẫn do backend quyết định.
  useEffect(() => {
    getCurrentUser()
      .then(me => setCurrentUserId(me.user_id || null))
      .catch(() => { /* không có id thì chỉ ảnh hưởng bộ lọc "Của tôi" */ });
  }, []);
  const [urlInitialized, setUrlInitialized] = useState(false);

  // Shortlist share dialog state
  const [shareDialogOpen, setShareDialogOpen] = useState(false);
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());
  const [shareRecipient, setShareRecipient] = useState<UserSummary | null>(null);
  const [shareRecipientQuery, setShareRecipientQuery] = useState('');
  const [shareRecipientOptions, setShareRecipientOptions] = useState<UserSummary[]>([]);
  const [shareAllowCv, setShareAllowCv] = useState(false);
  const [shareDueAt, setShareDueAt] = useState('');
  const [shareSubmitting, setShareSubmitting] = useState(false);
  const [expandedIds, setExpandedIds] = useState<Set<string>>(new Set());
  // Chọn nhiều dòng để xử lý hàng loạt (shortlist / loại) bằng chính endpoint
  // trạng thái hiện có; ma trận chuyển trạng thái vẫn quyết định việc gì hợp lệ.
  const [bulkMode, setBulkMode] = useState<null | 'shortlist' | 'reject'>(null);
  const [bulkReason, setBulkReason] = useState('');
  const [bulkProcessing, setBulkProcessing] = useState(false);
  // Biên bản của lô đang mở: từng hồ sơ, số bước đã ghi, chỗ dừng và lý do lỗi.
  const [bulkRun, setBulkRun] = useState<BulkRunRow[] | null>(null);
  const [bulkSkipped, setBulkSkipped] = useState(0);
  // Lô còn dở từ lần trước (đóng tab, mất mạng): đọc lại từ máy để không mất biên bản.
  const [recoveredRun, setRecoveredRun] = useState<StoredBulkRun | null>(null);
  // Large applicant lists mount a bounded window; expanding "more" only affects
  // rendering, never ranks, filters or the set used for shortlist sharing.
  const [visibleLimit, setVisibleLimit] = useState(50);
  const [loadingProgress, setLoadingProgress] = useState<number | null>(null);

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
        listAllApplications(positionId, { onProgress: (loaded) => setLoadingProgress(loaded) }),
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
          assigned_to: a.assigned_to ?? null,
          assigned_to_name: a.assigned_to_name ?? null,
        };
      });

      // Unassessed applications belong to the list too, but only while they are
      // still being screened: rejected/interviewed/offered rows are history, and
      // letting them in made the "Tất cả" count disagree with the dashboard and
      // put rows with no score into queues that promise a score.
      const rankedIds = new Set(merged.map(r => r.application_id));
      apps.forEach((a: any) => {
        if (!rankedIds.has(a.application_id) && inScreening(a.application_status)) {
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
            assigned_to: a.assigned_to ?? null,
            assigned_to_name: a.assigned_to_name ?? null,
          });
        }
      });

      setRankingError(null);
      setRankingItems(merged);
      setLoadingProgress(null);
    } catch (err: any) {
      setRankingError(err.response?.data?.detail || t("Không thể tải bảng xếp hạng"));
    } finally {
      setLoading(false);
      setLoadingProgress(null);
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
    // Ignore late responses after leaving the page so a stale list cannot flash back.
    loadRanking();
    operationsApi.getActiveForPosition(positionId).then(res => {
      if (mounted && res.data) { setAssessing(true); setOperationStatus(res.data); pollOperation(res.data.operation_id); }
    }).catch(() => { if (mounted) setError(t("Không thể tải tiến trình đang xử lý.")); });
    return () => { mounted = false; stopPolling(); };
  }, [loadRanking, stopPolling, pollOperation, positionId, t]);

  // Cảnh báo trùng chỉ hữu ích khi biết hồ sơ đối ứng là ai, nên dữ liệu phải có
  // sẵn ngay khi màn hình mở — không bắt HR cuộn xuống cuối trang bấm một nút.
  // Tải khi vào hàng đợi trùng, và cả khi danh sách có dòng bị gắn cờ.
  useEffect(() => {
    const hasFlaggedRow = rankingItems.some(item => item.has_duplicate_warning);
    if (queue !== 'DUPLICATE' && !hasFlaggedRow) return;
    if (duplicateSignals !== null || duplicateLoading) return;
    loadDuplicates();
  }, [queue, rankingItems, duplicateSignals, duplicateLoading, loadDuplicates]);

  useEffect(() => {
    // The URL wins: it survives a refresh, a new tab and a shared link. Fall back
    // to the stored context only when the URL was opened bare.
    const params = new URLSearchParams(window.location.search);
    const fromUrl = normalizeApplicantQueue(params.get('queue'));
    const sortParam = params.get('sort');
    const stored = fromUrl ? null : readApplicantNavigation(positionId);
    const initialQueue = fromUrl || stored?.queue || 'ALL';
    setQueue(initialQueue);
    if (sortParam === 'REVIEW_PRIORITY' || sortParam === 'RANK' || sortParam === 'SCORE_DESC' || sortParam === 'COVERAGE_ASC' || sortParam === 'NEWEST') setSort(sortParam);
    else if (stored && !fromUrl) setSort(stored.sort);
    else if (params.get('queue') && initialQueue !== 'ALL' && initialQueue !== 'SHORTLIST') setSort('REVIEW_PRIORITY');
    setSearchQuery(params.get('q') || (stored && !fromUrl ? stored.search : '') || '');
    setUrlInitialized(true);
  }, [positionId]);

  // Changing the queue or the sort is a deliberate move between two views, so it
  // deserves a history entry: Back should return to the previous filter, not
  // leave the app. Typing in the search box replaces instead, otherwise every
  // keystroke would add one.
  const navigableState = useRef({ queue, sort });
  useEffect(() => {
    if (!urlInitialized) return;
    const query = applicantSearchParams(queue, sort, searchQuery).toString();
    const href = `${window.location.pathname}${query ? `?${query}` : ''}`;
    const previous = navigableState.current;
    const isDeliberateMove = previous.queue !== queue || previous.sort !== sort;
    navigableState.current = { queue, sort };
    if (isDeliberateMove) window.history.pushState(null, '', href);
    else window.history.replaceState(null, '', href);
  }, [queue, sort, searchQuery, urlInitialized]);

  // Browser Back/Forward must restore what the URL says, or the pushed entry is
  // worse than no entry at all.
  useEffect(() => {
    if (!urlInitialized) return;
    const onPopState = () => {
      const params = new URLSearchParams(window.location.search);
      const nextQueue = normalizeApplicantQueue(params.get('queue')) || 'ALL';
      const nextSortParam = params.get('sort');
      const nextSort: ApplicantSort = isApplicantSort(nextSortParam) ? (nextSortParam as ApplicantSort) : 'RANK';
      navigableState.current = { queue: nextQueue, sort: nextSort };
      setQueue(nextQueue);
      setSort(nextSort);
      setSearchQuery(params.get('q') || '');
    };
    window.addEventListener('popstate', onPopState);
    return () => window.removeEventListener('popstate', onPopState);
  }, [urlInitialized]);

  // Coming back from a profile should land where the reviewer left off, not at
  // the top of a list that may have 50+ mounted rows.
  const restoredScroll = useRef(false);
  useEffect(() => {
    if (restoredScroll.current || !urlInitialized || loading || !rankingItems.length) return;
    const params = new URLSearchParams(window.location.search);
    if (params.get('restore') !== 'scroll') return;
    const target = readApplicantNavigation(positionId)?.scrollY || 0;
    restoredScroll.current = true;
    if (!target) return;
    const timer = window.setTimeout(() => window.scrollTo({ top: target, behavior: 'auto' }), 60);
    return () => window.clearTimeout(timer);
  }, [urlInitialized, loading, rankingItems.length, positionId]);

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
    // Every screening row can be selected, shortlisted or not: the batch bar
    // decides which of them a given action can actually touch.
    const visibleIds = visibleItems.filter(i => inScreening(i.application_status)).map(i => i.application_id);
    const allSelected = visibleIds.length > 0 && visibleIds.every(id => selectedIds.has(id));
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
    if (!shareRecipient || selectedShortlistedIds.length === 0) return;
    try {
      setShareSubmitting(true); setShareError(null);
      await shortlistApi.create({
        position_id: positionId,
        shared_with_user_id: shareRecipient.user_id,
        // Sharing stays limited to Shortlist rows: a batch that also contains
        // unreviewed records must not silently widen what the Hiring Manager sees.
        application_ids: Array.from(selectedItems.filter(i => i.is_shortlisted).map(i => i.application_id)),
        note: '',
        allow_cv_view: shareAllowCv,
        ...(shareDueAt ? { due_at: new Date(shareDueAt).toISOString() } : {}),
      });
      setShareDialogOpen(false);
      setShareRecipient(null);
      setShareRecipientQuery('');
      setSelectedIds(new Set());
      setShareAllowCv(false);
      setShareDueAt('');
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

  // "Clear filters" only appears when something is actually narrowed, and it
  // resets the sort too so the reviewer is never left in a filtered-looking view.
  const criteriaFilter: ApplicantCriteriaFilter = {
    criterionId: criterionId || null,
    // Kết quả chỉ có nghĩa khi đã chọn tiêu chí; không chọn thì không lọc theo kết quả.
    outcome: criterionId ? criterionOutcome : 'ALL',
    verificationWaitingDays: verificationWaiting === '' ? null : verificationWaiting === 'any' ? 0 : Number(verificationWaiting),
  };
  const criterionOptions = Array.from(
    rankingItems.reduce((all, item) => {
      for (const result of item.criterion_results || []) {
        if (!all.has(result.criterion_id)) all.set(result.criterion_id, result.criterion_name);
      }
      return all;
    }, new Map<string, string>()).entries(),
  ).map(([id, name]) => ({ id, name }));
  const criterionName = criterionOptions.find(option => option.id === criterionId)?.name || '';

  const clearFilters = () => {
    setQueue('ALL');
    setSort('RANK');
    setSearchQuery('');
    setOwnerFilter('ALL');
    setCriterionId('');
    setCriterionOutcome('MISSING');
    setVerificationWaiting('');
  };
  const filtersActive = queue !== 'ALL' || searchQuery.trim() !== '' || sort !== 'RANK' || ownerFilter !== 'ALL' || hasApplicantCriteriaFilter(criteriaFilter);

  // Queues describe work still in screening. Rows outside it can still be
  // rendered (badge "Ngoài sàng lọc") but must not inflate a queue figure that
  // the dashboard reports under the same name.
  const screeningItems = rankingItems.filter(item => inScreening(item.application_status));
  const queueCounts = applicantQueueCounts(screeningItems);
  const filteredItems = filterAndSortApplicantItems(rankingItems, queue, searchQuery, sort, criteriaFilter);
  const ownerCounts = applicantOwnershipCounts(screeningItems, currentUserId);
  const ownerFilteredItems = filterApplicantItemsByOwner(filteredItems, ownerFilter, currentUserId);
  const { visible: visibleItems, hasMore, nextLimit } = windowApplicantItems(ownerFilteredItems, visibleLimit);
  useEffect(() => { setVisibleLimit(50); }, [queue, sort, searchQuery, criterionId, criterionOutcome, verificationWaiting]);

  // --- Hành động hàng loạt ------------------------------------------------
  // Chỉ hồ sơ còn trong vòng sàng lọc mới chọn được; hồ sơ đã phỏng vấn/đã loại
  // là lịch sử, đưa vào lô sẽ làm sai biên bản. Việc gì hợp lệ vẫn do ma trận
  // chuyển trạng thái quyết định: shortlist trực tiếp chỉ từ Đang xem.
  const selectableItems = rankingItems.filter(item => inScreening(item.application_status));
  const selectedItems = selectableItems.filter(item => selectedIds.has(item.application_id));
  const selectedShortlistedIds = selectedItems.filter(item => item.is_shortlisted).map(item => item.application_id);
  // Hồ sơ Mới shortlist được, nhưng phải qua hai bước hợp lệ của ma trận hiện có:
  // NEW → IN_REVIEW → SHORTLIST. Không có bước nhảy tắt và không có endpoint mới.
  const bulkShortlistTargets = selectedItems.filter(item => item.application_status === 'IN_REVIEW' || item.application_status === 'NEW');
  // The floating bar is fixed, so the page has to reserve exactly as much room as
  // it actually takes: on a phone it wraps onto several rows, and a hard-coded
  // padding would either hide the last row again or leave a gap. Measured, not
  // guessed.
  const bulkBarRef = useRef<HTMLDivElement>(null);
  const [bulkBarHeight, setBulkBarHeight] = useState(0);
  useEffect(() => {
    const node = bulkBarRef.current;
    if (!node) { setBulkBarHeight(0); return; }
    const measure = () => setBulkBarHeight(Math.ceil(node.getBoundingClientRect().height));
    measure();
    if (typeof ResizeObserver === 'undefined') return;
    const observer = new ResizeObserver(measure);
    observer.observe(node);
    return () => observer.disconnect();
  }, [selectedItems.length]);

  const openBulk = (mode: 'shortlist' | 'reject') => {
    const targets = mode === 'shortlist' ? bulkShortlistTargets : selectedItems;
    setBulkMode(mode);
    setBulkReason('');
    setBulkSkipped(selectedItems.length - targets.length);
    // Lô được chốt ngay khi mở hộp thoại, kèm số bước hợp lệ của từng hồ sơ, để
    // danh sách xem trước và biên bản sau khi chạy nói về đúng cùng một tập.
    setBulkRun(createBulkRun(targets.map(item => ({
      application_id: item.application_id,
      candidate_name: item.candidate_name,
      application_status: item.application_status || 'NEW',
    })), mode));
  };
  const closeBulk = () => {
    if (bulkProcessing) return;
    setBulkMode(null);
    setBulkRun(null);
  };

  const updateBulkRow = (applicationId: string, patch: Partial<BulkRunRow>) => {
    setBulkRun(prev => (prev ? prev.map(row => (row.application_id === applicationId ? { ...row, ...patch } : row)) : prev));
  };

  // Mỗi bước là một lần gọi endpoint trạng thái hiện có, theo đúng thứ tự của ma
  // trận chuyển trạng thái. Một hồ sơ lỗi không làm mất kết quả của hồ sơ khác, và
  // bước đã ghi vẫn được giữ nên lần thử lại chỉ đi tiếp phần còn thiếu.
  const runBulkRows = async (mode: 'shortlist' | 'reject', rows: BulkRunRow[], reason: string) => {
    const bulkStartedAt = Date.now();
    setBulkProcessing(true);
    const results: BulkRunRow[] = [];
    for (const row of rows) {
      updateBulkRow(row.application_id, { state: 'running', error: null });
      let applied = row.applied;
      let reached = row.reached_status;
      let state: BulkRowState = 'done';
      let error: string | null = null;
      try {
        for (const step of row.steps.slice(row.applied)) {
          await applicationsApi.updateStatus(row.application_id, step as ApplicationStatus, reason || undefined);
          applied += 1;
          reached = step;
          updateBulkRow(row.application_id, { applied, reached_status: step });
        }
      } catch (err: any) {
        state = 'failed';
        error = localizeServerMessage(err.response?.data?.detail || t('Lỗi không xác định'));
      }
      updateBulkRow(row.application_id, { state, applied, reached_status: reached, error });
      results.push({ ...row, state, applied, reached_status: reached, error });
    }
    setBulkProcessing(false);
    await loadRanking();
    const failed = results.filter(item => item.state === 'failed');
    // Đo mức dùng lô: số hồ sơ mỗi lần chạy, số lỗi và thời gian, để biết lô có
    // thực sự thay được việc làm từng hồ sơ hay không.
    recordUxEvent({
      type: 'BULK_RUN',
      at: Date.now(),
      application_id: positionId,
      duration_ms: Date.now() - bulkStartedAt,
      records: results.length,
      failed: failed.length,
    });
    if (failed.length === 0) {
      // Không còn gì để xem lại: đóng biên bản và để thông báo nói kết quả.
      try { window.localStorage.removeItem(bulkRunStorageKey(positionId)); } catch { /* storage chỉ là tiện ích */ }
      setRecoveredRun(null);
      setBulkMode(null);
      setBulkRun(null);
      setSelectedIds(new Set());
      const twoStepCount = mode === 'shortlist' ? results.filter(item => item.from_status === 'NEW').length : 0;
      if (mode === 'shortlist' && twoStepCount > 0) {
        setNotice(t('Đã shortlist {0} hồ sơ, trong đó {1} hồ sơ Mới ghi nhận hai lần chuyển trạng thái (Mới → Đang xem → Shortlist).', results.length, twoStepCount));
      } else {
        setNotice(t('Đã cập nhật {0} hồ sơ sang {1}.', results.length, t(APPLICATION_STATUSES[mode === 'shortlist' ? 'SHORTLIST' : 'REJECTED_SCREENING'].label)));
      }
      return;
    }
    // Còn lỗi: giữ hộp thoại mở như biên bản của lần chạy, và chỉ giữ lại đúng
    // những hồ sơ lỗi trong lựa chọn để thanh hành động không mời chạy lại việc đã xong.
    setSelectedIds(new Set(failed.map(item => item.application_id)));
    setNotice(t('Đã cập nhật {0}/{1} hồ sơ. {2} hồ sơ lỗi — xem lý do và thử lại ngay trong hộp thoại.', results.length - failed.length, results.length, failed.length));
  };

  const handleBulkApply = async () => {
    if (!bulkMode || bulkProcessing || !bulkRun) return;
    const reason = bulkReason.trim();
    const pendingRows = bulkRun.filter(row => row.state === 'pending');
    if (!pendingRows.length) return;
    if (bulkMode === 'reject' && !reason) return;
    await runBulkRows(bulkMode, pendingRows, reason);
  };

  // Thử lại chỉ phần lỗi: hồ sơ đã xong không bị gọi lại, hồ sơ dừng giữa đường đi
  // tiếp từ bước còn thiếu thay vì lặp lại bước đã ghi vào lịch sử.
  const handleBulkRetry = async () => {
    if (!bulkMode || bulkProcessing || !bulkRun) return;
    const pending = retryFailed(bulkRun).filter(row => row.state === 'pending');
    if (!pending.length) return;
    setBulkRun(prev => (prev ? retryFailed(prev) : prev));
    await runBulkRows(bulkMode, pending, bulkReason.trim());
  };

  // Biên bản được giữ trên máy: đóng tab giữa lô 30–50 hồ sơ không còn làm mất
  // dấu những gì đã ghi, và lần mở sau vẫn thử lại được đúng phần lỗi.
  useEffect(() => {
    if (!bulkMode || !bulkRun) return;
    try {
      if (bulkRun.every(row => row.state === 'done')) {
        window.localStorage.removeItem(bulkRunStorageKey(positionId));
        return;
      }
      // Mở hộp thoại rồi đóng ngay chưa ghi gì thì không đáng nhắc lại sau này.
      if (!bulkRun.some(row => row.state !== 'pending')) return;
      window.localStorage.setItem(bulkRunStorageKey(positionId), JSON.stringify(toStoredBulkRun(positionId, bulkMode, bulkReason, bulkRun)));
    } catch {
      // Trình duyệt chặn storage thì lô vẫn chạy bình thường.
    }
  }, [positionId, bulkMode, bulkRun, bulkReason]);

  useEffect(() => {
    let stored: StoredBulkRun | null = null;
    try {
      stored = parseStoredBulkRun(window.localStorage.getItem(bulkRunStorageKey(positionId)), positionId);
    } catch {
      stored = null;
    }
    setRecoveredRun(stored && hasUnfinishedRows(stored.rows) ? stored : null);
  }, [positionId]);

  const openRecoveredRun = () => {
    if (!recoveredRun) return;
    setBulkMode(recoveredRun.mode);
    setBulkReason(recoveredRun.reason);
    setBulkSkipped(0);
    setBulkRun(recoveredRun.rows);
  };
  const dismissRecoveredRun = () => {
    try { window.localStorage.removeItem(bulkRunStorageKey(positionId)); } catch { /* storage chỉ là tiện ích */ }
    setRecoveredRun(null);
  };

  const bulkRows = bulkRun || [];
  const bulkProgress = bulkRunProgress(bulkRows);
  const bulkFinished = bulkRows.length > 0 && bulkProgress.pending === 0 && bulkProgress.running === 0;
  const bulkCurrentRow = bulkRows.find(row => row.state === 'running') || bulkRows.find(row => row.state === 'pending');
  const bulkTwoStep = bulkRows.filter(row => row.steps.length > 1).length;
  const recoveredProgress = recoveredRun ? bulkRunProgress(recoveredRun.rows) : null;
  const statusLabel = (status: string) => t(APPLICATION_STATUSES[status as ApplicationStatus]?.label || status);

  const storeNavigationContext = () => {
    storeApplicantNavigation({
      positionId,
      queue,
      sort,
      search: searchQuery,
      applicationIds: filteredItems.map(item => item.application_id),
      storedAt: Date.now(),
      scrollY: typeof window !== 'undefined' ? window.scrollY : 0,
    });
  };

  // Every link into a profile carries the browse context, so the profile can
  // rebuild the exact list URL when the reviewer comes back — even in a new tab
  // where sessionStorage is empty.
  const profileHref = (applicationId: string) => applicantProfileHref(positionId, applicationId, queue, sort, searchQuery);

  // Lối vào cho việc duyệt liên tiếp: hồ sơ đầu tiên trong đúng danh sách đang
  // xem mà còn việc (chưa xếp hạng hoặc bằng chứng cần xác minh). Không có hồ sơ
  // nào như vậy thì lấy hồ sơ đầu danh sách; danh sách rỗng thì không hiện nút.
  const nextReviewItem = visibleItems.find(item => !isAssessed(item) || needsVerification(item)) || visibleItems[0] || null;

  // Cặp hồ sơ đối ứng của một dòng bị gắn cờ, lấy từ chính danh sách cảnh báo.
  const duplicateCounterparts = (applicationId: string) => {
    const pairs: { id: string; name: string }[] = [];
    (duplicateSignals || []).forEach(signal => {
      const isFirst = signal.application_id_1 === applicationId;
      const isSecond = signal.application_id_2 === applicationId;
      if (!isFirst && !isSecond) return;
      const otherId = isFirst ? signal.application_id_2 : signal.application_id_1;
      const otherName = isFirst ? signal.candidate_name_2 : signal.candidate_name_1;
      const fromList = rankingItems.find(item => item.application_id === otherId)?.candidate_name;
      pairs.push({ id: otherId, name: otherName || fromList || otherId });
    });
    return pairs;
  };

  // Đích đến của cảnh báo phải nằm ngay trên dòng: một cảnh báo "trùng" mà không
  // nói trùng với ai thì HR chỉ còn cách tự đi tìm.
  const renderDuplicateCounterparts = (item: RankingItem) => {
    const pairs = duplicateCounterparts(item.application_id);
    return (
      <Box
        data-testid={`duplicate-counterpart-${item.application_id}`}
        sx={{ display: 'flex', gap: 0.75, flexWrap: 'wrap', alignItems: 'center', mt: 0.5 }}
      >
        {duplicateSignals === null ? (
          duplicateLoading
            ? <Typography variant="caption" color="text.secondary">{t('Đang tải hồ sơ đối ứng…')}</Typography>
            : <Button size="small" onClick={loadDuplicates} sx={{ px: 0.5, minWidth: 0 }}>{t('Thử tải lại cảnh báo trùng')}</Button>
        ) : pairs.length === 0 ? (
          <Typography variant="caption" color="text.secondary">{t('Chưa có cặp hồ sơ đối ứng trong danh sách cảnh báo.')}</Typography>
        ) : (
          <>
            <Typography variant="caption" color="text.secondary">{t('Trùng với:')}</Typography>
            {pairs.map(pair => (
              <React.Fragment key={pair.id}>
                <MuiLink
                  component={Link}
                  href={profileHref(pair.id)}
                  onClick={storeNavigationContext}
                  variant="caption"
                  sx={{ fontWeight: 700 }}
                  aria-label={t('Mở hồ sơ đối ứng {0}', pair.name)}
                >
                  {pair.name}
                </MuiLink>
                {/* Quyết định trùng lặp cần thấy cả hai cùng lúc: mở A rồi mở B
                    bắt HR nhớ dữ liệu của hồ sơ trước trong đầu. */}
                <Button
                  component={Link}
                  href={duplicateCompareHref(positionId, item.application_id, pair.id)}
                  size="small"
                  variant="outlined"
                  startIcon={<CompareArrowsIcon fontSize="small" />}
                  data-testid={`compare-pair-${item.application_id}-${pair.id}`}
                  aria-label={t('So sánh cạnh nhau với {0}', pair.name)}
                  sx={{ ml: 0.5, px: 0.75, minWidth: 0, fontSize: 11, py: 0 }}
                >
                  {t('So sánh')}
                </Button>
              </React.Fragment>
            ))}
          </>
        )}
      </Box>
    );
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

  const assessedCount = screeningItems.filter(isAssessed).length;
  const totalApplications = screeningItems.length;

  if (loading) {
    return (
      <Box sx={{ display: 'flex', flexDirection: 'column', alignItems: 'center', mt: 10, gap: 2 }} role="status" aria-live="polite">
        <CircularProgress color="secondary" />
        <Typography variant="body2" color="text.secondary">
          {loadingProgress != null ? t("Đang tải danh sách ứng viên theo trang: {0} hồ sơ. Bộ lọc và xếp hạng áp dụng sau khi tải xong.", loadingProgress) : t("Đang tải danh sách ứng viên...")}
        </Typography>
      </Box>
    );
  }

  return (
    <Box sx={{ pb: bulkBarHeight ? `${bulkBarHeight + 24}px` : 0 }}>
      <Button component={Link} href={`/positions/${positionId}`} startIcon={<ArrowBackIcon />} sx={{ mb: 1 }}>{t("Quay lại vị trí")}</Button>
      <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', flexWrap: 'wrap', gap: 2, mb: 3 }}>
        <Box>
          <Typography variant="h2" sx={{ fontSize: 22, color: '#0A2B57', mb: 0.5 }}>{t("Danh sách ứng viên")}</Typography>
          <Typography variant="body2" color="text.secondary">{t("Xếp hạng sàng lọc theo phiên bản tiêu chí mới nhất đã duyệt; số thứ hạng là tại lần chạy gần nhất.")}</Typography>
        </Box>
        <Box sx={{ display: 'flex', gap: 1, flexWrap: 'wrap', alignItems: 'center' }}>
          {/* Duyệt liên tiếp: lối vào hồ sơ kế tiếp nằm ngay cạnh hành động
              chính, không phải cuộn xuống bảng để tìm dòng đầu tiên. */}
          {nextReviewItem && (
            <Tooltip title={t("Tiếp theo: {0}", nextReviewItem.candidate_name || t("Chưa trích xuất tên"))} arrow>
              <Button
                component={Link}
                href={profileHref(nextReviewItem.application_id)}
                onClick={storeNavigationContext}
                variant="outlined"
                color="secondary"
                startIcon={<PlayArrowIcon />}
                data-testid="open-next-profile"
                sx={{ whiteSpace: 'nowrap' }}
              >
                {t("Mở hồ sơ kế tiếp")}
              </Button>
            </Tooltip>
          )}
          {/* Cùng một tiêu chí trên nhiều hồ sơ: khi cả loạt hồ sơ bị nghi ở
              cùng một tiêu chí, mở từng hồ sơ để tìm đúng chỗ đó là việc lặp. */}
          <Button
            component={Link}
            href={`/positions/${positionId}/applicants/by-criterion`}
            variant="outlined"
            color="secondary"
            startIcon={<ChecklistIcon />}
            data-testid="review-by-criterion"
            sx={{ whiteSpace: 'nowrap' }}
          >
            {t("Duyệt theo tiêu chí")}
          </Button>
          {/* Một hành động chính, phần còn lại vào menu: ba nút ngang hàng khiến
              HR phải đọc cả ba mới biết nút nào là việc chính. */}
          <Button
            variant="contained"
            color="secondary"
            startIcon={assessing ? <CircularProgress size={18} color="inherit" /> : <PlaylistAddCheckIcon />}
            onClick={handleRunAssessment}
            disabled={assessing}
          >
            {assessing ? t("Đang đánh giá...") : t("Chạy đánh giá & xếp hạng")}
          </Button>
          {/* Ba chấm một mình thì HR phải bấm mới biết bên trong có gì, nên có
              tooltip nêu đúng hai thao tác ẩn. Tooltip chỉ để gợi ý; nhãn cho
              trình đọc màn hình vẫn là aria-label. */}
          <Tooltip title={t("Làm mới và Chia sẻ Shortlist")} arrow>
            <IconButton
              aria-label={t("Hành động khác: Làm mới, Chia sẻ Shortlist")}
              aria-haspopup="menu"
              aria-expanded={Boolean(actionsMenuAnchor)}
              onClick={event => setActionsMenuAnchor(event.currentTarget)}
              sx={{ border: '1px solid #D0D7E2', borderRadius: 1 }}
            >
              <MoreVertIcon />
            </IconButton>
          </Tooltip>
          <Menu
            anchorEl={actionsMenuAnchor}
            open={Boolean(actionsMenuAnchor)}
            onClose={() => setActionsMenuAnchor(null)}
            anchorOrigin={{ vertical: 'bottom', horizontal: 'right' }}
            transformOrigin={{ vertical: 'top', horizontal: 'right' }}
          >
            <MenuItem onClick={() => { setActionsMenuAnchor(null); loadRanking(); }}>
              <RefreshIcon fontSize="small" sx={{ mr: 1 }} />{t("Làm mới")}
            </MenuItem>
            <MenuItem onClick={() => { setActionsMenuAnchor(null); handleOpenShare(); }}>
              <ShareIcon fontSize="small" sx={{ mr: 1 }} />{t("Chia sẻ Shortlist")}
            </MenuItem>
          </Menu>
        </Box>
      </Box>

      {error && (
        <Alert severity="error" sx={{ mb: 3 }} onClose={() => setError(null)}>
          {t(error)}
        </Alert>
      )}

      {/* Operation progress */}
      {operationStatus && operationStatus.status && operationStatus.status !== 'COMPLETED' && operationStatus.status !== 'FAILED' && (
        <OperationProgressPanel operation={operationStatus} positionId={positionId} />
      )}

      {loading && loadingProgress != null && <Alert severity="info" sx={{ mb: 3 }} icon={<CircularProgress size={18} />}>{t("Đang tải danh sách ứng viên theo trang: {0} hồ sơ. Bộ lọc và xếp hạng áp dụng sau khi tải xong.", loadingProgress)}</Alert>}
      {rankingError && <Alert severity="error" sx={{ mb: 3 }} action={<Button color="inherit" onClick={loadRanking}>{t("Thử lại")}</Button>}>{t(rankingError)}</Alert>}
      {!rankingError && <>
      {/* R6-c (bản cân bằng): hai con số không trùng chip nào được giữ, nhưng ở
          dạng một dòng thay vì hai thẻ cao 89px. Hai thẻ "Cần HR xác minh" và
          "Cảnh báo trùng lặp" đã bị bỏ vì chip hàng đợi ngay dưới đếm đúng hai
          thứ đó, kèm số — giữ cả hai là nói cùng một câu hai lần. */}
      {/* Review queues and filters */}
      {/* Lô còn dở từ lần trước: đóng tab hay mất mạng không còn làm mất biên bản,
          và HR vẫn thử lại được đúng phần lỗi thay vì tự dò 30–50 hồ sơ. */}
      {recoveredRun && recoveredProgress && !bulkMode && (
        <Alert
          severity="warning"
          sx={{ mb: 2 }}
          data-testid="bulk-run-recovered"
          action={(
            <Box sx={{ display: 'flex', gap: 1 }}>
              <Button color="inherit" size="small" onClick={openRecoveredRun} data-testid="bulk-run-open">{t("Xem biên bản")}</Button>
              <Button color="inherit" size="small" onClick={dismissRecoveredRun} data-testid="bulk-run-dismiss">{t("Bỏ qua")}</Button>
            </Box>
          )}
        >
          {t("Lô {0} lần trước chưa xong: {1}/{2} hồ sơ đã cập nhật, {3} lỗi, {4} chưa rõ kết quả. Biên bản được giữ lại để rà và thử lại phần lỗi.",
            recoveredRun.mode === 'shortlist' ? t("Shortlist") : t("Loại hồ sơ"),
            recoveredProgress.done,
            recoveredRun.rows.length,
            recoveredProgress.failed,
            recoveredProgress.interrupted)}
        </Alert>
      )}
      <QueueFilterChips value={queue} counts={queueCounts} onChange={setQueue} />
      {/* Lọc theo bằng chứng, không chỉ theo tên: "hồ sơ thiếu bằng chứng cho tiêu
          chí X" và "hồ sơ chờ tôi xác minh quá 3 ngày" là hai thao tác HR làm mỗi
          ngày, trước đây phải mở từng hồ sơ để tự dò. */}
      {/* Một thanh lọc duy nhất: tìm kiếm, người phụ trách, sắp xếp ở hàng đầu;
          tiêu chí, bằng chứng và thời gian chờ ở hàng thứ hai; câu giải thích
          cách sắp xếp là dòng chú thích cuối thanh. Trước đây là sáu khối rời
          nhau, đẩy dòng dữ liệu đầu tiên xuống 700px. */}
      <Paper variant="outlined" sx={{ p: 1.5, borderRadius: 2 }} data-testid="applicant-filter-bar">
        <Box sx={{ display: 'flex', gap: 1.5, alignItems: 'center', flexWrap: 'wrap' }}>
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
              flex: '1 1 240px',
              maxWidth: 350,
              borderRadius: '30px',
              backgroundColor: '#F3EEEE',
              '&.Mui-focused': { backgroundColor: '#FFFFFF' }
            }}
            size="small"
            inputProps={{ 'aria-label': t("Tìm kiếm theo tên ứng viên...") }}
          />
          {/* Lọc theo người phụ trách: một ô chọn thay cho hàng chip riêng — cùng
              số đếm, nhưng không chiếm thêm một dòng trước bảng. */}
          <FormControl size="small" sx={{ minWidth: 185 }} data-testid="owner-filter">
            <InputLabel id="applicant-owner-label" shrink>{t('Lọc theo người phụ trách')}</InputLabel>
            <Select
              labelId="applicant-owner-label"
              value={ownerFilter}
              label={t('Lọc theo người phụ trách')}
              onChange={event => setOwnerFilter(event.target.value as ApplicantOwnership)}
              inputProps={{ 'data-testid': 'owner-select' }}
              notched
            >
              {APPLICANT_OWNERSHIP_FILTERS.map(filter => (
                <MenuItem key={filter} value={filter} data-testid={`owner-option-${filter}`}>
                  {`${t(APPLICANT_OWNERSHIP_LABELS[filter])} (${ownerCounts[filter]})`}
                </MenuItem>
              ))}
            </Select>
          </FormControl>
          <FormControl size="small" sx={{ minWidth: 200 }}>
            <InputLabel id="applicant-sort-label" shrink>{t("Sắp xếp danh sách")}</InputLabel>
            <Select
              labelId="applicant-sort-label"
              value={sort}
              label={t("Sắp xếp danh sách")}
              onChange={(e) => setSort(e.target.value as ApplicantSort)}
              inputProps={{ 'data-testid': 'sort-select' }}
              startAdornment={<SortIcon fontSize="small" sx={{ mr: 0.5, color: 'text.secondary' }} />}
              notched
            >
              <MenuItem value="REVIEW_PRIORITY">{t("Ưu tiên rà soát")}</MenuItem>
              <MenuItem value="RANK">{t("Thứ hạng")}</MenuItem>
              <MenuItem value="SCORE_DESC">{t("Điểm phù hợp cao nhất")}</MenuItem>
              <MenuItem value="COVERAGE_ASC">{t("Độ phủ thấp trước")}</MenuItem>
              <MenuItem value="NEWEST">{t("Mới nhất")}</MenuItem>
            </Select>
          </FormControl>
          <Box sx={{ flex: 1 }} />
          <Button
            size="small"
            startIcon={<InfoOutlinedIcon />}
            endIcon={showHowToRead ? <ExpandLessIcon /> : <ExpandMoreIcon />}
            aria-expanded={showHowToRead}
            aria-controls="how-to-read-applicants"
            onClick={() => setShowHowToRead(!showHowToRead)}
            sx={{ px: 0.5, whiteSpace: 'nowrap' }}
            data-testid="how-to-read-toggle"
          >{t("Cách đọc danh sách")}</Button>
        </Box>
        {/* Lọc theo bằng chứng, không chỉ theo tên: "hồ sơ thiếu bằng chứng cho tiêu
            chí X" và "hồ sơ chờ tôi xác minh quá 3 ngày" là hai thao tác HR làm mỗi
            ngày, trước đây phải mở từng hồ sơ để tự dò. */}
        <Box sx={{ display: 'flex', gap: 1.5, mt: 1, alignItems: 'center', flexWrap: 'wrap' }} data-testid="criteria-filter">
          <FormControl size="small" sx={{ minWidth: 230, maxWidth: 330 }}>
            <InputLabel id="applicant-criterion-label" shrink>{t("Tiêu chí")}</InputLabel>
            <Select
              labelId="applicant-criterion-label"
              value={criterionId}
              label={t("Tiêu chí")}
              onChange={(e) => setCriterionId(e.target.value)}
              inputProps={{ 'data-testid': 'criterion-filter-select' }}
              notched
            >
              <MenuItem value="">{t("Mọi tiêu chí")}</MenuItem>
              {criterionOptions.map(option => (
                <MenuItem key={option.id} value={option.id}>{option.name}</MenuItem>
              ))}
            </Select>
          </FormControl>
          <FormControl size="small" sx={{ minWidth: 190 }} disabled={!criterionId}>
            <InputLabel id="applicant-criterion-outcome-label" shrink>{t("Bằng chứng")}</InputLabel>
            <Select
              labelId="applicant-criterion-outcome-label"
              value={criterionId ? criterionOutcome : 'ALL'}
              label={t("Bằng chứng")}
              onChange={(e) => setCriterionOutcome(e.target.value as ApplicantCriterionOutcome)}
              inputProps={{ 'data-testid': 'criterion-outcome-select' }}
              notched
            >
              {APPLICANT_CRITERION_OUTCOMES.map(outcome => (
                <MenuItem key={outcome} value={outcome}>{t(APPLICANT_CRITERION_OUTCOME_LABELS[outcome])}</MenuItem>
              ))}
            </Select>
          </FormControl>
          <FormControl size="small" sx={{ minWidth: 200 }}>
            <InputLabel id="applicant-waiting-label" shrink>{t("Chờ xác minh")}</InputLabel>
            <Select
              labelId="applicant-waiting-label"
              value={verificationWaiting}
              label={t("Chờ xác minh")}
              onChange={(e) => setVerificationWaiting(e.target.value as '' | 'any' | '3' | '7')}
              inputProps={{ 'data-testid': 'verification-waiting-select' }}
              notched
            >
              <MenuItem value="">{t("Không lọc theo thời gian chờ")}</MenuItem>
              <MenuItem value="any">{t("Đang chờ tôi xác minh")}</MenuItem>
              <MenuItem value="3">{t("Quá 3 ngày")}</MenuItem>
              <MenuItem value="7">{t("Quá 7 ngày")}</MenuItem>
            </Select>
          </FormControl>
          <Box sx={{ flex: 1 }} />
          {filtersActive && (
            <Button size="small" onClick={clearFilters} data-testid="clear-applicant-filters">{t("Xoá bộ lọc và tìm kiếm")}</Button>
          )}
        </Box>
        <Typography
          variant="caption"
          color="text.secondary"
          data-testid="sort-explanation"
          sx={{ display: 'block', mt: 1 }}
        >
          {sort === 'REVIEW_PRIORITY'
            ? t('Danh sách ưu tiên vấn đề cần xử lý, không phải thứ tự xếp hạng. Số hạng vẫn thuộc lần chạy gần nhất.')
            : t('Sắp theo thứ hạng của lần chạy gần nhất; hồ sơ chưa có hạng được đưa xuống cuối.')}
        </Typography>
      </Paper>

      {/* Dòng đếm nằm chung hàng với ô tìm: trước đây nó chiếm một dòng riêng
          (16px + lề) chỉ để nói "Hiển thị 4/12". */}
      <Box sx={{ display: 'flex', gap: 2, alignItems: 'center', flexWrap: 'wrap', mb: 2 }}>
        <Typography variant="caption" color="text.secondary" data-testid="applicant-funnel">
          {t("{0}/{1} hồ sơ đã có trong xếp hạng", assessedCount, totalApplications)}
          {' ·'}
        </Typography>
        <Typography variant="caption" color="text.secondary" data-testid="applicant-count">
          {t("Hiển thị {0}/{1} hồ sơ của vị trí.", filteredItems.length, rankingItems.length)}
          {searchQuery.trim() ? ` · ${t("Đang lọc theo tên: “{0}”.", searchQuery.trim())}` : ` · ${t("Không lọc theo tên.")}`}
          {queue !== 'ALL' ? ` · ${t("Hàng đợi: {0}.", t(APPLICANT_QUEUE_LABELS[queue]))}` : ''}
          {criterionId ? ` · ${t("Tiêu chí “{0}”: {1}.", criterionName, t(APPLICANT_CRITERION_OUTCOME_LABELS[criterionOutcome]))}` : ''}
          {criteriaFilter.verificationWaitingDays !== null
            ? ` · ${verificationWaiting === 'any'
              ? t("Chỉ hồ sơ đang chờ tôi xác minh.")
              : t("Chỉ hồ sơ chờ xác minh quá {0} ngày.", criteriaFilter.verificationWaitingDays)}`
            : ''}
        </Typography>
      </Box>

      {hasMore && (
        <Alert severity="info" sx={{ mb: 2 }} action={<Button color="inherit" size="small" onClick={() => setVisibleLimit(nextLimit)}>{t("Hiện thêm 50 hồ sơ")}</Button>}>
          {t("Đang hiển thị {0}/{1} hồ sơ để trang nhẹ và dễ đọc. Xếp hạng, bộ lọc và lựa chọn chia sẻ vẫn áp dụng cho toàn bộ danh sách.", visibleItems.length, ownerFilteredItems.length)}
        </Alert>
      )}

      {/* Thanh hành động nổi: chỉ xuất hiện khi có lựa chọn, để danh sách không
          mất chiều cao và người duyệt luôn thấy hành động nằm ngay tầm mắt. */}
      {selectedItems.length > 0 && (
        <Paper
          ref={bulkBarRef}
          elevation={8}
          role="region"
          aria-label={t('Hành động cho hồ sơ đã chọn')}
          data-testid="bulk-action-bar"
          sx={{
            position: 'fixed',
            // On a phone the bar spans the screen edge to edge: shrink-to-fit made
            // it a 195px-wide column that filled a third of the viewport. Touch
            // targets are at least 44px, and labels never wrap mid-word.
            bottom: { xs: 8, md: 24 },
            left: { xs: 8, md: '50%' },
            right: { xs: 8, md: 'auto' },
            transform: { xs: 'none', md: 'translateX(-50%)' },
            zIndex: 5,
            px: { xs: 1.5, md: 2 },
            py: { xs: 1, md: 1.25 },
            border: '1px solid #B9CBE2',
            backgroundColor: '#EFF8FF',
            display: 'flex',
            alignItems: 'center',
            gap: { xs: 1, md: 1.5 },
            flexWrap: 'wrap',
            maxWidth: { xs: 'none', md: 'calc(100% - 32px)' },
            // 44px targets, and tight enough that the three actions take two rows
            // on a 360px phone instead of four, so the bar does not eat the list.
            '& .MuiButton-root': { minHeight: 44, whiteSpace: 'nowrap', fontSize: { xs: 13, md: 14 }, px: { xs: 1.25, md: 2 } },
          }}
        >
          <Typography variant="body2" fontWeight={700} data-testid="bulk-selection-count">
            {t("Đã chọn {0} hồ sơ", selectedItems.length)}
          </Typography>
          <Button size="small" onClick={() => setSelectedIds(new Set())}>{t("Bỏ chọn")}</Button>
          <Box sx={{ flex: 1 }} />
          <Tooltip title={bulkShortlistTargets.length > 0
            ? t("Shortlist các hồ sơ Đang xem và Mới trong lựa chọn; hồ sơ Mới đi qua hai bước Mới → Đang xem → Shortlist")
            : t("Chỉ hồ sơ đang ở trạng thái Đang xem hoặc Mới mới shortlist được")}>
            <span>
              <Button
                size="small"
                variant="outlined"
                startIcon={<BookmarkAddOutlinedIcon />}
                onClick={() => openBulk('shortlist')}
                disabled={bulkShortlistTargets.length === 0}
                data-testid="bulk-shortlist-open"
              >
                {t("Shortlist {0} hồ sơ", bulkShortlistTargets.length)}
              </Button>
            </span>
          </Tooltip>
          <Button
            size="small"
            variant="outlined"
            color="error"
            onClick={() => openBulk('reject')}
            data-testid="bulk-reject-open"
          >
            {t("Loại {0} hồ sơ", selectedItems.length)}
          </Button>
          <Button
            size="small"
            variant="contained"
            color="secondary"
            startIcon={<ShareIcon />}
            onClick={handleOpenShare}
            disabled={selectedShortlistedIds.length === 0}
            data-testid="bulk-share"
          >
            {t("Chia sẻ Shortlist")}
          </Button>
        </Paper>
      )}

      {/* Nội dung nghiệp vụ giữ nguyên từng chữ; chỉ mặc định thu gọn vì nó
          từng chiếm 3 dòng trước dòng dữ liệu đầu tiên. */}
      <Box sx={{ mb: 2 }}>
        <Collapse in={showHowToRead} timeout="auto" unmountOnExit>
          <Alert severity="info" id="how-to-read-applicants" sx={{ mb: 1 }}>
            {t("Cách đọc danh sách: điểm một phần chỉ tính trên phần trọng số đã có bằng chứng (cột Độ phủ), chưa phải điểm cuối. Ô chọn ở đầu mỗi dòng dùng để shortlist hoặc loại nhiều hồ sơ cùng lúc; hồ sơ đã Shortlist cũng có thể chọn để chia sẻ cho Hiring Manager. Mở rộng từng dòng để xem kết quả theo từng tiêu chí.")}
          </Alert>
        </Collapse>
      </Box>

      {/* Cards keep the primary actions visible on narrow screens. */}
      <Box sx={{ display: { xs: 'grid', md: 'none' }, gap: 2 }}>
        {filteredItems.length === 0 ? (
          <Paper sx={{ p: 4, textAlign: 'center', color: 'text.secondary' }}>
            {rankingItems.length === 0 ? t("Chưa có hồ sơ nào. Tải CV lên để bắt đầu.") : t("Không có hồ sơ nào phù hợp bộ lọc.")}
          </Paper>
        ) : visibleItems.map(item => (
          <Card key={item.application_id} sx={{ border: '1px solid #E9EEF4' }}>
            <CardContent>
              <Box sx={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', gap: 1 }}>
                <Box><Typography variant="subtitle1" fontWeight={700} color="#0A2B57">{item.candidate_name || t("Chưa trích xuất tên")}</Typography>
                  <Typography variant="caption" color="text.secondary">{t("Thứ hạng: ")}{item.rank_number ?? '—'} · {item.application_status && isApplicationStatus(item.application_status) ? t(APPLICATION_STATUSES[item.application_status].label) : t("Chưa rõ trạng thái")}{daysWaiting(item.created_at) != null ? ` · ${daysWaiting(item.created_at) === 0 ? t("Nhận hôm nay") : t("Chờ {0} ngày", daysWaiting(item.created_at) as number)}` : ''}</Typography></Box>
                {getMatchingStatusBadge(item)}
              </Box>
              <Box sx={{ display: 'flex', gap: 1, flexWrap: 'wrap', mt: 1.5 }}>
                {item.file_processing_status === 'NEEDS_HR_REVIEW' && <Chip size="small" color="error" variant="outlined" label={t("Cần HR xử lý CV")} />}
                {item.has_duplicate_warning && <Chip size="small" color="warning" variant="outlined" label={t("Hồ sơ trùng lặp")} />}
                {item.evidence_coverage != null && item.evidence_coverage < COVERAGE_THRESHOLD && <Chip size="small" color="warning" variant="outlined" label={t("Độ phủ thấp — cần xác minh")} />}
              </Box>
              {item.has_duplicate_warning && renderDuplicateCounterparts(item)}
              <Typography variant="body2" sx={{ mt: 1.5 }}>{t("Điểm: ")}<strong>{item.matching_score == null ? '—' : `${item.matching_score}%`}</strong>{isPartialScore(item) && <Chip size="small" label={t("một phần")} sx={{ height: 20, fontSize: 10, ml: 0.5, backgroundColor: '#FFFAEB', color: '#B54708', fontWeight: 700 }} />}{t("· Độ phủ: ")}<strong>{item.evidence_coverage == null ? '—' : `${Math.round(item.evidence_coverage * 100)}%`}</strong></Typography>
              <Button size="small" onClick={() => toggleExpanded(item.application_id)} endIcon={expandedIds.has(item.application_id) ? <ExpandLessIcon fontSize="small" /> : <ExpandMoreIcon fontSize="small" />} sx={{ mt: 0.5, px: 0.5 }}>{t("Chi tiết tiêu chí")}</Button>
              {expandedIds.has(item.application_id) && <Box sx={{ mt: 1 }}>{renderCriterionBreakdown(item)}</Box>}
              {inScreening(item.application_status) && <FormControlLabel sx={{ display: 'flex', mt: 0.5 }} control={<Checkbox checked={selectedIds.has(item.application_id)} onChange={() => handleToggleSelect(item.application_id)} inputProps={{ 'aria-label': t("Chọn hồ sơ {0}", item.candidate_name || t("ứng viên")) }} />} label={t("Chọn hồ sơ")} />}
              <Box sx={{ display: 'flex', gap: 1, flexWrap: 'wrap', mt: 1.5 }}>
                <Button component={Link} href={profileHref(item.application_id)} onClick={storeNavigationContext} variant="outlined" size="small">{t("Xem chi tiết")}</Button>
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
                <Tooltip title={t("Chọn tất cả hồ sơ đang hiển thị, kể cả chưa shortlist")}>
                  <span>
                    <Checkbox
                      inputProps={{ 'aria-label': t("Chọn tất cả hồ sơ đang hiển thị") }}
                      checked={visibleItems.filter(i => inScreening(i.application_status)).length > 0
                        && visibleItems.filter(i => inScreening(i.application_status)).every(i => selectedIds.has(i.application_id))}
                      indeterminate={selectedItems.length > 0
                        && !visibleItems.filter(i => inScreening(i.application_status)).every(i => selectedIds.has(i.application_id))}
                      onChange={handleSelectAllVisible}
                      disabled={visibleItems.filter(i => inScreening(i.application_status)).length === 0}
                    />
                  </span>
                </Tooltip>
              </TableCell>
              <TableCell width="70">{t("Thứ hạng")}</TableCell>
              <TableCell>{t("Ứng viên")}</TableCell>
              <TableCell width="170">{t("Mức phù hợp")}</TableCell>
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
              visibleItems.map((item) => (
                <React.Fragment key={item.application_id}>
                <TableRow hover selected={selectedIds.has(item.application_id)}>
                  <TableCell padding="checkbox">
                    <Tooltip title={inScreening(item.application_status)
                      ? t("Chọn hồ sơ {0} để xử lý hàng loạt", item.candidate_name || t("ứng viên"))
                      : t("Hồ sơ ngoài vòng sàng lọc không chọn được vì đã qua bước này")}>
                      <span>
                        <Checkbox
                          inputProps={{ 'aria-label': t("Chọn hồ sơ {0}", item.candidate_name || t("ứng viên")) }}
                          checked={selectedIds.has(item.application_id)}
                          disabled={!inScreening(item.application_status)}
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
                    <Box sx={{ display: 'flex', gap: 0.5, mt: 0.5, flexWrap: 'wrap', alignItems: 'center' }}>
                      {item.application_status && isApplicationStatus(item.application_status) && <Chip label={t(APPLICATION_STATUSES[item.application_status].label)} size="small" sx={{ height: 20, fontSize: 10 }} />}
                      {(() => {
                        // Age is information, not a sort key: it never changes the
                        // rank or the order the reviewer chose.
                        const waiting = daysWaiting(item.created_at);
                        if (waiting == null) return null;
                        return (
                          <Typography
                            variant="caption"
                            sx={{ color: waiting >= WAITING_ATTENTION_DAYS ? '#B54708' : 'text.secondary', fontWeight: waiting >= WAITING_ATTENTION_DAYS ? 600 : 400 }}
                          >
                            {waiting === 0 ? t("Nhận hôm nay") : t("Chờ {0} ngày", waiting)}
                          </Typography>
                        );
                      })()}
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
                      {item.evidence_coverage != null && item.evidence_coverage < COVERAGE_THRESHOLD && (
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
                    {item.has_duplicate_warning && renderDuplicateCounterparts(item)}
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
                                (item.evidence_coverage ?? 0) >= COVERAGE_THRESHOLD ? '#067647'
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
                    <Tooltip title={item.is_shortlisted ? t("Bỏ shortlist") : item.application_status === 'IN_REVIEW' ? t("Thêm vào shortlist") : t("Chuyển hồ sơ sang Đang xem trước khi shortlist")}>
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
                        href={profileHref(item.application_id)}
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
                        href={profileHref(item.application_id)}
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
                <MuiLink component={Link} href={profileHref(signal.application_id_1)} onClick={storeNavigationContext}>
                  {signal.candidate_name_1 || signal.application_id_1}
                </MuiLink>
                <Typography>↔</Typography>
                <MuiLink component={Link} href={profileHref(signal.application_id_2)} onClick={storeNavigationContext}>
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
          <TextField fullWidth type="datetime-local" margin="normal" label={t('Hạn phản hồi tùy chọn')} InputLabelProps={{ shrink: true }} value={shareDueAt} onChange={e => setShareDueAt(e.target.value)} helperText={t('Để trống: 3 ngày làm việc theo giờ Việt Nam, chưa tính ngày lễ.')} />
          <Box sx={{ mt: 2 }}>
            <Typography variant="subtitle2" sx={{ mb: 1 }}>{t("Ứng viên được chia sẻ ({0})", selectedShortlistedIds.length)}
            </Typography>
            <Box sx={{ maxHeight: 220, overflowY: 'auto', border: '1px solid #F2F4F7', borderRadius: 1, p: 1 }}>
              {rankingItems.filter(i => selectedShortlistedIds.includes(i.application_id)).map(i => (
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
              {selectedShortlistedIds.length === 0 && (
                <Typography variant="caption" color="text.secondary">{t("Chưa chọn hồ sơ nào đã Shortlist. Hãy chọn hồ sơ Shortlist trong danh sách.")}</Typography>
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
            disabled={!shareRecipient || selectedShortlistedIds.length === 0 || shareSubmitting}
          >
            {shareSubmitting ? t("Đang gửi...") : t("Chia sẻ")}
          </Button>
        </DialogActions>
      </Dialog>
      {/* Xác nhận hàng loạt: nêu đúng số hồ sơ sẽ đổi, số bị bỏ qua và lý do chung
          trước khi ghi bất cứ thứ gì. */}
      <Dialog open={Boolean(bulkMode)} onClose={closeBulk} maxWidth="sm" fullWidth data-testid="bulk-dialog">
        <DialogTitle>
          {bulkMode === 'shortlist'
            ? t("Shortlist {0} hồ sơ", bulkRows.length)
            : t("Loại {0} hồ sơ", bulkRows.length)}
        </DialogTitle>
        <DialogContent dividers>
          {bulkProcessing && (
            <Box sx={{ mb: 2 }} role="status" aria-live="polite" data-testid="bulk-progress">
              <Typography variant="body2" fontWeight={700} sx={{ mb: 0.5 }}>
                {t("Đang xử lý {0}/{1}: {2}", Math.min(bulkProgress.finished + 1, bulkProgress.total), bulkProgress.total, bulkCurrentRow?.candidate_name || t("Chưa trích xuất tên"))}
              </Typography>
              <LinearProgress variant="determinate" value={bulkProgress.total ? Math.round((bulkProgress.finished / bulkProgress.total) * 100) : 0} />
            </Box>
          )}
          {!bulkProcessing && bulkFinished && bulkProgress.failed > 0 && (
            <Alert severity="warning" sx={{ mb: 2 }} data-testid="bulk-failure-summary">
              {t("{0}/{1} hồ sơ đã cập nhật. {2} hồ sơ lỗi: lý do và chỗ dừng ở từng dòng bên dưới; có thể thử lại riêng phần lỗi.", bulkProgress.done, bulkProgress.total, bulkProgress.failed)}
            </Alert>
          )}
          {!bulkProcessing && bulkProgress.interrupted > 0 && (
            <Alert severity="warning" sx={{ mb: 2 }} data-testid="bulk-interrupted-summary">
              {t("{0} hồ sơ bị gián đoạn khi đang ghi nên chưa rõ kết quả; mở từng hồ sơ để kiểm tra trạng thái trước khi làm lại.", bulkProgress.interrupted)}
            </Alert>
          )}
          {bulkMode === 'shortlist' ? (
            <>
              <DialogContentText sx={{ mb: 1.5 }}>
                {t("Các hồ sơ dưới đây chuyển sang trạng thái Shortlist. Trạng thái của từng hồ sơ được ghi nhận riêng như khi bấm trên từng dòng.")}
              </DialogContentText>
              {bulkTwoStep > 0 && (
                <Alert severity="info" sx={{ mb: 2 }} data-testid="bulk-two-step">
                  {t("{0} hồ sơ đang ở trạng thái Mới sẽ ghi nhận hai lần chuyển trạng thái: Mới → Đang xem → Shortlist. Mỗi bước là một lần gọi API trạng thái hiện có, nên lịch sử của hồ sơ sẽ có hai mục.", bulkTwoStep)}
                </Alert>
              )}
              {bulkSkipped > 0 && (
                <Alert severity="warning" sx={{ mb: 2 }} data-testid="bulk-skipped">
                  {t("Bỏ qua {0} hồ sơ trong lựa chọn vì không shortlist được từ trạng thái hiện tại (hồ sơ đã Shortlist không cần làm lại; hồ sơ ngoài sàng lọc là lịch sử).", bulkSkipped)}
                </Alert>
              )}
            </>
          ) : (
            <DialogContentText sx={{ mb: 1.5 }}>
              {t("Các hồ sơ dưới đây bị loại ở vòng sàng lọc. Lý do bên dưới được ghi cho từng hồ sơ.")}
            </DialogContentText>
          )}
          <Box sx={{ mb: 1.5 }} component="ol" data-testid="bulk-rows">
            {bulkRows.map(row => {
              const state = BULK_ROW_STATE[row.state];
              const stop = stopPoint(row);
              return (
                <Box component="li" key={row.application_id} sx={{ mb: 1 }} data-testid={`bulk-row-${row.application_id}`}>
                  <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, flexWrap: 'wrap' }}>
                    <Typography variant="body2">{row.candidate_name || t("Chưa trích xuất tên")}</Typography>
                    {row.steps.length > 1 && (
                      <Typography component="span" variant="caption" color="text.secondary">
                        {t("Mới · 2 bước chuyển trạng thái")}
                      </Typography>
                    )}
                    <Chip
                      size="small"
                      label={t(state.label)}
                      data-testid={`bulk-row-state-${row.application_id}`}
                      sx={{ height: 22, fontSize: 11, fontWeight: 700, backgroundColor: state.bg, color: state.color }}
                    />
                  </Box>
                  {row.state === 'failed' && row.error && (
                    <Typography variant="caption" sx={{ display: 'block', color: '#B42318' }} data-testid={`bulk-row-error-${row.application_id}`}>
                      {t("Lỗi: {0}", row.error)}
                    </Typography>
                  )}
                  {row.state === 'failed' && stop && (
                    <Typography variant="caption" sx={{ display: 'block', color: '#B54708' }} data-testid={`bulk-row-stop-${row.application_id}`}>
                      {t("Đã ghi nhận bước {0}, chưa tới {1}.", statusLabel(stop.reached), statusLabel(stop.target))}
                    </Typography>
                  )}
                  {row.state === 'interrupted' && (
                    <Typography variant="caption" sx={{ display: 'block', color: '#B54708' }} data-testid={`bulk-row-interrupted-${row.application_id}`}>
                      {t("Lô bị gián đoạn khi đang ghi hồ sơ này; mở hồ sơ để kiểm tra trạng thái trước khi làm lại.")}{' '}
                      <MuiLink href={applicantProfileHref(positionId, row.application_id, queue, sort, searchQuery)} underline="always">{t("Mở hồ sơ")}</MuiLink>
                    </Typography>
                  )}
                </Box>
              );
            })}
          </Box>
          <TextField
            fullWidth
            multiline
            minRows={2}
            label={bulkMode === 'shortlist' ? t("Lý do chung (tùy chọn)") : t("Lý do chung (bắt buộc)")}
            required={bulkMode === 'reject'}
            value={bulkReason}
            onChange={event => setBulkReason(event.target.value)}
            disabled={bulkProcessing}
            inputProps={{ maxLength: 1000 }}
            helperText={bulkMode === 'reject' ? t("Lý do này được ghi cho mọi hồ sơ bị loại trong lần này.") : undefined}
          />
        </DialogContent>
        <DialogActions sx={{ p: 2, flexDirection: { xs: 'column', sm: 'row' }, gap: 1 }}>
          {bulkFinished ? (
            <>
              <Button onClick={closeBulk} sx={{ minHeight: 44, width: { xs: '100%', sm: 'auto' } }}>{t("Đóng")}</Button>
              {bulkProgress.failed > 0 && (
                <Button
                  variant="contained"
                  color="error"
                  onClick={handleBulkRetry}
                  disabled={bulkMode === 'reject' && !bulkReason.trim()}
                  data-testid="bulk-retry"
                  sx={{ minHeight: 44, width: { xs: '100%', sm: 'auto' } }}
                >
                  {t("Thử lại {0} hồ sơ lỗi", bulkProgress.failed)}
                </Button>
              )}
            </>
          ) : (
            <>
              <Button onClick={closeBulk} disabled={bulkProcessing} sx={{ minHeight: 44, width: { xs: '100%', sm: 'auto' } }}>{t("Hủy")}</Button>
              <Button
                variant="contained"
                color={bulkMode === 'shortlist' ? 'secondary' : 'error'}
                onClick={handleBulkApply}
                disabled={bulkProcessing || bulkRows.length === 0 || (bulkMode === 'reject' && !bulkReason.trim())}
                data-testid="bulk-confirm"
                sx={{ minHeight: 44, width: { xs: '100%', sm: 'auto' } }}
              >
                {bulkProcessing
                  ? t("Đang cập nhật {0} hồ sơ…", bulkProgress.total)
                  : bulkMode === 'shortlist' ? t("Shortlist") : t("Loại hồ sơ")}
              </Button>
            </>
          )}
        </DialogActions>
      </Dialog>

      <ActionFeedback success={notice} onSuccessClose={() => setNotice(null)} />
    </Box>
  );
}
