/**
 * `requirement_spec` — logic dùng chung cho hai trang soạn tiêu chí.
 *
 * Vì sao phải là một chỗ: trang thư viện rubric và trang chi tiết vị trí cùng
 * gửi `requirement_spec` lên cùng một schema. Chép logic hai nơi thì có ngày
 * lệch nhau, và lỗi sẽ nằm ở trang ít được thử hơn — đúng chuyện đã xảy ra:
 * trang rubric sửa rồi, trang vị trí vẫn 422.
 *
 * Hợp đồng với backend (``app/schemas/criteria.py``, chốt theo audit M1):
 *
 * * ``YEARS`` cần ``min_years``
 * * ``DEGREE`` cần ``required_degree_level``
 * * ``LANGUAGE`` cần ngôn ngữ hoặc một mức (IELTS/TOEIC/CEFR/định tính)
 * * ``SKILL``/``CERTIFICATION`` cần ít nhất một thuật ngữ
 *
 * Schema cố ý chặt: tiêu chí "số năm kinh nghiệm" mà không nêu bao nhiêu năm là
 * tiêu chí chưa có tiêu chuẩn, cho lưu là để nó lọt vào chấm điểm. Nên phần
 * việc của giao diện là **gửi đủ**, không phải thuyết phục backend nới lỏng.
 */

export const SPEC_KINDS = ['SKILL', 'YEARS', 'DEGREE', 'CERTIFICATION', 'LANGUAGE'] as const;
export type SpecKind = (typeof SPEC_KINDS)[number];

/** Nhãn người đọc được. HR không bao giờ thấy mã ``SKILL``/``YEARS``. */
export const KIND_LABEL: Record<SpecKind, string> = {
  SKILL: 'Kỹ năng hoặc công nghệ',
  YEARS: 'Số năm kinh nghiệm',
  DEGREE: 'Bằng cấp',
  CERTIFICATION: 'Chứng chỉ',
  LANGUAGE: 'Ngoại ngữ',
};

/** Chấp nhận cả object có kiểu riêng (``RequirementSpec``) lẫn JSONB thô. */
export type RawSpec = object | null | undefined;

/** Đọc ``kind`` từ JSONB tự do; spec hỏng hoặc lạ thì coi như SKILL. */
export function specKindOf(spec: RawSpec): SpecKind {
  const asRecord = (spec && typeof spec === 'object' ? spec : {}) as Record<string, unknown>;
  const raw = typeof asRecord.kind === 'string' ? (asRecord.kind as string).toUpperCase() : '';
  return (SPEC_KINDS as readonly string[]).includes(raw) ? (raw as SpecKind) : 'SKILL';
}

/** Tách chuỗi từ khoá " a, ,b " thành mảng sạch. */
export function splitKeywords(value: string): string[] {
  return value.split(',').map(k => k.trim()).filter(Boolean);
}

/**
 * Dựng ``requirement_spec`` gửi lên máy chủ.
 *
 * ``terms`` luôn được điền từ từ khoá, hoặc từ tên tiêu chí nếu chưa có từ khoá
 * nào — vì schema từ chối ``SKILL`` không có thuật ngữ, và từ chối cả spec rỗng.
 *
 * Ngưỡng của loại KHÔNG được chọn bị xoá: để ``min_years`` lại trên một tiêu
 * chí ``SKILL`` là dữ liệu chết, người đọc sau không biết nó còn hiệu lực không.
 */
export function buildSpec(
  spec: RawSpec,
  keywords: string,
  fallbackName = '',
): Record<string, unknown> | null {
  const base = (spec && typeof spec === 'object' ? spec : null) as Record<string, unknown> | null;
  const kind = specKindOf(base);
  const terms = splitKeywords(keywords);
  const effectiveTerms = terms.length > 0 ? terms : (fallbackName.trim() ? [fallbackName.trim()] : []);

  // Chưa có spec và cũng không có gì để dò: gửi null để máy tự suy từ chữ,
  // thay vì gửi một spec rỗng mà schema sẽ từ chối.
  if (!base && effectiveTerms.length === 0) return null;
  if (!base) return { kind, terms: effectiveTerms };

  const out: Record<string, unknown> = { ...base, kind };
  out.terms = effectiveTerms;
  if (kind !== 'YEARS') out.min_years = null;
  if (kind !== 'DEGREE') out.required_degree_level = null;
  if (kind !== 'LANGUAGE') {
    out.required_languages = [];
    out.required_ielts = null;
    out.required_toeic = null;
    out.required_cefr = null;
    out.required_language_rank = null;
  }
  return out;
}

/** Đổi loại: giữ mọi khoá khác, xoá ngưỡng của loại không còn được chọn. */
export function withKind(spec: RawSpec, next: SpecKind): Record<string, unknown> {
  const base: Record<string, unknown> = { ...((spec && typeof spec === 'object' ? spec : {}) as Record<string, unknown>), kind: next };
  if (next !== 'YEARS') base.min_years = null;
  if (next !== 'DEGREE') base.required_degree_level = null;
  if (next !== 'LANGUAGE') {
    base.required_languages = [];
    base.required_ielts = null;
    base.required_toeic = null;
    base.required_cefr = null;
    base.required_language_rank = null;
  }
  return base;
}

/**
 * Kiểm trước khi gửi: tiêu chí này còn thiếu gì để schema chấp nhận?
 *
 * Trả về câu mô tả **bằng ngôn ngữ HR hiểu** — không phải tên trường kỹ thuật.
 * Nhờ vậy HR biết phải sửa ô nào thay vì nhận một câu 422 chung chung.
 */
export function specProblem(spec: Record<string, unknown> | null | undefined): string | null {
  if (!spec) return null;
  const kind = specKindOf(spec);
  const has = (v: unknown) => v !== null && v !== undefined && v !== '';
  if (kind === 'YEARS' && !has(spec.min_years)) {
    return 'chưa có số năm tối thiểu — điền ô "Số năm tối thiểu", hoặc đổi cách so khớp sang "Kỹ năng hoặc công nghệ".';
  }
  if (kind === 'DEGREE' && !has(spec.required_degree_level)) {
    return 'chưa chọn bậc bằng tối thiểu.';
  }
  if (kind === 'LANGUAGE') {
    const languages = Array.isArray(spec.required_languages) ? spec.required_languages : [];
    const hasLevel = languages.length > 0
      || has(spec.required_ielts) || has(spec.required_toeic)
      || has(spec.required_cefr) || has(spec.required_language_rank);
    if (!hasLevel) {
      return 'chưa nêu ngôn ngữ nào, cũng chưa có mức IELTS/TOEIC/CEFR tối thiểu.';
    }
  }
  if ((kind === 'SKILL' || kind === 'CERTIFICATION')) {
    const terms = Array.isArray(spec.terms) ? spec.terms : [];
    if (terms.length === 0) {
      return 'chưa có thuật ngữ nào để máy dò — điền ô "Thuật ngữ bằng chứng".';
    }
  }
  return null;
}


/**
 * Ép kết quả về đúng kiểu mà ``api.ts`` khai báo (``RequirementSpec``).
 *
 * Kiểu đó đòi ``kind``/``terms``/``required_languages`` luôn có — đúng với thứ
 * ta gửi lên sau ``buildSpec``, nhưng ``Record<string, unknown>`` thì TypeScript
 * không tự biết. Ép ở đây, một chỗ, thay vì rải ``as`` khắp hai trang.
 */
export function asApiSpec(
  spec: Record<string, unknown> | null,
): import('@/types').RequirementSpec | null {
  if (!spec) return null;
  return {
    kind: specKindOf(spec),
    terms: Array.isArray(spec.terms) ? (spec.terms as string[]) : [],
    min_years: (spec.min_years as number | null | undefined) ?? null,
    required_degree_level: (spec.required_degree_level as number | null | undefined) ?? null,
    required_languages: Array.isArray(spec.required_languages) ? (spec.required_languages as string[]) : [],
    required_ielts: (spec.required_ielts as number | null | undefined) ?? null,
    required_toeic: (spec.required_toeic as number | null | undefined) ?? null,
    required_cefr: (spec.required_cefr as import('@/types').RequirementSpec['required_cefr']) ?? null,
    required_language_rank: (spec.required_language_rank as number | null | undefined) ?? null,
  };
}
