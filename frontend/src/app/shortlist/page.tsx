'use client';

import { useI18n } from '@/i18n/I18nProvider';

import * as React from 'react';
import {
  Box,
  Typography,
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
  IconButton,
  Tooltip,
  Dialog,
  DialogTitle,
  DialogContent,
  DialogActions,
  Button,
} from '@mui/material';
import VisibilityIcon from '@mui/icons-material/Visibility';
import RefreshIcon from '@mui/icons-material/Refresh';
import ActionFeedback from '@/components/common/ActionFeedback';
import LinkOffIcon from '@mui/icons-material/LinkOff';
import { useCallback, useEffect, useState } from 'react';
import { shortlistApi } from '@/lib/api';
import StatusBadge from '@/components/common/StatusBadge';
import ScorecardReminders from '@/components/shortlist/ScorecardReminders';
import { useRouter } from 'next/navigation';

interface FeedbackItem {
  feedback_id: string;
  feedback_from: string;
  author_name?: string | null;
  content: string;
  created_at: string;
}

interface ShortlistShare {
  share_id: string;
  position?: { title?: string; position_code?: string };
  created_by_profile?: { display_name?: string };
  application_count?: number;
  feedback_count?: number;
  position_id?: string;
  direction?: 'sent' | 'received';
  recipient_profile?: { display_name?: string };
  allow_cv_view?: boolean;
  share_level_feedback_blocked?: boolean;
  status?: string;
  created_at?: string;
  note?: string;
  feedback?: FeedbackItem[];
  applications?: Array<{
    application_id: string;
    candidate_name?: string;
    display_name?: string;
    matching_score?: number;
    matching_status?: string;
  }>;
}

export default function ShortlistPage() {
  const { t, dateLocale } = useI18n();
  const router = useRouter();
  const [positionFilter, setPositionFilter] = useState('');
  const [shares, setShares] = useState<ShortlistShare[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [revokeShare, setRevokeShare] = useState<ShortlistShare | null>(null);
  const [revokeLoading, setRevokeLoading] = useState(false);
  const [revokeError, setRevokeError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  const loadData = useCallback(async (initial = false) => {
    try {
      if (initial) setLoading(true);
      const res = await shortlistApi.getSharedWithMe();
      // `res.data || []` guards null only. A wrapper object (or an error body that
      // still resolved) sails through and then crashes the whole screen on
      // `visibleShares.length`…`.map`, leaving HR with "Application error" instead
      // of a retry. Only an actual array is acceptable here.
      const payload = res.data;
      setShares(Array.isArray(payload) ? payload : Array.isArray(payload?.items) ? payload.items : []);
      setError(null);
    } catch (err: any) {
      setError(err.response?.data?.detail || t("Không thể tải danh sách shortlist"));
    } finally {
      setLoading(false);
    }
  }, [t]);
  useEffect(() => { loadData(true); }, [loadData]);
  useEffect(() => { setPositionFilter(new URLSearchParams(window.location.search).get('position') || ''); }, []);
  useEffect(() => {
    const id = new URLSearchParams(window.location.search).get('share');
    if (id) router.replace(`/shortlist/${encodeURIComponent(id)}`);
  }, [router]);

  const handleOpenDetail = (share: ShortlistShare) => {
    router.push(`/shortlist/${encodeURIComponent(share.share_id)}`);
  };

  const handleRevoke = async () => {
    if (!revokeShare || revokeLoading) return;
    try {
      setRevokeLoading(true); setRevokeError(null);
      await shortlistApi.revoke(revokeShare.share_id);
      setRevokeShare(null); setNotice(t("Đã thu hồi quyền truy cập shortlist."));
      await loadData();
    } catch (err: any) {
      setRevokeError(err.response?.data?.detail || t("Không thể thu hồi shortlist"));
    } finally { setRevokeLoading(false); }
  };

  const visibleShares = positionFilter ? shares.filter(share => share.position_id === positionFilter) : shares;

  if (loading) {
    return (
      <Box sx={{ display: 'flex', justifyContent: 'center', mt: 10 }}>
        <CircularProgress color="secondary" />
      </Box>
    );
  }

  return (
    <Box>
      <Box sx={{ display: 'flex', justifyContent: 'space-between', gap: 2, flexWrap: 'wrap', mb: 4 }}>
        <Box><Typography variant="h1" sx={{ fontSize: 28, color: '#0A2B57', mb: 0.5 }}>{t("Shortlist được chia sẻ")}</Typography>
        <Typography variant="body2" color="text.secondary">{t("Theo dõi shortlist đã gửi hoặc nhận và trao đổi phản hồi chuyên môn")}</Typography></Box>
        <Button variant="outlined" startIcon={<RefreshIcon />} onClick={() => loadData()}>{t("Làm mới")}</Button>
      </Box>

      {positionFilter && <Alert severity="info" sx={{ mb: 2 }} action={<Button color="inherit" onClick={() => { setPositionFilter(''); window.history.replaceState(null, '', '/shortlist'); }}>{t('Xóa bộ lọc')}</Button>}>
        {t('Đang lọc chia sẻ theo vị trí này.')} {visibleShares[0]?.position?.title || ''}
      </Alert>}
      <ScorecardReminders />
      {error && (
        <Alert severity="error" sx={{ mb: 3 }} action={<Button color="inherit" onClick={() => loadData()}>{t("Thử lại")}</Button>}>
          {t(error)}
        </Alert>
      )}

      {!error && <>
      <Box sx={{ display: { xs: 'grid', md: 'none' }, gap: 2 }}>
        {visibleShares.length === 0 ? (
          <Paper sx={{ p: 4, textAlign: 'center', color: 'text.secondary' }}>{positionFilter ? t('Không có chia sẻ nào cho vị trí này trong phạm vi được phép xem.') : t("Chưa có shortlist được gửi hoặc nhận.")}</Paper>
        ) : visibleShares.map(share => (
          <Card key={share.share_id} sx={{ border: '1px solid #E9EEF4' }}>
            <CardContent>
              <Typography variant="subtitle1" fontWeight={700} color="#0A2B57">{share.position?.title || t("Vị trí tuyển dụng")}</Typography>
              <Typography variant="caption" color="text.secondary">{share.position?.position_code} · {share.direction === 'sent' ? t("Bạn / HR → {0}", share.recipient_profile?.display_name || 'Hiring Manager') : t("Từ {0}", share.created_by_profile?.display_name || 'HR')}</Typography>
              <Box sx={{ display: 'flex', flexWrap: 'wrap', gap: 1, mt: 1.5 }}>
                <Chip size="small" label={t("{0} ứng viên", share.application_count ?? 0)} />
                <Chip size="small" label={t("{0} phản hồi", share.feedback_count ?? 0)} />
                <StatusBadge type={share.allow_cv_view ? 'file-completed' : 'file-review'} label={share.allow_cv_view ? t("Được xem CV") : t("Chỉ xem tóm tắt")} />
              </Box>
              <Box sx={{ display: 'flex', flexWrap: 'wrap', gap: 1, mt: 2 }}>
                <Button variant="outlined" size="small" onClick={() => handleOpenDetail(share)}>{t("Xem chi tiết và phản hồi")}</Button>
                {share.direction === 'sent' && share.status === 'ACTIVE' && <Button color="error" size="small" onClick={() => { setRevokeError(null); setRevokeShare(share); }}>{t("Thu hồi")}</Button>}
              </Box>
            </CardContent>
          </Card>
        ))}
      </Box>
      <TableContainer component={Paper} sx={{ display: { xs: 'none', md: 'block' }, borderRadius: 2, boxShadow: '0 1px 3px rgba(0,0,0,0.05)' }}>
        <Table aria-label={t("Danh sách shortlist")}>
          <TableHead>
            <TableRow>
              <TableCell>{t("Vị trí")}</TableCell>
              <TableCell>{t("Chia sẻ bởi")}</TableCell>
              <TableCell>{t("Số ứng viên")}</TableCell>
              <TableCell>{t("Quyền xem CV")}</TableCell>
              <TableCell>{t("Trạng thái")}</TableCell>
              <TableCell>{t("Ngày chia sẻ")}</TableCell>
              <TableCell align="right">{t("Thao tác")}</TableCell>
            </TableRow>
          </TableHead>
          <TableBody>
            {visibleShares.length === 0 ? (
              <TableRow>
                <TableCell colSpan={7} align="center" sx={{ py: 8, color: 'text.secondary' }}>{positionFilter ? t('Không có chia sẻ nào cho vị trí này trong phạm vi được phép xem.') : t("Chưa có shortlist nào được chia sẻ với bạn")}</TableCell>
              </TableRow>
            ) : (
              visibleShares.map((share) => (
                <TableRow key={share.share_id} hover>
                  <TableCell>
                    <Typography variant="body2" fontWeight={500}>
                      {share.position?.title}
                    </Typography>
                    <Typography variant="caption" color="text.secondary" fontFamily="monospace">
                      {share.position?.position_code}
                    </Typography>
                  </TableCell>
                  <TableCell>
                    <Typography variant="body2">
                      {share.direction === 'sent' ? `HR → ${share.recipient_profile?.display_name || 'Hiring Manager'}` : (share.created_by_profile?.display_name || 'HR Recruiter')}
                    </Typography>
                  </TableCell>
                  <TableCell>
                    <Chip label={t("{0} ứng viên", share.application_count || 0)} size="small" />
                    {(share.feedback_count || 0) > 0 && <Typography variant="caption" display="block">{share.feedback_count}{t("phản hồi")}</Typography>}
                  </TableCell>
                  <TableCell>
                    {share.allow_cv_view ? (
                      <StatusBadge type="file-completed" label={t("Được phép")} />
                    ) : (
                      <StatusBadge type="file-review" label={t("Chỉ xem tóm tắt")} />
                    )}
                  </TableCell>
                  <TableCell>
                    <StatusBadge
                      type={share.status === 'ACTIVE' ? 'app-shortlist' : 'app-rejected'}
                      label={share.status === 'ACTIVE' ? t("Đang hoạt động") : t("Đã thu hồi")}
                    />
                  </TableCell>
                  <TableCell>
                    <Typography variant="body2" color="text.secondary">
                      {share.created_at ? new Date(share.created_at).toLocaleDateString(dateLocale) : '—'}
                    </Typography>
                  </TableCell>
                  <TableCell align="right" sx={{ whiteSpace: 'nowrap' }}>
                    <Tooltip title={t("Xem chi tiết và phản hồi")}>
                      <IconButton
                        sx={{ color: '#0A2B57' }}
                        aria-label={t("Xem chi tiết và phản hồi")}
                        onClick={() => handleOpenDetail(share)}
                      >
                        <VisibilityIcon />
                      </IconButton>
                    </Tooltip>
                    {share.direction === 'sent' && share.status === 'ACTIVE' && (
                      <Tooltip title={t("Thu hồi shortlist")}><IconButton color="error" aria-label={t("Thu hồi shortlist")}
                        onClick={() => { setRevokeError(null); setRevokeShare(share); }}><LinkOffIcon /></IconButton></Tooltip>
                    )}
                  </TableCell>
                </TableRow>
              ))
            )}
          </TableBody>
        </Table>
      </TableContainer>
      </>}

      <Dialog open={!!revokeShare} onClose={() => !revokeLoading && setRevokeShare(null)} maxWidth="xs" fullWidth>
        <DialogTitle>{t("Thu hồi shortlist?")}</DialogTitle>
        <DialogContent>
          {revokeError && <Alert severity="error" sx={{ mb: 2 }}>{t(revokeError)}</Alert>}
          <Typography>{t("Hiring Manager sẽ không còn truy cập được shortlist này. Các liên kết CV đã cấp trước đó có thể còn hiệu lực tối đa 10 phút.")}</Typography>
        </DialogContent>
        <DialogActions><Button onClick={() => setRevokeShare(null)} disabled={revokeLoading}>{t("Hủy")}</Button>
          <Button color="error" variant="contained" onClick={handleRevoke} disabled={revokeLoading}>{revokeLoading ? t("Đang thu hồi…") : t("Thu hồi")}</Button></DialogActions>
      </Dialog>
      <ActionFeedback success={notice} onSuccessClose={() => setNotice(null)} />
    </Box>
  );
}
