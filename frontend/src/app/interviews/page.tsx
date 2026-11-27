'use client';

/**
 * "Lịch của tôi" — buổi phỏng vấn trong tuần mà tôi là người tham gia.
 *
 * Cố ý làm danh sách theo ngày chứ không phải lưới tháng: câu HR hỏi hằng ngày
 * là "tuần này tôi phải phỏng vấn ai", không phải "tháng này có gì". Lưới tháng
 * cần kéo-thả, chuyển tháng, xử lý tràn ô — nhiều bề mặt hơn nhu cầu.
 *
 * Tuần tính từ thứ Hai, theo giờ Việt Nam. Chọn thứ Hai chứ không phải Chủ nhật
 * vì lịch làm việc Việt Nam bắt đầu từ thứ Hai; tuần bắt đầu bằng Chủ nhật sẽ
 * đặt hai ngày cuối tuần ở hai đầu khác nhau, khó đọc.
 */
import { useCallback, useEffect, useMemo, useState } from 'react';
import {
  Alert, Box, Button, Chip, CircularProgress, Paper, Table, TableBody, TableCell,
  TableContainer, TableHead, TableRow, Typography,
} from '@mui/material';
import ChevronLeftIcon from '@mui/icons-material/ChevronLeft';
import ChevronRightIcon from '@mui/icons-material/ChevronRight';
import { useRouter } from 'next/navigation';
import { useI18n } from '@/i18n/I18nProvider';
import { interviewsApi } from '@/lib/api';
import { formatVietnamTime } from '@/components/positions/InterviewPanel';
import { addDays, mondayOf, vietnamDayKey } from '@/lib/interviewWeek';

type Interview = {
  interview_id: string;
  application_id: string;
  position_code: string;
  position_title: string;
  candidate_name: string | null;
  round_number: number;
  status: 'SCHEDULED' | 'DONE' | 'CANCELLED' | 'NO_SHOW';
  starts_at: string;
  // Hai trường này API đã trả từ B1 (_INTERVIEW_SELECT) nhưng kiểu ở đây thiếu,
  // nên trước đó không màn nào dùng được chúng dù dữ liệu vẫn về.
  total_scorecards: number;
  submitted_scorecards: number;
  ends_at: string;
  location_kind: 'ONSITE' | 'ONLINE' | 'PHONE';
  location_text: string | null;
  participant_count: number;
};

const STATUS_LABEL: Record<Interview['status'], string> = {
  SCHEDULED: 'Đã hẹn', DONE: 'Đã diễn ra', CANCELLED: 'Đã huỷ', NO_SHOW: 'Ứng viên không đến',
};


export default function MyInterviewsPage() {
  const { t } = useI18n();
  const router = useRouter();
  const [weekStart, setWeekStart] = useState(() => mondayOf(new Date()));
  const [items, setItems] = useState<Interview[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true); setError(null);
    try {
      const from = weekStart.toISOString();
      const to = addDays(weekStart, 7).toISOString();
      const response = await interviewsApi.list({ from_at: from, to_at: to, mine: true });
      setItems(response.data);
    } catch (err: any) {
      setError(err.response?.data?.detail || t('Không tải được lịch phỏng vấn.'));
    } finally { setLoading(false); }
  }, [weekStart, t]);

  useEffect(() => { void load(); }, [load]);

  const byDay = useMemo(() => {
    const groups = new Map<string, Interview[]>();
    for (const item of items) {
      // Nhóm theo ngày Việt Nam, không theo ngày UTC — buổi 23:00 UTC là 06:00
      // hôm sau ở Việt Nam, và xếp nhầm ngày là lỗi người dùng thấy ngay.
      const key = vietnamDayKey(item.starts_at);
      groups.set(key, [...(groups.get(key) || []), item]);
    }
    return groups;
  }, [items]);

  const days = Array.from({ length: 7 }, (_, index) => addDays(weekStart, index));

  return <Box>
    <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', mb: 2, flexWrap: 'wrap', gap: 1 }}>
      <Box>
        <Typography variant="h4" sx={{ fontSize: 22 }}>{t('Lịch phỏng vấn của tôi')}</Typography>
        <Typography variant="body2" color="text.secondary">
          {t('Các buổi bạn là người phỏng vấn hoặc người dự, theo tuần. Giờ hiện theo giờ Việt Nam (GMT+7).')}
        </Typography>
      </Box>
      <Box sx={{ display: 'flex', gap: 1, alignItems: 'center' }}>
        <Button startIcon={<ChevronLeftIcon />} onClick={() => setWeekStart(addDays(weekStart, -7))}>{t('Tuần trước')}</Button>
        <Button onClick={() => setWeekStart(mondayOf(new Date()))}>{t('Tuần này')}</Button>
        <Button endIcon={<ChevronRightIcon />} onClick={() => setWeekStart(addDays(weekStart, 7))}>{t('Tuần sau')}</Button>
      </Box>
    </Box>

    {error && <Alert severity="error" sx={{ mb: 2 }} onClose={() => setError(null)}>{t(error)}</Alert>}

    {loading ? <CircularProgress /> : <TableContainer component={Paper} variant="outlined">
      <Table size="small">
        <TableHead><TableRow>
          <TableCell sx={{ width: 130 }}>{t('Ngày')}</TableCell>
          <TableCell>{t('Thời gian')}</TableCell>
          <TableCell>{t('Vị trí')}</TableCell>
          <TableCell>{t('Ứng viên')}</TableCell>
          <TableCell>{t('Vòng')}</TableCell>
          <TableCell>{t('Hình thức')}</TableCell>
          <TableCell>{t('Trạng thái')}</TableCell>
          <TableCell>{t('Phiếu chấm')}</TableCell>
        </TableRow></TableHead>
        <TableBody>
          {days.map(day => {
            const key = vietnamDayKey(day);
            const dayItems = byDay.get(key) || [];
            if (!dayItems.length) return <TableRow key={key}>
              <TableCell sx={{ color: 'text.secondary' }}>
                {new Intl.DateTimeFormat('vi-VN', { timeZone: 'Asia/Ho_Chi_Minh', weekday: 'short', day: '2-digit', month: '2-digit' }).format(day)}
              </TableCell>
              <TableCell colSpan={6} sx={{ color: 'text.disabled' }}>{t('Không có buổi nào')}</TableCell>
            </TableRow>;
            // Cả dòng bấm được: người phỏng vấn vào đây để mở phiếu chấm của
            // mình. Không có lối này thì họ biết lịch nhưng không có đường tới
            // việc phải làm.
            return dayItems.map((item, index) => <TableRow key={item.interview_id} hover
              onClick={() => router.push(`/interviews/${item.interview_id}`)}
              sx={{ cursor: 'pointer' }}>
              <TableCell>
                {index === 0 && new Intl.DateTimeFormat('vi-VN', { timeZone: 'Asia/Ho_Chi_Minh', weekday: 'short', day: '2-digit', month: '2-digit' }).format(day)}
              </TableCell>
              <TableCell>{formatVietnamTime(item.starts_at)}</TableCell>
              <TableCell>{item.position_code} · {item.position_title}</TableCell>
              <TableCell>{item.candidate_name || '—'}</TableCell>
              <TableCell>{item.round_number}</TableCell>
              <TableCell>
                {t(item.location_kind === 'ONSITE' ? 'Tại văn phòng' : item.location_kind === 'ONLINE' ? 'Trực tuyến' : 'Qua điện thoại')}
              </TableCell>
              <TableCell>
                <Chip size="small" variant="outlined" label={t(STATUS_LABEL[item.status])}
                  color={item.status === 'SCHEDULED' ? 'info' : item.status === 'DONE' ? 'success' : 'default'} />
              </TableCell>
              <TableCell>
                {/* Chỉ hiện khi buổi đã có phiếu: buổi chưa tới mà hiện "0/3" thì
                    trông như đang trễ hạn trong khi chưa ai phải làm gì. */}
                {item.total_scorecards > 0 && (
                  <Typography variant="caption" color={item.submitted_scorecards < item.total_scorecards ? 'warning.main' : 'text.secondary'}>
                    {t('Đã nộp {0}/{1}').replace('{0}', String(item.submitted_scorecards)).replace('{1}', String(item.total_scorecards))}
                  </Typography>
                )}
              </TableCell>
            </TableRow>);
          })}
        </TableBody>
      </Table>
    </TableContainer>}
  </Box>;
}
