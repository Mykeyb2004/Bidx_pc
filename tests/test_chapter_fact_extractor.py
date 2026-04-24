from bid_writer.chapter_fact_extractor import ChapterFactExtractor


def test_parse_fact_response_parses_global_and_local_lines():
    facts = ChapterFactExtractor.parse_fact_response(
        """
- [global] 项目经理: 张三
- [local] 阶段划分: 调研、开发、测试
""".strip(),
        max_facts=10,
    )

    assert [(fact.scope, fact.category, fact.value) for fact in facts] == [
        ("global", "项目经理", "张三"),
        ("local", "阶段划分", "调研、开发、测试"),
    ]


def test_parse_fact_response_handles_no_facts_and_max_limit():
    assert ChapterFactExtractor.parse_fact_response("无可提取事实", max_facts=10) == []

    facts = ChapterFactExtractor.parse_fact_response(
        """
- [global] 项目经理: 张三
- [global] 驻场人数: 不少于 5 人
- [local] 阶段划分: 调研、开发、测试
""".strip(),
        max_facts=2,
    )

    assert len(facts) == 2
    assert facts[0].category == "项目经理"
    assert facts[1].category == "驻场人数"
