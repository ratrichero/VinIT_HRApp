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
  TextField,
  Divider,
  Avatar,
  Snackbar,
} from '@mui/material';
import VisibilityIcon from '@mui/icons-material/Visibility';
import SendIcon from '@mui/icons-material/Send';
import PersonIcon from '@mui/icons-material/Person';
import RefreshIcon from '@mui/icons-material/Refresh';
import LinkOffIcon from '@mui/icons-material/LinkOff';
import { useCallback, useEffect, useState } from 'react';
import { shortlistApi } from '@/lib/api';
import StatusBadge from '@/components/common/StatusBadge';
import Link from 'next/link';

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
  const [shares, setShares] = useState<ShortlistShare[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [detailError, setDetailError] = useState<string | null>(null);
  const [revokeShare, setRevokeShare] = useState<ShortlistShare | null>(null);
  const [revokeLoading, setRevokeLoading] = useState(false);
  const [revokeError, setRevokeError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [selectedShare, setSelectedShare] = useState<ShortlistShare | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [feedbackText, setFeedbackText] = useState('');
  const [submittingFeedback, setSubmittingFeedback] = useState(false);

  const loadData = useCallback(async (initial = false) => {
    try {
      if (initial) setLoading(true);
      const res = await shortlistApi.getSharedWithMe();
      setShares(res.data || []); setError(null);
    } catch (err: any) {
      setError(err.response?.data?.detail || t("Không thể tải danh sách shortlist"));
    } finally {
      setLoading(false);
    }
  }, [t]);
  useEffect(() => { loadData(true); }, [loadData]);

  const handleOpenDetail = async (share: ShortlistShare) => {
    setSelectedShare(share);
    setFeedbackText(''); setDetailError(null);
    try {
      setDetailLoading(true);
      const res = await shortlistApi.getDetail(share.share_id);
      setSelectedShare(current => current?.share_id === share.share_id ? res.data : current);
    } catch (err: any) {
      setDetailError(err.response?.data?.detail || t("Không thể tải chi tiết shortlist"));
    } finally {
      setDetailLoading(false);
    }
  };

  const handleCloseDetail = () => {
    setSelectedShare(null);
    setFeedbackText(''); setDetailError(null);
  };

  const handleSubmitFeedback = async () => {
    if (!selectedShare || !feedbackText.trim()) return;
    try {
      setSubmittingFeedback(true); setDetailError(null);
      await shortlistApi.addFeedback(selectedShare.share_id, feedbackText.trim());
      // Reload detail
      const res = await shortlistApi.getDetail(selectedShare.share_id);
      setSelectedShare(res.data);
      setFeedbackText('');
      // Refresh list to update counts
      await loadData();
    } catch (err: any) {
      setDetailError(err.response?.data?.detail || t("Không thể gửi phản hồi"));
    } finally {
      setSubmittingFeedback(false);
    }
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

      {error && (
        <Alert severity="error" sx={{ mb: 3 }} action={<Button color="inherit" onClick={() => loadData()}>{t("Thử lại")}</Button>}>
          {t(error)}
        </Alert>
      )}

      {!error && <>
      <Box sx={{ display: { xs: 'grid', md: 'none' }, gap: 2 }}>
        {shares.length === 0 ? (
          <Paper sx={{ p: 4, textAlign: 'center', color: 'text.secondary' }}>{t("Chưa có shortlist được gửi hoặc nhận.")}</Paper>
        ) : shares.map(share => (
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
            {shares.length === 0 ? (
              <TableRow>
                <TableCell colSpan={7} align="center" sx={{ py: 8, color: 'text.secondary' }}>{t("Chưa có shortlist nào được chia sẻ với bạn")}</TableCell>
              </TableRow>
            ) : (
              shares.map((share) => (
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
                    <Tooltip title={t("Xem chi tiết & phản hồi")}>
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

      {/* Detail + Feedback Dialog */}
      <Dialog open={!!selectedShare} onClose={handleCloseDetail} maxWidth="md" fullWidth>
        {selectedShare && (
          <>
            <DialogTitle>
              <Typography variant="h6" color="#0A2B57">
                Shortlist — {selectedShare.position?.title}
              </Typography>
              <Typography variant="caption" color="text.secondary">{t("                Chia sẻ bởi")} {selectedShare.created_by_profile?.display_name || 'HR'} ·{' '}
                {selectedShare.created_at ? new Date(selectedShare.created_at).toLocaleDateString(dateLocale) : ''}
              </Typography>
            </DialogTitle>
            <DialogContent dividers>
              {detailError && <Alert severity="error" sx={{ mb: 2 }}>{t(detailError)}</Alert>}
              {detailLoading ? (
                <Box sx={{ display: 'flex', justifyContent: 'center', py: 6 }}>
                  <CircularProgress size={28} />
                </Box>
              ) : (
                <>
                  {selectedShare.note && (
                    <Alert severity="info" sx={{ mb: 2 }}>
                      <strong>{t("Ghi chú từ HR:")}</strong> {selectedShare.note}
                    </Alert>
                  )}

                  <Typography variant="subtitle2" sx={{ mb: 1 }}>{t("                    Danh sách ứng viên (")}{selectedShare.applications?.length || 0})
                  </Typography>
                  <Box sx={{ mb: 3, border: '1px solid #F2F4F7', borderRadius: 1, maxHeight: 200, overflowY: 'auto' }}>
                    {(selectedShare.applications || []).map((a, idx) => (
                      <Box key={a.application_id} sx={{
                        display: 'flex',
                        justifyContent: 'space-between',
                        alignItems: 'center',
                        py: 1,
                        px: 2,
                        borderBottom: idx < (selectedShare.applications?.length || 0) - 1 ? '1px solid #F2F4F7' : 'none'
                      }}>
                        <Button component={Link} href={`/positions/${selectedShare.position_id}/applicants/${a.application_id}`}
                          size="small" sx={{ textAlign: 'left', px: 0.5 }}>
                          {a.candidate_name || a.display_name || t("Ứng viên")}
                        </Button>
                        <Chip
                          size="small"
                          label={{ MEETS_MANDATORY: t("Đáp ứng bắt buộc"), NEEDS_HR_VERIFICATION: t("Cần HR xác minh"), POSSIBLE_MISMATCH: t("Cần xem xét"), NOT_ASSESSED: t("Chưa đánh giá") }[a.matching_status || ''] || t("Chưa đánh giá hoặc kết quả đã cũ")}
                          color={a.matching_status === 'MEETS_MANDATORY' ? 'success' : 'default'}
                        />
                      </Box>
                    ))}
                    {(!selectedShare.applications || selectedShare.applications.length === 0) && (
                      <Typography variant="body2" color="text.secondary" sx={{ py: 2, px: 2 }}>{t("Không có dữ liệu ứng viên.")}</Typography>
                    )}
                  </Box>

                  <Divider sx={{ mb: 2 }} />

                  <Typography variant="subtitle2" sx={{ mb: 1 }}>{t("                    Phản hồi (")}{(selectedShare.feedback || []).length})
                  </Typography>
                  <Box sx={{ mb: 2, maxHeight: 180, overflowY: 'auto' }}>
                    {(selectedShare.feedback || []).length === 0 ? (
                      <Typography variant="body2" color="text.secondary">{t("Chưa có phản hồi nào.")}</Typography>
                    ) : (
                      selectedShare.feedback!.map((f) => (
                        <Box key={f.feedback_id} sx={{ display: 'flex', gap: 1.5, mb: 2 }}>
                          <Avatar sx={{ width: 32, height: 32, bgcolor: '#0A2B57' }}>
                            <PersonIcon fontSize="small" />
                          </Avatar>
                          <Box sx={{ flex: 1 }}>
                            <Box sx={{ display: 'flex', gap: 1, alignItems: 'baseline' }}>
                              <Typography variant="body2" fontWeight={600}>
                                {f.author_name || t("Người dùng")}
                              </Typography>
                              <Typography variant="caption" color="text.secondary">
                                {new Date(f.created_at).toLocaleString(dateLocale)}
                              </Typography>
                            </Box>
                            <Typography variant="body2" sx={{ whiteSpace: 'pre-wrap' }}>
                              {f.content}
                            </Typography>
                          </Box>
                        </Box>
                      ))
                    )}
                  </Box>

                  {selectedShare.status === 'ACTIVE' && selectedShare.share_level_feedback_blocked && (
                    <Alert severity="info" sx={{ mt: 2 }}>{t("Shortlist đã thay đổi do retention; hãy yêu cầu HR tạo shortlist mới để gửi phản hồi chung")}</Alert>
                  )}
                  {selectedShare.status === 'ACTIVE' && !selectedShare.share_level_feedback_blocked && (
                    <Box sx={{ mt: 2 }}>
                      <TextField
                        label={t("Phản hồi của bạn")}
                        multiline
                        rows={3}
                        fullWidth
                        value={feedbackText}
                        onChange={(e) => setFeedbackText(e.target.value)}
                        inputProps={{ maxLength: 3000 }}
                        placeholder={t("Đánh giá tổng quan shortlist, đề xuất ứng viên nên mời phỏng vấn, lý do, câu hỏi thêm cho HR...")}
                      />
                    </Box>
                  )}
                </>
              )}
            </DialogContent>
            <DialogActions>
              <Button onClick={handleCloseDetail}>{t("Đóng")}</Button>
              {selectedShare.status === 'ACTIVE' && !selectedShare.share_level_feedback_blocked && (
                <Button
                  variant="contained"
                  color="secondary"
                  endIcon={<SendIcon />}
                  onClick={handleSubmitFeedback}
                  disabled={!feedbackText.trim() || submittingFeedback || detailLoading}
                >
                  {submittingFeedback ? t("Đang gửi...") : t("Gửi phản hồi")}
                </Button>
              )}
            </DialogActions>
          </>
        )}
      </Dialog>
      <Dialog open={!!revokeShare} onClose={() => !revokeLoading && setRevokeShare(null)} maxWidth="xs" fullWidth>
        <DialogTitle>{t("Thu hồi shortlist?")}</DialogTitle>
        <DialogContent>
          {revokeError && <Alert severity="error" sx={{ mb: 2 }}>{t(revokeError)}</Alert>}
          <Typography>{t("Hiring Manager sẽ không còn truy cập được shortlist này. Các liên kết CV đã cấp trước đó có thể còn hiệu lực tối đa 10 phút.")}</Typography>
        </DialogContent>
        <DialogActions><Button onClick={() => setRevokeShare(null)} disabled={revokeLoading}>{t("Hủy")}</Button>
          <Button color="error" variant="contained" onClick={handleRevoke} disabled={revokeLoading}>{revokeLoading ? t("Đang thu hồi…") : t("Thu hồi")}</Button></DialogActions>
      </Dialog>
      <Snackbar open={!!notice} message={notice ? t(notice) : ""} autoHideDuration={5000} onClose={() => setNotice(null)} />
    </Box>
  );
}
