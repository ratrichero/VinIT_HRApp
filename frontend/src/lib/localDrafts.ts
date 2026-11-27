/**
 * Draft storage for work that is not saved to the server yet.
 *
 * Scorecard comments are internal assessment notes, so drafts are:
 * - scoped to the share (and therefore to one reviewer's browser/profile),
 * - expired after DRAFT_TTL_MS,
 * - purged when access is lost, the draft is discarded, or the work is saved.
 *
 * `localStorage` is not encrypted. Anyone who can use this browser profile can
 * read the drafts, so they must never hold CV content, contact details, tokens
 * or anything beyond what the reviewer typed into the scorecard.
 */

export const DRAFT_PREFIX = 'hra:draft:';
export const DRAFT_TTL_MS = 7 * 24 * 60 * 60 * 1000;

type Envelope<T> = { saved_at: number; data: T };

function defaultStorage(): Storage | null {
  try {
    return typeof window !== 'undefined' ? window.localStorage : null;
  } catch {
    // Private mode or a blocked storage origin: drafts degrade to memory only.
    return null;
  }
}

/** True when this browser will actually keep drafts (not private mode / blocked). */
export function draftsStorable(storage: Storage | null = defaultStorage()): boolean {
  if (!storage) return false;
  try {
    const probe = `${DRAFT_PREFIX}probe`;
    storage.setItem(probe, '1');
    storage.removeItem(probe);
    return true;
  } catch {
    return false;
  }
}

export function writeDraft<T>(key: string, data: T, now = Date.now(), storage: Storage | null = defaultStorage()): boolean {
  if (!storage) return false;
  try {
    storage.setItem(key, JSON.stringify({ saved_at: now, data } satisfies Envelope<T>));
    return true;
  } catch {
    // Quota or serialisation errors must never break the review screen.
    return false;
  }
}

export function readDraft<T>(key: string, now = Date.now(), storage: Storage | null = defaultStorage()): T | null {
  if (!storage) return null;
  try {
    const raw = storage.getItem(key);
    if (!raw) return null;
    const parsed = JSON.parse(raw) as Envelope<T>;
    if (!parsed || typeof parsed.saved_at !== 'number' || !('data' in parsed)) {
      storage.removeItem(key);
      return null;
    }
    if (now - parsed.saved_at > DRAFT_TTL_MS || now < parsed.saved_at) {
      storage.removeItem(key);
      return null;
    }
    return parsed.data;
  } catch {
    return null;
  }
}

export function removeDraft(key: string, storage: Storage | null = defaultStorage()): void {
  try {
    storage?.removeItem(key);
  } catch {
    // Nothing to do: a leftover key only wastes a little space until it expires.
  }
}

export function purgeDrafts(prefix: string, storage: Storage | null = defaultStorage()): number {
  if (!storage) return 0;
  let removed = 0;
  try {
    const keys: string[] = [];
    for (let index = 0; index < storage.length; index += 1) {
      const key = storage.key(index);
      if (key && key.startsWith(prefix)) keys.push(key);
    }
    keys.forEach(key => {
      storage.removeItem(key);
      removed += 1;
    });
  } catch {
    return removed;
  }
  return removed;
}

export function scorecardDraftKey(shareId: string, scorecardId: string): string {
  return `${DRAFT_PREFIX}scorecard:${shareId}:${scorecardId}`;
}

export function shareFeedbackDraftKey(shareId: string): string {
  return `${DRAFT_PREFIX}share-feedback:${shareId}`;
}

/**
 * Nháp rubric mẫu đang soạn ở `/rubrics`, chưa lưu lên máy chủ.
 *
 * Vì sao cần: nút "Sinh từ JD" (cả hai đường) chỉ **điền biểu mẫu** — không
 * lưu gì. HR dán một JD dài, chờ AI, sửa vài tiêu chí rồi lỡ đóng tab là mất
 * toàn bộ công đoạn đó, không có dấu vết nào trên máy chủ để khôi phục.
 *
 * Chỉ chứa nội dung rubric HR đang viết: tên, mô tả, trọng số. Không chứa JD
 * gốc, không chứa thông tin ứng viên. `localStorage` không mã hoá nên ranh giới
 * này phải giữ.
 */
export function rubricDraftKey(): string {
  // Một khoá duy nhất, không tách theo template_version_id: HR chỉ soạn một
  // bản tại một thời điểm. Tách khoá theo phiên bản thì có thể tồn tại hai nháp
  // cùng lúc, và lúc khôi phục phải đoán cái nào mới hơn — đoán sai là mất bản
  // mới. Bản nháp thuộc phiên bản nào được ghi bên trong chính nó.
  //
  // `:v2` vì hình dạng nháp đã đổi: trước nâng cấp, nháp lưu trường `specs`
  // (chuỗi JSON của requirement_spec). Nay spec nằm trong chính từng item. Nháp
  // `:v1` khôi phục vào code mới sẽ mất phần spec — mà mất spec thì DEGREE thành
  // SKILL, tức âm thầm đổi cách chấm. Tăng phiên bản để nháp cũ bị **bỏ**, không
  // phải đọc sai: mất một bản nháp chưa lưu là phiền, đổi sai cách chấm là lỗi.
  return `${DRAFT_PREFIX}rubric:pending:v2`;
}

/** Xoá mọi nháp rubric đang soạn (dùng khi đã lưu, hoặc khi bắt đầu bộ khác). */
export function purgeRubricDrafts(storage: Storage | null = defaultStorage()): number {
  return purgeDrafts(`${DRAFT_PREFIX}rubric:`, storage);
}

/** Everything this reviewer typed for one share, used on access loss and sign-out. */
export function purgeShareDrafts(shareId: string, storage: Storage | null = defaultStorage()): number {
  return purgeDrafts(`${DRAFT_PREFIX}scorecard:${shareId}:`, storage) + purgeDrafts(`${DRAFT_PREFIX}share-feedback:${shareId}`, storage);
}
