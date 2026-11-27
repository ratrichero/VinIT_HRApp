'use client';

import { useCallback, useEffect, useState } from 'react';
import { Accordion, AccordionDetails as AccordionContent, AccordionSummary, Alert, Box, Button, Card, CardContent, CircularProgress, Dialog, DialogActions, DialogContent, DialogTitle, Divider, MenuItem, Stack, TextField, Typography } from '@mui/material';
import ExpandMoreIcon from '@mui/icons-material/ExpandMore';
import { useI18n } from '@/i18n/I18nProvider';
import { localizeServerMessage } from '@/i18n/serverMessages';
import { positionsApi, rubricApi } from '@/lib/api';
import { purgeRubricDrafts, readDraft, removeDraft, rubricDraftKey, writeDraft } from '@/lib/localDrafts';
import { useUnsavedChangesGuard } from '@/hooks/useUnsavedChangesGuard';
import { optionalRequirementSpec, rubricKeywords } from '@/lib/phase2Workflow';
import backendProposal from '@/data/rubric-proposal-it-backend.json';
import RubricItemEditor, { CategoryHeader, groupTotal, type RubricItem } from '@/components/positions/RubricItemEditor';

type Family = { job_family_id: string; name: string; code: string };
type Capabilities = { user_id: string; can_create: boolean; can_publish: boolean };
// Một nguồn duy nhất cho hình dạng tiêu chí: component tự viết nó.
// Hai bản định nghĩa song song là cách chắc chắn nhất để chúng lệch nhau.
type Item = RubricItem;
type Version = { template_version_id: string; title: string; family_name?: string; job_family_id: string; level_band: string | null; created_by: string; status: 'DRAFT' | 'PUBLISHED' | 'ARCHIVED'; version_number: number; revision: number; mandatory_weight_total: number | string; nice_to_have_weight_total: number | string; items: Item[] };
const familyLabel = (code: string, name: string, t: (key: string) => string) => code === 'ADMIN_OPERATIONS' ? t('Vận hành & Hành chính') : name;
const statusLabel = (status: Version['status'], t: (key: string) => string) => ({ DRAFT: t('Bản nháp'), PUBLISHED: t('Đã xuất bản'), ARCHIVED: t('Đã lưu trữ') }[status]);
const emptyItem = (): Item => ({ name: '', description: '', category: 'MUST_HAVE', weight_in_group: 100, expected_evidence_keywords: [], requirement_spec: null, evidence_guidance: null });

export default function RubricsPage() {
  const { t } = useI18n();
  const [families, setFamilies] = useState<Family[]>([]);
  const [versions, setVersions] = useState<Version[]>([]);
  const [capabilities, setCapabilities] = useState<Capabilities | null>(null);
  const [selected, setSelected] = useState<Version | null>(null);
  const [creating, setCreating] = useState(false);
  const [family, setFamily] = useState('');
  const [title, setTitle] = useState('');
  const [level, setLevel] = useState('');
  const [mandatory, setMandatory] = useState('70');
  const [nice, setNice] = useState('30');
  const [items, setItems] = useState<Item[]>([]);
  const [specs, setSpecs] = useState<string[]>([]);
  const [keywords, setKeywords] = useState<string[]>([]);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const [dirty, setDirty] = useState(false);
  // Sinh rubric từ JD của một vị trí: mở hộp chọn vị trí, rồi nạp bản nháp.
  const [suggestOpen, setSuggestOpen] = useState(false);
  const [suggestPositions, setSuggestPositions] = useState<Array<{ position_id: string; title: string; job_family_id: string | null }>>([]);
  const [suggestPosition, setSuggestPosition] = useState('');
  const [suggesting, setSuggesting] = useState(false);
  // Sinh nháp từ JD dán tay: dựng rubric mẫu TRƯỚC khi mở vị trí nào.
  const [jdOpen, setJdOpen] = useState(false);
  const [jdText, setJdText] = useState('');
  const [jdTitle, setJdTitle] = useState('');
  const [jdFamily, setJdFamily] = useState('');
  const [jdBusy, setJdBusy] = useState(false);
  // Nháp khôi phục được sau khi đóng tab: nháp chỉ nằm trong bộ nhớ trình duyệt
  // cho tới khi bấm Lưu, nên đóng tab/mất điện là mất trắng công đoạn sinh nháp.
  const [recovered, setRecovered] = useState<{ savedAt: number } | null>(null);
  const canEdit = creating || (!!selected && selected.status === 'DRAFT' && !!capabilities && (capabilities.can_publish || (capabilities.can_create && selected.created_by === capabilities.user_id)));

  const load = useCallback(async () => {
    const [f, v, c] = await Promise.all([rubricApi.families(), rubricApi.templates(), rubricApi.capabilities()]);
    setFamilies(f.data); setVersions(v.data); setCapabilities(c.data);
  }, []);
  useEffect(() => { let active = true; load().catch((err: any) => { if (active) setError(err.response?.data?.detail || t('Không thể tải thư viện rubric.')); }).finally(() => { if (active) setLoading(false); }); return () => { active = false; }; }, [load, t]);
  /**
   * Trạng thái đang soạn, gom một chỗ để lưu nháp và khôi phục không bị lệch
   * với những gì biểu mẫu thực sự giữ.
   */
  const currentDraft = () => ({
    selected_id: selected?.template_version_id ?? null, creating,
    family, title, level, mandatory, nice, items, specs, keywords,
  });

  const applySnapshot = (d: any) => {
    setCreating(!!d.creating);
    setFamily(d.family || ''); setTitle(d.title || ''); setLevel(d.level || '');
    setMandatory(d.mandatory ?? '70'); setNice(d.nice ?? '30');
    setItems(Array.isArray(d.items) ? d.items : []);
    setSpecs(Array.isArray(d.specs) ? d.specs : []);
    setKeywords(Array.isArray(d.keywords) ? d.keywords : []);
  };

  // Chặn ba đường mất dữ liệu mà không hỏi: đóng tab, bấm link nội bộ, bấm Back.
  useUnsavedChangesGuard(dirty, t('Bản nháp rubric chưa lưu sẽ bị mất. Tiếp tục?'), { fallbackHref: '/rubrics' });

  // Lưu nháp xuống trình duyệt. Khôi phục được cả khi trình duyệt tắt ngang —
  // hộp thoại beforeunload không phải lúc nào cũng hiện (một số trình duyệt chỉ
  // hiện sau khi người dùng đã tương tác với trang).
  useEffect(() => {
    if (!dirty || loading) return;
    writeDraft(rubricDraftKey(), currentDraft());
    // currentDraft() đọc trực tiếp state; đưa từng field vào deps thay vì dùng
    // hàm để không lưu lại mỗi lần render vì một object mới.
  }, [dirty, loading, selected, creating, family, title, level, mandatory, nice, items, specs, keywords]); // eslint-disable-line react-hooks/exhaustive-deps

  // Nháp cũ chưa lưu (đóng tab, mất điện) — hỏi khôi phục thay vì lặng lẽ bỏ.
  useEffect(() => {
    if (loading) return;
    const stored = readDraft<any>(rubricDraftKey());
    if (!stored || !Array.isArray(stored.items) || !stored.items.length) return;
    if (!window.confirm(t('Có bản nháp rubric chưa lưu từ lần trước. Khôi phục?'))) {
      purgeRubricDrafts();
      return;
    }
    void (async () => {
      applySnapshot(stored);
      if (stored.selected_id) {
        // Nháp của một phiên bản ĐÃ CÓ: phải nạp lại `selected` từ máy chủ, nếu
        // không thì `save` gọi update(selected!.template_version_id) trên null.
        // Nạp hỏng (bị xoá, mất quyền) thì chuyển thành nháp mới để không mất
        // nội dung HR đã viết — tệ nhất là lưu thành một rubric khác.
        try { setSelected((await rubricApi.getVersion(stored.selected_id)).data); setCreating(false); }
        catch (err: any) {
          // 403/404: phiên bản không còn thuộc quyền của người này — bỏ nháp,
          // không giữ nội dung rubric của người khác trong máy.
          if ([403, 404].includes(err?.response?.status)) { purgeRubricDrafts(); return; }
          setSelected(null); setCreating(true);
        }
      }
      setRecovered({ savedAt: Date.now() });
      setDirty(true);
    })();
  }, [loading]); // eslint-disable-line react-hooks/exhaustive-deps

  const discardLocalDraft = () => {
    purgeRubricDrafts();
    setRecovered(null);
  };

  const populate = (v: Version) => {
    setSelected(v); setCreating(false); setMandatory(String(v.mandatory_weight_total)); setNice(String(v.nice_to_have_weight_total));
    setItems(v.items); setSpecs(v.items.map(i => i.requirement_spec ? JSON.stringify(i.requirement_spec, null, 2) : '')); setKeywords(v.items.map(i => i.expected_evidence_keywords.join(', ')));  setDirty(false);
  };
  const select = async (id: string) => {
    if (dirty && !window.confirm(t('Bỏ các thay đổi chưa lưu?'))) return;
    try { setBusy(true); setError(''); populate((await rubricApi.getVersion(id)).data); }
    catch (err: any) { setError(err.response?.data?.detail || t('Không thể tải phiên bản rubric.')); }
    finally { setBusy(false); }
  };
  const create = () => {
    setNotice('');
    if (dirty && !window.confirm(t('Bỏ các thay đổi chưa lưu?'))) return;
    setSelected(null); setCreating(true); setFamily(families[0]?.job_family_id || ''); setTitle(''); setLevel(''); setMandatory('70'); setNice('30'); setItems([]); setSpecs([]); setKeywords([]); setError(''); setDirty(false);
  };
  const openSuggest = async () => {
    if (dirty && !window.confirm(t('Bỏ các thay đổi chưa lưu?'))) return;
    setSuggestOpen(true); setSuggestPosition(''); setError(''); setSuggesting(false);
    try {
      const res = await positionsApi.listAll();
      // Chỉ vị trí đã có nhóm mới sinh được rubric — rubric không nhóm thì
      // không tái sử dụng được, mất ý nghĩa của thư viện.
      setSuggestPositions(res.filter((item: any) => item.job_family_id));
    } catch (err: any) {
      setError(err.response?.data?.detail || t('Không thể tải danh sách vị trí.'));
      setSuggestOpen(false);
    }
  };
  const runSuggest = async () => {
    if (!suggestPosition) return;
    try {
      setSuggesting(true); setError('');
      const res = await rubricApi.suggestFromPosition(suggestPosition);
      const data = res.data;
      populateDraft(data);
      setSuggestOpen(false);
      // Nói rõ bản nháp đến từ đâu và chưa được lưu — nếu không, HR dễ tưởng
      // vừa tạo xong một rubric trong thư viện.
      setNotice(data.rejected_items
        ? t('Đã sinh nháp từ JD (bỏ {0} tiêu chí không hợp lệ). CHƯA lưu — rà soát rồi bấm lưu.', String(data.rejected_items))
        : t('Đã sinh nháp từ JD. CHƯA lưu — rà soát rồi bấm lưu.'));
    } catch (err: any) {
      setError(err.response?.data?.detail ? localizeServerMessage(err.response.data.detail) : t('Không thể sinh rubric từ JD.'));
      setSuggestOpen(false);
    } finally { setSuggesting(false); }
  };
  /** Điền biểu mẫu từ một bộ nháp — dùng chung cho cả hai nguồn sinh nháp. */
  const populateDraft = (data: any) => {
    setSelected(null); setCreating(true);
    setFamily(data.job_family_id); setTitle(data.title); setLevel('');
    setMandatory('70'); setNice('30');
    setItems((data.items as Item[]).map(item => ({ ...item, weight_in_group: item.weight_in_group ?? (item as any).weight })));
    setSpecs((data.items as Item[]).map(item => item.requirement_spec ? JSON.stringify(item.requirement_spec, null, 2) : ''));
    setKeywords((data.items as Item[]).map(item => item.expected_evidence_keywords.join(', ')));
    setDirty(true);
  };

  const openJdSuggest = () => {
    if (dirty && !window.confirm(t('Bỏ các thay đổi chưa lưu?'))) return;
    setJdOpen(true); setJdText(''); setJdTitle(''); setError(''); setJdBusy(false);
    setJdFamily((families[0] && families[0].job_family_id) || '');
  };

  const runJdSuggest = async () => {
    if (!jdText.trim() || !jdFamily) return;
    try {
      setJdBusy(true); setError('');
      const res = await rubricApi.suggestFromJd({ job_family_id: jdFamily, jd_text: jdText.trim(), title: jdTitle.trim() || undefined });
      const data = res.data;
      populateDraft(data);
      setJdOpen(false);
      setNotice(data.rejected_items
        ? t('Đã sinh nháp từ JD dán tay (bỏ {0} tiêu chí không hợp lệ). CHƯA lưu — rà soát rồi bấm lưu.', String(data.rejected_items))
        : t('Đã sinh nháp từ JD dán tay. CHƯA lưu — rà soát rồi bấm lưu.'));
    } catch (err: any) {
      setError(err.response?.data?.detail ? localizeServerMessage(err.response.data.detail) : t('Không thể sinh rubric từ JD dán tay.'));
      setJdOpen(false);
    } finally { setJdBusy(false); }
  };

  const useProposal = () => {
    if (dirty && !window.confirm(t('Bỏ các thay đổi chưa lưu?'))) return;
    const family = families.find(f => f.code === backendProposal.job_family_code);
    if (!family) { setError(t('Nhóm IT & Digital không khả dụng.')); return; }
    const proposedItems = backendProposal.items as Item[];
    setSelected(null); setCreating(true); setFamily(family.job_family_id);
    setTitle(backendProposal.title); setLevel(backendProposal.level_band || '');
    setMandatory(String(backendProposal.mandatory_weight_total)); setNice(String(backendProposal.nice_to_have_weight_total));
    setItems(proposedItems.map(item => ({ ...item })));
    setSpecs(proposedItems.map(item => item.requirement_spec ? JSON.stringify(item.requirement_spec, null, 2) : ''));
    setKeywords(proposedItems.map(item => item.expected_evidence_keywords.join(', ')));
    setError(''); setDirty(true);
  };
  const changeItem = (index: number, patch: Partial<Item>) => { setItems(current => current.map((item, i) => i === index ? { ...item, ...patch } : item)); setDirty(true); };
  const save = async () => {
    try {
      setBusy(true); setError('');
      const payload = { mandatory_weight_total: Number(mandatory), nice_to_have_weight_total: Number(nice), items: items.map((item, i) => ({ ...item, expected_evidence_keywords: rubricKeywords(keywords[i]), weight_in_group: Number(item.weight_in_group), requirement_spec: optionalRequirementSpec(specs[i] || '') })) };
      const result = creating ? await rubricApi.create({ ...payload, job_family_id: family, title, level_band: level || null }) : await rubricApi.update(selected!.template_version_id, { ...payload, expected_revision: selected!.revision });
      // Đã lên máy chủ thì nháp trong trình duyệt không còn là bản mới nhất.
      purgeRubricDrafts(); setRecovered(null);
      populate(result.data); await load();
    } catch (err: any) { setError(err instanceof SyntaxError ? t('Requirement spec phải là JSON hợp lệ.') : (err.response?.data?.detail || t('Không thể lưu rubric.'))); }
    finally { setBusy(false); }
  };
  const act = async (action: 'publish' | 'clone') => {
    if (!selected || dirty) return;
    if (!window.confirm(action === 'publish' ? t('Xuất bản phiên bản này? Phiên bản đã xuất bản sẽ bất biến.') : t('Tạo phiên bản nháp mới từ rubric này?'))) return;
    try { setBusy(true); setError(''); const result = action === 'publish' ? await rubricApi.publish(selected.template_version_id, selected.revision) : await rubricApi.clone(selected.template_version_id); populate(result.data); await load(); }
    catch (err: any) {
      // Mất quyền hoặc rubric đã bị xoá: nội dung đang soạn không còn là việc
      // của tài khoản này nữa, nên đừng giữ lại trong trình duyệt.
      if ([403, 404].includes(err.response?.status)) discardLocalDraft();
      setError(err.response?.data?.detail || t('Không thể cập nhật rubric.'));
    }
    finally { setBusy(false); }
  };
  return <Box>
    <Typography variant="h1" sx={{ fontSize: 28, color: '#0A2B57', mb: 1 }}>{t('Thư viện rubric')}</Typography>
    <Typography color="text.secondary" sx={{ mb: 2 }}>{t('HR tạo bản nháp; HR Lead xuất bản. Đề xuất chưa phải chuẩn nghiệp vụ.')}</Typography>
    {error && <Alert severity="error" sx={{ mb: 2 }} onClose={() => setError('')}>{localizeServerMessage(error)}</Alert>}
    {notice && <Alert severity="success" sx={{ mb: 2 }} onClose={() => setNotice('')} data-testid="rubric-notice">{notice}</Alert>}
    {/* Nháp khôi phục từ trình duyệt: nói rõ nó CHƯA lên máy chủ, và cho bỏ đi
        nếu HR không muốn dùng tiếp — nếu không, nháp cũ sẽ quay lại mãi. */}
    {recovered && dirty && <Alert severity="warning" sx={{ mb: 2 }} data-testid="rubric-recovered"
      action={<Button color="inherit" size="small" onClick={discardLocalDraft}>{t('Bỏ bản nháp')}</Button>}>
      {t('Đã khôi phục bản nháp rubric CHƯA lưu từ lần trước. Kiểm tra lại rồi bấm Lưu bản nháp — cho tới lúc đó nó chỉ nằm trong trình duyệt này.')}
    </Alert>}

    {/* Hướng dẫn ngay trên trang: người mới mở /rubrics lần đầu không biết
        "rubric" là gì và ba nút khác nhau ở đâu. Giải thích tại chỗ tốt hơn
        một tài liệu mà không ai tìm thấy. */}
    <Accordion sx={{ mb: 2 }} data-testid="rubric-help">
      <AccordionSummary expandIcon={<ExpandMoreIcon />}>
        <Typography fontWeight={600}>{t('Rubric là gì? Bắt đầu từ đâu?')}</Typography>
      </AccordionSummary>
      <AccordionContent>
        <Stack spacing={1.5}>
          <Typography variant="body2">
            <b>{t('Rubric là bộ tiêu chí để chấm ứng viên cho một nhóm công việc.')}</b>{' '}
            {t('Không có rubric thì hệ thống không biết "giỏi" nghĩa là gì, và điểm số không so sánh được giữa các ứng viên.')}
          </Typography>
          <Typography variant="body2">
            {t('Rubric khoá thước đo lại TRƯỚC KHI xem CV — đó là toàn bộ giá trị của nó. Quyết định thước đo trước khi biết ai là người được đo.')}
          </Typography>
          <Divider />
          <Typography variant="body2" fontWeight={600}>{t('Ba vòng đời khác nhau, đừng nhầm:')}</Typography>
          <Typography variant="body2" component="div">
            <ol style={{ margin: 0, paddingLeft: 20 }}>
              <li>{t('Rubric mẫu (trang này) — dùng lại cho nhiều vị trí cùng nhóm')}</li>
              <li>{t('Bộ tiêu chí của một vị trí — sinh ra từ rubric mẫu, thuộc riêng vị trí đó')}</li>
              <li>{t('Kết quả chấm — điểm của từng ứng viên theo bộ tiêu chí đó')}</li>
            </ol>
          </Typography>
          <Typography variant="body2" color="text.secondary">
            {t('Sửa rubric mẫu KHÔNG làm đổi bộ tiêu chí của vị trí đã dùng nó. Đó là lý do phải "áp dụng" rubric vào vị trí.')}
          </Typography>
          <Divider />
          <Typography variant="body2" fontWeight={600}>{t('Ba nút ở cột trái:')}</Typography>
          <Typography variant="body2" component="div">
            <ul style={{ margin: 0, paddingLeft: 20 }}>
              <li><b>{t('Tạo rubric nháp')}</b> — {t('biểu mẫu trống, tự gõ 100%. Không dùng AI.')}</li>
              <li><b>{t('Sinh từ JD của một vị trí')}</b> — {t('AI đọc JD và đề xuất tiêu chí. Cần vị trí đã có Nhóm vị trí. KHÔNG tự lưu.')}</li>
              <li><b>{t('Dùng bộ mẫu ví dụ')}</b> — {t('tiêu chí viết sẵn trong mã nguồn, để xem một rubric đầy đủ trông thế nào. Không phải AI.')}</li>
            </ul>
          </Typography>
          <Divider />
          <Typography variant="body2" fontWeight={600}>{t('Quy trình khi đăng một job mới:')}</Typography>
          <Typography variant="body2" component="div">
            <ol style={{ margin: 0, paddingLeft: 20 }}>
              <li>{t('Tạo vị trí — nhớ chọn Nhóm vị trí')}</li>
              <li>{t('Vào vị trí → tab Tiêu chí')}</li>
              <li>{t('Chọn: dùng tiêu chí AI tự sinh, hoặc áp rubric đã xuất bản (chuẩn nhất khi tuyển nhiều vị trí cùng nhóm)')}</li>
              <li>{t('Duyệt tiêu chí — chưa duyệt thì không chấm điểm được')}</li>
              <li>{t('Tải CV, chấm điểm, xếp hạng')}</li>
            </ol>
          </Typography>
          <Alert severity="info" sx={{ mt: 1 }}>
            {t('Chỉ HR Lead xuất bản được rubric. HR thường tạo nháp để HR Lead duyệt — đây là cố ý, vì xuất bản nghĩa là "bộ tiêu chí này dùng chung được".')}
          </Alert>
        </Stack>
      </AccordionContent>
    </Accordion>
    {loading ? <CircularProgress /> : capabilities && <Stack direction={{ xs: 'column', lg: 'row' }} spacing={2} alignItems="start">
      <Card variant="outlined" sx={{ width: { xs: '100%', lg: 360 }, flexShrink: 0 }}><CardContent>
        {capabilities.can_create && <Stack spacing={1}>
          <Button variant="contained" onClick={create} disabled={busy}>{t('Tạo rubric nháp')}</Button>
          <Button variant="outlined" onClick={openSuggest} disabled={busy}>{t('Sinh từ JD của một vị trí')}</Button>
          <Button variant="outlined" onClick={openJdSuggest} disabled={busy}>{t('Sinh từ JD dán tay')}</Button>
          <Button onClick={useProposal} disabled={busy} sx={{ justifyContent: 'flex-start', textAlign: 'left' }}>{t('Dùng bộ mẫu ví dụ (Backend Python)')}</Button>
          <Typography variant="caption">{t('Bộ mẫu ví dụ là tiêu chí viết sẵn trong mã nguồn, KHÔNG phải AI sinh ra. Hai nút "Sinh từ JD" mới gọi AI: một nút đọc JD của vị trí đã có, một nút đọc JD anh dán vào — dùng khi muốn dựng rubric trước khi mở vị trí. Cả ba đều chỉ điền biểu mẫu, HR phải rà soát rồi bấm lưu.')}</Typography>
        </Stack>}
        {!capabilities.can_create && <Alert severity="warning" sx={{ mt: 1 }}>
          {t('Tài khoản của bạn xem được thư viện nhưng không tạo được rubric. Cần vai trò HR tuyển dụng, Trưởng nhóm HR hoặc Quản trị viên — nhờ Quản trị viên cấp trong mục Người dùng.')}
        </Alert>}
        {versions.length === 0 && <Typography sx={{ mt: 2 }}>{t('Chưa có rubric nào.')}</Typography>}
        {versions.map(v => <Button key={v.template_version_id} fullWidth sx={{ mt: 1, justifyContent: 'flex-start', textAlign: 'left' }} variant={selected?.template_version_id === v.template_version_id ? 'outlined' : 'text'} disabled={busy} onClick={() => select(v.template_version_id)}>{v.title} · v{v.version_number} · {statusLabel(v.status, t)} · {families.find(f => f.job_family_id === v.job_family_id) ? familyLabel(families.find(f => f.job_family_id === v.job_family_id)!.code, v.family_name || '', t) : v.family_name}</Button>)}
      </CardContent></Card>
      {(creating || selected) && (
        <Card variant="outlined" sx={{ flex: 1, width: '100%' }}>
          <CardContent>
            <Stack spacing={2}>
              {creating ? (
                <>
                  <TextField select label={t('Nhóm vị trí')} value={family} onChange={e => { setFamily(e.target.value); setDirty(true); }}>
                    {families.map(f => <MenuItem value={f.job_family_id} key={f.job_family_id}>{familyLabel(f.code, f.name, t)}</MenuItem>)}
                  </TextField>
                  <TextField required label={t('Tên rubric')} value={title} onChange={e => { setTitle(e.target.value); setDirty(true); }} />
                  <TextField label={t('Cấp độ (tùy chọn)')} value={level} onChange={e => { setLevel(e.target.value); setDirty(true); }} />
                </>
              ) : (
                <Typography variant="h2" sx={{ fontSize: 20 }}>
                  {selected?.title} · v{selected?.version_number} · {selected && statusLabel(selected.status, t)} {selected?.level_band && `· ${selected.level_band}`}
                </Typography>
              )}

              {/* Trọng số nhóm + tổng điểm của cả rubric. Hai nhóm phải cộng 100. */}
              <Box sx={{ display: 'flex', gap: 2, flexWrap: 'wrap', alignItems: 'center' }}>
                <TextField
                  type="number" size="small" label={t('Trọng số bắt buộc (%)')}
                  value={mandatory} disabled={!canEdit}
                  onChange={e => { setMandatory(e.target.value); setDirty(true); }}
                  sx={{ width: 190 }}
                  helperText={Number(mandatory) + Number(nice) === 100 ? t('Tổng hai nhóm: 100%') : t('Tổng hai nhóm phải bằng 100%')}
                  error={Number(mandatory) + Number(nice) !== 100}
                />
                <TextField
                  type="number" size="small" label={t('Trọng số ưu tiên (%)')}
                  value={nice} disabled={!canEdit}
                  onChange={e => { setNice(e.target.value); setDirty(true); }}
                  sx={{ width: 190 }}
                />
              </Box>
              <Typography variant="caption" color="text.secondary">
                {t('Trọng số nhóm là tỉ lệ điểm giữa hai nhóm, không phải trọng số tiêu chí. Mỗi nhóm phải có tiêu chí cộng đúng 100% trước khi xuất bản.')}
              </Typography>

              {/* HAI CỘT: bắt buộc bên trái, ưu tiên bên phải — cùng cách bố trí với
                  trang chi tiết vị trí tab Tiêu chí, để HR không phải học hai
                  giao diện cho cùng một khái niệm. Trên màn hẹp hai cột xếp dọc. */}
              <Box sx={{ display: 'grid', gap: 2, gridTemplateColumns: { xs: '1fr', md: '1fr 1fr' } }}>
                {(['MUST_HAVE', 'NICE_TO_HAVE'] as const).map(category => {
                  const indexes = items.map((item, i) => ({ item, i })).filter(({ item }) => item.category === category);
                  return (
                    <Card key={category} variant="outlined" sx={{ borderColor: '#E4EAF2', backgroundColor: '#FCFDFE' }}>
                      <CardContent>
                        <CategoryHeader category={category} items={items} />
                        {indexes.length === 0 && (
                          <Typography variant="body2" color="text.secondary" sx={{ py: 2, textAlign: 'center' }}>
                            {t('Chưa có tiêu chí nào trong nhóm này.')}
                          </Typography>
                        )}
                        {indexes.map(({ item, i }, positionInColumn) => (
                          <Box key={i}>
                            {positionInColumn > 0 && <Divider />}
                            <RubricItemEditor
                              item={item}
                              index={i}
                              keywords={keywords[i] || ''}
                              spec={specs[i] || ''}
                              canEdit={canEdit}
                              onChange={patch => changeItem(i, patch)}
                              onKeywordsChange={value => { setKeywords(current => current.map((v, n) => n === i ? value : v)); setDirty(true); }}
                              onSpecChange={value => { setSpecs(current => current.map((v, n) => n === i ? value : v)); setDirty(true); }}
                              onRemove={() => {
                                setItems(current => current.filter((_, n) => n !== i));
                                setSpecs(current => current.filter((_, n) => n !== i));
                                setKeywords(current => current.filter((_, n) => n !== i));
                                setDirty(true);
                              }}
                              onMove={direction => {
                                // Đổi chỗ với tiêu chí cùng nhóm liền kề, không phải với
                                // phần tử kế tiếp trong mảng: hai nhóm nằm ở hai cột nên
                                // "lên/xuống" phải hiểu theo cột người dùng đang nhìn.
                                const siblings = indexes.map(entry => entry.i);
                                const at = siblings.indexOf(i);
                                const target = siblings[at + direction];
                                if (target === undefined) return;
                                setItems(current => {
                                  const next = [...current];
                                  [next[i], next[target]] = [next[target], next[i]];
                                  return next;
                                });
                                setSpecs(current => {
                                  const next = [...current];
                                  [next[i], next[target]] = [next[target], next[i]];
                                  return next;
                                });
                                setKeywords(current => {
                                  const next = [...current];
                                  [next[i], next[target]] = [next[target], next[i]];
                                  return next;
                                });
                                setDirty(true);
                              }}
                            />
                          </Box>
                        ))}
                        <Divider sx={{ my: 1.5 }} />
                        <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: 1 }}>
                          <Typography
                            variant="body2"
                            color={indexes.length === 0 || Math.abs(groupTotal(items, category) - 100) < 0.005 ? 'text.secondary' : 'error'}
                            fontWeight={groupTotal(items, category) === 100 ? 400 : 600}
                          >
                            {t('Tổng trong nhóm:')} {groupTotal(items, category)}% / 100%
                          </Typography>
                          {canEdit && (
                            <Button
                              size="small"
                              onClick={() => {
                                // Thêm vào ĐÚNG cột: nhóm của tiêu chí mới phải khớp cột
                                // người dùng vừa bấm, không để họ thêm rồi phải đổi nhóm tay.
                                setItems(current => [...current, { ...emptyItem(), category }]);
                                setSpecs(current => [...current, '']);
                                setKeywords(current => [...current, '']);
                                setDirty(true);
                              }}
                            >
                              {t('Thêm tiêu chí')}
                            </Button>
                          )}
                        </Box>
                      </CardContent>
                    </Card>
                  );
                })}
              </Box>

              <Box sx={{ display: 'flex', gap: 1, flexWrap: 'wrap', alignItems: 'center' }}>
                {canEdit && <Button variant="contained" disabled={busy || (creating && (!family || !title.trim()))} onClick={save}>{t('Lưu bản nháp')}</Button>}
                {!creating && selected?.status === 'DRAFT' && capabilities.can_publish && <Button variant="outlined" disabled={busy || dirty} onClick={() => act('publish')}>{t('Xuất bản rubric')}</Button>}
                {!creating && selected?.status === 'PUBLISHED' && capabilities.can_create && <Button variant="outlined" disabled={busy} onClick={() => act('clone')}>{t('Tạo phiên bản nháp mới')}</Button>}
                {dirty && <Typography variant="caption">{t('Có thay đổi chưa lưu.')}</Typography>}
              </Box>
              {!creating && selected?.status === 'DRAFT' && !capabilities.can_publish && (
                <Alert severity="info">
                  {t('Chỉ Trưởng nhóm HR hoặc Quản trị viên xuất bản được rubric. Bản nháp này cần người có vai trò đó xuất bản.')}
                </Alert>
              )}
            </Stack>
          </CardContent>
        </Card>
      )}
    </Stack>}

    <Dialog open={suggestOpen} onClose={() => !suggesting && setSuggestOpen(false)} fullWidth maxWidth="sm">
      <DialogTitle>{t('Sinh rubric nháp từ JD của một vị trí')}</DialogTitle>
      <DialogContent>
        <Typography sx={{ mb: 2 }}>
          {t('Chọn một vị trí đã có mô tả công việc. AI sẽ đọc JD đó và đề xuất bộ tiêu chí. Bản nháp KHÔNG được lưu cho tới khi anh bấm lưu.')}
        </Typography>
        {!suggesting && !suggestPositions.length && <Alert severity="info">
          {t('Chưa có vị trí nào được gán Nhóm vị trí. Gán nhóm cho vị trí trước — rubric không nhóm thì không tái sử dụng được.')}
        </Alert>}
        {suggestPositions.length > 0 && <TextField select fullWidth label={t('Vị trí')} value={suggestPosition} disabled={suggesting} onChange={e => setSuggestPosition(e.target.value)}>
          {suggestPositions.map(item => <MenuItem key={item.position_id} value={item.position_id}>{item.title}</MenuItem>)}
        </TextField>}
        {suggesting && <Stack direction="row" spacing={1} alignItems="center" sx={{ mt: 2 }}>
          <CircularProgress size={20} /><Typography variant="body2">{t('AI đang đọc JD và đề xuất tiêu chí...')}</Typography>
        </Stack>}
      </DialogContent>
      <DialogActions>
        <Button onClick={() => setSuggestOpen(false)} disabled={suggesting}>{t('Hủy')}</Button>
        <Button variant="contained" onClick={runSuggest} disabled={suggesting || !suggestPosition}>{t('Sinh nháp')}</Button>
      </DialogActions>
    </Dialog>

    <Dialog open={jdOpen} onClose={() => !jdBusy && setJdOpen(false)} fullWidth maxWidth="md">
      <DialogTitle>{t('Sinh rubric nháp từ JD dán tay')}</DialogTitle>
      <DialogContent>
        <Typography sx={{ mb: 2 }}>
          {t('Dán JD vào đây để dựng rubric mẫu cho một loại vị trí sắp tuyển, không cần tạo vị trí trước. AI chỉ đề xuất; bản nháp KHÔNG được lưu cho tới khi anh bấm lưu.')}
        </Typography>
        <Stack spacing={2}>
          <TextField select fullWidth required label={t('Rubric thuộc nhóm vị trí')} value={jdFamily} disabled={jdBusy}
            onChange={e => setJdFamily(e.target.value)}
            helperText={t('Nhóm quyết định rubric này dùng lại được cho những vị trí nào.')}>
            {families.map(f => <MenuItem value={f.job_family_id} key={f.job_family_id}>{familyLabel(f.code, f.name, t)}</MenuItem>)}
          </TextField>
          <TextField fullWidth label={t('Tên rubric (tùy chọn)')} value={jdTitle} disabled={jdBusy}
            onChange={e => setJdTitle(e.target.value)} inputProps={{ maxLength: 200 }}
            helperText={t('Bỏ trống thì hệ thống đặt tên "Nháp từ JD dán tay". Sửa được sau khi lưu.')} />
          <TextField fullWidth required multiline minRows={10} label={t('Nội dung JD')} value={jdText} disabled={jdBusy}
            onChange={e => setJdText(e.target.value)} inputProps={{ maxLength: 100000 }}
            helperText={t('Tối thiểu 50 ký tự. JD càng nêu rõ yêu cầu thì tiêu chí sinh ra càng dùng được.')} />
        </Stack>
        {jdText.trim().length > 0 && jdText.trim().length < 50 && <Alert severity="warning" sx={{ mt: 2 }}>
          {t('JD quá ngắn để sinh tiêu chí có nghĩa. Cần thêm ít nhất {0} ký tự nữa.', String(50 - jdText.trim().length))}
        </Alert>}
        {jdBusy && <Stack direction="row" spacing={1} alignItems="center" sx={{ mt: 2 }}>
          <CircularProgress size={20} /><Typography variant="body2">{t('AI đang đọc JD và đề xuất tiêu chí...')}</Typography>
        </Stack>}
      </DialogContent>
      <DialogActions>
        <Button onClick={() => setJdOpen(false)} disabled={jdBusy}>{t('Hủy')}</Button>
        <Button variant="contained" onClick={runJdSuggest} disabled={jdBusy || !jdFamily || jdText.trim().length < 50}>
          {jdBusy ? t('Đang sinh…') : t('Sinh nháp')}
        </Button>
      </DialogActions>
    </Dialog>
  </Box>;
}
