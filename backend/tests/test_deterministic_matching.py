from app.services.deterministic_matching import deterministic_matcher


def criterion(criterion_id, name, description, category="MUST_HAVE", keywords=None):
    return {
        "criterion_id": criterion_id,
        "name": name,
        "description": description,
        "category": category,
        "weight_in_group": 100,
        "expected_evidence_keywords": keywords or [],
    }


def test_chunking_preserves_page_section_and_offsets():
    text = (
        "--- Page 1 ---\n"
        "Summary\n"
        "Backend developer.\n\n"
        "--- Page 2 ---\n"
        "WORK EXPERIENCE\n"
        "Built Python services for five years.\n\n"
        "Skills: Docker, Kubernetes\n"
    )
    chunks = deterministic_matcher.chunk_document(text)
    assert [chunk.chunk_id for chunk in chunks] == ["chunk-0001", "chunk-0002", "chunk-0003"]
    assert chunks[0].page_number == 1 and chunks[0].section == "SUMMARY"
    assert chunks[1].page_number == 2 and chunks[1].section == "WORK"
    assert chunks[2].section == "SKILL"
    for chunk in chunks:
        assert text[chunk.char_start:chunk.char_end] == chunk.text


def test_skill_rule_is_deterministic_and_uses_aliases():
    criteria = [criterion("c1", "JavaScript", "JavaScript experience", keywords=["JS"])]
    text = "WORK EXPERIENCE\nDeveloped JavaScript applications with React for four years."
    first = deterministic_matcher.evaluate_criteria(text, criteria, {})
    second = deterministic_matcher.evaluate_criteria(text, criteria, {})
    assert first == second
    finding = first["findings"][0]
    assert finding["outcome"] == "STRONG_MATCH"
    assert finding["decision_source"] == "RULE"
    assert finding["evidence_chunk_id"].startswith("chunk-")
    assert "JavaScript applications" in finding["evidence"]["verbatim_quote"]
    assert first["unresolved_criterion_ids"] == []


def test_years_rule_matches_and_rejects_explicit_evidence():
    criteria = [criterion("c1", "Python experience", "At least 5 years of Python experience")]
    enough = deterministic_matcher.evaluate_criteria(
        "WORK EXPERIENCE\nBuilt Python platforms for 8 years.", criteria, {})
    not_enough = deterministic_matcher.evaluate_criteria(
        "WORK EXPERIENCE\nBuilt Python tools for 2 years.", criteria, {})
    assert enough["findings"][0]["outcome"] == "STRONG_MATCH"
    # One quantified fragment is not a reliable career total, so the safer
    # result is unresolved rather than a rule NO_MATCH.
    assert not_enough["findings"] == []
    assert not_enough["unresolved_criterion_ids"] == ["c1"]


def test_years_rule_can_sum_non_overlapping_date_ranges():
    criteria = [criterion("c1", "Backend experience", "Minimum 5 years of backend experience")]
    text = (
        "WORK EXPERIENCE\n"
        "Backend Engineer 2016 - 2019. Built APIs.\n\n"
        "Senior Backend Engineer 2019 - 2022. Led services."
    )
    result = deterministic_matcher.evaluate_criteria(text, criteria, {})
    assert result["candidate_years_experience"] >= 5
    assert result["findings"][0]["outcome"] in {"MATCH", "STRONG_MATCH"}


def test_degree_and_language_rules():
    criteria = [
        criterion("degree", "Education", "Bachelor degree required"),
        criterion("lang", "English", "English language, IELTS 6.5 required", category="NICE_TO_HAVE"),
    ]
    text = (
        "EDUCATION\nBachelor of Computer Science, Example University.\n\n"
        "LANGUAGES\nEnglish IELTS 7.0."
    )
    result = deterministic_matcher.evaluate_criteria(text, criteria, {})
    outcomes = {finding["criterion_id"]: finding["outcome"] for finding in result["findings"]}
    assert outcomes == {"degree": "MATCH", "lang": "MATCH"}


def test_degree_below_requirement_is_explicit_no_match():
    criteria = [criterion("degree", "Education", "Master degree required")]
    result = deterministic_matcher.evaluate_criteria(
        "EDUCATION\nBachelor of Computer Science, Example University.", criteria, {})
    assert result["findings"][0]["outcome"] == "NO_MATCH"


def test_absent_skill_is_unresolved_not_no_match():
    criteria = [criterion("c1", "Rust", "Rust experience")]
    result = deterministic_matcher.evaluate_criteria(
        "WORK EXPERIENCE\nBuilt Python services for five years.", criteria, {})
    assert result["findings"] == []
    assert result["unresolved_criterion_ids"] == ["c1"]


def test_negated_skill_mention_is_unresolved_not_a_rule_match():
    criteria = [criterion(
        "docker", "Docker/container delivery", "Docker or containerised deployment experience",
        category="NICE_TO_HAVE", keywords=["Docker", "container", "Kubernetes"],
    )]
    text = (
        "WORK EXPERIENCE\n"
        "Developed Python backend APIs and PostgreSQL reports.\n\n"
        "Skills\nPython, PostgreSQL, SQL, Linux, Git.\n\n"
        "Note: this synthetic CV intentionally does not claim Docker or container delivery experience."
    )
    result = deterministic_matcher.evaluate_criteria(text, criteria, {})
    assert result["findings"] == []
    assert result["unresolved_criterion_ids"] == ["docker"]
    # The negation behaviour changed in v1.2, Docker synonym grouping in
    # v1.3, and the Python years gate/framework grouping in v1.4; the
    # version is part of the assessment fingerprint, so existing
    # assessments must be recalculated after any of these changes.
    assert result["rule_version"] == "deterministic-rules-v1.4"


def test_positive_skill_still_matches_when_another_sentence_is_negated():
    criteria = [criterion(
        "docker", "Docker/container delivery", "Docker or containerised deployment experience",
        category="NICE_TO_HAVE", keywords=["Docker", "container", "Kubernetes"],
    )]
    text = (
        "WORK EXPERIENCE\n"
        "No Docker use in the first role. Delivered services with Docker container deployments in the second role."
    )
    result = deterministic_matcher.evaluate_criteria(text, criteria, {})
    assert result["findings"]
    assert result["findings"][0]["decision_source"] == "RULE"
    assert "Docker container deployments" in result["findings"][0]["evidence"]["verbatim_quote"]


def test_vietnamese_negated_skill_mention_is_unresolved():
    criteria = [criterion(
        "docker", "Docker/container delivery", "Docker or containerised deployment experience",
        category="NICE_TO_HAVE", keywords=["Docker", "container", "Kubernetes"],
    )]
    result = deterministic_matcher.evaluate_criteria(
        "KINH NGHIỆM\nChưa có kinh nghiệm Docker hoặc triển khai container.", criteria, {})
    assert result["findings"] == []
    assert result["unresolved_criterion_ids"] == ["docker"]


def test_docker_synonyms_are_one_concept_and_match_positive_evidence():
    criteria = [criterion(
        "docker", "Docker/container delivery", "Docker or containerised deployment experience",
        category="NICE_TO_HAVE", keywords=["Docker", "container", "Kubernetes"],
    )]
    spec = deterministic_matcher.build_requirement_spec(criteria[0])
    assert [term.label for term in spec.terms] == ["docker"]
    assert "containers" in spec.terms[0].variants
    assert "containerised" in spec.terms[0].variants

    cases = {
        "Delivered services with Docker containers and CI pipelines; maintained containerised staging deployments.": "STRONG_MATCH",
        "Đóng gói dịch vụ bằng Docker và triển khai lên môi trường staging.": "MATCH",
        "Packaged internal tools with Docker for staging use.": "MATCH",
    }
    for text, expected in cases.items():
        result = deterministic_matcher.evaluate_criteria(f"WORK EXPERIENCE\n{text}", criteria, {})
        assert result["findings"], text
        assert result["findings"][0]["outcome"] == expected
        assert result["findings"][0]["decision_source"] == "RULE"


def test_docker_remains_unresolved_when_note_says_it_is_unclear():
    criteria = [criterion(
        "docker", "Docker/container delivery", "Docker or containerised deployment experience",
        category="NICE_TO_HAVE", keywords=["Docker", "container", "Kubernetes"],
    )]
    result = deterministic_matcher.evaluate_criteria(
        "Skills\nJava, Spring Boot, MySQL.\n\n"
        "Note: PostgreSQL and Docker remain unclear.", criteria, {})
    assert result["findings"] == []
    assert result["unresolved_criterion_ids"] == ["docker"]


def test_requirement_spec_detects_measurable_kinds():
    years = deterministic_matcher.build_requirement_spec(
        criterion("y", "Python", "At least 3 years of Python experience"))
    degree = deterministic_matcher.build_requirement_spec(
        criterion("d", "Education", "Master's degree in Computer Science"))
    cert = deterministic_matcher.build_requirement_spec(
        criterion("c", "AWS Certification", "AWS Certified Solutions Architect"))
    language = deterministic_matcher.build_requirement_spec(
        criterion("l", "English", "English proficiency, IELTS 6.0"))
    assert (years.kind, years.min_years) == ("YEARS", 3.0)
    assert (degree.kind, degree.required_degree_level) == ("DEGREE", 4)
    assert cert.kind == "CERTIFICATION"
    assert (language.kind, language.required_ielts) == ("LANGUAGE", 6.0)


def test_years_rule_sums_distinct_duration_sentences_and_quotes_duration():
    criteria = [criterion("c1", "Python experience", "At least 5 years of Python experience")]
    text = (
        "WORK EXPERIENCE\n"
        "Python Engineer at A. Built APIs for 3 years.\n\n"
        "Python Engineer at B. Built services for 3 years."
    )
    result = deterministic_matcher.evaluate_criteria(text, criteria, {})
    finding = result["findings"][0]
    assert result["candidate_years_experience"] == 6
    assert finding["outcome"] in {"MATCH", "STRONG_MATCH"}
    assert "years" in finding["evidence"]["verbatim_quote"]


def test_years_rule_does_not_no_match_from_unreliable_duration_fragment():
    criteria = [criterion("c1", "Python experience", "At least 5 years of Python experience")]
    result = deterministic_matcher.evaluate_criteria(
        "WORK EXPERIENCE\nBuilt Python tools for 2 years. Other work is undated.",
        criteria, {})
    assert result["findings"] == []
    assert result["unresolved_criterion_ids"] == ["c1"]


def test_language_rule_is_order_independent_and_conflicts_are_unresolved():
    criteria = [criterion("lang", "English", "English language, IELTS 7.0 required")]
    high_first = deterministic_matcher.evaluate_criteria(
        "LANGUAGES\nEnglish IELTS 7.0. English IELTS 5.5.", criteria, {})
    low_first = deterministic_matcher.evaluate_criteria(
        "LANGUAGES\nEnglish IELTS 5.5. English IELTS 7.0.", criteria, {})
    assert high_first["findings"] == []
    assert low_first["findings"] == []
    assert high_first["unresolved_criterion_ids"] == ["lang"]
    assert low_first["unresolved_criterion_ids"] == ["lang"]


def test_language_rule_preserves_decimal_quote_and_uses_level_sentence():
    criteria = [criterion("lang", "English", "English language, IELTS 7.0 required")]
    result = deterministic_matcher.evaluate_criteria(
        "EDUCATION\nPhD in Management.\n\nLANGUAGES\nIELTS 6.5.", criteria, {})
    finding = result["findings"][0]
    assert finding["outcome"] == "NO_MATCH"
    assert finding["evidence"]["verbatim_quote"] == "IELTS 6.5."


def test_degree_rule_does_not_use_lower_cv_quote_for_profile_only_match():
    criteria = [criterion("degree", "Education", "Master degree required")]
    result = deterministic_matcher.evaluate_criteria(
        "EDUCATION\nBachelor of Computer Science, Example University.",
        criteria,
        {"education": ["Master of Finance"]},
    )
    assert result["findings"] == []
    assert result["unresolved_criterion_ids"] == ["degree"]


def test_degree_below_outside_education_section_is_unresolved():
    criteria = [criterion("degree", "Education", "Master degree required")]
    result = deterministic_matcher.evaluate_criteria(
        "WORK EXPERIENCE\nSupported bachelor-level coursework tooling.", criteria, {})
    assert result["findings"] == []
    assert result["unresolved_criterion_ids"] == ["degree"]


def test_phrase_constituent_token_does_not_satisfy_skill():
    criteria = [criterion("c1", "Python programming", "Python programming", keywords=["Python programming"])]
    result = deterministic_matcher.evaluate_criteria(
        "SKILLS\nProgramming reliable business systems for clients.", criteria, {})
    assert result["findings"] == []
    assert result["unresolved_criterion_ids"] == ["c1"]
    assert result["fallback_chunks"]["c1"]


def _production_python_criterion():
    """The IT-0004 shape: HR-stored spec stays SKILL, years live in wording."""
    item = criterion(
        "python", "Python backend experience",
        "At least 4 years building production Python backend APIs.",
        keywords=["Python", "backend APIs", "FastAPI", "Django", "Flask"],
    )
    item["requirement_spec"] = {
        "kind": "SKILL",
        "terms": ["Python", "backend APIs", "FastAPI", "Django", "Flask"],
        "min_years": None,
        "required_languages": [],
    }
    return item


def test_python_framework_alternatives_are_one_concept():
    spec = deterministic_matcher.build_requirement_spec(_production_python_criterion())
    assert [term.label for term in spec.terms] == ["python", "backend apis", "python framework"]
    assert spec.min_years == 4.0
    # A Django-specific rubric must not be broadened to other frameworks.
    django_only = criterion("d", "Django", "Django experience", keywords=["Django"])
    django_spec = deterministic_matcher.build_requirement_spec(django_only)
    assert "python framework" not in [term.label for term in django_spec.terms]


def test_skill_spec_with_years_wording_uses_years_gate():
    criteria = [_production_python_criterion()]
    strong = deterministic_matcher.evaluate_criteria(
        "Summary\nBackend engineer with 6 years of experience building production Python backend APIs.\n\n"
        "Experience\n- Built Python backend APIs with FastAPI and PostgreSQL.", criteria, {})
    assert strong["findings"][0]["outcome"] == "STRONG_MATCH"
    assert strong["findings"][0]["reasoning"].startswith("Deterministic years rule")

    five_years = deterministic_matcher.evaluate_criteria(
        "Summary\nPython backend engineer with 5 years of API development experience.\n\n"
        "Experience\n- Built Python backend APIs and PostgreSQL-backed services.", criteria, {})
    assert five_years["findings"][0]["outcome"] == "MATCH"
    assert five_years["findings"][0]["reasoning"].startswith("Deterministic years rule")

    # Stated 2 years against a 4-year gate stays unresolved, never a skill
    # MATCH and never an automatic NO_MATCH from an unreliable fragment.
    two_years = deterministic_matcher.evaluate_criteria(
        "Summary\nBackend developer with 2 years of Python experience.\n\n"
        "Experience\n- Developed Python backend APIs with FastAPI for order processing.", criteria, {})
    assert two_years["findings"] == []
    assert two_years["unresolved_criterion_ids"] == ["python"]

    # Full skill coverage without any quantified duration is also
    # unresolved: the years gate cannot be verified from skills alone.
    no_years = deterministic_matcher.evaluate_criteria(
        "Experience\n- Delivered Python backend APIs with FastAPI and PostgreSQL.", criteria, {})
    assert no_years["findings"] == []
    assert no_years["unresolved_criterion_ids"] == ["python"]


def test_vietnamese_years_are_quantified_and_can_strong_match():
    criteria = [_production_python_criterion()]
    result = deterministic_matcher.evaluate_criteria(
        "Tóm tắt\nKỹ sư backend với 5 năm kinh nghiệm phát triển API Python cho hệ thống nội bộ.\n\n"
        "Kinh nghiệm\n- Phát triển backend APIs bằng Python và FastAPI cho quy trình phê duyệt.",
        criteria, {})
    assert result["candidate_years_experience"] == 5
    assert result["findings"][0]["outcome"] == "STRONG_MATCH"


def test_explicit_requirement_spec_overrides_text_inference():
    item = criterion("c1", "Backend role", "General backend work")
    item["requirement_spec"] = {
        "kind": "YEARS",
        "terms": ["Python"],
        "min_years": 5,
    }
    spec = deterministic_matcher.build_requirement_spec(item)
    assert spec.kind == "YEARS"
    assert spec.min_years == 5
    assert [term.label for term in spec.terms] == ["python"]


def test_vietnamese_degree_phrasings_are_recognised_as_degree_criteria():
    """Cách người Việt viết yêu cầu học vấn phải về kind=DEGREE.

    Trước đây DEGREE_PATTERNS chỉ có "cu nhan"/"bachelor", nên "Tốt nghiệp đại
    học" và "Đại học trở lên" rơi về SKILL: máy đi dò từ khoá thay vì so bậc
    bằng, và HR không thấy ô "Bậc bằng tối thiểu" để điền. Bốn câu dưới là bốn
    cách viết gặp nhiều nhất trong JD tiếng Việt.
    """
    cases = {
        "Tốt nghiệp đại học chuyên ngành CNTT trở lên.": 3,
        "Tốt nghiệp đại học.": 3,
        "Đại học trở lên chuyên ngành CNTT": 3,
        "Bằng cao đẳng trở lên": 2,
        "Tốt nghiệp THPT": 1,
    }
    for description, expected_level in cases.items():
        spec = deterministic_matcher.build_requirement_spec(
            criterion("d", "Học vấn", description))
        assert spec.kind == "DEGREE", f"{description!r} → {spec.kind}"
        assert spec.required_degree_level == expected_level, description


def test_degree_criterion_without_a_level_leaves_level_empty():
    """Nêu học vấn mà không nêu bậc thì để trống, KHÔNG đoán.

    Đoán một bậc là gán ngưỡng chưa ai duyệt, và ngưỡng đó đi thẳng vào điểm
    số. Để trống thì HR thấy ô "Bậc bằng tối thiểu" và tự quyết.
    """
    spec = deterministic_matcher.build_requirement_spec(
        criterion("d", "Học vấn", "Có bằng cấp liên quan tới vị trí"))
    assert spec.kind == "DEGREE"
    assert spec.required_degree_level is None


def test_degree_wording_does_not_swallow_years_or_skill_criteria():
    """Mở rộng nhận diện học vấn không được kéo nhầm tiêu chí khác."""
    years = deterministic_matcher.build_requirement_spec(
        criterion("y", "Kinh nghiệm", "Ít nhất 3 năm kinh nghiệm Python"))
    skill = deterministic_matcher.build_requirement_spec(
        criterion("s", "Kỹ năng", "Thành thạo Python và FastAPI"))
    assert (years.kind, years.min_years) == ("YEARS", 3.0)
    assert skill.kind == "SKILL"
