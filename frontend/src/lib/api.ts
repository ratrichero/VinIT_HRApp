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
  getWorkspace: (id: string) => apiClient.get(`/positions/${id}/workspace`),
  getDuplicateSignals: (id: string) => apiClient.get<DuplicateSignal[]>(`/positions/${id}/duplicate-signals`),
  update: (id: string, data: any) => apiClient.patch(`/positions/${id}`, data),
  getJdVersions: (id: string) => apiClient.get(`/positions/${id}/jd-versions`),
  createJdVersion: (id: string, data: { content_text: string; language_code: string; expected_jd_version_id: string }) => apiClient.post(`/positions/${id}/jd-versions`, data),
};

export const departmentsApi = {
  list: (includeInactive = false) => apiClient.get('/departments', { params: { include_inactive: includeInactive } }),
  create: (data: { name: string; code_format: string; is_active: boolean }) => apiClient.post('/departments', data),
  update: (id: string, data: { name?: string; code_format?: string; is_active?: boolean }) => apiClient.patch(`/departments/${id}`, data),
  delete: (id: string) => apiClient.delete(`/departments/${id}`),
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
  getPrivateNotes: (id: string) => apiClient.get(`/applications/${id}/private-notes`),
  addPrivateNote: (id: string, content: string) => apiClient.post(`/applications/${id}/private-notes`, { content }),
  getStatusEvents: (id: string) => apiClient.get(`/applications/${id}/status-events`),
  reprocess: (id: string) => apiClient.post(`/applications/${id}/reprocess`),
  updateStatus: (id: string, newStatus: string, reason?: string, note?: string) =>
    apiClient.patch(`/applications/${id}/status`, { new_status: newStatus, reason, note }),
  getCvUrl: (id: string) => apiClient.get(`/applications/${id}/cv-download-url`),
  getCvBlob: (id: string) => apiClient.get(`/applications/${id}/cv-file`, { responseType: 'blob' }),
};

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
  testAiConnection: (data: any) => apiClient.post('/admin/ai/test-connection', data),
  createAiConfig: (data: any) => apiClient.post('/admin/ai/config', data),
  enableAiConfig: (id: string) => apiClient.post(`/admin/ai/config/${id}/enable`),
  getActiveAiConfig: () => apiClient.get('/admin/ai/active-config'),
  getWorkerHealth: () => apiClient.get('/admin/worker/health'),
  getAiOptions: () => apiClient.get('/admin/ai/options'),
};
