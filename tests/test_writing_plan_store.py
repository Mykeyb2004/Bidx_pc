import hashlib
import json
import re

import pytest

import bid_writer.writing_plan_store as writing_plan_store
from bid_writer.writing_plan_store import (
    WritingPlanExternalModificationError,
    WritingPlanItem,
    WritingPlanSnapshot,
    WritingPlanStore,
    WritingPlanStoreError,
    WritingPlanValidationError,
    extract_node_number,
)


@pytest.mark.parametrize(
    ("heading", "expected"),
    [
        ("1.4.2 进场核验", "1.4.2"),
        ("1. 项目实施方案", "1"),
        ("2.3.1：服务机制", "2.3.1"),
        ("2.3.10 相邻编号", "2.3.10"),
        ("项目 2.3.1", None),
        ("2.3.1A 不应识别", None),
    ],
)
def test_extract_node_number(heading: str, expected: str | None) -> None:
    assert extract_node_number(heading) == expected


def test_load_snapshot_uses_exact_node_matches_and_preserves_text(tmp_path) -> None:
    path = tmp_path / "writing-plan.json"
    payload = {
        "version": 1,
        "items": [
            {"node": "2.3.1", "writing_plan": "第一行\n第二行"},
            {"node": "2.3.10", "writing_plan": "相邻编号"},
        ],
    }
    raw = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    path.write_bytes(raw)

    snapshot = WritingPlanStore(path).load_snapshot()

    assert snapshot.items == (
        WritingPlanItem(node="2.3.1", writing_plan="第一行\n第二行"),
        WritingPlanItem(node="2.3.10", writing_plan="相邻编号"),
    )
    assert snapshot.fingerprint == hashlib.sha256(raw).hexdigest()
    assert snapshot.get("2.3.1") == "第一行\n第二行"
    assert snapshot.get("2.3.10") == "相邻编号"
    assert snapshot.get("2.3") is None


def test_load_snapshot_returns_empty_snapshot_for_missing_file(tmp_path) -> None:
    snapshot = WritingPlanStore(tmp_path / "missing.json").load_snapshot()

    assert snapshot.items == ()
    assert snapshot.fingerprint is None


def test_summarize_writing_plan_coverage_counts_only_nonempty_exact_plans() -> None:
    snapshot = WritingPlanSnapshot(
        items=(
            WritingPlanItem(node="1.4.1", writing_plan="计划甲"),
            WritingPlanItem(node="1.4.2", writing_plan="  "),
            WritingPlanItem(node="1.4.20", writing_plan="相邻编号计划"),
        ),
        fingerprint="fingerprint",
    )

    coverage = writing_plan_store.summarize_writing_plan_coverage(
        ["1.4.1 总体安排", "1.4.2 进场核验", "1.4.3 服务周期", "无编号节点"],
        snapshot,
    )

    assert coverage.total_headings == 4
    assert coverage.numbered_headings == 3
    assert coverage.planned_headings == 1
    assert coverage.unplanned_headings == 3
    assert coverage.unnumbered_headings == 1


def test_save_first_nonempty_plan_creates_formatted_utf8_file(tmp_path) -> None:
    path = tmp_path / "nested" / "writing-plan.json"
    store = WritingPlanStore(path)

    saved = store.save(
        "2.3.1",
        "第一行\n第二行",
        expected_snapshot=WritingPlanSnapshot(items=(), fingerprint=None),
    )

    raw = path.read_bytes()
    assert raw == (
        b'{\n'
        b'  "version": 1,\n'
        b'  "items": [\n'
        b'    {\n'
        b'      "node": "2.3.1",\n'
        b'      "writing_plan": "'
        + "第一行\\n第二行".encode("utf-8")
        + b'"\n'
        b'    }\n'
        b'  ]\n'
        b'}\n'
    )
    assert saved.items == (
        WritingPlanItem(node="2.3.1", writing_plan="第一行\n第二行"),
    )
    assert saved.fingerprint == hashlib.sha256(raw).hexdigest()


def test_save_updates_in_place_and_appends_new_nodes(tmp_path) -> None:
    path = tmp_path / "writing-plan.json"
    path.write_text(
        json.dumps(
            {
                "version": 1,
                "items": [
                    {"node": "1.1", "writing_plan": "甲"},
                    {"node": "1.2", "writing_plan": "乙"},
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    store = WritingPlanStore(path)

    snapshot = store.load_snapshot()
    snapshot = store.save("1.1", "更新", expected_snapshot=snapshot)
    snapshot = store.save("1.3", "新增", expected_snapshot=snapshot)

    assert snapshot.items == (
        WritingPlanItem(node="1.1", writing_plan="更新"),
        WritingPlanItem(node="1.2", writing_plan="乙"),
        WritingPlanItem(node="1.3", writing_plan="新增"),
    )


def test_save_whitespace_only_plan_deletes_matching_node(tmp_path) -> None:
    path = tmp_path / "writing-plan.json"
    path.write_text(
        json.dumps(
            {
                "version": 1,
                "items": [
                    {"node": "1.1", "writing_plan": "甲"},
                    {"node": "1.2", "writing_plan": "乙"},
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    store = WritingPlanStore(path)

    snapshot = store.save(
        "1.1", " \n\t ", expected_snapshot=store.load_snapshot()
    )

    assert snapshot.items == (WritingPlanItem(node="1.2", writing_plan="乙"),)
    assert WritingPlanStore(path).load_snapshot() == snapshot


def test_save_missing_store_delete_is_noop(tmp_path) -> None:
    path = tmp_path / "missing" / "writing-plan.json"
    store = WritingPlanStore(path)

    snapshot = store.save(
        "1.1",
        "  ",
        expected_snapshot=WritingPlanSnapshot(items=(), fingerprint=None),
    )

    assert snapshot == WritingPlanSnapshot(items=(), fingerprint=None)
    assert not path.exists()
    assert not path.parent.exists()


@pytest.mark.parametrize(
    ("raw", "message"),
    [
        (b"not-json", "JSON"),
        (b"\xff", "UTF-8"),
        (b"[]", "对象"),
        (b'{"items": []}', "版本"),
        (b'{"version": true, "items": []}', "版本"),
        (b'{"version": 2, "items": []}', "版本"),
        (b'{"version": 1, "items": {}}', "items"),
        (b'{"version": 1, "items": [null]}', "item"),
        (
            b'{"version": 1, "items": [{"node": 1, "writing_plan": "x"}]}',
            "node",
        ),
        (
            b'{"version": 1, "items": [{"node": "1.a", "writing_plan": "x"}]}',
            "node",
        ),
        (
            b'{"version": 1, "items": [{"node": "1.1", "writing_plan": 1}]}',
            "writing_plan",
        ),
        (
            b'{"version": 1, "items": ['
            b'{"node": "1.1", "writing_plan": "x"}, '
            b'{"node": " 1.1 ", "writing_plan": "y"}]}',
            "重复节点",
        ),
    ],
)
def test_invalid_store_is_rejected_and_never_overwritten(
    tmp_path, raw: bytes, message: str
) -> None:
    path = tmp_path / "writing-plan.json"
    path.write_bytes(raw)
    store = WritingPlanStore(path)

    with pytest.raises(WritingPlanValidationError) as caught:
        store.load_snapshot()
    assert str(path) in str(caught.value)
    assert message in str(caught.value)

    forged_snapshot = WritingPlanSnapshot(
        items=(), fingerprint=hashlib.sha256(raw).hexdigest()
    )
    with pytest.raises(WritingPlanValidationError):
        store.save("1.1", "不得覆盖", expected_snapshot=forged_snapshot)
    assert path.read_bytes() == raw


def test_validation_errors_use_actionable_chinese_messages(tmp_path) -> None:
    version_path = tmp_path / "version.json"
    version_path.write_text('{"version": 2, "items": []}', encoding="utf-8")

    with pytest.raises(
        WritingPlanValidationError,
        match=rf"撰写计划文件版本必须为 1：{re.escape(str(version_path))}",
    ):
        WritingPlanStore(version_path).load_snapshot()

    duplicate_path = tmp_path / "duplicate.json"
    duplicate_path.write_text(
        '{"version": 1, "items": ['
        '{"node": "2.3.1", "writing_plan": "甲"}, '
        '{"node": " 2.3.1 ", "writing_plan": "乙"}]}',
        encoding="utf-8",
    )

    with pytest.raises(
        WritingPlanValidationError,
        match=rf"撰写计划文件存在重复节点“2\.3\.1”：{re.escape(str(duplicate_path))}",
    ):
        WritingPlanStore(duplicate_path).load_snapshot()


def test_save_rejects_invalid_node_without_touching_file(tmp_path) -> None:
    path = tmp_path / "writing-plan.json"
    store = WritingPlanStore(path)

    with pytest.raises(WritingPlanValidationError, match="node"):
        store.save(
            "1.a",
            "内容",
            expected_snapshot=WritingPlanSnapshot(items=(), fingerprint=None),
        )

    assert not path.exists()


def test_external_modification_before_save_is_preserved(tmp_path) -> None:
    path = tmp_path / "writing-plan.json"
    path.write_text(
        '{"version": 1, "items": [{"node": "1.1", "writing_plan": "原文"}]}',
        encoding="utf-8",
    )
    store = WritingPlanStore(path)
    snapshot = store.load_snapshot()
    external_raw = (
        '{"version": 1, "items": '
        '[{"node": "1.1", "writing_plan": "外部修改"}]}'
    ).encode("utf-8")
    path.write_bytes(external_raw)

    with pytest.raises(
        WritingPlanExternalModificationError, match="外部修改"
    ) as caught:
        store.save("1.1", "本次修改", expected_snapshot=snapshot)

    assert str(path) in str(caught.value)
    assert path.read_bytes() == external_raw


def test_external_modification_from_missing_to_created_is_preserved(tmp_path) -> None:
    path = tmp_path / "writing-plan.json"
    store = WritingPlanStore(path)
    snapshot = store.load_snapshot()
    external_raw = b'{"version": 1, "items": []}'
    path.write_bytes(external_raw)

    with pytest.raises(WritingPlanExternalModificationError):
        store.save("1.1", "本次修改", expected_snapshot=snapshot)

    assert path.read_bytes() == external_raw


def test_save_failure_removes_only_its_temporary_file(
    tmp_path, monkeypatch
) -> None:
    path = tmp_path / "writing-plan.json"
    unrelated = tmp_path / "keep.tmp"
    unrelated.write_text("保留", encoding="utf-8")

    def fail_replace(source, destination) -> None:
        raise OSError("replace failed")

    monkeypatch.setattr(writing_plan_store.os, "replace", fail_replace)

    with pytest.raises(WritingPlanStoreError) as caught:
        WritingPlanStore(path).save(
            "1.1",
            "内容",
            expected_snapshot=WritingPlanSnapshot(items=(), fingerprint=None),
        )

    assert isinstance(caught.value.__cause__, OSError)
    assert str(path) in str(caught.value)
    assert not path.exists()
    assert unrelated.read_text(encoding="utf-8") == "保留"
    assert list(tmp_path.iterdir()) == [unrelated]
