'use client';

import axios, { AxiosInstance } from 'axios';
import { localizeServerMessage } from '@/i18n/serverMessages';

// The browser always uses the same origin. Next.js proxies /v1 to the backend,
// which also works when the UI is viewed through a remote preview host.
const apiClient: AxiosInstance = axios.create({
  baseURL: '/v1',
  headers: {
    'Content-Type': 'application/json',
  },
});

// Add request interceptor to attach auth token
apiClient.interceptors.request.use((config) => {
  if (typeof window !== 'undefined') {
    const token = localStorage.getItem('hra_access_token');
    if (token) {
      config.headers.Authorization = `Bearer ${token}`;
    }
  }
  return config;
});

// Add response interceptor to handle 401
apiClient.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response?.data?.detail) error.response.data.detail = localizeServerMessage(error.response.data.detail);
    if (error.response?.status === 401 && typeof window !== 'undefined' && !error.config?.url?.includes('/auth/login')) {
      localStorage.removeItem('hra_access_token');
      window.location.href = '/';
    }
    return Promise.reject(error);
  }
);

export default apiClient;

export type DuplicateSignal = {
  signal_id: string; signal_type: string; confidence: number; detector_version: string | null;
  review_status: string; created_at: string;
  application_id_1: string; candidate_name_1: string | null;
  application_id_2: string; candidate_name_2: string | null;
};

// API Functions
export const authApi = {
  login: (email: string, password: string) =>
    apiClient.post('/auth/login', { email, password }),
  me: () => apiClient.get('/auth/me'),
  bootstrapStatus: () => apiClient.get('/auth/bootstrap-status'),
  bootstrap: (data: { email: string; display_name: string; password: string; setup_token: string }) =>
    apiClient.post('/auth/bootstrap', data),
  changePassword: (current_password: string, new_password: string) =>
    apiClient.post('/auth/change-password', { current_password, new_password }),
};

export const positionsApi = {
  list: (status?: string) =>
    apiClient.get('/positions', { params: { status } }),
  listAll: async () => {
    const all: any[] = [];
    for (let page = 1; ; page += 1) {
      const response = await apiClient.get('/positions', { params: { page, page_size: 100 } });
      all.push(...response.data);
      if (response.data.length < 100) return all;
    }
  },
  create: (data: any) => apiClient.post('/positions', data),
  getById: (id: string) => apiClient.get(`/positions/${id}`),
  getHiringManagers: (id: string) => apiClient.get(`/positions/${id}/hiring-managers`),
  changeHiringManager: (id: string, userId: string, expectedAssignments: string[]) => apiClient.put(`/positions/${id}/hiring-manager`, { hiring_manager_user_id: userId, expected_assignments: expectedAssignments }),
  getWorkspace: (id: string) => apiClient.get(`/positions/${id}/workspace`),
  getDuplicateSignals: (id: string) => apiClient.get<DuplicateSignal[]>(`/positions/${id}/duplicate-signals`),
  update: (id: string, data: any) => apiClient.patch(`/positions/${id}`, data),
  getJdVersions: (id: string) => apiClient.get(`/positions/${id}/jd-versions`),
  // language_code KHÔNG còn gửi lên: máy chủ tự dò ngôn ngữ từ nội dung JD.
  createJdVersion: (id: string, data: { content_text: string; expected_jd_version_id: string }) => apiClient.post(`/positions/${id}/jd-versions`, data),
};

export const departmentsApi = {
  list: (includeInactive = false) => apiClient.get('/departments', { params: { include_inactive: includeInactive } }),
  create: (data: { name: string; code_format: string; is_active: boolean }) => apiClient.post('/departments', data),
  update: (id: string, data: { name?: string; code_format?: string; is_active?: boolean }) => apiClient.patch(`/departments/${id}`, data),
  delete: (id: string) => apiClient.delete(`/departments/${id}`),
};

export const jobFamiliesApi = {
  // include_inactive chỉ trả về được với ADMIN — dùng cho màn hình quản trị.
  list: (includeInactive = false) => apiClient.get('/job-families', { params: { include_inactive: includeInactive } }),
  create: (data: { code: string; name: string }) => apiClient.post('/job-families', data),
  // `code` cố ý không có ở đây: nó là khoá nghiệp vụ, đổi mã của nhóm đang dùng
  // là đổi nghĩa dữ liệu cũ. Chỉ đổi tên và trạng thái.
  update: (id: string, data: { name?: string; is_active?: boolean }) => apiClient.patch(`/job-families/${id}`, data),
};

export const criteriaApi = {
  listVersions: (positionId: string) =>
    apiClient.get(`/criteria/position/${positionId}/versions`),
  getById: (id: string) => apiClient.get(`/criteria/${id}`),
  generateDraft: (positionId: string) =>
    apiClient.post(`/criteria/generate/${positionId}`),
  approve: (id: string, action: 'APPROVE' | 'DIRECT_APPROVE' | 'REJECT' | 'REQUEST_CHANGES', comment?: string) =>
    apiClient.post(`/criteria/${id}/approve`, { action, comment }),
  getApprovalEvents: (id: string) => apiClient.get(`/criteria/${id}/approval-events`),
  createItem: (versionId: string, data: { name: string; description: string; category: 'MUST_HAVE' | 'NICE_TO_HAVE'; weight_in_group: number; expected_evidence_keywords: string[]; requirement_spec?: import('@/types').RequirementSpec | null }) =>
    apiClient.post(`/criteria/${versionId}/items`, data),
  updateItem: (versionId: string, itemId: string, data: { name: string; description: string; category: 'MUST_HAVE' | 'NICE_TO_HAVE'; weight_in_group: number; expected_evidence_keywords: string[]; requirement_spec?: import('@/types').RequirementSpec | null }) =>
    apiClient.patch(`/criteria/${versionId}/items/${itemId}`, data),
  deleteItem: (versionId: string, itemId: string) =>
    apiClient.delete(`/criteria/${versionId}/items/${itemId}`),
  // Huỷ bản nháp để mở đường cho rubric mẫu (apply_template từ chối khi đang
  // có bộ tiêu chí DRAFT). Chỉ dùng được với DRAFT chưa từng chấm.
  discardDraft: (versionId: string) =>
    apiClient.delete(`/criteria/${versionId}/draft`),
  updateItemWeights: (versionId: string, items: { criterion_id: string; weight_in_group: number }[]) =>
    apiClient.patch(`/criteria/${versionId}/items/weights`, { items }),
  updateWeights: (versionId: string, mandatory: number, nice: number) =>
    apiClient.patch(`/criteria/${versionId}/weights`, { mandatory_weight_total: mandatory, nice_to_have_weight_total: nice }),
  getApproved: (positionId: string) =>
    apiClient.get(`/criteria/position/${positionId}/approved`),
};

export const applicationsApi = {
  uploadBatch: (positionId: string, files: File[], onProgress?: (percent: number) => void) => {
    const formData = new FormData();
    files.forEach((file) => formData.append('files', file));
    return apiClient.post(`/applications/upload-batch/${positionId}`, formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
      onUploadProgress: (progressEvent) => {
        if (onProgress && progressEvent.total) {
          onProgress(Math.round((progressEvent.loaded * 100) / progressEvent.total));
        }
      },
    });
  },
  list: (positionId: string, params?: any) =>
    apiClient.get('/applications', { params: { position_id: positionId, ...params } }),
  listAll: async (positionId: string) => {
    const all: any[] = [];
    const pageSize = 100;
    for (let page = 1; ; page += 1) {
      const response = await apiClient.get('/applications', {
        params: { position_id: positionId, page, page_size: pageSize },
      });
      all.push(...response.data);
      if (response.data.length < pageSize) return all;
    }
  },
  getById: (id: string) => apiClient.get(`/applications/${id}`),
  getProfile: (id: string) => apiClient.get(`/applications/${id}/profile`),
  updateProfile: (id: string, data: any) => apiClient.put(`/applications/${id}/profile`, data),
  // `signal` để rời hồ sơ là cắt được request đang bay, không chỉ bỏ câu trả lời.
  getPrivateNotes: (id: string, signal?: AbortSignal) => apiClient.get(`/applications/${id}/private-notes`, { signal }),
  assign: (id: string, assignedToUserId: string | null) =>
    apiClient.patch(`/applications/${id}/assignment`, { assigned_to_user_id: assignedToUserId }),
  addPrivateNote: (id: string, content: string, criterionId?: string) =>
    apiClient.post(`/applications/${id}/private-notes`, criterionId ? { content, criterion_id: criterionId } : { content }),
  getStatusEvents: (id: string) => apiClient.get(`/applications/${id}/status-events`),
  reprocess: (id: string) => apiClient.post(`/applications/${id}/reprocess`),
  updateStatus: (id: string, newStatus: string, reason?: string, note?: string) =>
    apiClient.patch(`/applications/${id}/status`, { new_status: newStatus, reason, note }),
  getCvBlob: (id: string) => apiClient.get(`/applications/${id}/cv-file`, { responseType: 'blob' }),
};

/**
 * Loads every application of a position page by page. `listAll` above is a
 * convenience used by pages that do not need progress; the ranking page uses
 * this to show progress and to stop a runaway loop on a broken response.
 */
export async function listAllApplications(
  positionId: string,
  options: { pageSize?: number; onProgress?: (loaded: number) => void; maxPages?: number } = {},
) {
  const { pageSize = 100, onProgress, maxPages = 100 } = options;
  const all: any[] = [];
  for (let page = 1; page <= maxPages; page += 1) {
    const response = await apiClient.get('/applications', { params: { position_id: positionId, page, page_size: pageSize } });
    if (!Array.isArray(response.data)) throw new Error('Unexpected application list response');
    all.push(...response.data);
    onProgress?.(all.length);
    if (response.data.length < pageSize) return all;
  }
  throw new Error('Application list exceeds the supported pagination window');
}

export const operationsApi = {
  getStatus: (id: string) => apiClient.get(`/operations/${id}`),
  getActiveForPosition: (id: string) => apiClient.get(`/operations/position/${id}/active`),
};

export const assessmentsApi = {
  runForPosition: (positionId: string) =>
    apiClient.post(`/assessments/run/${positionId}`),
  getById: (id: string) => apiClient.get(`/assessments/${id}`),
  generateRanking: (positionId: string) =>
    apiClient.post(`/assessments/ranking/generate/${positionId}`),
  getLatestRanking: (positionId: string) =>
    apiClient.get(`/assessments/ranking/latest/${positionId}`),
  // The reviewer's own decision about one criterion. Kept apart from the engine's
  // verification_status: this records a person, a time and a reason.
  reviewCriterionResult: (resultId: string, decision: 'CONFIRMED' | 'REJECTED', comment?: string) =>
    apiClient.post(`/assessments/results/${resultId}/review`, { decision, comment }),
};

export const usersApi = {
  list: (params?: { search?: string; position_id?: string; role?: 'HIRING_MANAGER' }) =>
    apiClient.get('/users', { params }),
};

export const shortlistApi = {
  create: (data: any) => apiClient.post('/shortlist/share', data),
  getSharedWithMe: () => apiClient.get('/shortlist/shared-with-me'),
  getDetail: (id: string) => apiClient.get(`/shortlist/${id}`),
  getPotentialRecipients: (positionId: string) =>
    apiClient.get(`/shortlist/potential-recipients/${positionId}`),
  getShortlistedApps: (positionId: string) =>
    apiClient.get(`/shortlist/shortlisted-applications/${positionId}`),
  addFeedback: (id: string, content: string, applicationId?: string) =>
    apiClient.post(`/shortlist/${id}/feedback`, { content, application_id: applicationId }),
  revoke: (id: string) => apiClient.post(`/shortlist/${id}/revoke`),
};

export const dashboardApi = {
  getSummary: () => apiClient.get('/dashboard/summary'),
  getWorkQueue: () => apiClient.get('/dashboard/work-queue'),
  getPosition: (id: string) => apiClient.get(`/dashboard/position/${id}`),
};

export const adminApi = {
  listUsers: (params: { search?: string; role?: string; account_status?: string; page?: number }) =>
    apiClient.get('/admin/users', { params }),
  createUser: (data: { email: string; display_name: string; password: string; roles: string[] }) =>
    apiClient.post('/admin/users', data),
  updateUser: (id: string, data: { display_name: string; account_status: string; roles: string[] }) =>
    apiClient.patch(`/admin/users/${id}`, data),
  resetUserPassword: (id: string, new_password: string) =>
    apiClient.post(`/admin/users/${id}/reset-password`, { new_password }),
  listAiConfigs: () => apiClient.get('/admin/ai/config'),
  // Ngưỡng nghiệp vụ HR tự đặt (trước đây là hằng số trong backend).
  getSettings: () => apiClient.get('/admin/settings'),
  updateSetting: (key: string, value: number) => apiClient.patch(`/admin/settings/${key}`, { value }),
  getLlmUsageSummary: () => apiClient.get('/admin/ai/usage-summary'),
  getLlmOperations: (params: { days: number; limit: number; offset: number }) => apiClient.get('/admin/ai/operations', { params }),
  testAiConnection: (data: any) => apiClient.post('/admin/ai/test-connection', data),
  createAiConfig: (data: any) => apiClient.post('/admin/ai/config', data),
  enableAiConfig: (id: string) => apiClient.post(`/admin/ai/config/${id}/enable`),
  getActiveAiConfig: () => apiClient.get('/admin/ai/active-config'),
  listAuxiliaryDrafts: () => apiClient.get('/admin/ai/auxiliary-drafts'),
  getReranker: () => apiClient.get('/admin/ai/reranker'),
  enableReranker: (data: { bge_config_id: string; destinations_approved: boolean }) => apiClient.post('/admin/ai/reranker/enable', data),
  disableReranker: () => apiClient.post('/admin/ai/reranker/disable'),
  getBgeRouteSet: () => apiClient.get('/admin/ai/bge/route-set'),
  selectBgeRouteSet: (data: { route_config_ids: string[]; destinations_approved: boolean }) => apiClient.post('/admin/ai/bge/route-set', data),
  disableBge: () => apiClient.post('/admin/ai/bge/disable'),
  createBgeDraft: (data: { provider_name: string; model_name: string; api_base: string; api_key?: string; dimension: 1024; index_version: string; top_k: number; min_similarity: number }) => apiClient.post('/admin/ai/bge/drafts', data),
  createLtrDraft: (data: { mode: string; model_version: string | null }) => apiClient.post('/admin/ai/ltr/drafts', data),
  listLtrModels: () => apiClient.get('/admin/ltr/models'),
  reviewLtrModel: (version: string, action: 'approve' | 'reject', reason: string) => apiClient.post(`/admin/ltr/models/${encodeURIComponent(version)}/${action}`, { reason }),
  getLtrSelection: () => apiClient.get('/admin/ai/ltr/selection'),
  selectLtr: (data: { mode: 'OFF' | 'SHADOW' | 'ACTIVE'; draft_config_id?: string; model_version?: string; reason: string; shadow_approved?: boolean; active_approved?: boolean }) => apiClient.post('/admin/ai/ltr/selection', data),
  getWorkerHealth: () => apiClient.get('/admin/worker/health'),
  getAiOptions: () => apiClient.get('/admin/ai/options'),
};

export const interviewsApi = {
  // `mine` cho màn "Lịch của tôi"; thiếu nó thì phải là HR của vị trí.
  list: (params: { position_id?: string; from_at?: string; to_at?: string; mine?: boolean }) =>
    apiClient.get('/interviews', { params }),
  get: (id: string) => apiClient.get(`/interviews/${id}`),
  create: (data: {
    application_id: string; round_number?: number; starts_at: string; ends_at: string;
    location_kind: 'ONSITE' | 'ONLINE' | 'PHONE'; location_text?: string | null;
    participants: Array<{ user_id: string; participant_role?: 'INTERVIEWER' | 'OBSERVER' }>;
  }) => apiClient.post('/interviews', data),
  update: (id: string, data: Record<string, unknown>) => apiClient.patch(`/interviews/${id}`, data),
  changeStatus: (id: string, status: 'SCHEDULED' | 'DONE' | 'CANCELLED' | 'NO_SHOW') =>
    apiClient.post(`/interviews/${id}/status`, { status }),
  scorecards: (id: string) => apiClient.get(`/interviews/${id}/scorecards`),
  createScorecards: (id: string) => apiClient.post(`/interviews/${id}/scorecards`),
  // Thay toàn bộ danh sách: gửi trạng thái cuối cùng, không gửi hiệu thêm/bớt.
  replaceParticipants: (id: string, participants: Array<{ user_id: string; participant_role: string }>) =>
    apiClient.put(`/interviews/${id}/participants`, { participants }),
};

export const notificationsApi = {
  list: (unreadOnly = false) => apiClient.get('/notifications', { params: unreadOnly ? { unread_only: true } : {} }),
  markRead: (ids: string[] = []) => apiClient.post('/notifications/read', { notification_ids: ids }),
};

export const scorecardsApi = {
  reminders: () => apiClient.get('/scorecards/reminders'),
  reopenHistory: (id: string) => apiClient.get(`/scorecards/${id}/reopen-history`),
  forShare: (shareId: string) => apiClient.get(`/scorecards/share/${shareId}`),
  // Cùng dạng dữ liệu với forShare, nhưng nguồn là buổi phỏng vấn: HR thấy cả
  // buổi, người phỏng vấn chỉ thấy phiếu của mình.
  forInterview: (interviewId: string) => apiClient.get(`/scorecards/interview/${interviewId}`),
  save: (id: string, data: unknown) => apiClient.put(`/scorecards/${id}`, data),
  submit: (id: string, expectedRevision: number) => apiClient.post(`/scorecards/${id}/submit`, { expected_revision: expectedRevision }),
  reopen: (id: string, expectedRevision: number, reason: string) => apiClient.post(`/scorecards/${id}/reopen`, { expected_revision: expectedRevision, reason }),
  setDueDate: (id: string, expectedRevision: number, dueAt: string) => apiClient.put(`/scorecards/${id}/due-date`, { expected_revision: expectedRevision, due_at: dueAt }),
};

export const rubricApi = {
  capabilities: () => apiClient.get('/rubric-library/capabilities'),
  families: () => apiClient.get('/rubric-library/families'),
  templates: () => apiClient.get('/rubric-library/templates'),
  getVersion: (id: string) => apiClient.get(`/rubric-library/versions/${id}`),
  create: (data: unknown) => apiClient.post('/rubric-library/templates', data),
  update: (id: string, data: unknown) => apiClient.put(`/rubric-library/versions/${id}`, data),
  publish: (id: string, revision: number) => apiClient.post(`/rubric-library/versions/${id}/publish`, { expected_revision: revision }),
  clone: (id: string) => apiClient.post(`/rubric-library/versions/${id}/clone`),
  // allowOtherFamily: HR đã thấy nhãn đỏ "(khác nhóm vị trí)" và chủ động chọn.
  // Máy chủ mặc định từ chối áp chéo nhóm để không lỡ tay qua đường API.
  apply: (positionId: string, versionId: string, allowOtherFamily = false) =>
    apiClient.post(`/rubric-library/positions/${positionId}/apply`, { template_version_id: versionId, allow_other_family: allowOtherFamily }),
  // Sinh NHÁP rubric từ JD của một vị trí. Không lưu gì trên máy chủ.
  suggestFromPosition: (positionId: string) => apiClient.post('/rubric-library/suggest-from-position', { position_id: positionId }),
  // Sinh NHÁP rubric từ một JD dán tay, cho HR dựng template trước khi mở vị trí.
  // Cũng không lưu gì trên máy chủ.
  suggestFromJd: (data: { job_family_id: string; jd_text: string; title?: string }) =>
    apiClient.post('/rubric-library/suggest-from-jd', data),
  // Máy sẽ so khớp tiêu chí này theo cách nào. Thuần tính toán, không lưu gì.
  previewSpec: (data: { name: string; description: string; expected_evidence_keywords: string[] }) =>
    apiClient.post('/rubric-library/preview-spec', data),
};

/**
 * Hàng đợi lưu trữ/xoá dữ liệu theo hồ sơ. Chỉ có bốn thao tác người dùng làm
 * được — liệt kê, tạo, xác nhận, huỷ; bước thực thi nằm ngoài màn hình này.
 */
export const retentionApi = {
  listCases: (positionId: string) => apiClient.get(`/retention/positions/${positionId}/cases`),
  generateCases: (positionId: string) => apiClient.post(`/retention/positions/${positionId}/cases/generate`),
  confirmCase: (caseId: string) => apiClient.post(`/retention/cases/${caseId}/confirm`),
  cancelCase: (caseId: string) => apiClient.post(`/retention/cases/${caseId}/cancel`),
};

/** Dọn dữ liệu test. Tách khỏi adminApi để chỗ gọi lộ rõ đây là thao tác phá huỷ. */
export const testDataApi = {
  getScopes: () => apiClient.get('/admin/test-data/scopes'),
  preview: (scopes: string[]) => apiClient.post('/admin/test-data/preview', { scopes }),
  execute: (scopes: string[], confirmation: string) =>
    apiClient.post('/admin/test-data/execute', { scopes, confirmation }),
};
