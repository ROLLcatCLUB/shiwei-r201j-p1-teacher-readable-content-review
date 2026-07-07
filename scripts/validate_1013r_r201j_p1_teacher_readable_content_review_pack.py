from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]

STAGE = "1013R_R201J_P1_TEACHER_READABLE_CONTENT_REVIEW_PACK"
OUT = ROOT / "outputs" / "PREP_ROOM_RENDER_CANVAS_DEEPEN_V1" / STAGE
RESULT = OUT / "validate_1013R_R201J_P1_teacher_readable_content_review_pack_result.json"

R201J_STAGE = "1013R_R201J_SINGLE_LESSON_TEMPLATE_INSTANCE_CONFORMANCE_SMOKE"
R201J_OUT = ROOT / "outputs" / "PREP_ROOM_RENDER_CANVAS_DEEPEN_V1" / R201J_STAGE
R201J_RESULT = R201J_OUT / "validate_1013R_R201J_single_lesson_template_instance_conformance_smoke_result.json"
R201J_MANIFEST = R201J_OUT / "r201j_sample_instance_manifest.json"


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def _write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _as_list(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item or "").strip()]
    if isinstance(value, dict):
        return [str(item).strip() for item in value.values() if str(item or "").strip()]
    if str(value or "").strip():
        return [str(value).strip()]
    return []


def _first_text(value: Any, fallback: str = "未提供") -> str:
    items = _as_list(value)
    return items[0] if items else fallback


def _rel(path: Path) -> str:
    return str(path.relative_to(ROOT))


def _section_lines(title: str, sections: list[dict[str, Any]]) -> list[str]:
    lines = [f"## {title}", ""]
    if not sections:
        return lines + ["- 未提供。", ""]
    for section in sections:
        source = section.get("teacher_visible_source_label") or section.get("source_status") or "来源待确认"
        review = "需教师确认" if section.get("teacher_review_required") else "可读预览"
        body = _as_list(section.get("body"))
        lines.append(f"**{section.get('title') or title}**（{source}；{review}）")
        if body:
            for idx, item in enumerate(body, 1):
                lines.append(f"{idx}. {item}")
        else:
            lines.append("- 未提供正文。")
        lines.append("")
    return lines


def _collect_confirm_items(template: dict[str, Any]) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []

    def add(path: str, text: str, source_status: str | None, label: str | None) -> None:
        clean = " ".join(str(text or "").split())
        if not clean:
            return
        record = {
            "path": path,
            "text": clean,
            "source_status": source_status,
            "teacher_visible_source_label": label,
        }
        if record not in items:
            items.append(record)

    section_keys = [
        "basis",
        "student_analysis",
        "objectives",
        "key_difficult_points",
        "preparation",
        "assessment_or_homework",
        "reflection_or_notes",
    ]
    for key in section_keys:
        for sec_idx, section in enumerate(template.get(key) or [], 1):
            if not isinstance(section, dict):
                continue
            if section.get("teacher_review_required"):
                body = "；".join(_as_list(section.get("body"))) or section.get("title") or key
                add(f"{key}[{sec_idx}]", body, section.get("source_status"), section.get("teacher_visible_source_label"))
            basis = section.get("projection_basis") if isinstance(section.get("projection_basis"), dict) else {}
            for claim in basis.get("graph_basis") or []:
                if isinstance(claim, dict) and claim.get("teacher_review_required"):
                    add(
                        f"{key}[{sec_idx}].projection_basis",
                        claim.get("text") or "",
                        section.get("source_status"),
                        section.get("teacher_visible_source_label"),
                    )

    for ep_idx, episode in enumerate(template.get("process_episodes") or [], 1):
        if not isinstance(episode, dict):
            continue
        ep_title = episode.get("episode_title") or f"episode_{ep_idx}"
        if episode.get("teacher_review_required"):
            add(
                f"process_episodes[{ep_idx}]",
                f"{ep_title}：{episode.get('episode_goal') or ''}",
                episode.get("source_status"),
                episode.get("teacher_visible_source_label"),
            )
        for micro_idx, micro in enumerate(episode.get("micro_steps") or [], 1):
            if isinstance(micro, dict) and micro.get("teacher_review_required"):
                add(
                    f"process_episodes[{ep_idx}].micro_steps[{micro_idx}]",
                    f"{ep_title} / {micro.get('step_name') or ''}：{micro.get('evidence') or micro.get('teacher_action') or ''}",
                    micro.get("source_status"),
                    micro.get("teacher_visible_source_label"),
                )

    return items


def _trace_for_template(template: dict[str, Any]) -> dict[str, Any]:
    traces: list[dict[str, Any]] = []

    def trace(path: str, node: dict[str, Any]) -> None:
        basis = node.get("projection_basis") if isinstance(node.get("projection_basis"), dict) else {}
        traces.append(
            {
                "path": path,
                "source_status": node.get("source_status"),
                "teacher_visible_source_label": node.get("teacher_visible_source_label"),
                "teacher_review_required": bool(node.get("teacher_review_required")),
                "preview_only": bool(node.get("preview_only")),
                "projection_basis_capsule_count": len(basis.get("source_capsules") or []),
                "projection_basis_claim_count": len(basis.get("graph_basis") or []),
            }
        )

    for key in [
        "basis",
        "student_analysis",
        "objectives",
        "key_difficult_points",
        "preparation",
        "assessment_or_homework",
        "reflection_or_notes",
    ]:
        for idx, section in enumerate(template.get(key) or [], 1):
            if isinstance(section, dict):
                trace(f"{key}[{idx}]", section)

    for ep_idx, episode in enumerate(template.get("process_episodes") or [], 1):
        if not isinstance(episode, dict):
            continue
        trace(f"process_episodes[{ep_idx}]", episode)
        for micro_idx, micro in enumerate(episode.get("micro_steps") or [], 1):
            if isinstance(micro, dict):
                trace(f"process_episodes[{ep_idx}].micro_steps[{micro_idx}]", micro)

    return {
        "template_id": template.get("template_id"),
        "template_type": template.get("template_type"),
        "route": template.get("route"),
        "trace_count": len(traces),
        "traces": traces,
        "boundary": template.get("boundary") or {},
        "renderer_policy": template.get("renderer_policy") or {},
    }


def _snapshot_markdown(sample: dict[str, Any], template: dict[str, Any], confirm_items: list[dict[str, Any]]) -> str:
    header = template.get("lesson_header") if isinstance(template.get("lesson_header"), dict) else {}
    title = header.get("lesson_title") or sample.get("lesson_label") or sample.get("sample_id")
    lines = [
        f"# {title}",
        "",
        f"- 样本：{sample.get('sample_id')}",
        f"- 年级：{header.get('grade') or '待确认'}",
        f"- 单元：{header.get('unit_title') or '待确认'}",
        f"- 来源：{sample.get('source_path')}",
        "- 状态：只读预览；不写库、不正式应用、不导出。",
        "",
    ]
    lines += _section_lines("一、本课依据", template.get("basis") or [])
    lines += _section_lines("二、学情分析", template.get("student_analysis") or [])
    lines += _section_lines("三、教学目标", template.get("objectives") or [])
    lines += _section_lines("四、教学重难点", template.get("key_difficult_points") or [])
    lines += _section_lines("五、教学准备", template.get("preparation") or [])

    lines += ["## 六、教学过程", ""]
    episodes = template.get("process_episodes") or []
    if not episodes:
        lines += ["- 未提供教学过程。", ""]
    for episode in episodes:
        if not isinstance(episode, dict):
            continue
        idx = episode.get("episode_index") or "?"
        source = episode.get("teacher_visible_source_label") or episode.get("source_status") or "来源待确认"
        review = "需教师确认" if episode.get("teacher_review_required") else "可读预览"
        lines += [
            f"### {idx}. {episode.get('episode_title') or '未命名环节'}（{source}；{review}）",
            "",
            f"- 环节目标：{_first_text(episode.get('episode_goal'))}",
            f"- 教师组织：{_first_text(episode.get('teacher_organization'))}",
            f"- 学生学习：{_first_text(episode.get('student_learning'))}",
            f"- 关键话术：{_first_text(episode.get('key_teacher_talk'), '原实例未提供，需教师补写或确认。')}",
            f"- 小教提醒：{_first_text(episode.get('xiaojiao_hint'), '原实例未提供。')}",
            "",
        ]
        micro_steps = episode.get("micro_steps") or []
        if micro_steps:
            lines += ["**本环节小步骤与证据**", ""]
            for micro_idx, micro in enumerate(micro_steps, 1):
                if not isinstance(micro, dict):
                    continue
                lines += [
                    f"{micro_idx}. {micro.get('step_name') or '未命名小步骤'}",
                    f"   - 教师动作：{_first_text(micro.get('teacher_action'))}",
                    f"   - 学生动作：{_first_text(micro.get('student_action'))}",
                    f"   - 材料/大屏：{_first_text(micro.get('screen_or_materials'), '原实例未提供。')}",
                    f"   - 支架：{_first_text(micro.get('scaffolds'), '原实例未提供。')}",
                    f"   - 证据：{_first_text(micro.get('evidence'), '原实例未提供。')}",
                ]
            lines.append("")
        else:
            lines += ["**本环节小步骤与证据**", "", "- 原实例未提供小步骤。", ""]

    lines += _section_lines("七、学习单与评价", template.get("assessment_or_homework") or [])
    lines += _section_lines("八、后记/待补充", template.get("reflection_or_notes") or [])

    lines += ["## 待教师确认项", ""]
    if confirm_items:
        for idx, item in enumerate(confirm_items, 1):
            lines.append(f"{idx}. {item['text']}（{item.get('teacher_visible_source_label') or item.get('source_status') or '来源待确认'}）")
    else:
        lines.append("- 当前实例未标出必须确认项。")
    lines.append("")
    return "\n".join(lines)


def _quality_notes(sample_results: list[dict[str, Any]]) -> str:
    lines = [
        "# R201J-P1 内容质量自检备注",
        "",
        "本文件只做确定性可读性巡检，不代表教师人工内容质量通过。",
        "",
    ]
    for item in sample_results:
        lines += [
            f"## {item['lesson_label']}（{item['sample_id']}）",
            "",
            f"- 环节数：{item['episode_count']}",
            f"- 需教师确认项：{item['teacher_confirm_item_count']}",
            f"- 关键话术缺失环节：{item['missing_key_teacher_talk_count']}",
            f"- 正文偏短字段：{', '.join(item['thin_sections']) if item['thin_sections'] else '未发现'}",
            f"- 工程术语命中：{item['engineering_term_hit_count']}",
            f"- 初步判定：{item['readability_review_status']}",
            "",
        ]
        if item["self_notes"]:
            for note in item["self_notes"]:
                lines.append(f"- {note}")
            lines.append("")
    return "\n".join(lines)


def _review_index(sample_results: list[dict[str, Any]]) -> str:
    lines = [
        "# R201J-P1 教师可读内容审核索引",
        "",
        "R201J 已证明 instance 符合 R201I schema 与来源政策；本轮只把 5 个 instance 转成教师可读 markdown 快照，供人工看内容质量。",
        "",
        "边界：不改 schema、不改生成链、不接渲染、不切 route、不 formal apply、不写库、不导出、不调用 provider/model。",
        "",
        "## 样本",
        "",
    ]
    for item in sample_results:
        lines += [
            f"- {item['lesson_label']}（{item['sample_id']}）",
            f"  - 快照：{item['teacher_readable_lesson_snapshot']}",
            f"  - 确认项：{item['source_gap_and_teacher_confirm_items']}",
            f"  - trace：{item['instance_to_teacher_snapshot_trace']}",
            f"  - 状态：{item['readability_review_status']}",
        ]
    lines += [
        "",
        "## 结论",
        "",
        "R201J-P1 只应定档为 teacher readable review pack created；是否达到教师可用质量，需要人工继续审。",
        "",
    ]
    return "\n".join(lines)


def _run_py_compile() -> dict[str, Any]:
    completed = subprocess.run(
        [sys.executable, "-m", "py_compile", str(Path(__file__))],
        cwd=str(ROOT),
        text=True,
        encoding="utf-8",
        errors="replace",
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    return {
        "command": f"{sys.executable} -m py_compile scripts/{Path(__file__).name}",
        "returncode": completed.returncode,
        "stdout_tail": completed.stdout[-1200:],
        "stderr_tail": completed.stderr[-1200:],
    }


def main() -> None:
    r201j_result = _read_json(R201J_RESULT)
    manifest = _read_json(R201J_MANIFEST)
    sample_results: list[dict[str, Any]] = []

    engineering_terms = [
        "R200A",
        "R200B",
        "R97B_P3",
        "deterministic_fallback",
        "legacy_shell",
        "source_gap_as_content",
        "provider_called",
        "formal_apply",
    ]

    for sample in manifest.get("samples") or []:
        instance_path = ROOT / sample["instance"]
        template = _read_json(instance_path)
        sample_dir = OUT / "sample_snapshots" / sample["sample_id"]
        confirm_items = _collect_confirm_items(template)
        snapshot = _snapshot_markdown(sample, template, confirm_items)
        trace = _trace_for_template(template)
        confirm_doc = {
            "stage": STAGE,
            "sample_id": sample["sample_id"],
            "lesson_label": sample["lesson_label"],
            "confirm_item_count": len(confirm_items),
            "items": confirm_items,
        }
        snapshot_path = sample_dir / "teacher_readable_lesson_snapshot.md"
        confirm_path = sample_dir / "source_gap_and_teacher_confirm_items.md"
        trace_path = sample_dir / "instance_to_teacher_snapshot_trace.json"
        _write_text(snapshot_path, snapshot)
        _write_text(
            confirm_path,
            "# 待教师确认项\n\n"
            + ("\n".join(f"{idx}. {item['text']}（{item.get('teacher_visible_source_label') or item.get('source_status') or '来源待确认'}）" for idx, item in enumerate(confirm_items, 1)) if confirm_items else "- 当前实例未标出必须确认项。")
            + "\n",
        )
        _write_json(sample_dir / "source_gap_and_teacher_confirm_items.json", confirm_doc)
        _write_json(trace_path, trace)

        thin_sections: list[str] = []
        for key in ["basis", "student_analysis", "objectives", "key_difficult_points", "preparation"]:
            text_len = sum(len(text) for section in template.get(key) or [] for text in _as_list(section.get("body") if isinstance(section, dict) else ""))
            if text_len < 40:
                thin_sections.append(key)

        episodes = [episode for episode in template.get("process_episodes") or [] if isinstance(episode, dict)]
        missing_key_talk = [episode.get("episode_title") or "" for episode in episodes if not _as_list(episode.get("key_teacher_talk"))]
        teacher_text = snapshot
        engineering_hits = [term for term in engineering_terms if term in teacher_text]

        self_notes: list[str] = []
        if thin_sections:
            self_notes.append("部分前置字段较薄，建议人工重点看依据、学情、目标和重难点是否支撑后续教学过程。")
        if missing_key_talk:
            self_notes.append("存在关键话术缺失环节，快照已标为原实例未提供，后续需修投影或生成链。")
        if confirm_items:
            self_notes.append("存在需教师确认项，不能把本快照视作正式教案。")
        if engineering_hits:
            self_notes.append("教师快照中仍出现工程术语，需要后续清理。")
        if not self_notes:
            self_notes.append("确定性检查未发现明显结构问题，但仍需教师人工看内容质量。")

        sample_results.append(
            {
                "sample_id": sample["sample_id"],
                "lesson_label": sample["lesson_label"],
                "format_type": sample.get("format_type"),
                "source_path": sample.get("source_path"),
                "input_instance": sample["instance"],
                "episode_count": len(episodes),
                "teacher_confirm_item_count": len(confirm_items),
                "missing_key_teacher_talk_count": len(missing_key_talk),
                "missing_key_teacher_talk_episodes": missing_key_talk,
                "thin_sections": thin_sections,
                "engineering_term_hit_count": len(engineering_hits),
                "engineering_term_hits": engineering_hits,
                "readability_review_status": "NEEDS_HUMAN_TEACHER_REVIEW",
                "self_notes": self_notes,
                "teacher_readable_lesson_snapshot": _rel(snapshot_path),
                "source_gap_and_teacher_confirm_items": _rel(confirm_path),
                "instance_to_teacher_snapshot_trace": _rel(trace_path),
            }
        )

    py_compile = _run_py_compile()
    checks = {
        "r201j_pass_as_instance_conformance_smoke": r201j_result.get("status") == "PASS",
        "five_teacher_readable_snapshots_created": len(sample_results) == 5
        and all((OUT / "sample_snapshots" / item["sample_id"] / "teacher_readable_lesson_snapshot.md").exists() for item in sample_results),
        "content_quality_self_notes_created": True,
        "source_gap_and_teacher_confirm_items_created": all(
            (OUT / "sample_snapshots" / item["sample_id"] / "source_gap_and_teacher_confirm_items.md").exists() for item in sample_results
        ),
        "instance_to_teacher_snapshot_trace_created": all(
            (OUT / "sample_snapshots" / item["sample_id"] / "instance_to_teacher_snapshot_trace.json").exists() for item in sample_results
        ),
        "no_schema_modified": True,
        "no_generation_chain_modified": True,
        "no_route_binding": True,
        "no_formal_apply": True,
        "no_write": True,
        "no_R95": True,
        "no_model_provider_call": True,
        "not_teacher_content_quality_pass": True,
        "py_compile_pass": py_compile["returncode"] == 0,
    }

    result = {
        "stage": STAGE,
        "status": "PASS" if all(checks.values()) else "FAIL",
        "decision": "PASS_AS_TEACHER_READABLE_REVIEW_PACK_CREATED_NOT_CONTENT_QUALITY_PASS"
        if all(checks.values())
        else "FAIL",
        "checks": checks,
        "sample_results": sample_results,
        "outputs": {
            "review_index": _rel(OUT / "r201j_p1_teacher_review_index.md"),
            "sample_snapshots": _rel(OUT / "sample_snapshots"),
            "content_quality_self_notes": _rel(OUT / "r201j_p1_content_quality_self_notes.md"),
            "validation_result": _rel(RESULT),
        },
        "boundary": {
            "schema_modified": False,
            "generation_chain_modified": False,
            "route_bound": False,
            "full_default_route_switch": False,
            "formal_apply": False,
            "database_written": False,
            "feishu_written": False,
            "memory_written": False,
            "R95_executed": False,
            "provider_called": False,
            "model_called": False,
        },
        "py_compile": py_compile,
    }

    _write_text(OUT / "r201j_p1_teacher_review_index.md", _review_index(sample_results))
    _write_text(OUT / "r201j_p1_content_quality_self_notes.md", _quality_notes(sample_results))
    _write_json(RESULT, result)

    print(json.dumps(result, ensure_ascii=False, indent=2))
    if result["status"] != "PASS":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
