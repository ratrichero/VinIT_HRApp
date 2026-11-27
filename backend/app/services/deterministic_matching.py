"""Deterministic CV chunking and rule-based criterion matching.

This module deliberately contains no LLM calls.  It converts the redacted CV
text into addressable chunks, derives a small requirement specification from
an approved rubric item, retrieves candidate chunks lexically, and returns a
decision only when a transparent rule is strong enough.  Unresolved criteria
are returned to the caller for the existing strict-schema LLM fallback.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from datetime import date
from typing import Any

from app.core.config import settings

RULES_VERSION = settings.DETERMINISTIC_RULES_VERSION

# Canonical concept -> accepted surface forms.  Keys and values are compared
# after normalize_text(), so accents/case/punctuation do not matter.
TERM_ALIASES: dict[str, tuple[str, ...]] = {
    "javascript": ("javascript", "js"),
    "typescript": ("typescript", "ts"),
    "nodejs": ("nodejs", "node js", "node"),
    "react": ("react", "reactjs", "react js"),
    "angular": ("angular", "angularjs"),
    "vue": ("vue", "vuejs", "vue js"),
    "python": ("python",),
    "java": ("java",),
    "golang": ("golang", "go language"),
    "rust": ("rust",),
    "sql": ("sql", "structured query language"),
    "postgresql": ("postgresql", "postgres"),
    "mysql": ("mysql",),
    "mongodb": ("mongodb", "mongo"),
    "redis": ("redis",),
    "docker": ("docker",),
    "kubernetes": ("kubernetes", "k8s"),
    "aws": ("aws", "amazon web services"),
    "gcp": ("gcp", "google cloud", "google cloud platform"),
    "azure": ("azure", "microsoft azure"),
    "machine learning": ("machine learning", "ml"),
    "deep learning": ("deep learning",),
    "natural language processing": ("natural language processing", "nlp"),
    "data analysis": ("data analysis", "data analytics"),
    "microsoft excel": ("microsoft excel", "excel"),
    "power bi": ("power bi",),
    "testing": ("testing", "test automation", "automated testing", "qa"),
    "selenium": ("selenium",),
    "fastapi": ("fastapi",),
    "django": ("django",),
    "flask": ("flask",),
    "spring": ("spring", "spring boot"),
    "dotnet": ("dotnet", "dot net", "asp net"),
    "csharp": ("csharp", "c sharp"),
    "cplusplus": ("cplusplus", "c plus plus"),
    "english": ("english", "tieng anh"),
    "vietnamese": ("vietnamese", "tieng viet"),
    "japanese": ("japanese", "tieng nhat"),
    "korean": ("korean", "tieng han"),
    "chinese": ("chinese", "tieng trung", "mandarin"),
    "french": ("french", "tieng phap"),
    "german": ("german", "tieng duc"),
}

_ALIAS_TO_CANONICAL: dict[str, str] = {}
for _canonical, _variants in TERM_ALIASES.items():
    _ALIAS_TO_CANONICAL[_canonical] = _canonical
    for _variant in _variants:
        _ALIAS_TO_CANONICAL[_variant] = _canonical

SECTION_HEADINGS: dict[str, str] = {
    "summary": "SUMMARY",
    "professional summary": "SUMMARY",
    "profile": "SUMMARY",
    "objective": "SUMMARY",
    "career objective": "SUMMARY",
    "tom tat": "SUMMARY",
    "muc tieu nghe nghiep": "SUMMARY",
    "work experience": "WORK",
    "professional experience": "WORK",
    "employment history": "WORK",
    "work history": "WORK",
    "career history": "WORK",
    "experience": "WORK",
    "kinh nghiem": "WORK",
    "kinh nghiem lam viec": "WORK",
    "projects": "PROJECT",
    "project experience": "PROJECT",
    "selected projects": "PROJECT",
    "personal projects": "PROJECT",
    "du an": "PROJECT",
    "skills": "SKILL",
    "technical skills": "SKILL",
    "core skills": "SKILL",
    "technical expertise": "SKILL",
    "competencies": "SKILL",
    "core competencies": "SKILL",
    "ky nang": "SKILL",
    "ky nang ky thuat": "SKILL",
    "education": "EDUCATION",
    "academic background": "EDUCATION",
    "educational background": "EDUCATION",
    "hoc van": "EDUCATION",
    "trinh do hoc van": "EDUCATION",
    "certifications": "CERTIFICATION",
    "certification": "CERTIFICATION",
    "certificates": "CERTIFICATION",
    "certificate": "CERTIFICATION",
    "licenses": "CERTIFICATION",
    "chung chi": "CERTIFICATION",
    "languages": "LANGUAGE",
    "language": "LANGUAGE",
    "language skills": "LANGUAGE",
    "language proficiency": "LANGUAGE",
    "ngoai ngu": "LANGUAGE",
}

STOPWORDS = {
    "a", "an", "and", "are", "as", "at", "be", "by", "candidate", "candidates",
    "can", "capability", "degree", "developer", "development", "engineer",
    "experience", "experienced", "for", "from", "in", "including", "is",
    "knowledge", "level", "minimum", "of", "on", "or", "plus", "proficiency",
    "proficient", "proven", "required", "requirement", "requirements", "skill",
    "skills", "strong", "the", "to", "using", "with", "work", "working",
    "year", "years", "nam", "kinh", "nghiem", "ky", "nang", "ung", "vien",
    "co", "trong", "va", "voi", "ve", "cac", "duoc", "cho", "tu",
}

GENERIC_TERMS = {
    "bachelor", "master", "phd", "degree", "university", "college", "school",
    "certificate", "certification", "certified", "license", "language",
    "english", "vietnamese", "japanese", "korean", "chinese", "french", "german",
}

LANGUAGE_NAMES = (
    "english", "vietnamese", "japanese", "korean", "chinese", "mandarin",
    "french", "german", "spanish",
)

# Negation cues are compared after normalize_text(), so Vietnamese cues are
# written without diacritics ("khong" = không, "chua" = chưa).  A keyword
# that only appears after one of these cues is absence evidence, not proof
# that the candidate has the skill.
NEGATION_CUES = (
    "does not", "do not", "did not", "is not", "are not", "was not", "were not",
    "doesnt", "dont", "didnt", "isnt", "arent", "wasnt", "werent", "cannot",
    "never", "without", "no", "not", "none", "lack", "lacking",
    "khong co", "chua co", "khong", "chua", "thieu",
)
CONTRAST_CUES = ("but", "however", "instead", "nhung", "tuy nhien")
# Trailing uncertainty ("Docker remains unclear") is also absence evidence,
# even though the cue appears after the keyword.
UNCERTAIN_CUES = (
    "remain unclear", "remains unclear", "is unclear", "are unclear",
    "still unclear", "chua ro", "khong ro",
)

DEGREE_PATTERNS: tuple[tuple[int, tuple[str, ...]], ...] = (
    (5, ("phd", "ph d", "doctorate", "doctoral degree", "tien si")),
    (4, ("master", "masters", "msc", "mba", "meng", "thac si")),
    # "dai hoc" là cách người Việt viết phổ biến nhất cho bậc đại học, và nó
    # không chứa "cu nhan" nên trước đây bị bỏ sót: "Tốt nghiệp đại học" và
    # "Đại học trở lên" đều rơi về kind=SKILL, tức máy đi dò từ khoá thay vì so
    # bậc bằng. Xếp cùng bậc 3 với "cu nhan"/"bachelor" là đúng nghĩa.
    (3, ("bachelor", "bachelors", "bsc", "beng", "bs", "ba", "cu nhan", "dai hoc")),
    (2, ("associate degree", "cao dang")),
    (1, ("high school", "thpt", "trung hoc pho thong")),
)

#: Cụm báo hiệu yêu cầu học vấn mà không nêu bậc. Tách khỏi ``DEGREE_PATTERNS``
#: vì chúng không cho biết *bậc nào*, chỉ cho biết *đây là tiêu chí học vấn* —
#: đủ để xếp kind=DEGREE (và để HR thấy ô "Bậc bằng tối thiểu" mà điền), nhưng
#: không đủ để tự đoán một con số.
DEGREE_CUES: tuple[str, ...] = (
    "tot nghiep", "bang cap", "hoc van", "trinh do hoc van", "qualification",
)

CEFR_RANK = {"a1": 1, "a2": 2, "b1": 3, "b2": 4, "c1": 5, "c2": 6}
QUALITATIVE_LANGUAGE_RANK = {
    "basic": 1,
    "elementary": 2,
    "intermediate": 3,
    "professional": 4,
    "fluent": 5,
    "advanced": 5,
    "native": 6,
    "bilingual": 6,
}


def normalize_text(value: Any) -> str:
    """Normalize for deterministic lexical matching.

    Accents are removed and punctuation becomes whitespace.  A few symbols
    with semantic value (C++, C#, .NET, Node.js) are expanded first so they
    do not collapse into meaningless one-letter tokens.
    """
    text = str(value or "").lower().replace("đ", "d")
    text = re.sub(r"c\+\+", " cplusplus ", text)
    text = re.sub(r"c#", " csharp ", text)
    text = re.sub(r"(?<![a-z0-9])\.net(?![a-z0-9])", " dotnet ", text)
    text = re.sub(r"node\.js", " nodejs ", text)
    text = re.sub(r"react\.js", " reactjs ", text)
    text = re.sub(r"vue\.js", " vuejs ", text)
    decomposed = unicodedata.normalize("NFKD", text)
    without_accents = "".join(ch for ch in decomposed if not unicodedata.combining(ch))
    alnum = "".join(ch if ch.isalnum() else " " for ch in without_accents)
    return " ".join(alnum.split())


def _accentless_lower(value: Any) -> str:
    """Lowercase and strip accents without touching digits or punctuation.

    Duration phrases such as Vietnamese "5 năm" must still match the
    accent-free cue "nam", while decimal values ("7.5 years") keep their
    separator for the numeric patterns.
    """
    lowered = str(value or "").lower().replace("đ", "d")
    decomposed = unicodedata.normalize("NFKD", lowered)
    return "".join(ch for ch in decomposed if not unicodedata.combining(ch))


def _contains_phrase(normalized_text: str, phrase: str) -> bool:
    phrase = normalize_text(phrase)
    if not phrase:
        return False
    return f" {phrase} " in f" {normalized_text} "


@dataclass(frozen=True)
class DocumentChunk:
    chunk_id: str
    text: str
    page_number: int | None
    char_start: int
    char_end: int
    section: str = "OTHER"

    @property
    def normalized(self) -> str:
        return normalize_text(self.text)

    def to_dict(self) -> dict[str, Any]:
        return {
            "chunk_id": self.chunk_id,
            "text": self.text,
            "page_number": self.page_number,
            "char_start": self.char_start,
            "char_end": self.char_end,
            "section": self.section,
        }


@dataclass(frozen=True)
class TermGroup:
    label: str
    variants: tuple[str, ...]


@dataclass(frozen=True)
class RequirementSpec:
    criterion_id: str
    name: str
    category: str
    kind: str
    terms: tuple[TermGroup, ...] = ()
    min_years: float | None = None
    required_degree_level: int | None = None
    required_languages: tuple[str, ...] = ()
    required_ielts: float | None = None
    required_toeic: int | None = None
    required_cefr: str | None = None
    required_language_rank: int | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "criterion_id": self.criterion_id,
            "name": self.name,
            "category": self.category,
            "kind": self.kind,
            "terms": [
                {"label": term.label, "variants": list(term.variants)}
                for term in self.terms
            ],
            "min_years": self.min_years,
            "required_degree_level": self.required_degree_level,
            "required_languages": list(self.required_languages),
            "required_ielts": self.required_ielts,
            "required_toeic": self.required_toeic,
            "required_cefr": self.required_cefr,
            "required_language_rank": self.required_language_rank,
            "rule_version": RULES_VERSION,
        }


@dataclass
class _Candidate:
    chunk: DocumentChunk
    matched_labels: list[str] = field(default_factory=list)
    coverage: float = 0.0
    strength: float = 0.0


class DeterministicMatchingEngine:
    """Chunk, retrieve and decide measurable criteria without an LLM."""

    VERSION = RULES_VERSION

    # ------------------------------------------------------------------ text
    @staticmethod
    def _detect_heading(line: str) -> str | None:
        cleaned = line.strip().rstrip(":").strip()
        normalized = normalize_text(cleaned)
        if not normalized or len(cleaned) > 80:
            return None
        if normalized in SECTION_HEADINGS:
            return SECTION_HEADINGS[normalized]
        # Short all-caps headings such as "WORK EXPERIENCE" are covered by the
        # exact map above; also accept a known heading followed by a colon.
        for heading, section in SECTION_HEADINGS.items():
            if (normalized == heading or normalized.startswith(heading + " ")) and (
                line.strip().endswith(":") or cleaned.isupper() or len(normalized.split()) <= 4
            ):
                return section
        return None

    def chunk_document(self, text: str, max_chars: int = 900) -> list[DocumentChunk]:
        if max_chars < 100:
            raise ValueError("max_chars must be at least 100")
        source = text or ""
        raw: list[tuple[int, int, int | None, str]] = []
        page_number: int | None = None
        section = "OTHER"
        paragraph: list[tuple[int, int]] = []

        def flush_paragraph() -> None:
            if not paragraph:
                return
            start, end = paragraph[0][0], paragraph[-1][1]
            self._append_split(source, start, end, page_number, section, max_chars, raw)
            paragraph.clear()

        offset = 0
        for line in source.splitlines(True):
            content = line.rstrip("\r\n")
            line_start, line_end = offset, offset + len(content)
            offset += len(line)
            marker = re.fullmatch(r"\s*--- Page (\d+) ---\s*", content)
            if marker:
                flush_paragraph()
                page_number = int(marker.group(1))
                continue
            if not content.strip():
                flush_paragraph()
                continue
            inline_heading = re.match(r"\s*([^:]{2,50}):\s*(.+)$", content)
            if inline_heading and normalize_text(inline_heading.group(1)) in SECTION_HEADINGS:
                flush_paragraph()
                section = SECTION_HEADINGS[normalize_text(inline_heading.group(1))]
                paragraph.append((line_start + inline_heading.start(2), line_end))
                continue
            heading = self._detect_heading(content)
            if heading:
                flush_paragraph()
                section = heading
                continue
            paragraph.append((line_start, line_end))
        flush_paragraph()

        return [
            DocumentChunk(
                chunk_id=f"chunk-{index:04d}",
                text=source[start:end],
                page_number=page,
                char_start=start,
                char_end=end,
                section=chunk_section,
            )
            for index, (start, end, page, chunk_section) in enumerate(raw, start=1)
        ]

    @staticmethod
    def _append_split(
        source: str,
        start: int,
        end: int,
        page_number: int | None,
        section: str,
        max_chars: int,
        out: list[tuple[int, int, int | None, str]],
    ) -> None:
        if end - start <= max_chars:
            if source[start:end].strip():
                out.append((start, end, page_number, section))
            return
        segment = source[start:end]
        sentences = [
            (start + sentence_start, start + sentence_end)
            for sentence_start, sentence_end in DeterministicMatchingEngine._sentence_spans(segment)
        ]
        current: tuple[int, int] | None = None
        for sentence_start, sentence_end in sentences:
            if sentence_end - sentence_start > max_chars:
                if current:
                    out.append((current[0], current[1], page_number, section))
                    current = None
                word_start: int | None = None
                word_end = sentence_start
                for word in re.finditer(r"\S+", source[sentence_start:sentence_end]):
                    ws, we = sentence_start + word.start(), sentence_start + word.end()
                    if word_start is not None and we - word_start > max_chars:
                        out.append((word_start, word_end, page_number, section))
                        word_start = ws
                    if word_start is None:
                        word_start = ws
                    word_end = we
                if word_start is not None:
                    out.append((word_start, word_end, page_number, section))
                continue
            if current and sentence_end - current[0] > max_chars:
                out.append((current[0], current[1], page_number, section))
                current = (sentence_start, sentence_end)
            elif current:
                current = (current[0], sentence_end)
            else:
                current = (sentence_start, sentence_end)
        if current:
            out.append((current[0], current[1], page_number, section))

    # ---------------------------------------------------------- requirements
    @staticmethod
    def _add_term(groups: dict[str, TermGroup], phrase: Any) -> None:
        normalized = normalize_text(phrase)
        if not normalized or len(normalized) < 2:
            return
        canonical = _ALIAS_TO_CANONICAL.get(normalized)
        variants = {normalized}
        if canonical:
            variants.update(TERM_ALIASES[canonical])
            label = canonical
        else:
            # Constituent words of a phrase may help a human read the label,
            # but they must not satisfy the concept by themselves: e.g.
            # "programming" alone is not evidence for "Python programming".
            # Known concepts inside the phrase are added as separate term
            # groups by build_requirement_spec().
            label = normalized
        if label in GENERIC_TERMS and label not in TERM_ALIASES:
            return
        if label in groups:
            merged = tuple(sorted(set(groups[label].variants) | variants))
            groups[label] = TermGroup(label=label, variants=merged)
        else:
            groups[label] = TermGroup(label=label, variants=tuple(sorted(variants)))

    @staticmethod
    def _merge_container_delivery_terms(groups: dict[str, TermGroup]) -> dict[str, TermGroup]:
        """Treat Docker/container/Kubernetes keywords as one delivery concept.

        Rubrics commonly list these as alternative evidence for the same
        criterion ("Docker or containerised deployment").  Keeping them as
        separate denominator terms made a CV that only says "Docker" score
        1/4 coverage and fall through to the LLM.  Merge only when at least
        two of the synonym labels are present, so a Kubernetes-only rubric
        is not silently broadened to Docker.
        """
        synonym_labels = {"docker", "container", "kubernetes"}
        phrase_label = "docker container delivery"
        if len(synonym_labels & set(groups)) < 2 and phrase_label not in groups:
            return groups
        variants = {
            "container", "containers", "containerised", "containerized",
            "containerisation", "containerization", "container delivery",
            "container deployment", "container deployments", "docker",
            "docker container", "docker containers", "docker delivery",
            "docker deployment", "docker deployments", "kubernetes", "k8s",
        }
        for label in synonym_labels | {phrase_label}:
            if label in groups:
                variants.update(groups[label].variants)
        merged: dict[str, TermGroup] = {}
        inserted = False
        for label, group in groups.items():
            if label in synonym_labels or label == phrase_label:
                if not inserted:
                    merged["docker"] = TermGroup(
                        label="docker", variants=tuple(sorted(variants)))
                    inserted = True
                continue
            merged[label] = group
        if not inserted:
            merged["docker"] = TermGroup(label="docker", variants=tuple(sorted(variants)))
        return merged

    @staticmethod
    def _merge_python_framework_terms(groups: dict[str, TermGroup]) -> dict[str, TermGroup]:
        """Treat FastAPI/Django/Flask keywords as one framework concept.

        Rubrics list these frameworks as alternative evidence for Python
        backend work ("FastAPI, Django or Flask").  Keeping them as separate
        denominator terms capped a FastAPI-only CV at 3/5 coverage, blocked
        STRONG_MATCH and pushed otherwise clear CVs to the LLM fallback.
        Merge only when at least two framework labels are present, so a
        rubric that specifically requires Django keeps its exact meaning.
        """
        framework_labels = {"fastapi", "django", "flask"}
        if len(framework_labels & set(groups)) < 2:
            return groups
        variants = {"fastapi", "django", "flask"}
        for label in framework_labels:
            if label in groups:
                variants.update(groups[label].variants)
        merged: dict[str, TermGroup] = {}
        inserted = False
        for label, group in groups.items():
            if label in framework_labels:
                if not inserted:
                    merged["python framework"] = TermGroup(
                        label="python framework", variants=tuple(sorted(variants)))
                    inserted = True
                continue
            merged[label] = group
        if not inserted:
            merged["python framework"] = TermGroup(
                label="python framework", variants=tuple(sorted(variants)))
        return merged

    @staticmethod
    def _parse_min_years(combined: str) -> float | None:
        normalized = _accentless_lower(combined)
        values: list[float] = []
        for match in re.finditer(
            r"(\d+(?:[.,]\d+)?)\s*(?:-|to)\s*(\d+(?:[.,]\d+)?)\s*(?:years?|yrs?|nam)\b",
            normalized,
        ):
            values.append(float(match.group(1).replace(",", ".")))
        for match in re.finditer(
            r"(\d+(?:[.,]\d+)?)\s*\+?\s*(?:years?|yrs?|nam)\b", normalized
        ):
            values.append(float(match.group(1).replace(",", ".")))
        return max(values) if values else None

    @staticmethod
    def _required_degree_level(normalized: str) -> int | None:
        for level, patterns in DEGREE_PATTERNS:
            if any(_contains_phrase(normalized, pattern) for pattern in patterns):
                return level
        if "degree" in normalized.split() or "bang dai hoc" in normalized:
            return 3
        return None

    @staticmethod
    def _degree_level_in(normalized: str) -> int | None:
        levels = [
            level
            for level, patterns in DEGREE_PATTERNS
            if any(_contains_phrase(normalized, pattern) for pattern in patterns)
        ]
        if levels:
            return max(levels)
        if _contains_phrase(normalized, "university") or _contains_phrase(normalized, "college"):
            return 3
        return None

    def build_requirement_spec(self, criterion: dict[str, Any]) -> RequirementSpec:
        inferred = self._infer_requirement_spec(criterion)
        explicit = criterion.get("requirement_spec")
        if not isinstance(explicit, dict) or not explicit:
            return inferred

        kind = str(explicit.get("kind") or inferred.kind).upper()
        if kind not in {"SKILL", "YEARS", "DEGREE", "CERTIFICATION", "LANGUAGE"}:
            kind = inferred.kind
        groups: dict[str, TermGroup] = {}
        raw_terms = explicit.get("terms")
        if isinstance(raw_terms, list):
            for term in raw_terms:
                self._add_term(groups, term)
        groups = self._merge_container_delivery_terms(groups)
        groups = self._merge_python_framework_terms(groups)
        terms = tuple(list(groups.values())[:12]) or inferred.terms

        def pick(key: str, default: Any) -> Any:
            value = explicit.get(key)
            return default if value is None else value

        languages = explicit.get("required_languages")
        if not isinstance(languages, list) or not languages:
            languages = list(inferred.required_languages)
        return RequirementSpec(
            criterion_id=inferred.criterion_id,
            name=inferred.name,
            category=inferred.category,
            kind=kind,
            terms=terms,
            min_years=float(pick("min_years", inferred.min_years)) if pick("min_years", inferred.min_years) is not None else None,
            required_degree_level=int(pick("required_degree_level", inferred.required_degree_level)) if pick("required_degree_level", inferred.required_degree_level) is not None else None,
            required_languages=tuple(str(item).lower() for item in languages),
            required_ielts=float(pick("required_ielts", inferred.required_ielts)) if pick("required_ielts", inferred.required_ielts) is not None else None,
            required_toeic=int(pick("required_toeic", inferred.required_toeic)) if pick("required_toeic", inferred.required_toeic) is not None else None,
            required_cefr=str(pick("required_cefr", inferred.required_cefr)).upper() if pick("required_cefr", inferred.required_cefr) else None,
            required_language_rank=int(pick("required_language_rank", inferred.required_language_rank)) if pick("required_language_rank", inferred.required_language_rank) is not None else None,
        )

    def _infer_requirement_spec(self, criterion: dict[str, Any]) -> RequirementSpec:
        name = str(criterion.get("name") or "")
        description = str(criterion.get("description") or "")
        combined = f"{name}. {description}"
        normalized = normalize_text(combined)

        raw_keywords = criterion.get("expected_evidence_keywords") or []
        if isinstance(raw_keywords, str):
            try:
                import json

                parsed = json.loads(raw_keywords)
                raw_keywords = parsed if isinstance(parsed, list) else [raw_keywords]
            except (ValueError, TypeError):
                raw_keywords = [raw_keywords]

        groups: dict[str, TermGroup] = {}
        for keyword in raw_keywords if isinstance(raw_keywords, list) else []:
            self._add_term(groups, keyword)
        self._add_term(groups, name)
        # Scan the criterion text for known concepts (aliases cover both the
        # JD and CV surface forms, e.g. JD "JS" versus CV "JavaScript").
        for canonical, variants in TERM_ALIASES.items():
            if any(_contains_phrase(normalized, variant) for variant in variants):
                self._add_term(groups, canonical)
        if not groups:
            for token in normalized.split():
                if len(token) >= 3 and token not in STOPWORDS and token not in GENERIC_TERMS:
                    self._add_term(groups, token)
                if len(groups) >= 6:
                    break

        min_years = self._parse_min_years(combined)
        required_degree = self._required_degree_level(normalized)
        required_languages = tuple(
            language for language in LANGUAGE_NAMES if _contains_phrase(normalized, language)
        )
        lowered_combined = combined.lower()
        ielts = re.search(r"ielts[^0-9]{0,30}?(\d+(?:[.,]\d+)?)", lowered_combined)
        toeic = re.search(r"toeic[^0-9]{0,30}?(\d{3,4})", lowered_combined)
        cefr = re.search(r"\b([abc][12])\b", lowered_combined)
        qualitative_rank = None
        for label, rank in QUALITATIVE_LANGUAGE_RANK.items():
            if _contains_phrase(normalized, label):
                qualitative_rank = rank if qualitative_rank is None else max(qualitative_rank, rank)

        has_certification = any(
            marker in normalized
            for marker in ("certif", "licence", "license", "chung chi")
        )
        has_degree = required_degree is not None or any(
            marker in normalized for marker in ("degree", "bachelor", "master", "phd", "cu nhan", "thac si", "tien si")
        ) or any(_contains_phrase(normalized, cue) for cue in DEGREE_CUES)
        # A *mention* of language is not a language requirement. "Excellent
        # communication skills" or "proficiency in presenting" are ordinary soft
        # skills: marking them LANGUAGE produced a spec with kind=LANGUAGE and no
        # language/threshold at all, which the response schema rejects. That
        # failed serialization turned a successful generation into an opaque
        # HTTP 500 with no `detail`, so HR saw a generic "criteria could not be
        # created" even though the position and rubrics were saved.
        # Only claim LANGUAGE when a concrete language or threshold exists.
        has_language_threshold = bool(
            required_languages or ielts or toeic or cefr or qualitative_rank is not None
        )
        has_language = has_language_threshold or any(
            marker in normalized
            for marker in ("ielts", "toeic", "cefr", "tieng anh", "ngoai ngu")
        )

        if has_language and has_language_threshold:
            kind = "LANGUAGE"
        elif has_certification:
            kind = "CERTIFICATION"
        elif has_degree:
            kind = "DEGREE"
        elif min_years is not None:
            kind = "YEARS"
        else:
            kind = "SKILL"

        groups = self._merge_container_delivery_terms(groups)
        groups = self._merge_python_framework_terms(groups)
        return RequirementSpec(
            criterion_id=str(criterion.get("criterion_id") or ""),
            name=name,
            category=str(criterion.get("category") or ""),
            kind=kind,
            terms=tuple(list(groups.values())[:12]),
            min_years=min_years,
            required_degree_level=required_degree if kind == "DEGREE" else None,
            required_languages=required_languages if kind == "LANGUAGE" else (),
            required_ielts=float(ielts.group(1).replace(",", ".")) if ielts else None,
            required_toeic=int(toeic.group(1)) if toeic else None,
            required_cefr=cefr.group(1).upper() if cefr else None,
            required_language_rank=qualitative_rank if kind == "LANGUAGE" else None,
        )

    # ------------------------------------------------------------- durations
    @staticmethod
    def _explicit_years_in(text: str) -> list[float]:
        normalized = normalize_text(text)
        values = [
            float(match.group(1).replace(",", "."))
            for match in re.finditer(
                r"(\d+(?:[.,]\d+)?)\s*\+?\s*(?:years?|yrs?|nam)\b",
                _accentless_lower(text),
            )
        ]
        number_words = {
            "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6,
            "seven": 7, "eight": 8, "nine": 9, "ten": 10, "eleven": 11, "twelve": 12,
        }
        for match in re.finditer(
            r"\b(one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve)\s+"
            r"(?:years?|yrs?)\b", normalized
        ):
            values.append(float(number_words[match.group(1)]))
        return values

    @staticmethod
    def _date_intervals_in(text: str, current_year: int) -> list[tuple[int, int]]:
        """Return [start_month, end_month) intervals from date ranges."""
        lowered = _accentless_lower(text)
        intervals: list[tuple[int, int]] = []
        pattern = re.compile(
            r"(?:(0?[1-9]|1[0-2])\s*/\s*)?(20\d{2})\s*(?:-|–|—|\bto\b|\buntil\b)\s*"
            r"(?:(0?[1-9]|1[0-2])\s*/\s*)?(20\d{2}|present|now|current|nay|hien nay)"
        )
        for match in pattern.finditer(lowered):
            start_month = int(match.group(1)) if match.group(1) else 1
            start = int(match.group(2)) * 12 + (start_month - 1)
            end_token = match.group(4)
            if end_token.isdigit():
                end_month = int(match.group(3)) if match.group(3) else 12
                end = int(end_token) * 12 + end_month
            else:
                end = current_year * 12 + 12
            if end > start:
                intervals.append((start, end))
        return intervals

    @staticmethod
    def _merged_interval_years(intervals: list[tuple[int, int]]) -> float:
        if not intervals:
            return 0.0
        total_months = 0
        ordered_intervals = sorted(intervals)
        current_start, current_end = ordered_intervals[0]
        for start, end in ordered_intervals[1:]:
            if start <= current_end:
                current_end = max(current_end, end)
            else:
                total_months += current_end - current_start
                current_start, current_end = start, end
        total_months += current_end - current_start
        return round(total_months / 12, 2)

    @staticmethod
    def _iter_strings(value: Any):
        if isinstance(value, str):
            yield value
        elif isinstance(value, dict):
            for item in value.values():
                yield from DeterministicMatchingEngine._iter_strings(item)
        elif isinstance(value, (list, tuple)):
            for item in value:
                yield from DeterministicMatchingEngine._iter_strings(item)

    def _years_assessment(
        self,
        candidate_profile: dict[str, Any] | None,
        chunks: list[DocumentChunk],
        relevant_chunk_ids: set[str] | None = None,
    ) -> dict[str, Any]:
        """Best years estimate plus whether it is safe for a NO_MATCH.

        A NO_MATCH is only allowed from a reliable total: an explicit
        profile total or merged date intervals.  Separate duration phrases
        may prove a positive match when summed, but if their sum is below
        the threshold the CV may still contain unquantified experience, so
        the criterion stays unresolved instead of becoming a mismatch.
        """
        candidates: list[float] = []
        reliable_total = False
        profile = candidate_profile or {}

        try:
            total_value = float(profile.get("total_years_experience"))
            if total_value > 0:
                candidates.append(total_value)
                reliable_total = True
        except (TypeError, ValueError):
            pass

        explicit_keys: set[str] = set()
        explicit_values: list[float] = []

        def add_explicit(source_text: str) -> None:
            for sentence in self._sentences(source_text):
                values = self._explicit_years_in(sentence)
                if not values:
                    continue
                key = normalize_text(sentence)
                if key in explicit_keys:
                    continue
                explicit_keys.add(key)
                explicit_values.append(max(values))

        profile_intervals: list[tuple[int, int]] = []
        for value in self._iter_strings(profile):
            add_explicit(value)
            profile_intervals.extend(self._date_intervals_in(value, date.today().year))
        if profile_intervals:
            candidates.append(self._merged_interval_years(profile_intervals))
            reliable_total = True

        relevant = [
            chunk for chunk in chunks
            if (relevant_chunk_ids is None or chunk.chunk_id in relevant_chunk_ids)
            and chunk.section in {"WORK", "PROJECT", "SUMMARY"}
        ]
        chunk_intervals: list[tuple[int, int]] = []
        for chunk in relevant:
            add_explicit(chunk.text)
            chunk_intervals.extend(self._date_intervals_in(chunk.text, date.today().year))
        if chunk_intervals:
            candidates.append(self._merged_interval_years(chunk_intervals))
            reliable_total = True
        if explicit_values:
            candidates.append(round(sum(explicit_values), 2))

        return {
            "years": max(candidates) if candidates else None,
            "reliable_total": reliable_total,
            "explicit_duration_total": round(sum(explicit_values), 2) if explicit_values else None,
            "explicit_duration_count": len(explicit_values),
        }

    def candidate_years_experience(
        self,
        candidate_profile: dict[str, Any] | None,
        chunks: list[DocumentChunk],
        relevant_chunk_ids: set[str] | None = None,
    ) -> float | None:
        return self._years_assessment(candidate_profile, chunks, relevant_chunk_ids)["years"]

    # -------------------------------------------------------------- matching
    @staticmethod
    def _matched_labels(spec: RequirementSpec, normalized_chunk: str) -> list[str]:
        return [
            term.label
            for term in spec.terms
            if any(_contains_phrase(normalized_chunk, variant) for variant in term.variants)
        ]

    @staticmethod
    def _cue_positions(padded_text: str, cues: tuple[str, ...]) -> list[tuple[int, int]]:
        positions: list[tuple[int, int]] = []
        for cue in cues:
            needle = f" {cue} "
            start = padded_text.find(needle)
            while start != -1:
                positions.append((start, start + len(needle)))
                start = padded_text.find(needle, start + 1)
        return positions

    @classmethod
    def _is_negated_occurrence(cls, padded_sentence: str, term_start: int) -> bool:
        # "Docker remains unclear" states uncertainty after the keyword.
        if any(f" {cue} " in padded_sentence[term_start:] for cue in UNCERTAIN_CUES):
            return True
        negation_ends = [
            end for _start, end in cls._cue_positions(padded_sentence, NEGATION_CUES)
            # The cue's trailing space is also the term needle's leading
            # space, so an immediately preceding cue ends at term_start + 1.
            if end <= term_start + 1
        ]
        if not negation_ends:
            return False
        last_negation_end = max(negation_ends)
        # "No Docker, but deployed Kubernetes" negates only the first clause.
        return not any(
            last_negation_end <= start and end <= term_start
            for start, end in cls._cue_positions(padded_sentence, CONTRAST_CUES)
        )

    @classmethod
    def _positive_labels_in_sentence(
        cls, spec: RequirementSpec, sentence: str,
    ) -> list[str]:
        """Term labels with at least one non-negated mention in a sentence."""
        padded = f" {normalize_text(sentence)} "
        labels: list[str] = []
        for term in spec.terms:
            for variant in term.variants:
                needle = f" {normalize_text(variant)} "
                start = padded.find(needle)
                found_positive = False
                while start != -1:
                    if not cls._is_negated_occurrence(padded, start):
                        found_positive = True
                        break
                    start = padded.find(needle, start + 1)
                if found_positive:
                    labels.append(term.label)
                    break
        return labels

    @classmethod
    def _positive_matched_labels(
        cls, spec: RequirementSpec, chunk: DocumentChunk,
    ) -> list[str]:
        found: set[str] = set()
        for sentence in cls._sentences(chunk.text):
            found.update(cls._positive_labels_in_sentence(spec, sentence))
        return [term.label for term in spec.terms if term.label in found]

    @classmethod
    def _positive_sentence_count(cls, spec: RequirementSpec, chunk: DocumentChunk) -> int:
        return sum(
            1 for sentence in cls._sentences(chunk.text)
            if cls._positive_labels_in_sentence(spec, sentence)
        )

    @staticmethod
    def _section_factor(kind: str, section: str) -> float:
        relevant = {
            "SKILL": {"WORK", "PROJECT", "SKILL"},
            "YEARS": {"WORK", "PROJECT"},
            "DEGREE": {"EDUCATION"},
            "CERTIFICATION": {"CERTIFICATION", "WORK"},
            "LANGUAGE": {"LANGUAGE"},
        }.get(kind, set())
        if section in relevant:
            return 1.0
        if section == "SUMMARY":
            return 0.82
        if section == "OTHER":
            return 0.72
        return 0.45

    def _candidates(self, spec: RequirementSpec, chunks: list[DocumentChunk]) -> list[_Candidate]:
        candidates: list[_Candidate] = []
        total_terms = max(1, len(spec.terms))
        for chunk in chunks:
            matched = self._positive_matched_labels(spec, chunk)
            if not matched:
                continue
            coverage = len(matched) / total_terms
            strength = 0.30 + 0.62 * coverage * self._section_factor(spec.kind, chunk.section)
            if chunk.section in {"WORK", "PROJECT", "SKILL", "EDUCATION", "CERTIFICATION", "LANGUAGE"}:
                strength += 0.04
            candidates.append(_Candidate(
                chunk=chunk,
                matched_labels=matched,
                coverage=round(coverage, 4),
                strength=round(min(0.97, strength), 4),
            ))
        candidates.sort(key=lambda item: (-item.strength, -item.coverage, item.chunk.chunk_id))
        return candidates

    def _fallback_chunks(
        self,
        spec: RequirementSpec,
        chunks: list[DocumentChunk],
        limit: int = 5,
    ) -> list[dict[str, Any]]:
        """Top chunks an adjudicator may inspect for an unresolved criterion."""
        selected: list[DocumentChunk] = []
        strengths: dict[str, float] = {}
        for candidate in self._candidates(spec, chunks):
            selected.append(candidate.chunk)
            strengths[candidate.chunk.chunk_id] = candidate.strength
            if len(selected) >= limit:
                break
        if len(selected) < limit:
            relevant_sections = {
                "YEARS": {"WORK", "PROJECT"},
                "DEGREE": {"EDUCATION"},
                "CERTIFICATION": {"CERTIFICATION", "WORK"},
                "LANGUAGE": {"LANGUAGE"},
                "SKILL": {"WORK", "PROJECT", "SKILL"},
            }.get(spec.kind, set())
            chosen = {chunk.chunk_id for chunk in selected}
            for chunk in chunks:
                if chunk.section in relevant_sections and chunk.chunk_id not in chosen:
                    selected.append(chunk)
                    chosen.add(chunk.chunk_id)
                    if len(selected) >= limit:
                        break
        return [
            {**chunk.to_dict(), "retrieval_strength": strengths.get(chunk.chunk_id)}
            for chunk in selected[:limit]
        ]

    @staticmethod
    def _sentence_spans(text: str) -> list[tuple[int, int]]:
        """Sentence spans that do not split decimal numbers such as 7.0."""
        spans: list[tuple[int, int]] = []
        start = 0
        index = 0

        def push(end: int) -> None:
            span_start, span_end = start, end
            while span_start < span_end and text[span_start].isspace():
                span_start += 1
            while span_end > span_start and text[span_end - 1].isspace():
                span_end -= 1
            if span_end > span_start:
                spans.append((span_start, span_end))

        while index < len(text):
            char = text[index]
            if (char == "." and 0 < index < len(text) - 1
                    and text[index - 1].isdigit() and text[index + 1].isdigit()):
                index += 1
                continue
            if char in ".!?":
                end = index + 1
                while end < len(text) and text[end] in ".!?":
                    end += 1
                push(end)
                start = index = end
                continue
            if char in ";\n":
                push(index + 1 if char == ";" else index)
                start = index = index + 1
                continue
            index += 1
        push(len(text))
        return spans

    @classmethod
    def _sentences(cls, text: str) -> list[str]:
        return [text[start:end] for start, end in cls._sentence_spans(text)]

    @staticmethod
    def _best_quote(candidate: _Candidate, spec: RequirementSpec) -> str:
        text = candidate.chunk.text
        sentences = DeterministicMatchingEngine._sentences(text)
        if len(sentences) <= 1:
            return text.strip()[:340]

        def sentence_score(sentence: str) -> tuple[int, int, int]:
            normalized = normalize_text(sentence)
            matched = len(DeterministicMatchingEngine._positive_labels_in_sentence(spec, sentence))
            has_duration = bool(
                DeterministicMatchingEngine._explicit_years_in(sentence)
                or DeterministicMatchingEngine._date_intervals_in(sentence, date.today().year)
            )
            has_degree = DeterministicMatchingEngine._degree_level_in(normalized) is not None
            has_language_level = bool(DeterministicMatchingEngine._language_level_in(sentence))
            # The quote must prove the rule that fired: a YEARS decision needs
            # its duration sentence, a DEGREE decision its degree sentence,
            # and a LANGUAGE decision its level-bearing sentence.
            if spec.kind == "YEARS":
                return (1 if has_duration else 0, matched, -len(sentence))
            if spec.kind == "DEGREE":
                return (1 if has_degree else 0, matched, -len(sentence))
            if spec.kind == "LANGUAGE":
                return (1 if has_language_level else 0, matched, -len(sentence))
            signals = int(has_duration) + int(has_degree) + int(has_language_level)
            return (matched, signals, -len(sentence))

        return max(sentences, key=sentence_score)

    @staticmethod
    def _finding(
        spec: RequirementSpec,
        candidate: _Candidate,
        outcome: str,
        strength: float,
        reasoning: str,
        quote_override: str | None = None,
    ) -> dict[str, Any]:
        strength = round(min(0.99, max(0.0, strength)), 3)
        return {
            "criterion_id": spec.criterion_id,
            "outcome": outcome,
            "confidence": strength,
            "confidence_band": "HIGH" if strength >= 0.85 else "MEDIUM" if strength >= 0.65 else "LOW",
            "evidence_strength": strength,
            "decision_source": "RULE",
            "rule_version": RULES_VERSION,
            "evidence_chunk_id": candidate.chunk.chunk_id,
            "reasoning": reasoning,
            "evidence": {
                "verbatim_quote": quote_override or DeterministicMatchingEngine._best_quote(candidate, spec),
                "page_number": candidate.chunk.page_number,
                "chunk_id": candidate.chunk.chunk_id,
                "char_start": candidate.chunk.char_start,
                "char_end": candidate.chunk.char_end,
            },
            "requires_verification": False,
        }

    def _evaluate_years(
        self,
        spec: RequirementSpec,
        chunks: list[DocumentChunk],
        candidate_profile: dict[str, Any] | None,
    ) -> dict[str, Any] | None:
        candidates = self._candidates(spec, chunks)
        relevant_ids = {candidate.chunk.chunk_id for candidate in candidates} or None
        assessment = self._years_assessment(candidate_profile, chunks, relevant_ids)
        years = assessment["years"]
        if years is None or spec.min_years is None:
            return None
        if years < spec.min_years and not assessment["reliable_total"]:
            # Quantified fragments below the threshold do not prove the
            # candidate lacks other relevant experience.
            return None
        evidence_pool = candidates or [
            _Candidate(chunk=chunk, matched_labels=[], coverage=0.0, strength=0.6)
            for chunk in chunks if chunk.section in {"WORK", "PROJECT"}
        ]
        if not evidence_pool:
            return None

        def evidence_rank(candidate: _Candidate) -> tuple[int, float, str]:
            has_duration = 1 if (
                self._explicit_years_in(candidate.chunk.text)
                or self._date_intervals_in(candidate.chunk.text, date.today().year)
            ) else 0
            return has_duration, candidate.strength, candidate.chunk.chunk_id

        best = max(evidence_pool, key=evidence_rank)
        matched_text = ", ".join(best.matched_labels) if best.matched_labels else "experience history"
        if years >= spec.min_years:
            outcome = "STRONG_MATCH" if years >= spec.min_years + 2 or years >= spec.min_years * 1.5 else "MATCH"
            return self._finding(
                spec, best, outcome, max(best.strength, 0.88),
                f"Deterministic years rule: approximately {years:g} years found for "
                f"{matched_text}; requirement is {spec.min_years:g} years.",
            )
        return self._finding(
            spec, best, "NO_MATCH", max(best.strength, 0.8),
            f"Deterministic years rule: approximately {years:g} years found for "
            f"{matched_text}; requirement is {spec.min_years:g} years.",
        )

    def _evaluate_degree(
        self,
        spec: RequirementSpec,
        chunks: list[DocumentChunk],
        candidate_profile: dict[str, Any] | None,
    ) -> dict[str, Any] | None:
        # Chưa biết bậc thì KHÔNG kết luận gì. Trước đây dòng này là
        # ``spec.required_degree_level or 3``: tiêu chí "có bằng cấp liên quan"
        # không nêu bậc bị chấm ngầm theo bậc đại học, nên ứng viên có bằng cao
        # đẳng bị NO_MATCH vì một ngưỡng chưa ai đặt. Trả ``None`` để tiêu chí
        # thành unresolved — HR thấy nó cần xử lý thay vì nhận một kết luận bịa.
        required = spec.required_degree_level
        if required is None:
            return None
        education_chunks = [chunk for chunk in chunks if chunk.section == "EDUCATION"]

        def highest_in(pool: list[DocumentChunk]) -> tuple[int | None, DocumentChunk | None]:
            best_level: int | None = None
            best_chunk: DocumentChunk | None = None
            for chunk in pool:
                level = self._degree_level_in(chunk.normalized)
                if level is not None and (best_level is None or level > best_level):
                    best_level, best_chunk = level, chunk
            return best_level, best_chunk

        highest, best_chunk = highest_in(education_chunks)
        # A NO_MATCH is only defensible when an Education section was found
        # and parsed.  Otherwise a lower mention elsewhere stays unresolved.
        allow_no_match = bool(education_chunks and highest is not None)
        if highest is None:
            highest, best_chunk = highest_in(chunks)
            allow_no_match = False
        if highest is None or best_chunk is None:
            return None

        profile_levels = [
            level for value in self._iter_strings((candidate_profile or {}).get("education"))
            if (level := self._degree_level_in(normalize_text(value))) is not None
        ]
        if profile_levels and max(profile_levels) > highest:
            # The profile claims more than the CV quote can prove; do not
            # attach a lower-degree quote to a higher-degree conclusion.
            return None

        candidate = _Candidate(
            chunk=best_chunk, matched_labels=self._matched_labels(spec, best_chunk.normalized),
            coverage=1.0, strength=0.9,
        )
        if highest >= required:
            outcome = "STRONG_MATCH" if highest > required else "MATCH"
            return self._finding(
                spec, candidate, outcome, 0.92,
                f"Deterministic degree rule: education evidence reaches level {highest}; "
                f"requirement level is {required}.",
            )
        if not allow_no_match:
            return None
        return self._finding(
            spec, candidate, "NO_MATCH", 0.78,
            f"Deterministic degree rule: highest education evidence is level {highest}; "
            f"requirement level is {required}.",
        )

    @staticmethod
    def _language_level_in(text: str) -> dict[str, float | int | str]:
        normalized = normalize_text(text)
        lowered = str(text or "").lower()
        result: dict[str, float | int | str] = {}
        ielts = re.search(r"ielts[^0-9]{0,30}?(\d+(?:[.,]\d+)?)", lowered)
        toeic = re.search(r"toeic[^0-9]{0,30}?(\d{3,4})", lowered)
        cefr = re.search(r"\b([abc][12])\b", lowered)
        if ielts:
            result["ielts"] = float(ielts.group(1).replace(",", "."))
        if toeic:
            result["toeic"] = int(toeic.group(1))
        if cefr:
            result["cefr"] = cefr.group(1).upper()
        for label, rank in QUALITATIVE_LANGUAGE_RANK.items():
            if _contains_phrase(normalized, label):
                result["rank"] = max(int(result.get("rank", 0)), rank)
        return result

    def _evaluate_language(
        self,
        spec: RequirementSpec,
        chunks: list[DocumentChunk],
    ) -> dict[str, Any] | None:
        candidates = [
            candidate for candidate in self._candidates(spec, chunks)
            if not spec.required_languages
            or any(language in candidate.matched_labels or _contains_phrase(candidate.chunk.normalized, language)
                   for language in spec.required_languages)
        ]
        # IELTS/TOEIC evidence may appear without repeating the language name
        # (for example under an Education heading).  Scan those chunks too.
        known_ids = {candidate.chunk.chunk_id for candidate in candidates}
        for chunk in chunks:
            if chunk.chunk_id in known_ids:
                continue
            if (self._language_level_in(chunk.text)
                    or any(marker in chunk.normalized for marker in ("ielts", "toeic", "cefr"))):
                labels = self._matched_labels(spec, chunk.normalized)
                candidates.append(_Candidate(
                    chunk=chunk,
                    matched_labels=labels,
                    coverage=1.0 if labels else 0.5,
                    strength=0.78,
                ))
        if not candidates:
            return None
        language_text = ", ".join(spec.required_languages) or "the required language"

        # Collect every stated level, not just the first one in a chunk.
        # Conflicting levels for the same test stay unresolved: the CV may
        # list an old and a current score and order alone cannot decide.
        observations: list[dict[str, Any]] = []
        for candidate in candidates:
            for sentence in self._sentences(candidate.chunk.text):
                levels = self._language_level_in(sentence)
                for metric, value in levels.items():
                    observations.append({
                        "candidate": candidate,
                        "quote": sentence,
                        "metric": metric,
                        "value": value,
                    })

        required: list[tuple[str, float]] = []
        if spec.required_ielts is not None:
            required.append(("ielts", float(spec.required_ielts)))
        if spec.required_toeic is not None:
            required.append(("toeic", float(spec.required_toeic)))
        if spec.required_cefr is not None:
            required.append(("cefr", float(CEFR_RANK[spec.required_cefr.lower()])))
        if spec.required_language_rank is not None:
            required.append(("rank", float(spec.required_language_rank)))

        if not required:
            best = candidates[0]
            return self._finding(
                spec, best, "MATCH", max(best.strength, 0.8),
                f"Deterministic language rule: {language_text} is evidenced in the CV.",
            )

        def comparable(observation: dict[str, Any]) -> float:
            if observation["metric"] == "cefr":
                return float(CEFR_RANK.get(str(observation["value"]).lower(), 0))
            return float(observation["value"])

        satisfied: list[dict[str, Any]] = []
        below: list[dict[str, Any]] = []
        metrics_with_values: set[str] = set()
        for metric, threshold in required:
            metric_observations = [item for item in observations if item["metric"] == metric]
            if not metric_observations:
                continue
            metrics_with_values.add(metric)
            if len({comparable(item) for item in metric_observations}) > 1:
                return None  # Conflicting stated levels: HR must verify.
            observation = metric_observations[0]
            if comparable(observation) >= threshold:
                satisfied.append(observation)
            else:
                below.append(observation)

        if satisfied:
            observation = satisfied[0]
            return self._finding(
                spec, observation["candidate"], "MATCH",
                max(observation["candidate"].strength, 0.86),
                f"Deterministic language rule: {language_text} level evidence meets the requirement.",
                quote_override=observation["quote"],
            )
        if below and len(metrics_with_values) == len(required):
            observation = below[0]
            return self._finding(
                spec, observation["candidate"], "NO_MATCH",
                max(observation["candidate"].strength, 0.78),
                f"Deterministic language rule: {language_text} level evidence is below the requirement.",
                quote_override=observation["quote"],
            )
        return None

    def _evaluate_generic(
        self,
        spec: RequirementSpec,
        chunks: list[DocumentChunk],
    ) -> dict[str, Any] | None:
        candidates = self._candidates(spec, chunks)
        if not candidates:
            return None
        best = candidates[0]
        if best.coverage < 0.5 or best.strength < 0.58:
            return None
        quote = self._best_quote(best, spec)
        duration_years = self._explicit_years_in(quote)
        strong = (
            (duration_years and max(duration_years) >= 3)
            or (len(best.matched_labels) >= 2 and best.coverage >= 0.8
                and best.chunk.section in {"WORK", "PROJECT"})
            # A single-concept rubric (e.g. Docker delivery after synonym
            # grouping) can still be strong when work evidence repeats it in
            # independent sentences.
            or (best.coverage >= 0.8
                and self._positive_sentence_count(spec, best.chunk) >= 2
                and best.chunk.section in {"WORK", "PROJECT"})
        )
        outcome = "STRONG_MATCH" if strong else "MATCH"
        kind_label = "certification" if spec.kind == "CERTIFICATION" else "skill"
        return self._finding(
            spec, best, outcome, best.strength,
            f"Deterministic {kind_label} rule: matched {', '.join(best.matched_labels)} "
            f"in {best.chunk.section} evidence ({best.chunk.chunk_id}).",
        )

    def _evaluate_spec(
        self,
        spec: RequirementSpec,
        chunks: list[DocumentChunk],
        candidate_profile: dict[str, Any] | None = None,
    ) -> dict[str, Any] | None:
        if spec.kind == "YEARS" or (spec.kind == "SKILL" and spec.min_years is not None):
            # A quantified duration in the criterion is a gate, not a hint:
            # stored specs may keep kind=SKILL (an HR-edited or AI-drafted
            # spec) while min_years still comes from the approved wording.
            # The skill rule alone must never declare a MATCH when the CV
            # states fewer years than required, nor when no duration can be
            # quantified at all; both stay unresolved for HR/LLM review.
            finding = self._evaluate_years(spec, chunks, candidate_profile)
            if finding is None or finding["outcome"] == "NO_MATCH":
                return finding
            # Full skill coverage in work evidence can still lift the plain
            # years MATCH to STRONG_MATCH; the duration gate stays decisive.
            strong_skill = any(
                len(candidate.matched_labels) >= 2
                and candidate.coverage >= 0.8
                and candidate.chunk.section in {"WORK", "PROJECT"}
                for candidate in self._candidates(spec, chunks)
            )
            if strong_skill and finding["outcome"] == "MATCH":
                finding = {
                    **finding,
                    "outcome": "STRONG_MATCH",
                    "reasoning": (
                        finding["reasoning"]
                        + " Skill terms are also fully covered in WORK evidence."
                    ),
                }
            return finding
        if spec.kind == "DEGREE":
            return self._evaluate_degree(spec, chunks, candidate_profile)
        if spec.kind == "LANGUAGE":
            return self._evaluate_language(spec, chunks)
        return self._evaluate_generic(spec, chunks)

    def evaluate_criterion(
        self,
        criterion: dict[str, Any],
        chunks: list[DocumentChunk],
        candidate_profile: dict[str, Any] | None = None,
    ) -> dict[str, Any] | None:
        return self._evaluate_spec(self.build_requirement_spec(criterion), chunks, candidate_profile)

    def evaluate_criteria(
        self,
        cv_text: str,
        criteria: list[dict[str, Any]],
        candidate_profile: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Return decisive rule findings plus the criteria left for fallback."""
        chunks = self.chunk_document(cv_text or "")
        findings: list[dict[str, Any]] = []
        unresolved: list[str] = []
        fallback_chunks: dict[str, list[dict[str, Any]]] = {}
        requirement_specs: dict[str, dict[str, Any]] = {}
        for criterion in criteria:
            spec = self.build_requirement_spec(criterion)
            requirement_specs[spec.criterion_id] = spec.to_dict()
            finding = self._evaluate_spec(spec, chunks, candidate_profile)
            if finding:
                findings.append(finding)
            else:
                unresolved.append(spec.criterion_id)
                fallback_chunks[spec.criterion_id] = self._fallback_chunks(spec, chunks)
        return {
            "findings": findings,
            "unresolved_criterion_ids": unresolved,
            "chunks": [chunk.to_dict() for chunk in chunks],
            "fallback_chunks": fallback_chunks,
            "requirement_specs": requirement_specs,
            "candidate_years_experience": self.candidate_years_experience(candidate_profile, chunks),
            "rule_version": RULES_VERSION,
        }


deterministic_matcher = DeterministicMatchingEngine()
