#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""accept.py —— 分段验收闸门

把 acceptance-protocol.md 的验收协议变成机械闸门：**前置未过，不许进下一关**。
纸面规则会被静默跳过，所以必须由脚本挡。

用法：
    python accept.py --project <目录> --list                 # 看进度与下一关
    python accept.py --project <目录> --show V2              # 看某关该验什么
    python accept.py --project <目录> --pass V2 --note "..."
    python accept.py --project <目录> --fail V2 --note "第5段语速快"
    python accept.py --project <目录> --skip V4 --note "复用上期参考帧"
    python accept.py --project <目录> --json

状态记录在 <项目>/acceptance.json。
"""
from __future__ import annotations

import argparse
import glob
import json
import os
import sys
from datetime import datetime

try:  # Windows 控制台中文（stdout 与 stderr 都要，否则报错信息乱码）
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    sys.stderr.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
except Exception:
    pass

SKILL_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# ── 关卡定义 ────────────────────────────────────────────────────────────
# prereq: 必须先 pass/skip 的关卡
# artifacts: 产出物 glob（相对项目根）；hard=True 时缺失报 FAIL
# verify: 该关怎么验收（打印给用户）
# rubric: 判据
GATES: list[dict] = [
    dict(id="A1", name="意图", prereq=[],
         verify="对话：观众反应 / 投放平台 / 一句话主题（interview-bank §1）",
         rubric="三项都问到了，没替用户拍板"),
    dict(id="A2", name="参照锚定", prereq=["A1"],
         verify="对话：像什么 / 明确不像什么（interview-bank §2）",
         rubric="提取出三个可执行维度并交回确认"),
    dict(id="A3", name="感觉翻译", prereq=["A2"],
         verify="给参数表让用户逐行挑（feeling-to-params.md）",
         rubric="参数表每行用户都能说'对'或'改成X'；自洽性红线已过"),
    dict(id="A4", name="硬约束", prereq=["A3"],
         verify="逐项问 consent.json 七项，每项给候选",
         rubric="七项齐全且 decided_by=user"),
    dict(id="A5", name="可行性+拍板", prereq=["A4"],
         artifacts=[("creative-brief.md", True)],
         verify="三段式话术（feasibility.md）→ 摆策划书 → 要明确确认",
         rubric="用户明确说'就按这个开工'"),
    dict(id="B1", name="机械体检", prereq=["A5"],
         verify="python <vd>/scripts/spec_review.py --project .",
         rubric="FAIL 清零；B2 五判据全过（尤其运镜 100%、承接 ≥1/3）"),
    dict(id="V1", name="解说词", prereq=["B1"],
         artifacts=[("narration.json", True)],
         verify="读全文 + 时长预估",
         rubric="一句一场景 / 块≤16字 / 时长在区间 / 三类废句已删 / 数字有出处"),
    dict(id="V2", name="配音", prereq=["V1"],
         artifacts=[("audio/*.mp3", True)],
         verify="逐段听 audio/<id>.mp3（一声一文件）",
         rubric="音色/语速/断句/重音；含数字的段查字幕块起点；无声画错位"),
    dict(id="V3", name="分镜+风格", prereq=["V2"],
         artifacts=[("script/storyboard.md", True), ("style-plan.json", False)],
         verify="读 storyboard.md + style-plan 的 why 列",
         rubric="四列齐 / 风格3-4种无连续3场同 / 每场运镜 / 承接≥1/3 / 全局约束齐"),
    dict(id="V4", name="参考帧", prereq=["V3"],
         verify="node peek_frame.mjs . <id> --at-sec 3.5,12（秒级出图）",
         rubric="DNA对/一焦点/主角带光/无碎屑/亮底带paper类/字幕带空"),
    dict(id="V5", name="全片静帧", prereq=["V4"],
         verify="三条体检全绿 + qc_sheet 肉眼 + grep -l 占位 frames/*.html",
         rubric="lint/beats/layout 全绿（layout ERROR 清零）/ 无占位残留 / 家族一致"),
    dict(id="V6", name="打样", prereq=["V5"],
         artifacts=[("out/*preview*.mp4", False)],
         verify="node render_video.mjs . --preview 30 --jpeg --keep-frames",
         rubric="前3秒抓人/字号舒服/语速合适/节奏有起伏/转场自然/亮底字幕皮肤"),
    dict(id="V7", name="混音", prereq=["V6"],
         artifacts=[("audio/mix.wav", True)],
         verify="ffplay audio/mix.wav + 看 sfx.json cue 表",
         rubric="音效贴帧±0.05s/高潮有impact/说话时BGM让位/响度-14LUFS"),
    dict(id="V8", name="全片", prereq=["V7"],
         artifacts=[("out/*.mp4", False)],
         verify="连看一遍（别跳），记时间码",
         rubric="qc_report FAIL清零 / 时长差<0.5s / 连贯 / 结尾不拖沓"),
    dict(id="V9", name="封面", prereq=["V8"],
         artifacts=[("out/cover_169.png", True), ("out/cover_34.png", False)],
         verify="node cover_build.mjs . && node check_cover.mjs .",
         rubric="三要素齐 / check_cover FAIL清零 / 封面文字与首帧钩子同义"),
]

BY_ID = {g["id"]: g for g in GATES}
STATE_PATH = "acceptance.json"


def _now() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def _load(path: str) -> dict:
    """utf-8-sig：Windows 上 PS/记事本写的 JSON 常带 BOM（lessons L7）。"""
    if not os.path.isfile(path):
        return {}
    try:
        with open(path, encoding="utf-8-sig") as f:
            return json.load(f)
    except Exception:
        return {}


def _save(path: str, data: dict) -> None:
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.write("\n")


def _find(proj: str, pattern: str) -> list[str]:
    return sorted(glob.glob(os.path.join(proj, pattern)))


def check_artifacts(proj: str, gate: dict) -> list[tuple[str, str, bool]]:
    """返回 [(pattern, 说明, 是否硬性)]"""
    out = []
    for pattern, hard in gate.get("artifacts", []):
        hits = _find(proj, pattern)
        out.append((pattern, f"{len(hits)} 个", hard))
    return out


def status_of(state: dict, gid: str) -> str:
    return (state.get(gid) or {}).get("status", "pending")


def prereq_ok(state: dict, gate: dict) -> tuple[bool, list[str]]:
    missing = []
    for p in gate.get("prereq", []):
        st = status_of(state, p)
        if st not in ("pass", "skip"):
            missing.append(f"{p}({st})")
    return (not missing), missing


# ── 命令 ────────────────────────────────────────────────────────────────
def cmd_list(proj: str, state: dict) -> int:
    icon = {"pass": "OK ", "fail": "!! ", "skip": "-- ", "pending": " . "}
    print("=" * 76)
    print(" 分段验收进度")
    print(f" 项目：{proj}")
    print("=" * 76)
    nxt = None
    for g in GATES:
        st = status_of(state, g["id"])
        note = (state.get(g["id"]) or {}).get("note", "")
        line = f"[{icon.get(st, '??')}] {g['id']:<3} {g['name']:<10} {st}"
        if note:
            line += f"   （{note}）"
        print(line)
        if nxt is None and st not in ("pass", "skip"):
            nxt = g
    print("-" * 76)
    done = sum(1 for g in GATES if status_of(state, g["id"]) in ("pass", "skip"))
    print(f" 已过 {done}/{len(GATES)}")
    if nxt:
        ok, missing = prereq_ok(state, nxt)
        if ok:
            print(f" → 下一关：{nxt['id']} {nxt['name']}")
            print(f"   验收：{nxt['verify']}")
            print(f"   判据：{nxt['rubric']}")
        else:
            print(f" → 下一关 {nxt['id']} 前置未完成：{', '.join(missing)}")
    else:
        print(" → 全部通过，可交付")
    print("=" * 76)
    return 0


def cmd_show(proj: str, state: dict, gid: str) -> int:
    g = BY_ID.get(gid)
    if not g:
        print(f"未知关卡：{gid}。可用：{', '.join(BY_ID)}", file=sys.stderr)
        return 2
    st = status_of(state, gid)
    ok, missing = prereq_ok(state, g)
    print("=" * 76)
    print(f" {g['id']} · {g['name']}   当前状态：{st}")
    print("=" * 76)
    print(f" 前置：{', '.join(g.get('prereq') or ['（无）'])}")
    print(f"       完成情况：{'OK' if ok else '未完成 —— ' + ', '.join(missing)}")
    print(f"\n 怎么验收：\n   {g['verify']}")
    print(f"\n 判据：\n   {g['rubric']}")
    arts = check_artifacts(proj, g)
    if arts:
        print("\n 产出物：")
        for pattern, desc, hard in arts:
            tag = "必需" if hard else "可选"
            print(f"   [{tag}] {pattern}  → {desc}")
    print("\n 记一笔：")
    print(f"   python accept.py --project . --pass {g['id']} --note \"...\"")
    print("=" * 76)
    return 0


def cmd_set(proj: str, state: dict, gid: str, status: str, note: str,
            force: bool) -> int:
    g = BY_ID.get(gid)
    if not g:
        print(f"未知关卡：{gid}", file=sys.stderr)
        return 2

    # 闸门：前置未过不许放行（skip 也要前置过；fail 总是允许）
    if status in ("pass", "skip"):
        ok, missing = prereq_ok(state, g)
        if not ok and not force:
            print("=" * 76)
            print(f" ✗ 拒绝放行 {gid}：前置未完成")
            print(f"   缺：{', '.join(missing)}")
            print("   先过前置，或明确用 --force 越级（会记录在案）")
            print("=" * 76)
            return 1

    # 产出物存在性（硬性的缺失时报 FAIL，但允许 --force）
    warns = []
    for pattern, hard in g.get("artifacts", []):
        if hard and not _find(proj, pattern):
            warns.append(pattern)
    if warns and status == "pass" and not force:
        print("=" * 76)
        print(f" ✗ 拒绝通过 {gid}：找不到产出物证据")
        for w in warns:
            print(f"   缺失：{w}")
        print("   说明这一段还没真的产出。确认无误再 --force。")
        print("=" * 76)
        return 1

    if status == "skip" and not note.strip():
        print("✗ skip 必须写理由（--note），静默跳过是事故", file=sys.stderr)
        return 1

    state[gid] = {"status": status, "at": _now(), "note": note,
                  "forced": bool(force) if not prereq_ok(state, g)[0] else False}
    _save(os.path.join(proj, STATE_PATH), state)

    tag = {"pass": "✓ 通过", "fail": "✗ 打回", "skip": "→ 跳过"}[status]
    print(f"{tag}  {gid} {g['name']}")
    if note:
        print(f"   备注：{note}")
    if status == "fail":
        print("   下一步：按 acceptance-protocol.md §3 回退路径图重跑对应环节")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="分段验收闸门")
    ap.add_argument("--project", required=True)
    ap.add_argument("--list", action="store_true", help="看进度与下一关")
    ap.add_argument("--show", metavar="GATE", help="看某关该验什么")
    ap.add_argument("--pass", dest="do_pass", metavar="GATE")
    ap.add_argument("--fail", dest="do_fail", metavar="GATE")
    ap.add_argument("--skip", dest="do_skip", metavar="GATE")
    ap.add_argument("--note", default="", help="验收意见（落进档案）")
    ap.add_argument("--force", action="store_true",
                    help="越级/跳过产出物检查（会记录 forced=true）")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    proj = os.path.abspath(args.project)
    if not os.path.isdir(proj):
        print(f"[accept] 目录不存在：{proj}", file=sys.stderr)
        return 2
    state = _load(os.path.join(proj, STATE_PATH))

    if args.json:
        print(json.dumps({"project": proj, "state": state,
                          "gates": [g["id"] for g in GATES]},
                         ensure_ascii=False, indent=2))
        return 0

    if args.show:
        return cmd_show(proj, state, args.show)
    if args.do_pass:
        return cmd_set(proj, state, args.do_pass, "pass", args.note, args.force)
    if args.do_fail:
        return cmd_set(proj, state, args.do_fail, "fail", args.note, args.force)
    if args.do_skip:
        return cmd_set(proj, state, args.do_skip, "skip", args.note, args.force)
    return cmd_list(proj, state)


if __name__ == "__main__":
    raise SystemExit(main())
