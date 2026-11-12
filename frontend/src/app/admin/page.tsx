'use client';

import { useI18n } from '@/i18n/I18nProvider';

import * as React from 'react';
import { useCallback, useEffect, useState } from 'react';
import {
  Alert, Box, Button, Card, CardContent, Checkbox, Chip, CircularProgress, FormControl, FormControlLabel, Grid,
  InputLabel, MenuItem, Select, TextField, Typography,
} from '@mui/material';
import RefreshIcon from '@mui/icons-material/Refresh';
import { adminApi } from '@/lib/api';

type WorkerHealth = { pending: number; processing: number; stale_heartbeat: number; long_running: number; failed_24h: number; recoveries_24h: number; oldest_pending_seconds: number };
type RuntimeConfig = { config_id?: string | null; provider: string; provider_name?: string | null; model_name: string; api_base?: string | null; temperature_default: number; external_api_allowed: boolean; api_key_configured?: boolean; api_key_hint?: string | null; fallbacks?: RuntimeConfig[] };
type AIOptions = { models: string[]; endpoints: string[]; external_api_allowed: boolean; custom_openai_compatible?: { api_key_encryption_configured: boolean } };
type ConfigVersion = RuntimeConfig & { config_id: string; status: string; created_at: string };
type ConnectionTestResult = { ok: boolean; status_code?: number | null; latency_ms?: number; provider_name?: string | null; model?: string; provider_returned_model?: string | null; error_code?: string; message: string };
type AuxDraft = { config_id: string; service_type: 'BGE' | 'LTR'; config: Record<string, string | number | null>; api_key_configured: boolean; api_key_hint?: string | null; created_at: string };
type LtrModel = { model_version: string; status: string; artifact_sha256?: string | null; data_sha256?: string | null; metrics?: Record<string, unknown> };
type LtrSelection = { selection_id: string; mode: string; model_version?: string | null; artifact_sha256?: string | null };

const normalizeBaseUrl = (value: string) => value.trim().replace(/\/+$/, '').replace(/\/chat\/completions$/, '');

export default function AdminPage() {
  const { t, dateLocale } = useI18n();
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
  const [ltrMode, setLtrMode] = useState('OFF');
  const [ltrVersion, setLtrVersion] = useState('');
  const [ltrSelection, setLtrSelection] = useState<LtrSelection | null>(null);
  const [ltrManagedHint, setLtrManagedHint] = useState(false);
  const [ltrDraftId, setLtrDraftId] = useState('');
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
  const activeKeyReusable = isCompatible && source === 'database' && config?.provider === 'compatible'
    && Boolean(config.api_key_configured) && normalizeBaseUrl(customBaseUrl) !== ''
    && normalizeBaseUrl(customBaseUrl) === normalizeBaseUrl(config.api_base || '');

  const load = useCallback(async () => {
    try {
      setLoading(true); setError(null);
      const [active, worker, permitted, history, auxiliary, models, bgeSet, ltrSelected] = await Promise.all([
        adminApi.getActiveAiConfig(), adminApi.getWorkerHealth(), adminApi.getAiOptions(), adminApi.listAiConfigs(),
        adminApi.listAuxiliaryDrafts(), adminApi.listLtrModels(), adminApi.getBgeRouteSet(), adminApi.getLtrSelection(),
      ]);
      setAuxDrafts(auxiliary.data); setLtrModels(models.data);
      setLtrSelection(ltrSelected.data.selection);
      setLtrManagedHint(Boolean(ltrSelected.data.managed_allowed && ltrSelected.data.worker_mode_hint === 'SHADOW'));
      setLtrShadowApproved(false);
      setBgeRouteIds((bgeSet.data.route_set?.routes || []).map((route: { config_id: string }) => route.config_id));
      setBgeRuntimeEnabled(Boolean(bgeSet.data.semantic_enabled && bgeSet.data.managed_routing_allowed));
      setBgeApproved(false);
      const current: RuntimeConfig = active.data.config;
      setConfig(current); setSource(active.data.source); setAllowed(active.data.allowed_by_this_process);
      setHealth(worker.data); setOptions(permitted.data); setVersions(history.data);
      setProvider(current.provider); setProviderName(current.provider_name || '');
      setModel(current.model_name); setEndpoint(current.api_base || '');
      setCustomModel(current.provider === 'compatible' ? current.model_name : '');
      setCustomBaseUrl(current.provider === 'compatible' ? (current.api_base || '') : '');
      setApiKey('');
      setTestResult(null);
      setTemperature(String(current.temperature_default));
      setFallbackIds((current.fallbacks || []).map(item => item.config_id).filter((id): id is string => Boolean(id)));
      setFallbackApproved(false);
    } catch (err: any) {
      setError(err.response?.data?.detail || t("Không thể tải cấu hình AI và trạng thái hàng đợi."));
    } finally { setLoading(false); }
  }, [t]);
  useEffect(() => { load(); }, [load]);

  const save = async (activateNow: boolean) => {
    const value = Number(temperature);
    const selectedModel = isCompatible ? customModel.trim() : model;
    const selectedEndpoint = isCompatible ? customBaseUrl.trim() : endpoint;
    if (!selectedModel || !selectedEndpoint || !Number.isFinite(value) || value < 0 || value > 1) {
      setError(t(isCompatible
        ? "Vui lòng nhập Base URL, Model và temperature trong khoảng 0–1."
        : "Vui lòng chọn model, endpoint và temperature trong khoảng 0–1.")); return;
    }
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
    try {
      setSaving(true); setError(null); setSuccess(null);
      const payload = isCompatible
        ? { provider, provider_name: providerName.trim(), model_name: selectedModel, api_base: selectedEndpoint,
            ...(apiKey ? { api_key: apiKey } : {}), temperature_default: value, fallback_config_ids: fallbackIds, fallback_destinations_approved: fallbackApproved }
        : { provider, model_name: selectedModel, api_base: selectedEndpoint, temperature_default: value, fallback_config_ids: fallbackIds, fallback_destinations_approved: fallbackApproved };
      const created = await adminApi.createAiConfig(payload);
      setApiKey('');
      if (activateNow) await adminApi.enableAiConfig(created.data.config_id);
      await load();
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
        ...(apiKey ? { api_key: apiKey } : {}), temperature_default: value,
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
      setBgeKey(''); await load(); setSuccess(t("Đã lưu bản nháp BGE; runtime chưa thay đổi."));
    } catch (err: any) { setError(err.response?.data?.detail || t("Không thể lưu bản nháp BGE.")); }
    finally { setSaving(false); }
  };
  const saveBgeRouteSet = async () => {
    if (!bgeApproved) { setError(t("Cần xác nhận từng endpoint BGE đã được phê duyệt xử lý dữ liệu")); return; }
    try {
      setSaving(true); setError(null); setSuccess(null);
      const result = await adminApi.selectBgeRouteSet({ route_config_ids: bgeRouteIds, destinations_approved: bgeApproved });
      await load();
      setSuccess(t(result.data.runtime_enabled ? "Đã chọn chuỗi BGE; kiểm tra cấu hình từng worker trước khi sử dụng." : "Đã chọn chuỗi BGE; tiến trình API báo runtime đang bị khóa bởi cấu hình môi trường."));
    } catch (err: any) { setError(err.response?.data?.detail || t("Không thể chọn chuỗi BGE.")); }
    finally { setSaving(false); }
  };
  const saveLtrDraft = async () => {
    try {
      setSaving(true); setError(null); setSuccess(null);
      await adminApi.createLtrDraft({ mode: ltrMode, model_version: ltrVersion || null });
      await load(); setSuccess(t("Đã lưu bản nháp LTR; runtime chưa thay đổi."));
    } catch (err: any) { setError(err.response?.data?.detail || t("Không thể lưu bản nháp LTR.")); }
    finally { setSaving(false); }
  };
  const reviewLtr = async (version: string, action: 'approve' | 'reject') => {
    try {
      setSaving(true); setError(null); setSuccess(null);
      await adminApi.reviewLtrModel(version, action, ltrReason.trim());
      setLtrReason(''); await load(); setSuccess(t("Đã ghi nhận đánh giá model LTR."));
    } catch (err: any) { setError(err.response?.data?.detail || t("Không thể đánh giá model LTR.")); }
    finally { setSaving(false); }
  };
  const selectLtr = async (mode: 'OFF' | 'SHADOW') => {
    try {
      setSaving(true); setError(null); setSuccess(null);
      await adminApi.selectLtr({ mode, reason: ltrReason.trim(), ...(mode === 'SHADOW' ? { draft_config_id: ltrDraftId, shadow_approved: ltrShadowApproved } : {}) });
      setLtrReason(''); await load(); setSuccess(t("Đã ghi lựa chọn LTR; kiểm tra cấu hình từng worker."));
    } catch (err: any) { setError(err.response?.data?.detail || t("Không thể chọn cấu hình LTR.")); }
    finally { setSaving(false); }
  };
  const activate = async (id: string) => {
    try {
      setSaving(true); setError(null); setSuccess(null);
      await adminApi.enableAiConfig(id); await load(); setSuccess(t("Đã kích hoạt phiên bản cấu hình."));
    } catch (err: any) { setError(err.response?.data?.detail || t("Không thể kích hoạt cấu hình AI.")); }
    finally { setSaving(false); }
  };

  return (
    <Box>
      <Box sx={{ display: 'flex', justifyContent: 'space-between', flexWrap: 'wrap', gap: 2, mb: 3 }}>
        <Box><Typography variant="h1" sx={{ fontSize: 26, color: '#0A2B57' }}>{t("Quản trị AI")}</Typography>
          <Typography variant="body2" color="text.secondary" sx={{ mt: 0.5 }}>{t("Cấu hình và giám sát dịch vụ xử lý")}</Typography></Box>
        <Button startIcon={<RefreshIcon />} variant="outlined" onClick={load} disabled={loading || saving}>{t("Làm mới")}</Button>
      </Box>
      {error && <Alert severity="error" sx={{ mb: 2 }} onClose={() => setError(null)}>{t(error)}</Alert>}
      {success && <Alert severity="success" sx={{ mb: 2 }} onClose={() => setSuccess(null)}>{t(success)}</Alert>}
      {loading ? <Box sx={{ textAlign: 'center', py: 8 }}><CircularProgress color="secondary" /></Box> : config && options && (
        <>
          <Alert severity="info" sx={{ mb: 3 }}>{isCompatible
            ? t("Với OpenAI Compatible, Admin nhập tên nhà cung cấp, Base URL, API Key và Model. API Key được mã hóa phía server, không hiển thị lại và không ghi vào snapshot tác vụ.")
            : t("Với Local/OpenAI/Azure gateway, chỉ chọn được model và endpoint do người vận hành cho phép; API key dùng từ môi trường/secret manager. Chọn OpenAI Compatible nếu cần nhập tên nhà cung cấp, Base URL, API Key và Model. Chính sách mạng và ALLOW_EXTERNAL_API không thể thay đổi tại đây.")}</Alert>
          {isCompatible && !apiKeyEncryptionReady && <Alert severity="warning" sx={{ mb: 3 }}>{t("Server chưa cấu hình khóa mã hóa để lưu API Key. Quản trị viên hệ thống cần đặt AI_CONFIG_ENCRYPTION_KEY trong môi trường backend rồi khởi động lại.")}</Alert>}
          {isCompatible && !options.external_api_allowed && <Alert severity="warning" sx={{ mb: 3 }}>{t("Endpoint HTTPS bên ngoài chỉ gửi được khi server bật ALLOW_EXTERNAL_API=true. Endpoint nội bộ/loopback vẫn phải qua kiểm tra chính sách mạng.")}</Alert>}
          {!allowed && <Alert severity="warning" sx={{ mb: 3 }}>{t("Cấu hình hiện tại chưa hợp lệ theo chính sách của tiến trình này. Kiểm tra danh sách cho phép và kết nối trước khi dùng AI.")}</Alert>}
          <Alert severity="info" sx={{ mb: 3 }}>{t("Mọi lựa chọn nhà cung cấp chỉ dùng giao thức OpenAI-compatible /chat/completions với Bearer. Không hỗ trợ trực tiếp API Azure riêng (api-key/api-version); cần gateway tương thích đã được phê duyệt.")}</Alert>
          <Card variant="outlined"><CardContent sx={{ p: 3 }}>
            <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, mb: 3 }}><Typography variant="h4">{t("Cấu hình đang sử dụng")}</Typography><Chip size="small" label={source === 'database' ? t("Phiên bản đã kích hoạt") : t("Mặc định môi trường")} /></Box>
            <Grid container spacing={3}>
              {[
                [t("Nhà cung cấp"), config.provider_name ? `${config.provider_name} (${config.provider})` : config.provider],
                ['Model', config.model_name], ['API endpoint', config.api_base || t("Chưa cấu hình")],
                ['API Key', config.api_key_configured ? `${t("Đã cấu hình")} ${config.api_key_hint || ''}`.trim() : t("Chưa cấu hình")],
                [t("Temperature tạo tiêu chí"), String(config.temperature_default)], [t("API bên ngoài"), config.external_api_allowed ? t("Môi trường cho phép") : t("Không cho phép")],
              ].map(([label, value]) => <Grid item xs={12} sm={6} key={label}>
                <Typography variant="caption" color="text.secondary">{label}</Typography>
                <Typography variant="body1" sx={{ mt: 0.5, wordBreak: 'break-word', fontWeight: 600 }}>{value}</Typography>
              </Grid>)}
            </Grid>
          </CardContent></Card>
          <Card variant="outlined" sx={{ mt: 3 }}><CardContent sx={{ p: 3 }}>
            <Typography variant="h4" sx={{ mb: 2 }}>{t("Tạo và kích hoạt phiên bản mới")}</Typography>
            {!isCompatible && options.endpoints.length === 0 && <Alert severity="warning" sx={{ mb: 2 }}>{t("Chưa có endpoint được phép. Quản trị viên hệ thống cần cấu hình môi trường trước.")}</Alert>}
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
                  helperText={activeKeyReusable ? t("Đã lưu API key {0}. Để trống để giữ nguyên cho cùng Base URL.", config.api_key_hint || '') : t("API key được mã hóa phía server và không hiển thị lại.")} /></Grid>
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
            <FormControl fullWidth size="small" sx={{ mt: 2 }}>
              <InputLabel id="llm-fallback-label">{t("LLM dự phòng theo thứ tự")}</InputLabel>
              <Select labelId="llm-fallback-label" multiple label={t("LLM dự phòng theo thứ tự")}
                value={fallbackIds} onChange={event => {
                  const value = event.target.value;
                  const next = typeof value === 'string' ? value.split(',') : value;
                  if (next.length <= 3) { setFallbackIds(next); setFallbackApproved(false); }
                }}
                renderValue={selected => selected.map((id, index) => {
                  const route = versions.find(item => item.config_id === id);
                  return `${index + 1}. ${route?.provider_name || route?.provider || id} / ${route?.model_name || ''}`;
                }).join(' → ')}>
                {versions.map(version => <MenuItem key={version.config_id} value={version.config_id}>
                  {version.provider_name || version.provider} · {version.model_name} · {version.status}
                </MenuItem>)}
              </Select>
            </FormControl>
            <Typography variant="caption" color="text.secondary" sx={{ display: 'block', mt: 1 }}>{t("Chọn tối đa 3 cấu hình LLM đã lưu theo thứ tự. Lưu bản nháp trước để thêm nhà cung cấp mới. Mỗi fallback chỉ dùng cấu hình được chọn, không dùng chuỗi lồng của nó. Chỉ cấu hình các nhà cung cấp đã được phê duyệt xử lý dữ liệu.")}</Typography>
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
          <Card variant="outlined" sx={{ mt: 3 }}><CardContent sx={{ p: 3 }}>
            <Typography variant="h4" sx={{ mb: 2 }}>{t("Cấu hình BGE và LTR — bản nháp")}</Typography>
            <Alert severity="warning" sx={{ mb: 2 }}>{t("Bản nháp chỉ lưu thông tin và không tự bật BGE/LTR. Chọn chuỗi BGE riêng; worker còn chịu các khóa môi trường. Không thay thế phê duyệt privacy, chất lượng và triển khai. BGE không phải LLM chat; LTR dùng model registry.")}</Alert>
            <Typography variant="h6" sx={{ mb: 1 }}>{t("BGE embedding")}</Typography>
            <Grid container spacing={2}>
              <Grid item xs={12} sm={6}><TextField fullWidth size="small" label={t("Nhà cung cấp")} value={bgeProvider} onChange={e => setBgeProvider(e.target.value)} /></Grid>
              <Grid item xs={12} sm={6}><TextField fullWidth size="small" label="Model" value={bgeModel} onChange={e => setBgeModel(e.target.value)} /></Grid>
              <Grid item xs={12}><TextField fullWidth size="small" label="Base URL" value={bgeBase} onChange={e => setBgeBase(e.target.value)} /></Grid>
              <Grid item xs={12} sm={6}><TextField fullWidth size="small" type="password" label="API Key" value={bgeKey} onChange={e => setBgeKey(e.target.value)} autoComplete="new-password" /></Grid>
              <Grid item xs={12} sm={6}><TextField fullWidth size="small" label="Index version" value={bgeIndex} onChange={e => setBgeIndex(e.target.value)} /></Grid>
            </Grid>
            <Typography variant="caption" color="text.secondary">{t("Mặc định: 1024 chiều, top-k 5, ngưỡng 0.35. API key được mã hóa phía server; không hiển thị lại.")}</Typography>
            <Box sx={{ mt: 1 }}><Button variant="outlined" onClick={saveBgeDraft} disabled={saving || !bgeProvider.trim() || !bgeBase.trim() || !bgeModel.trim() || !bgeIndex.trim()}>{t("Lưu bản nháp BGE")}</Button></Box>
            <FormControl fullWidth size="small" sx={{ mt: 2 }}>
              <InputLabel id="bge-routes-label">{t("BGE chính và dự phòng theo thứ tự")}</InputLabel>
              <Select labelId="bge-routes-label" multiple label={t("BGE chính và dự phòng theo thứ tự")} value={bgeRouteIds}
                onChange={event => { const value = event.target.value; const next = typeof value === 'string' ? value.split(',') : value; if (next.length <= 4) { setBgeRouteIds(next); setBgeApproved(false); } }}
                renderValue={selected => selected.map((id, index) => { const item = auxDrafts.find(d => d.config_id === id); return `${index + 1}. ${item?.config.provider_name || id} / ${item?.config.model_name || ''}`; }).join(' → ')}>
                {auxDrafts.filter(draft => draft.service_type === 'BGE').map(draft => <MenuItem key={draft.config_id} value={draft.config_id}>{String(draft.config.provider_name)} · {String(draft.config.model_name)} · {new Date(draft.created_at).toLocaleString(dateLocale)}</MenuItem>)}
              </Select>
            </FormControl>
            <Typography variant="caption" color="text.secondary" display="block">{t("Chọn tối đa 4 route: route đầu là chính; các route sau là dự phòng. Mỗi provider dùng vùng cache vector riêng.")}</Typography>
            <FormControlLabel control={<Checkbox checked={bgeApproved} onChange={event => setBgeApproved(event.target.checked)} />} label={t("Tôi xác nhận từng endpoint BGE đã được phê duyệt xử lý dữ liệu trong phạm vi sử dụng.")} />
            <Box><Button variant="outlined" onClick={saveBgeRouteSet} disabled={saving || !bgeRouteIds.length || !bgeApproved}>{t("Chọn chuỗi BGE")}</Button></Box>
            <Typography variant="caption" color="text.secondary">{t(bgeRuntimeEnabled ? "Tiến trình API cho phép BGE quản trị; cần kiểm tra từng worker." : "Tiến trình API báo BGE quản trị đang bị khóa bởi cấu hình môi trường.")}</Typography>
            <Typography variant="h6" sx={{ mt: 3, mb: 1 }}>{t("LTR ranking")}</Typography>
            <Grid container spacing={2}>
              <Grid item xs={12} sm={4}><FormControl fullWidth size="small"><InputLabel id="ltr-mode-label">{t("Chế độ dự kiến")}</InputLabel><Select labelId="ltr-mode-label" label={t("Chế độ dự kiến")} value={ltrMode} onChange={e => setLtrMode(e.target.value)}><MenuItem value="OFF">OFF</MenuItem><MenuItem value="SHADOW">SHADOW</MenuItem><MenuItem value="ACTIVE">ACTIVE</MenuItem></Select></FormControl></Grid>
              <Grid item xs={12} sm={8}><FormControl fullWidth size="small"><InputLabel id="ltr-model-label">{t("Model trong registry")}</InputLabel><Select labelId="ltr-model-label" label={t("Model trong registry")} value={ltrVersion} onChange={e => setLtrVersion(e.target.value)}><MenuItem value="">{t("Không chọn")}</MenuItem>{ltrModels.map(item => <MenuItem key={item.model_version} value={item.model_version}>{item.model_version} · {item.status}</MenuItem>)}</Select></FormControl></Grid>
            </Grid>
            <Box sx={{ mt: 1 }}><Button variant="outlined" onClick={saveLtrDraft} disabled={saving || (ltrMode !== 'OFF' && !ltrVersion)}>{t("Lưu bản nháp LTR")}</Button></Box>
            <Alert severity="info" sx={{ mt: 2 }}>{t("Model phải được review và đạt gate trước khi chọn SHADOW. Chưa hỗ trợ chọn ACTIVE từ đây; các khóa môi trường của từng worker vẫn quyết định runtime. OFF này không tắt cấu hình LTR legacy. Metrics tự khai không thay thế HR gold hoặc phê duyệt pilot.")}</Alert>
            <TextField fullWidth size="small" sx={{ mt: 2 }} label={t("Lý do review hoặc lựa chọn LTR")} value={ltrReason} onChange={e => setLtrReason(e.target.value)} inputProps={{ maxLength: 1000 }} />
            {ltrModels.map(item => <Box key={item.model_version} sx={{ mt: 1, wordBreak: 'break-word' }}>
              <Typography variant="body2">{item.model_version} · {item.status} · SHA-256: {item.artifact_sha256 || '—'}</Typography>
              <Typography variant="caption" display="block">{t("Metrics và hash dữ liệu")}: {JSON.stringify(item.metrics || {})} · {item.data_sha256 || '—'}</Typography>
              {item.status === 'DRAFT' && <Box><Button size="small" disabled={saving || !ltrReason.trim()} onClick={() => reviewLtr(item.model_version, 'approve')}>{t("Phê duyệt model")}</Button><Button size="small" disabled={saving || !ltrReason.trim()} onClick={() => reviewLtr(item.model_version, 'reject')}>{t("Từ chối model")}</Button></Box>}
            </Box>)}
            <FormControl fullWidth size="small" sx={{ mt: 2 }}><InputLabel id="ltr-draft-selection">{t("Draft LTR SHADOW")}</InputLabel><Select labelId="ltr-draft-selection" label={t("Draft LTR SHADOW")} value={ltrDraftId} onChange={e => { setLtrDraftId(e.target.value); setLtrShadowApproved(false); }}><MenuItem value="">{t("Không chọn")}</MenuItem>{auxDrafts.filter(d => d.service_type === 'LTR' && d.config.mode === 'SHADOW').map(d => <MenuItem key={d.config_id} value={d.config_id}>{String(d.config.model_version)} · {new Date(d.created_at).toLocaleString(dateLocale)}</MenuItem>)}</Select></FormControl>
            <FormControlLabel control={<Checkbox checked={ltrShadowApproved} onChange={e => setLtrShadowApproved(e.target.checked)} />} label={t("Tôi xác nhận phạm vi SHADOW đã được phê duyệt.")} />
            <Box><Button variant="outlined" onClick={() => selectLtr('SHADOW')} disabled={saving || !ltrDraftId || !ltrReason.trim() || !ltrShadowApproved}>{t("Chọn LTR SHADOW")}</Button> <Button variant="outlined" onClick={() => selectLtr('OFF')} disabled={saving || !ltrReason.trim()}>{t("Chọn managed LTR OFF")}</Button></Box>
            <Typography variant="caption" display="block">{t("Lựa chọn hiện tại")}: {ltrSelection?.mode || 'OFF'} · {ltrSelection?.model_version || '—'} · {t(ltrManagedHint ? "Tiến trình API cho phép managed SHADOW; cần kiểm tra từng worker." : "Tiến trình API báo managed SHADOW đang bị khóa; cần kiểm tra từng worker.")}</Typography>
            {auxDrafts.length > 0 && <Box sx={{ mt: 2 }}><Typography variant="subtitle2">{t("Bản nháp gần đây")}</Typography>{auxDrafts.slice(0, 6).map(draft => <Typography key={draft.config_id} variant="caption" display="block">{draft.service_type} · {String(draft.config.model_name || draft.config.model_version || draft.config.mode || '')} · {new Date(draft.created_at).toLocaleString(dateLocale)} {draft.api_key_configured ? `· ${t("Đã lưu API key")} ${draft.api_key_hint || ''}` : ''}</Typography>)}</Box>}
          </CardContent></Card>
          {versions.length > 0 && <Card variant="outlined" sx={{ mt: 3 }}><CardContent sx={{ p: 3 }}>
            <Typography variant="h4" sx={{ mb: 2 }}>{t("Lịch sử phiên bản")}</Typography>
            {versions.map(version => <Box key={version.config_id} sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 2, flexWrap: 'wrap', py: 1 }}>
              <Box><Typography variant="body2" fontWeight={600}>{version.provider_name ? `${version.provider_name} · ` : ''}{version.model_name} · {t(version.status === "ACTIVE" ? "Đang hoạt động cấu hình" : version.status === "DRAFT" ? "Bản nháp cấu hình" : "Đã tắt cấu hình")}</Typography><Typography variant="caption" color="text.secondary" sx={{ wordBreak: 'break-all' }}>{version.api_base || t("Không có endpoint")} · {new Date(version.created_at).toLocaleString(dateLocale)} · {version.api_key_configured ? `${t("Đã lưu API key")} ${version.api_key_hint || ''}`.trim() : t("Chưa lưu API key")}</Typography></Box>
              {version.status !== 'ACTIVE' && <Button size="small" disabled={saving} onClick={() => activate(version.config_id)}>{t("Kích hoạt")}</Button>}
            </Box>)}
          </CardContent></Card>}
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
          <Alert severity="warning" sx={{ mt: 3 }}>{t("Chỉ sử dụng dịch vụ AI đã được phê duyệt để xử lý dữ liệu ứng viên. Che dữ liệu nhạy cảm chỉ là biện pháp giảm thiểu, không bảo đảm ẩn danh hoàn toàn.")}</Alert>
        </>
      )}
    </Box>
  );
}
