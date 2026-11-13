'use client';

import { useI18n } from '@/i18n/I18nProvider';

import * as React from 'react';
import { useCallback, useEffect, useState } from 'react';
import {
  Alert, Box, Button, Card, CardContent, Checkbox, Chip, CircularProgress, FormControl, FormControlLabel, Grid,
  InputLabel, MenuItem, Select, Tab, Tabs, TextField, Typography,
} from '@mui/material';
import RefreshIcon from '@mui/icons-material/Refresh';
import { adminApi } from '@/lib/api';
import { moveRoute } from '@/lib/orderedRoutes';
import { formatUsd } from '@/lib/llmCost';
import LlmOperations from './LlmOperations';

type WorkerHealth = { pending: number; processing: number; stale_heartbeat: number; long_running: number; failed_24h: number; recoveries_24h: number; oldest_pending_seconds: number };
type RuntimeConfig = { config_id?: string | null; provider: string; provider_name?: string | null; model_name: string; api_base?: string | null; temperature_default: number; external_api_allowed: boolean; api_key_configured?: boolean; api_key_hint?: string | null; fallbacks?: RuntimeConfig[]; input_price_per_million_usd?: number | string | null; output_price_per_million_usd?: number | string | null };
type LlmUsageSummary = { attempts: number; priced_attempts: number; unpriced_attempts: number; estimated_usd: string | number | null; first_observed_at: string | null; by_config: { config_id: string | null; model_name: string; provider: string; estimated_usd: string | number | null; unpriced_attempts: number }[] };
type AIOptions = { models: string[]; endpoints: string[]; external_api_allowed: boolean; custom_openai_compatible?: { api_key_encryption_configured: boolean } };
type ConfigVersion = RuntimeConfig & { config_id: string; status: string; created_at: string };
type ConnectionTestResult = { ok: boolean; status_code?: number | null; latency_ms?: number; provider_name?: string | null; model?: string; provider_returned_model?: string | null; error_code?: string; message: string };
type AuxDraft = { config_id: string; service_type: 'BGE' | 'LTR'; config: Record<string, string | number | null>; api_key_configured: boolean; api_key_hint?: string | null; created_at: string };
type LtrModel = { model_version: string; status: string; artifact_sha256?: string | null; data_sha256?: string | null; metrics?: Record<string, unknown> };
type LtrSelection = { selection_id: string; mode: string; model_version?: string | null; artifact_sha256?: string | null };

const normalizeBaseUrl = (value: string) => value.trim().replace(/\/+$/, '').replace(/\/chat\/completions$/, '');

export default function AdminPage() {
  const { t, dateLocale } = useI18n();
  const [section, setSection] = useState('llm');
  const [config, setConfig] = useState<RuntimeConfig | null>(null);
  const [source, setSource] = useState('environment');
  const [allowed, setAllowed] = useState(false);
  const [options, setOptions] = useState<AIOptions | null>(null);
  const [versions, setVersions] = useState<ConfigVersion[]>([]);
  const [health, setHealth] = useState<WorkerHealth | null>(null);
  const [provider, setProvider] = useState('local');
  const [providerName, setProviderName] = useState('');
  const [model, setModel] = useState('');
  const [endpoint, setEndpoint] = useState('');
  const [customModel, setCustomModel] = useState('');
  const [customBaseUrl, setCustomBaseUrl] = useState('');
  const [apiKey, setApiKey] = useState('');
  const [temperature, setTemperature] = useState('0.1');
  const [inputPrice, setInputPrice] = useState('');
  const [outputPrice, setOutputPrice] = useState('');
  const [editingConfig, setEditingConfig] = useState<RuntimeConfig | null>(null);
  const [usage, setUsage] = useState<LlmUsageSummary | null>(null);
  const [fallbackIds, setFallbackIds] = useState<string[]>([]);
  const [fallbackApproved, setFallbackApproved] = useState(false);
  const [auxDrafts, setAuxDrafts] = useState<AuxDraft[]>([]);
  const [ltrModels, setLtrModels] = useState<LtrModel[]>([]);
  const [bgeProvider, setBgeProvider] = useState('Cloudflare Workers AI');
  const [bgeModel, setBgeModel] = useState('@cf/baai/bge-m3');
  const [bgeBase, setBgeBase] = useState('');
  const [bgeKey, setBgeKey] = useState('');
  const [bgeIndex, setBgeIndex] = useState('bge-index-v1');
  const [bgeRouteIds, setBgeRouteIds] = useState<string[]>([]);
  const [bgeApproved, setBgeApproved] = useState(false);
  const [bgeRuntimeEnabled, setBgeRuntimeEnabled] = useState(false);
  const [rerankerSelection, setRerankerSelection] = useState<{ bge_config_id: string } | null>(null);
  const [rerankerDraft, setRerankerDraft] = useState('');
  const [rerankerApproved, setRerankerApproved] = useState(false);
  const [bgeConfigured, setBgeConfigured] = useState(false);
  const [ltrVersion, setLtrVersion] = useState('');
  const [ltrSelection, setLtrSelection] = useState<LtrSelection | null>(null);
  const [ltrEnabled, setLtrEnabled] = useState(false);
  const [ltrActiveApproved, setLtrActiveApproved] = useState(false);
  const [ltrReason, setLtrReason] = useState('');
  const [ltrShadowApproved, setLtrShadowApproved] = useState(false);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [testing, setTesting] = useState(false);
  const [testResult, setTestResult] = useState<ConnectionTestResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);

  const isCompatible = provider === 'compatible';
  const apiKeyEncryptionReady = options?.custom_openai_compatible?.api_key_encryption_configured ?? false;
  const activeKeyReusable = isCompatible && editingConfig?.provider === 'compatible'
    && Boolean(editingConfig.config_id && editingConfig.api_key_configured) && normalizeBaseUrl(customBaseUrl) !== ''
    && normalizeBaseUrl(customBaseUrl) === normalizeBaseUrl(editingConfig.api_base || '');

  const load = useCallback(async (sync: { llm?: boolean; bge?: boolean } = { llm: true, bge: true }) => {
    try {
      setLoading(true); setError(null);
      const [active, worker, permitted, history, auxiliary, models, bgeSet, ltrSelected, reranker, usageSummary] = await Promise.all([
        adminApi.getActiveAiConfig(), adminApi.getWorkerHealth(), adminApi.getAiOptions(), adminApi.listAiConfigs(),
        adminApi.listAuxiliaryDrafts(), adminApi.listLtrModels(), adminApi.getBgeRouteSet(), adminApi.getLtrSelection(), adminApi.getReranker(), adminApi.getLlmUsageSummary(),
      ]);
      setAuxDrafts(auxiliary.data); setLtrModels(models.data); setUsage(usageSummary.data);
      setRerankerSelection(reranker.data.selection); setRerankerApproved(false);
      setLtrSelection(ltrSelected.data.selection);
      setLtrEnabled(Boolean(ltrSelected.data.enabled));
      setLtrActiveApproved(false);
      setLtrShadowApproved(false);
      if (sync.bge) setBgeRouteIds((bgeSet.data.route_set?.routes || []).map((route: { config_id: string }) => route.config_id));
      setBgeRuntimeEnabled(Boolean(bgeSet.data.enabled));
      setBgeConfigured(Boolean(bgeSet.data.route_set?.routes?.length));
      setBgeApproved(false);
      const current: RuntimeConfig = active.data.config;
      setConfig(current); setSource(active.data.source); setAllowed(active.data.allowed_by_this_process);
      setHealth(worker.data); setOptions(permitted.data); setVersions(history.data);
      if (sync.llm) {
        setProvider(current.provider); setProviderName(current.provider_name || '');
        setModel(current.model_name); setEndpoint(current.api_base || '');
        setCustomModel(current.provider === 'compatible' ? current.model_name : '');
        setCustomBaseUrl(current.provider === 'compatible' ? (current.api_base || '') : '');
        setApiKey('');
        setTestResult(null);
        setTemperature(String(current.temperature_default));
        setEditingConfig(current);
        setInputPrice(current.input_price_per_million_usd == null ? '' : String(current.input_price_per_million_usd));
        setOutputPrice(current.output_price_per_million_usd == null ? '' : String(current.output_price_per_million_usd));
        setFallbackIds((current.fallbacks || []).map(item => item.config_id).filter((id): id is string => Boolean(id)));
        setFallbackApproved(false);
      }
    } catch (err: any) {
      setError(err.response?.data?.detail || t("Không thể tải cấu hình AI và trạng thái hàng đợi."));
    } finally { setLoading(false); }
  }, [t]);
  useEffect(() => { load(); }, [load]);

  const editLlm = (item: RuntimeConfig) => {
    setEditingConfig(item); setProvider(item.provider); setProviderName(item.provider_name || '');
    setModel(item.model_name); setEndpoint(item.api_base || '');
    setCustomModel(item.model_name); setCustomBaseUrl(item.api_base || '');
    setTemperature(String(item.temperature_default)); setApiKey(''); setTestResult(null);
    setInputPrice(item.input_price_per_million_usd == null ? '' : String(item.input_price_per_million_usd));
    setOutputPrice(item.output_price_per_million_usd == null ? '' : String(item.output_price_per_million_usd));
    setFallbackIds(item.config_id === config?.config_id ? (config?.fallbacks || []).map(route => route.config_id).filter((id): id is string => Boolean(id)) : []);
    setFallbackApproved(false);
    document.getElementById('llm-editor')?.scrollIntoView({ behavior: 'smooth', block: 'start' });
  };

  const save = async (activateNow: boolean) => {
    const value = Number(temperature);
    const selectedModel = isCompatible ? customModel.trim() : model;
    const selectedEndpoint = isCompatible ? customBaseUrl.trim() : endpoint;
    if (!selectedModel || !selectedEndpoint || !Number.isFinite(value) || value < 0 || value > 1) {
      setError(t(isCompatible
        ? "Vui lòng nhập Base URL, Model và temperature trong khoảng 0–1."
        : "Vui lòng chọn model, endpoint và temperature trong khoảng 0–1.")); return;
    }
    const validPrice = (v: string) => v === '' || (/^\d+(?:\.\d{1,6})?$/.test(v) && Number(v) <= 1000000);
    if (!validPrice(inputPrice) || !validPrice(outputPrice)) { setError(t("Giá phải từ 0 đến 1.000.000, tối đa 6 chữ số thập phân.")); return; }
    if (fallbackIds.length && !fallbackApproved) {
      setError(t("Cần xác nhận từng nhà cung cấp dự phòng đã được phê duyệt xử lý dữ liệu")); return;
    }
    if (isCompatible && !providerName.trim()) {
      setError(t("Vui lòng nhập tên nhà cung cấp cho OpenAI Compatible.")); return;
    }
    if (isCompatible && !apiKey && !activeKeyReusable) {
      setError(t("Vui lòng nhập API Key cho nhà cung cấp OpenAI Compatible.")); return;
    }
    if (isCompatible && apiKey && !apiKeyEncryptionReady) {
      setError(t("Server chưa cấu hình khóa mã hóa để lưu API Key. Quản trị viên hệ thống cần đặt AI_CONFIG_ENCRYPTION_KEY trong môi trường backend rồi khởi động lại.")); return;
    }
    if (activateNow && !window.confirm(t("Kích hoạt cấu hình LLM mới cho các tác vụ tiếp theo?"))) return;
    try {
      setSaving(true); setError(null); setSuccess(null);
      const payload = isCompatible
        ? { provider, provider_name: providerName.trim(), model_name: selectedModel, api_base: selectedEndpoint,
            ...(apiKey ? { api_key: apiKey } : activeKeyReusable ? { reuse_config_id: editingConfig?.config_id } : {}), temperature_default: value, input_price_per_million_usd: inputPrice || null, output_price_per_million_usd: outputPrice || null, fallback_config_ids: fallbackIds, fallback_destinations_approved: fallbackApproved }
        : { provider, model_name: selectedModel, api_base: selectedEndpoint, temperature_default: value, input_price_per_million_usd: inputPrice || null, output_price_per_million_usd: outputPrice || null, fallback_config_ids: fallbackIds, fallback_destinations_approved: fallbackApproved };
      const created = await adminApi.createAiConfig(payload);
      setApiKey('');
      if (activateNow) await adminApi.enableAiConfig(created.data.config_id);
      await load({ llm: true });
      setSuccess(t(activateNow ? "Đã kích hoạt phiên bản cấu hình. Tác vụ đang chạy tiếp tục dùng cấu hình đã ghim." : "Đã lưu cấu hình LLM bản nháp."));
    } catch (err: any) { setError(err.response?.data?.detail || t("Không thể kích hoạt cấu hình AI.")); }
    finally { setSaving(false); }
  };
  const testConnection = async () => {
    if (!isCompatible) return;
    const value = Number(temperature);
    if (!customModel.trim() || !customBaseUrl.trim() || !Number.isFinite(value) || value < 0 || value > 1) {
      setTestResult({ ok: false, message: "Vui lòng nhập Base URL, Model và temperature trong khoảng 0–1." }); return;
    }
    if (!providerName.trim()) {
      setTestResult({ ok: false, message: "Vui lòng nhập tên nhà cung cấp cho OpenAI Compatible." }); return;
    }
    if (!apiKey && !activeKeyReusable) {
      setTestResult({ ok: false, message: "Vui lòng nhập API Key cho nhà cung cấp OpenAI Compatible." }); return;
    }
    try {
      setTesting(true); setTestResult(null); setError(null);
      const response = await adminApi.testAiConnection({
        provider, provider_name: providerName.trim(), model_name: customModel.trim(), api_base: customBaseUrl.trim(),
        ...(apiKey ? { api_key: apiKey } : activeKeyReusable ? { reuse_config_id: editingConfig?.config_id } : {}), temperature_default: value,
      });
      setTestResult(response.data);
    } catch (err: any) {
      setTestResult({ ok: false, message: err.response?.data?.detail || "Không thể kiểm tra kết nối tới nhà cung cấp." });
    } finally { setTesting(false); }
  };
  const saveBgeDraft = async () => {
    try {
      setSaving(true); setError(null); setSuccess(null);
      await adminApi.createBgeDraft({ provider_name: bgeProvider.trim(), model_name: bgeModel.trim(),
        api_base: bgeBase.trim(), ...(bgeKey ? { api_key: bgeKey } : {}), dimension: 1024,
        index_version: bgeIndex.trim(), top_k: 5, min_similarity: 0.35 });
      setBgeKey(''); await load({}); setSuccess(t("Đã lưu bản nháp BGE; runtime chưa thay đổi."));
    } catch (err: any) { setError(err.response?.data?.detail || t("Không thể lưu bản nháp BGE.")); }
    finally { setSaving(false); }
  };
  const saveBgeRouteSet = async () => {
    if (!bgeApproved) { setError(t("Cần xác nhận từng endpoint BGE đã được phê duyệt xử lý dữ liệu")); return; }
    if (!window.confirm(t("Bật BGE có thể gửi dữ liệu ứng viên tới endpoint đã chọn. Tiếp tục?"))) return;
    try {
      setSaving(true); setError(null); setSuccess(null);
      await adminApi.selectBgeRouteSet({ route_config_ids: bgeRouteIds, destinations_approved: bgeApproved });
      await load({ bge: true });
      setSuccess(t("Đã bật BGE trong database; trạng thái thực tế của worker chưa được xác minh."));
    } catch (err: any) { setError(err.response?.data?.detail || t("Không thể chọn chuỗi BGE.")); }
    finally { setSaving(false); }
  };
  const changeReranker = async (enable: boolean) => {
    if (!window.confirm(t(enable ? "Bật reranker sẽ gửi tiêu chí và đoạn CV đến Cloudflare. Tiếp tục?" : "Tắt reranker? Yêu cầu đang chạy có thể vẫn hoàn tất."))) return;
    try {
      setSaving(true); setError(null); setSuccess(null);
      if (enable) await adminApi.enableReranker({ bge_config_id: rerankerDraft, destinations_approved: rerankerApproved });
      else await adminApi.disableReranker();
      await load({});
      setSuccess(t("Đã cập nhật reranker trong database; trạng thái worker chưa được xác minh."));
    } catch (err: any) { setError(err.response?.data?.detail || t("Không thể cập nhật reranker.")); }
    finally { setSaving(false); }
  };

  const disableBge = async () => {
    if (!window.confirm(t("Tắt BGE? Các yêu cầu đang thực hiện có thể vẫn hoàn tất."))) return;
    try {
      setSaving(true); setError(null); setSuccess(null);
      await adminApi.disableBge(); await load({});
      setSuccess(t("Đã tắt BGE trong database; yêu cầu đang chạy có thể vẫn hoàn tất."));
    } catch (err: any) { setError(err.response?.data?.detail || t("Không thể tắt BGE.")); }
    finally { setSaving(false); }
  };
  const reviewLtr = async (version: string, action: 'approve' | 'reject') => {
    try {
      setSaving(true); setError(null); setSuccess(null);
      await adminApi.reviewLtrModel(version, action, ltrReason.trim());
      setLtrReason(''); await load({}); setSuccess(t("Đã ghi nhận đánh giá model LTR."));
    } catch (err: any) { setError(err.response?.data?.detail || t("Không thể đánh giá model LTR.")); }
    finally { setSaving(false); }
  };
  const selectLtr = async (mode: 'OFF' | 'SHADOW' | 'ACTIVE') => {
    const prompt = mode === 'ACTIVE'
      ? t("Bật LTR ACTIVE có thể thay đổi thứ tự ứng viên. Xác nhận triển khai?")
      : mode === 'SHADOW' ? t("Bật LTR SHADOW cho model đã chọn?") : t("Tắt LTR và dùng xếp hạng mặc định?");
    if (!window.confirm(prompt)) return;
    try {
      setSaving(true); setError(null); setSuccess(null);
      await adminApi.selectLtr({ mode, reason: ltrReason.trim(), ...(mode !== 'OFF' ? { model_version: ltrVersion, shadow_approved: ltrShadowApproved, active_approved: ltrActiveApproved } : {}) });
      setLtrReason(''); await load({}); setSuccess(t("Đã ghi lựa chọn LTR trong database; trạng thái worker chưa được xác minh."));
    } catch (err: any) { setError(err.response?.data?.detail || t("Không thể chọn cấu hình LTR.")); }
    finally { setSaving(false); }
  };
  const activate = async (id: string) => {
    if (!window.confirm(t("Kích hoạt cấu hình LLM mới cho các tác vụ tiếp theo?"))) return;
    try {
      setSaving(true); setError(null); setSuccess(null);
      await adminApi.enableAiConfig(id); await load({ llm: true }); setSuccess(t("Đã kích hoạt phiên bản cấu hình."));
    } catch (err: any) { setError(err.response?.data?.detail || t("Không thể kích hoạt cấu hình AI.")); }
    finally { setSaving(false); }
  };

  return (
    <Box>
      <Box sx={{ display: 'flex', justifyContent: 'space-between', flexWrap: 'wrap', gap: 2, mb: 3 }}>
        <Box><Typography variant="h1" sx={{ fontSize: 26, color: '#0A2B57' }}>{t("Quản trị AI")}</Typography>
          <Typography variant="body2" color="text.secondary" sx={{ mt: 0.5 }}>{t("Cấu hình và giám sát dịch vụ xử lý")}</Typography></Box>
        <Button startIcon={<RefreshIcon />} variant="outlined" onClick={() => load()} disabled={loading || saving}>{t("Làm mới")}</Button>
      </Box>
      {error && <Alert severity="error" sx={{ mb: 2 }} onClose={() => setError(null)}>{t(error)}</Alert>}
      {success && <Alert severity="success" sx={{ mb: 2 }} onClose={() => setSuccess(null)}>{t(success)}</Alert>}
      {loading ? <Box sx={{ textAlign: 'center', py: 8 }}><CircularProgress color="secondary" /></Box> : config && options && (
        <>
          <Tabs value={section} onChange={(_, value: string) => setSection(value)} variant="scrollable" scrollButtons="auto" aria-label={t("Nhóm cấu hình AI")} sx={{ mb: 3 }}>
            <Tab id="tab-operations" aria-controls="panel-operations" value="operations" label={t("Vận hành LLM")} /><Tab id="tab-llm" aria-controls="panel-llm" value="llm" label="LLM" /><Tab id="tab-bge" aria-controls="panel-bge" value="bge" label="BGE" /><Tab id="tab-ltr" aria-controls="panel-ltr" value="ltr" label="LTR" /><Tab id="tab-queue" aria-controls="panel-queue" value="queue" label={t("Hàng đợi")} />
          </Tabs>
          <Box role="tabpanel" id="panel-operations" aria-labelledby="tab-operations" hidden={section !== 'operations'}>{section === 'operations' && <LlmOperations />}</Box>
          <Box role="tabpanel" id="panel-llm" aria-labelledby="tab-llm" hidden={section !== 'llm'}>
          <Alert severity="info" sx={{ mb: 3 }}>{isCompatible
            ? t("Với OpenAI Compatible, Admin nhập tên nhà cung cấp, Base URL, API Key và Model. API Key được mã hóa phía server, không hiển thị lại và không ghi vào snapshot tác vụ.")
            : t("Với Local/OpenAI/Azure gateway, chỉ chọn được model và endpoint do người vận hành cho phép; API key dùng từ môi trường/secret manager. Chọn OpenAI Compatible nếu cần nhập tên nhà cung cấp, Base URL, API Key và Model. Chính sách mạng và ALLOW_EXTERNAL_API không thể thay đổi tại đây.")}</Alert>
          {isCompatible && !apiKeyEncryptionReady && <Alert severity="warning" sx={{ mb: 3 }}>{t("Server chưa cấu hình khóa mã hóa để lưu API Key. Quản trị viên hệ thống cần đặt AI_CONFIG_ENCRYPTION_KEY trong môi trường backend rồi khởi động lại.")}</Alert>}
          {isCompatible && !options.external_api_allowed && <Alert severity="warning" sx={{ mb: 3 }}>{t("Endpoint HTTPS bên ngoài chỉ gửi được khi server bật ALLOW_EXTERNAL_API=true. Endpoint nội bộ/loopback vẫn phải qua kiểm tra chính sách mạng.")}</Alert>}
          {!allowed && <Alert severity="warning" sx={{ mb: 3 }}>{t("Cấu hình hiện tại chưa hợp lệ theo chính sách của tiến trình này. Kiểm tra danh sách cho phép và kết nối trước khi dùng AI.")}</Alert>}
          <Alert severity="info" sx={{ mb: 3 }}>{t("Mọi lựa chọn nhà cung cấp chỉ dùng giao thức OpenAI-compatible /chat/completions với Bearer. Không hỗ trợ trực tiếp API Azure riêng (api-key/api-version); cần gateway tương thích đã được phê duyệt.")}</Alert>
          <Grid container spacing={3} alignItems="flex-start">
          <Grid item xs={12} md={8}>
          <Typography variant="h4" sx={{ mb: 1 }}>{t("Nhà cung cấp trong chuỗi hiện tại")}</Typography>
          <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>{t("Các thẻ dưới đây là cấu hình đang lưu, không xác nhận kết nối worker. Chỉnh sửa tạo phiên bản mới; chuỗi chỉ đổi sau khi kích hoạt.")}</Typography>
          {[config, ...(config.fallbacks || [])].map((item, index) => <Card variant="outlined" key={item.config_id || `route-${index}`} sx={{ mb: 2, borderColor: index === 0 ? 'primary.light' : 'divider' }}><CardContent sx={{ p: 2.5 }}>
            <Box sx={{ display: 'flex', justifyContent: 'space-between', gap: 1, flexWrap: 'wrap', alignItems: 'center' }}><Box sx={{ display: 'flex', gap: 1, alignItems: 'center', flexWrap: 'wrap' }}><Chip size="small" color={index === 0 ? 'primary' : 'default'} label={index === 0 ? t("Chính") : `${t("Dự phòng")} ${index}`} /><Typography fontWeight={700}>{item.provider_name || item.provider}</Typography></Box><Button size="small" onClick={() => editLlm(item)}>{t("Tạo phiên bản từ thẻ này")}</Button></Box>
            <Grid container spacing={1} sx={{ mt: 1 }}>
              <Grid item xs={12} sm={6}><Typography variant="caption" color="text.secondary">Model</Typography><Typography variant="body2">{item.model_name}</Typography></Grid>
              <Grid item xs={12} sm={6}><Typography variant="caption" color="text.secondary">Base URL</Typography><Typography variant="body2" sx={{ wordBreak: 'break-all' }}>{item.api_base || '—'}</Typography></Grid>
              <Grid item xs={12} sm={6}><Typography variant="caption" color="text.secondary">API Key</Typography><Typography variant="body2">{item.api_key_configured ? `${t("Đã lưu API key")} ${item.api_key_hint || ''}` : t("Chưa lưu API key")}</Typography></Grid>
              <Grid item xs={12} sm={6}><Typography variant="caption" color="text.secondary">{t("Giá USD / 1 triệu token (vào / ra)")}</Typography><Typography variant="body2">{item.input_price_per_million_usd ?? '—'} / {item.output_price_per_million_usd ?? '—'}</Typography></Grid>
            </Grid>
          </CardContent></Card>)}
          <Card id="llm-editor" variant="outlined" sx={{ mt: 3 }}><CardContent sx={{ p: 3 }}>
            <Typography variant="h4" sx={{ mb: 1 }}>{t("Tạo và kích hoạt phiên bản mới")}</Typography><Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>{t("Lưu bản nháp không thay đổi chuỗi đang chạy. Muốn thay dự phòng, lưu bản nháp rồi chọn nó trong chuỗi của phiên bản chính mới.")}</Typography>
            {!isCompatible && options.endpoints.length === 0 && <Alert severity="warning" sx={{ mb: 2 }}>{t("Chưa có endpoint được phép. Quản trị viên hệ thống cần cấu hình môi trường trước.")}</Alert>}
            <Box sx={{ display: 'flex', gap: 1, flexWrap: 'wrap', mb: 2 }}>
              <Typography variant="caption" color="text.secondary" sx={{ alignSelf: 'center' }}>{t("Mẫu nhanh (chỉ điền Base URL)")}:</Typography>
              {[['OpenAI', 'https://api.openai.com/v1'], ['OpenRouter', 'https://openrouter.ai/api/v1'], ['Groq', 'https://api.groq.com/openai/v1']].map(([name, base]) => <Button key={name} size="small" variant="outlined" onClick={() => { setProvider('compatible'); setProviderName(name); setCustomBaseUrl(base); setCustomModel(''); setApiKey(''); setEditingConfig(null); setTestResult(null); }}>{name}</Button>)}
            </Box>
            <Grid container spacing={2}>
              <Grid item xs={12} sm={6}><FormControl fullWidth size="small"><InputLabel id="ai-provider-label">{t("Nhà cung cấp")}</InputLabel>
                <Select labelId="ai-provider-label" label={t("Nhà cung cấp")} value={provider} onChange={e => {
                  const next = e.target.value; setProvider(next); setTestResult(null);
                  if (next === 'compatible') {
                    setCustomModel(current => current || model);
                    setCustomBaseUrl(current => current || endpoint);
                  } else setApiKey('');
                }}>
                  <MenuItem value="local">Local</MenuItem><MenuItem value="compatible">OpenAI Compatible</MenuItem><MenuItem value="openai">OpenAI-compatible (OpenAI)</MenuItem><MenuItem value="azure">OpenAI-compatible (Azure gateway)</MenuItem>
                </Select></FormControl></Grid>
              {isCompatible ? <>
                <Grid item xs={12} sm={6}><TextField fullWidth size="small" label={t("Tên nhà cung cấp")} value={providerName} onChange={e => { setProviderName(e.target.value); setTestResult(null); }} placeholder={t("Ví dụ: OpenAI, OpenRouter, DeepSeek")} inputProps={{ maxLength: 120 }} /></Grid>
                <Grid item xs={12} sm={7}><TextField fullWidth size="small" label="Base URL" value={customBaseUrl} onChange={e => { setCustomBaseUrl(e.target.value); setTestResult(null); }} placeholder={t("Ví dụ: https://api.openai.com/v1")} autoComplete="url" /></Grid>
                <Grid item xs={12} sm={5}><TextField fullWidth size="small" label="Model" value={customModel} onChange={e => { setCustomModel(e.target.value); setTestResult(null); }} placeholder={t("Nhập model của nhà cung cấp")} autoComplete="off" /></Grid>
                <Grid item xs={12} sm={8}><TextField fullWidth size="small" label="API Key" type="password" value={apiKey} onChange={e => { setApiKey(e.target.value); setTestResult(null); }} placeholder={t("Nhập API key của nhà cung cấp")} autoComplete="new-password"
                  helperText={activeKeyReusable ? t("Đã lưu API key {0}. Để trống để giữ nguyên cho cùng Base URL.", editingConfig?.api_key_hint || '') : t("API key được mã hóa phía server và không hiển thị lại.")} /></Grid>
                <Grid item xs={12} sm={4}><TextField fullWidth size="small" type="number" label="Temperature" value={temperature} onChange={e => { setTemperature(e.target.value); setTestResult(null); }} inputProps={{ min: 0, max: 1, step: 0.05 }} /></Grid>
              </> : <>
                <Grid item xs={12} sm={6}><FormControl fullWidth size="small"><InputLabel id="ai-model-label">{t("Model được phép")}</InputLabel>
                  <Select labelId="ai-model-label" label={t("Model được phép")} value={options.models.includes(model) ? model : ''} onChange={e => setModel(e.target.value)}>
                    {options.models.map(item => <MenuItem key={item} value={item}>{item}</MenuItem>)}
                  </Select></FormControl></Grid>
                <Grid item xs={12} sm={8}><FormControl fullWidth size="small"><InputLabel id="ai-endpoint-label">{t("Endpoint được phép")}</InputLabel>
                  <Select labelId="ai-endpoint-label" label={t("Endpoint được phép")} value={options.endpoints.includes(endpoint) ? endpoint : ''} onChange={e => setEndpoint(e.target.value)}>
                    {options.endpoints.map(item => <MenuItem key={item} value={item}>{item}</MenuItem>)}
                  </Select></FormControl></Grid>
                <Grid item xs={12} sm={4}><TextField fullWidth size="small" type="number" label="Temperature" value={temperature} onChange={e => setTemperature(e.target.value)} inputProps={{ min: 0, max: 1, step: 0.05 }} /></Grid>
              </>}
            </Grid>
            <Grid container spacing={2} sx={{ mt: 0.5 }}>
              <Grid item xs={12} sm={6}><TextField fullWidth size="small" label={t("Giá đầu vào (USD / 1 triệu token)")} value={inputPrice} onChange={e => setInputPrice(e.target.value)} inputProps={{ inputMode: 'decimal' }} placeholder="0.15" /></Grid>
              <Grid item xs={12} sm={6}><TextField fullWidth size="small" label={t("Giá đầu ra (USD / 1 triệu token)")} value={outputPrice} onChange={e => setOutputPrice(e.target.value)} inputProps={{ inputMode: 'decimal' }} placeholder="0.60" /></Grid>
            </Grid>
            <Typography variant="caption" color="text.secondary">{t("Để trống nếu chưa biết; 0 nghĩa là miễn phí. Giá là do Admin nhập và được ghim theo phiên bản.")}</Typography>
            <Box sx={{ mt: 2 }}>
              <Typography variant="subtitle1">{t("LLM dự phòng theo thứ tự")}</Typography>
              <Typography variant="caption" color="text.secondary" display="block">{t("Thêm tối đa 3 phiên bản đã lưu. Dùng nút lên/xuống để đổi thứ tự ưu tiên; chỉ chọn nhà cung cấp được phê duyệt xử lý dữ liệu.")}</Typography>
              {fallbackIds.map((id, index) => {
                const route = versions.find(item => item.config_id === id);
                return <Box key={id} sx={{ display: 'flex', alignItems: 'center', gap: 1, flexWrap: 'wrap', mt: 1 }}>
                  <Typography sx={{ flex: 1, minWidth: 180 }}>{index + 1}. {route ? `${route.provider_name || route.provider} · ${route.model_name}` : id}</Typography>
                  <Button size="small" disabled={saving || index === 0} onClick={() => { setFallbackIds(moveRoute(fallbackIds, index, -1)); setFallbackApproved(false); }} aria-label={`${t("Đưa lên")} ${index + 1}`}>{t("Lên")}</Button>
                  <Button size="small" disabled={saving || index === fallbackIds.length - 1} onClick={() => { setFallbackIds(moveRoute(fallbackIds, index, 1)); setFallbackApproved(false); }} aria-label={`${t("Đưa xuống")} ${index + 1}`}>{t("Xuống")}</Button>
                  <Button size="small" disabled={saving} onClick={() => { setFallbackIds(fallbackIds.filter(item => item !== id)); setFallbackApproved(false); }}>{t("Xóa")}</Button>
                </Box>;
              })}
              <FormControl fullWidth size="small" sx={{ mt: 2 }} disabled={saving || fallbackIds.length >= 3}>
                <InputLabel id="llm-fallback-add-label">{t("Thêm LLM dự phòng")}</InputLabel>
                <Select labelId="llm-fallback-add-label" label={t("Thêm LLM dự phòng")} value="" onChange={event => { if (event.target.value) { setFallbackIds([...fallbackIds, event.target.value]); setFallbackApproved(false); } }}>
                  {versions.filter(item => !fallbackIds.includes(item.config_id)).map(version => <MenuItem key={version.config_id} value={version.config_id}>{version.provider_name || version.provider} · {version.model_name} · {version.api_base || '—'} · {new Date(version.created_at).toLocaleString(dateLocale)} · {version.status}</MenuItem>)}
                </Select>
              </FormControl>
            </Box>
            <Typography variant="caption" color="text.secondary" display="block">{t("Lưu nhà cung cấp mới thành bản nháp trước khi thêm. Chuỗi lồng của các phiên bản dự phòng không được sử dụng.")}</Typography>
            {fallbackIds.length > 0 && <FormControlLabel control={<Checkbox checked={fallbackApproved} onChange={event => setFallbackApproved(event.target.checked)} />} label={t("Tôi xác nhận từng nhà cung cấp dự phòng đã được phê duyệt xử lý dữ liệu trong phạm vi sử dụng.")} />}
            <Typography variant="caption" color="text.secondary" sx={{ display: 'block', mt: 2 }}>{t("Temperature áp dụng khi tạo tiêu chí; trích xuất và đối chiếu CV luôn dùng 0. Các tác vụ đã bắt đầu giữ cấu hình của lần chạy đầu tiên, kể cả khi phục hồi.")}</Typography>
            <Typography variant="caption" color="text.secondary" sx={{ display: 'block', mt: 1 }}>{t("Kết quả đã có không tự đánh giá lại khi đổi cấu hình; pipeline chỉ đánh giá profile và tiêu chí chưa có kết quả hiện hành.")}</Typography>
            {isCompatible && <Typography variant="caption" color="text.secondary" sx={{ display: 'block', mt: 1 }}>{t("Test kết nối chỉ gửi một prompt kiểm tra tối thiểu, không lưu cấu hình và không dùng dữ liệu ứng viên.")}</Typography>}
            <Box sx={{ display: 'flex', gap: 2, flexWrap: 'wrap', mt: 2 }}>
              {isCompatible && <Button variant="outlined" onClick={testConnection} disabled={testing || saving} startIcon={testing ? <CircularProgress size={16} /> : undefined}>{testing ? t("Đang kiểm tra kết nối...") : t("Test kết nối")}</Button>}
              <Button variant="outlined" onClick={() => save(false)} disabled={saving || testing || (!isCompatible && !options.endpoints.length)}>{t("Lưu bản nháp")}</Button>
              <Button variant="contained" onClick={() => save(true)} disabled={saving || testing || (!isCompatible && !options.endpoints.length)}>{t("Tạo và kích hoạt")}</Button>
            </Box>
            {testResult && <Alert severity={testResult.ok ? "success" : "error"} sx={{ mt: 2 }} onClose={() => setTestResult(null)}>
              {t(testResult.message)}{testResult.status_code ? ` · HTTP ${testResult.status_code}` : ''}{testResult.latency_ms != null ? ` · ${testResult.latency_ms} ms` : ''}{testResult.provider_returned_model ? ` · ${testResult.provider_returned_model}` : ''}
            </Alert>}
          </CardContent></Card>
          {versions.length > 0 && <Card variant="outlined" sx={{ mt: 3 }}><CardContent sx={{ p: 3 }}>
            <Typography variant="h4" sx={{ mb: 2 }}>{t("Lịch sử phiên bản")}</Typography>
            {versions.map(version => <Box key={version.config_id} sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 2, flexWrap: 'wrap', py: 1 }}>
              <Box><Typography variant="body2" fontWeight={600}>{version.provider_name ? `${version.provider_name} · ` : ''}{version.model_name} · {t(version.status === "ACTIVE" ? "Đang hoạt động cấu hình" : version.status === "DRAFT" ? "Bản nháp cấu hình" : "Đã tắt cấu hình")}</Typography><Typography variant="caption" color="text.secondary" sx={{ wordBreak: 'break-all' }}>{version.api_base || t("Không có endpoint")} · {new Date(version.created_at).toLocaleString(dateLocale)} · {version.api_key_configured ? `${t("Đã lưu API key")} ${version.api_key_hint || ''}`.trim() : t("Chưa lưu API key")}</Typography></Box>
              <Box><Button size="small" disabled={saving} onClick={() => editLlm(version)}>{t("Tạo phiên bản từ thẻ này")}</Button>{version.status !== 'ACTIVE' && <Button size="small" disabled={saving} onClick={() => activate(version.config_id)}>{t("Kích hoạt")}</Button>}</Box>
            </Box>)}
          </CardContent></Card>}
          </Grid>
          <Grid item xs={12} md={4}>
            <Card variant="outlined" sx={{ position: { md: 'sticky' }, top: { md: 16 } }}><CardContent sx={{ p: 2.5 }}>
              <Typography variant="h6">{t("Chuỗi đang cấu hình")}</Typography>
              <Typography variant="caption" color="text.secondary">{source === 'database' ? t("Phiên bản đã kích hoạt") : t("Mặc định môi trường")} · {t("Chưa xác minh trạng thái từng worker.")}</Typography>
              {[config, ...(config.fallbacks || [])].map((item, index) => <Box key={item.config_id || index} sx={{ mt: 1.5 }}><Typography variant="body2" fontWeight={700}>{index + 1}. {item.provider_name || item.provider}</Typography><Typography variant="caption" color="text.secondary">{item.model_name} · {item.api_key_hint || '—'}</Typography></Box>)}
              <Typography variant="h6" sx={{ mt: 3 }}>{t("Chi phí LLM ước tính")}</Typography>
              <Typography variant="h5" sx={{ mt: 1 }}>{formatUsd(usage?.estimated_usd)}</Typography>
              {usage?.first_observed_at && <Typography variant="caption" color="text.secondary" display="block">{t("Từ lượt ghi nhận đầu tiên")}: {new Date(usage.first_observed_at).toLocaleString(dateLocale)}</Typography>}
              <Typography variant="caption" color="text.secondary" display="block">{t("Lượt có giá")}: {usage?.priced_attempts ?? 0} · {t("Chưa tính được")}: {usage?.unpriced_attempts ?? 0}</Typography>
              {(usage?.by_config || []).slice(0, 5).map((item, index) => <Typography key={item.config_id || `environment-${index}`} variant="caption" display="block" sx={{ mt: 0.5, wordBreak: 'break-word' }}>{versions.find(version => version.config_id === item.config_id)?.provider_name || item.provider} · {item.model_name}: {formatUsd(item.estimated_usd)} · {t("Chưa tính được")}: {item.unpriced_attempts}</Typography>)}
              {(usage?.by_config?.length || 0) > 5 && <Typography variant="caption" color="text.secondary">{t("Chỉ hiển thị 5 nhóm gần nhất; tổng gồm tất cả lượt đã ghi nhận.")}</Typography>}
              <Typography variant="caption" color="text.secondary" display="block" sx={{ mt: 1 }}>{t("Chỉ gồm lượt có token và giá; có thể thiếu retry, lỗi hoặc dữ liệu cũ. Không phải hóa đơn; test kết nối và BGE/reranker không tính.")}</Typography>
            </CardContent></Card>
          </Grid>
          </Grid>
          </Box>
          <Box role="tabpanel" id="panel-bge" aria-labelledby="tab-bge" hidden={section !== 'bge'}>
          <Card variant="outlined" sx={{ mt: 3 }}><CardContent sx={{ p: 3 }}>
            <Typography variant="h4" sx={{ mb: 2 }}>{t("BGE embedding")}</Typography>
            <Alert severity="warning" sx={{ mb: 2 }}>{t("Bản nháp không bật BGE. Bật chuỗi sau khi phê duyệt dữ liệu và endpoint; chính sách mạng vẫn được áp dụng. Yêu cầu đang chạy có thể tiếp tục sau khi tắt.")}</Alert>
            <Typography variant="body2" sx={{ mb: 1 }}>{t("Trạng thái trong database")}: <strong>{bgeRuntimeEnabled ? "ON" : "OFF"}</strong> · {t("Chưa xác minh trạng thái từng worker.")}</Typography>
            {bgeRuntimeEnabled && !bgeConfigured && <Alert severity="error" sx={{ mb: 2 }}>{t("BGE đang bật trong database nhưng chuỗi không khả dụng; worker mới sẽ dùng lexical.")}</Alert>}
            <Grid container spacing={2}>
              <Grid item xs={12} sm={6}><TextField fullWidth size="small" label={t("Nhà cung cấp")} value={bgeProvider} onChange={e => setBgeProvider(e.target.value)} /></Grid>
              <Grid item xs={12} sm={6}><TextField fullWidth size="small" label="Model" value={bgeModel} onChange={e => setBgeModel(e.target.value)} /></Grid>
              <Grid item xs={12}><TextField fullWidth size="small" label="Base URL" value={bgeBase} onChange={e => setBgeBase(e.target.value)} /></Grid>
              <Grid item xs={12} sm={6}><TextField fullWidth size="small" type="password" label="API Key" value={bgeKey} onChange={e => setBgeKey(e.target.value)} autoComplete="new-password" /></Grid>
              <Grid item xs={12} sm={6}><TextField fullWidth size="small" label="Index version" value={bgeIndex} onChange={e => setBgeIndex(e.target.value)} /></Grid>
            </Grid>
            <Typography variant="caption" color="text.secondary">{t("Mặc định: 1024 chiều, top-k 5, ngưỡng 0.35. API key được mã hóa phía server; không hiển thị lại.")}</Typography>
            <Box sx={{ mt: 1 }}><Button variant="outlined" onClick={saveBgeDraft} disabled={saving || !bgeProvider.trim() || !bgeBase.trim() || !bgeModel.trim() || !bgeIndex.trim()}>{t("Lưu bản nháp BGE")}</Button></Box>
            <Box sx={{ mt: 2 }}>
              <Typography variant="subtitle1">{t("BGE chính và dự phòng theo thứ tự")}</Typography>
              <Typography variant="caption" color="text.secondary" display="block">{t("Danh sách đang chỉnh sửa chỉ áp dụng khi bấm Bật / cập nhật BGE.")}</Typography>
              <Typography variant="caption" color="text.secondary" display="block">{t("Chọn tối đa 4 route: route đầu là chính; các route sau là dự phòng. Mỗi provider dùng vùng cache vector riêng.")}</Typography>
              {bgeRouteIds.map((id, index) => {
                const route = auxDrafts.find(item => item.config_id === id);
                return <Box key={id} sx={{ display: 'flex', alignItems: 'center', gap: 1, flexWrap: 'wrap', mt: 1 }}>
                  <Typography sx={{ flex: 1, minWidth: 180 }}>{index + 1}. {route ? `${route.config.provider_name} · ${route.config.model_name}` : id}</Typography>
                  <Button size="small" disabled={saving || index === 0} onClick={() => { setBgeRouteIds(moveRoute(bgeRouteIds, index, -1)); setBgeApproved(false); }} aria-label={`${t("Đưa lên")} ${index + 1}`}>{t("Lên")}</Button>
                  <Button size="small" disabled={saving || index === bgeRouteIds.length - 1} onClick={() => { setBgeRouteIds(moveRoute(bgeRouteIds, index, 1)); setBgeApproved(false); }} aria-label={`${t("Đưa xuống")} ${index + 1}`}>{t("Xuống")}</Button>
                  <Button size="small" disabled={saving} onClick={() => { setBgeRouteIds(bgeRouteIds.filter(item => item !== id)); setBgeApproved(false); }}>{t("Xóa")}</Button>
                </Box>;
              })}
              <FormControl fullWidth size="small" sx={{ mt: 2 }} disabled={saving || bgeRouteIds.length >= 4}>
                <InputLabel id="bge-route-add-label">{t("Thêm route BGE")}</InputLabel>
                <Select labelId="bge-route-add-label" label={t("Thêm route BGE")} value="" onChange={event => { if (event.target.value) { setBgeRouteIds([...bgeRouteIds, event.target.value]); setBgeApproved(false); } }}>
                  {auxDrafts.filter(item => item.service_type === 'BGE' && !bgeRouteIds.includes(item.config_id)).map(item => <MenuItem key={item.config_id} value={item.config_id}>{String(item.config.provider_name)} · {String(item.config.model_name)} · {new Date(item.created_at).toLocaleString(dateLocale)}</MenuItem>)}
                </Select>
              </FormControl>
            </Box>
            <FormControlLabel control={<Checkbox checked={bgeApproved} onChange={event => setBgeApproved(event.target.checked)} />} label={t("Tôi xác nhận từng endpoint BGE đã được phê duyệt xử lý dữ liệu trong phạm vi sử dụng.")} />
            <Box sx={{ display: 'flex', gap: 1, flexWrap: 'wrap' }}><Button variant="contained" onClick={saveBgeRouteSet} disabled={saving || !bgeRouteIds.length || !bgeApproved}>{t("Bật / cập nhật BGE")}</Button><Button variant="outlined" onClick={disableBge} disabled={saving || !bgeRuntimeEnabled}>{t("Tắt BGE")}</Button></Box>
            <Typography variant="h6" sx={{ mt: 4 }}>Cloudflare evidence reranker</Typography>
            <Alert severity="warning" sx={{ my: 2 }}>{t("Reranker độc lập với BGE và LTR. Dữ liệu đã che thông tin có thể vẫn nhận diện được; chỉ bật sau khi phê duyệt gửi CV/JD đến Cloudflare. Chỉ sắp lại đoạn bằng chứng, không xếp ứng viên.")}</Alert>
            <Typography variant="body2">{t("Trạng thái trong database")}: <strong>{rerankerSelection ? 'ON' : 'OFF'}</strong> · {t("Chưa xác minh trạng thái từng worker.")}</Typography>
            {rerankerSelection && <Typography variant="body2">{t("Tài khoản Cloudflare đang chọn")}: {String(auxDrafts.find(item => item.config_id === rerankerSelection.bge_config_id)?.config.api_base || rerankerSelection.bge_config_id)}</Typography>}
            <Typography variant="caption" display="block">@cf/baai/bge-reranker-base · {t("Chọn bản nháp BGE Cloudflare có API key và Base URL tài khoản /ai/v1. Chính sách ALLOW_EXTERNAL_API vẫn áp dụng.")}</Typography>
            <FormControl fullWidth size="small" sx={{ mt: 2 }}>
              <InputLabel id="reranker-draft-label">{t("Tài khoản Cloudflare")}</InputLabel>
              <Select labelId="reranker-draft-label" label={t("Tài khoản Cloudflare")} value={rerankerDraft} onChange={e => { setRerankerDraft(e.target.value); setRerankerApproved(false); }}>
                {auxDrafts.filter(item => item.service_type === 'BGE' && item.api_key_configured).map(item => <MenuItem key={item.config_id} value={item.config_id}>{String(item.config.provider_name)} · {String(item.config.api_base)} · {new Date(item.created_at).toLocaleString(dateLocale)}</MenuItem>)}
              </Select>
            </FormControl>
            <FormControlLabel control={<Checkbox checked={rerankerApproved} onChange={e => setRerankerApproved(e.target.checked)} />} label={t("Tôi xác nhận Cloudflare reranker đã được phê duyệt xử lý dữ liệu trong phạm vi sử dụng.")} />
            <Box sx={{ display: 'flex', gap: 1, flexWrap: 'wrap' }}><Button variant="contained" onClick={() => changeReranker(true)} disabled={saving || !rerankerDraft || !rerankerApproved}>{t("Bật / cập nhật reranker")}</Button><Button variant="outlined" onClick={() => changeReranker(false)} disabled={saving || !rerankerSelection}>{t("Tắt reranker")}</Button></Box>
          </CardContent></Card>
          </Box>
          <Box role="tabpanel" id="panel-ltr" aria-labelledby="tab-ltr" hidden={section !== 'ltr'}>
          <Card variant="outlined"><CardContent sx={{ p: 3 }}>
            <Typography variant="h6" sx={{ mt: 3, mb: 1 }}>{t("LTR ranking")}</Typography>
            <Typography variant="body2">{t("Trạng thái trong database")}: <strong>{ltrEnabled ? (ltrSelection?.mode || t("Không hợp lệ")) : 'OFF'}</strong> · {ltrEnabled ? ltrSelection?.model_version || '—' : '—'} · {t("Chưa xác minh trạng thái từng worker.")}</Typography>
            {ltrEnabled && (!ltrSelection || ltrSelection.mode === 'OFF') && <Alert severity="error" sx={{ mt: 2 }}>{t("LTR đang bật trong database nhưng selection không hợp lệ; worker mới sẽ dùng OFF.")}</Alert>}
            <Alert severity="warning" sx={{ mt: 2 }}>{t("SHADOW không đổi thứ tự. ACTIVE có thể đổi thứ tự trong cùng nhóm điều kiện bắt buộc; cần model đã duyệt, có ranking SHADOW và phê duyệt chất lượng thực tế. Một ranking SHADOW không chứng minh chất lượng HR gold.")}</Alert>
            <TextField fullWidth size="small" sx={{ mt: 2 }} label={t("Lý do review hoặc lựa chọn LTR")} value={ltrReason} onChange={e => setLtrReason(e.target.value)} inputProps={{ maxLength: 1000 }} />
            {ltrModels.map(item => <Box key={item.model_version} sx={{ mt: 1, wordBreak: 'break-word' }}>
              <Typography variant="body2">{item.model_version} · {item.status} · SHA-256: {item.artifact_sha256 || '—'}</Typography>
              <Typography variant="caption" display="block">{t("Metrics và hash dữ liệu")}: {JSON.stringify(item.metrics || {})} · {item.data_sha256 || '—'}</Typography>
              {item.status === 'DRAFT' && <Box><Button size="small" disabled={saving || !ltrReason.trim()} onClick={() => reviewLtr(item.model_version, 'approve')}>{t("Phê duyệt model")}</Button><Button size="small" disabled={saving || !ltrReason.trim()} onClick={() => reviewLtr(item.model_version, 'reject')}>{t("Từ chối model")}</Button></Box>}
            </Box>)}
            <FormControl fullWidth size="small" sx={{ mt: 2 }}><InputLabel id="ltr-model-label">{t("Model trong registry")}</InputLabel><Select labelId="ltr-model-label" label={t("Model trong registry")} value={ltrVersion} onChange={e => { setLtrVersion(e.target.value); setLtrShadowApproved(false); setLtrActiveApproved(false); }}><MenuItem value="">{t("Không chọn")}</MenuItem>{ltrModels.filter(item => item.status === 'APPROVED').map(item => <MenuItem key={item.model_version} value={item.model_version}>{item.model_version} · {item.status}</MenuItem>)}</Select></FormControl>
            <FormControlLabel control={<Checkbox checked={ltrShadowApproved} onChange={e => setLtrShadowApproved(e.target.checked)} />} label={t("Tôi xác nhận phạm vi SHADOW đã được phê duyệt.")} />
            <FormControlLabel control={<Checkbox checked={ltrActiveApproved} onChange={e => setLtrActiveApproved(e.target.checked)} />} label={t("Tôi xác nhận chất lượng thực tế, phạm vi ACTIVE và kế hoạch rollback đã được phê duyệt.")} />
            <Box sx={{ display: 'flex', gap: 1, flexWrap: 'wrap' }}><Button variant="outlined" onClick={() => selectLtr('SHADOW')} disabled={saving || !ltrVersion || !ltrReason.trim() || !ltrShadowApproved}>{t("Bật LTR SHADOW")}</Button><Button variant="contained" color="warning" onClick={() => selectLtr('ACTIVE')} disabled={saving || !ltrVersion || !ltrReason.trim() || !ltrActiveApproved}>{t("Bật LTR ACTIVE")}</Button><Button variant="outlined" onClick={() => selectLtr('OFF')} disabled={saving || !ltrReason.trim()}>{t("Tắt LTR")}</Button></Box>
            {auxDrafts.length > 0 && <Box sx={{ mt: 2 }}><Typography variant="subtitle2">{t("Bản nháp gần đây")}</Typography>{auxDrafts.slice(0, 6).map(draft => <Typography key={draft.config_id} variant="caption" display="block">{draft.service_type} · {String(draft.config.model_name || draft.config.model_version || draft.config.mode || '')} · {new Date(draft.created_at).toLocaleString(dateLocale)} {draft.api_key_configured ? `· ${t("Đã lưu API key")} ${draft.api_key_hint || ''}` : ''}</Typography>)}</Box>}
          </CardContent></Card>
          </Box>
          <Box role="tabpanel" id="panel-queue" aria-labelledby="tab-queue" hidden={section !== 'queue'}>
          {health && <Card variant="outlined" sx={{ mt: 3 }}><CardContent sx={{ p: 3 }}>
            <Typography variant="h4" sx={{ mb: 2 }}>{t("Giám sát hàng đợi xử lý")}</Typography>
            <Grid container spacing={2}>
              {[
                [t("Đang chờ"), health.pending], [t("Đang xử lý"), health.processing],
                [t("Mất heartbeat trên 2 phút"), health.stale_heartbeat], [t("Chạy trên 30 phút"), health.long_running],
                [t("Thất bại trong 24 giờ"), health.failed_24h], [t("Phục hồi trong 24 giờ"), health.recoveries_24h],
                [t("Tác vụ chờ lâu nhất (giây)"), health.oldest_pending_seconds],
              ].map(([label, value]) => <Grid item xs={6} sm={4} key={label}>
                <Typography variant="caption" color="text.secondary">{label}</Typography>
                <Typography variant="body1" sx={{ fontWeight: 600 }}>{value}</Typography>
              </Grid>)}
            </Grid>
            <Typography variant="caption" color="text.secondary" sx={{ display: 'block', mt: 2 }}>{t("Đây là chỉ số hàng đợi, không chứng minh worker còn sống. Không tự đặt lại tác vụ chỉ vì heartbeat cũ; xem runbook vận hành.")}</Typography>
          </CardContent></Card>}
          </Box>
          <Alert severity="warning" sx={{ mt: 3 }}>{t("Chỉ sử dụng dịch vụ AI đã được phê duyệt để xử lý dữ liệu ứng viên. Che dữ liệu nhạy cảm chỉ là biện pháp giảm thiểu, không bảo đảm ẩn danh hoàn toàn.")}</Alert>
        </>
      )}
    </Box>
  );
}
