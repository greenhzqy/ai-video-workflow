#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""spec_review.py —— video-director 阶段 B 机械体检

把 review-rubric.md 的纸质判据变成机械可查的闸门。
秒级出结果；退出码 1 = 有 FAIL。

用法：
    python spec_review.py --project <项目目录>
    python spec_review.py --project <目录> --json          # 机器可读
    python spec_review.py --project <目录> --no-style-plan # 不读 style-plan.json

检查范围：
    B1 自洽性        mood/pace/时长/画幅/确认项
    B2 单调度体检    风格数 / 同风格连场 / 运镜比 / 承接连律 / 强度起伏
    B4 契约一致性     与 html-explainer 的 brief/consent/gate_check 兼容
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys

try:
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
except Exception:
    pass

# ── 常量（与 review-rubric.md 保持同步） ────────────────────────────────
REQUIRED_CONSENT = ["theme", "style", "form", "voice", "duration_sec",
                    "cover", "render_channel"]

MOODS = {"calm", "neutral", "high"}
PACES = {"slow", "medium", "fast"}
AUDIENCES = {"general", "pro", "youth"}

# mood 与风格类别的互斥表：calm 配这些 = 情绪与画面语法相反
MOOD_STYLE_CONFLICT = {
    "calm": ("glitch", "electric", "voltage", "cyber", "neon"),
}

INTENSITY_MIN_SPREAD = 0.20   # 全片强度落差下限
MIN_SEC_PER_SCENE = 2.0       # 每场最短时长
STYLE_COUNT_MIN, STYLE_COUNT_MAX = 2, 4
MAX_SAME_STYLE_RUN = 2        # 连续同风格上限（>此值即违规）

# 运镜关键词（取自 motion-library 的 camera 组）
CAMERA_HINTS = re.compile(
    r"slowPush|camTrack|whipPan|camShake|layerMatrix|__motion|运镜|推镜|甩镜|视差",
    re.I)
# 承接关键词（取自 motion-library 的 carry 组）
CARRY_HINTS = re.compile(
    r"morphBox|irisOpen|diveInto|arcHop|gatherTo|railShift|sealDisc|承接|跨边界|延续", re.I)


class Report:
    def __init__(self) -> None:
        self.items: list[dict] = []

    def add(self, level: str, code: str, what: str, why: str = "",
            fix: str = "") -> None:
        self.items.append({"level": level, "code": code, "what": what,
                           "why": why, "fix": fix})

    def fail(self, code, what, why="", fix=""):
        self.add("FAIL", code, what, why, fix)

    def warn(self, code, what, why="", fix=""):
        self.add("WARN", code, what, why, fix)

    def info(self, code, what, why="", fix=""):
        self.add("INFO", code, what, why, fix)

    def ok(self, code, what):
        self.add("OK", code, what)

    def count(self, level):
        return sum(1 for i in self.items if i["level"] == level)


def _load_json(path: str):
    """读 JSON。用 utf-8-sig：Windows 上 PowerShell / 记事本 / Excel 写出的
    UTF-8 文件常带 BOM，用纯 utf-8 解码会在第 1 列就炸（lessons L7）。"""
    if not os.path.isfile(path):
        return None
    try:
        with open(path, encoding="utf-8-sig") as f:
            return json.load(f)
    except Exception as e:
        return {"__error__": f"{type(e).__name__}: {e}"}


def _as_intensity(v):
    try:
        x = float(v)
    except (TypeError, ValueError):
        return None
    return x if 0.0 <= x <= 1.0 else None


# ── B1 自洽性 ──────────────────────────────────────────────────────────
def check_self_consistency(rep: Report, brief: dict, consent: dict | None) -> None:
    topic = (brief.get("topic") or "").strip()
    if topic:
        rep.ok("B1-topic", f"主题已填：{topic}")
    else:
        rep.warn("B1-topic", "brief.topic 为空",
                 "style_director.py 用它做文本线索与主题哈希",
                 "A1 问 3 填上，或至少给 3 个关键词")

    mood = (brief.get("mood") or "").strip().lower()
    if not mood:
        rep.warn("B1-mood", "brief.mood 未定",
                 "它决定整片能量曲线的抬/压", "A3 轮在 calm/neutral/high 里挑一档")
    elif mood not in MOODS:
        rep.fail("B1-mood", f"brief.mood='{mood}' 不是合法取值",
                 f"style_director.py 只认 {sorted(MOODS)}",
                 f"改成 {sorted(MOODS)} 之一")
    else:
        rep.ok("B1-mood", f"mood={mood}")

    pace = (brief.get("pace") or "").strip().lower()
    if not pace:
        rep.warn("B1-pace", "brief.pace 未定", "影响风格池偏好",
                 "A3 轮在 slow/medium/fast 里挑一档")
    elif pace not in PACES:
        rep.fail("B1-pace", f"brief.pace='{pace}' 不是合法取值",
                 f"只认 {sorted(PACES)}", f"改成 {sorted(PACES)} 之一")
    else:
        rep.ok("B1-pace", f"pace={pace}")

    audience = (brief.get("audience") or "").strip().lower()
    if audience and audience not in AUDIENCES:
        rep.fail("B1-audience", f"brief.audience='{audience}' 不是合法取值",
                 f"只认 {sorted(AUDIENCES)}", f"改成 {sorted(AUDIENCES)} 之一")

    aspect = (brief.get("aspect") or "").strip()
    if not aspect:
        rep.warn("B1-aspect", "brief.aspect 未定", "决定画幅与封面张数",
                 "A4 轮按投放平台定（16:9 / 9:16）")

    # pace:fast 与强度矛盾（若能拿到 style-plan）
    director = brief.get("director") or {}
    curve = director.get("intensity_curve") or []

    # mood 与风格冲突
    style_txt = json.dumps(brief, ensure_ascii=False).lower()
    for m, needles in MOOD_STYLE_CONFLICT.items():
        if mood == m and any(n in style_txt for n in needles):
            rep.fail("B1-mood-style",
                     f"mood='{m}' 与所选风格（含 {[n for n in needles if n in style_txt]}）冲突",
                     "情绪与画面语法相反，成片会别扭",
                     "换风格，或改 mood")

    # 亮底配色 vs 字幕皮肤
    theme_txt = ""
    if consent and isinstance(consent.get("theme"), dict):
        theme_txt = str(consent["theme"].get("choice") or "")
    light_bg = bool(re.search(r"亮底|米白|白底|纸|#F[0-9A-Fa-f]{5}|#E[0-9A-Fa-f]{5}",
                              theme_txt + style_txt))
    if light_bg and not re.search(r"mg-sub|paper|亮底字幕|字幕皮肤", 
                                  json.dumps(brief, ensure_ascii=False) + theme_txt, re.I):
        rep.warn("B1-light-bg",
                 "疑似亮底配色但未见亮底字幕皮肤配置",
                 "渲染器默认白字黑描边，落在米白纸面等于看不见",
                 "主题里补 --mg-sub-fg/--mg-sub-stroke/--mg-track/--mg-tick，"
                 "并给亮底帧加 <body class=\"paper\">")

    # 快门
    shutter = str(director.get("shutter") or "")
    if not shutter:
        rep.info("B1-shutter", "未记录快门设置",
                 "位移 >80px/帧 的镜头不开快门会重影",
                 "若全片有快运镜，确认渲染用 --shutter 180")
    elif re.search(r"开|180|on|true|yes", shutter, re.I):
        rep.ok("B1-shutter", f"快门：{shutter}")


# ── B2 单调度体检 ──────────────────────────────────────────────────────
def check_monotony(rep: Report, plan: dict | None, brief: dict) -> None:
    if not plan:
        rep.warn("B2-noplan", "找不到 style-plan.json，单调度体检只能做粗判",
                 "完整体检需要 style_director.py 的产物",
                 "先跑 style_director.py --project . 生成 style-plan.json")
        return

    scenes = plan.get("scenes") or []
    if not scenes:
        rep.warn("B2-empty", "style-plan.json 里没有 scenes", "", "先跑 style_director.py")
        return

    # 判据 1：风格数
    used = []
    for s in scenes:
        p = s.get("primary")
        if p and p not in used:
            used.append(p)
    n = len(used)
    if n < STYLE_COUNT_MIN:
        rep.warn("B2-style-count", f"全片只用了 {n} 种风格",
                 f"<{STYLE_COUNT_MIN} 种会显得单调",
                 f"补到 {STYLE_COUNT_MIN}–{STYLE_COUNT_MAX} 种轮换")
    elif n > STYLE_COUNT_MAX:
        rep.warn("B2-style-count", f"全片用了 {n} 种风格",
                 f">{STYLE_COUNT_MAX} 种会显花",
                 "同类内合并，或收窄候选池（--styles）")
    else:
        rep.ok("B2-style-count", f"风格数 {n} 种（{', '.join(used)}）")

    # 判据 2：同风格连场
    run, run_start, worst = 1, 0, (1, 0)
    for i in range(1, len(scenes)):
        if scenes[i].get("primary") and scenes[i]["primary"] == scenes[i - 1].get("primary"):
            run += 1
        else:
            if run > worst[0]:
                worst = (run, run_start)
            run, run_start = 1, i
    if run > worst[0]:
        worst = (run, run_start)
    if worst[0] > MAX_SAME_STYLE_RUN:
        ids = [scenes[j].get("id") for j in
               range(worst[1], min(worst[1] + worst[0], len(scenes)))]
        rep.warn("B2-same-run",
                 f"第 {worst[1]+1} 场起连续 {worst[0]} 场同风格（{', '.join(str(x) for x in ids)}）",
                 f"连续 >{MAX_SAME_STYLE_RUN} 场会显得单调",
                 f"第 {worst[1]+MAX_SAME_STYLE_RUN+1} 场强制换（同类内换优先）")
    else:
        rep.ok("B2-same-run", f"最长同风格连续 {worst[0]} 场")

    # 判据 3（运镜）与判据 4（承接）需读分镜文本，见 check_camera_and_carry()

    # 判据 5：动效强度起伏
    inten = [_as_intensity(s.get("motion_intensity")) for s in scenes]
    vals = [v for v in inten if v is not None]
    if len(vals) >= 2:
        spread = max(vals) - min(vals)
        mean = sum(vals) / len(vals)
        if spread < INTENSITY_MIN_SPREAD:
            rep.warn("B2-intensity",
                     f"动效强度几乎拉平：{min(vals):.2f}–{max(vals):.2f}（落差 {spread:.2f}）",
                     f"落差 <{INTENSITY_MIN_SPREAD} 全片会显得平",
                     "排一条起伏曲线（开场高/收尾低），落差做到 ≥0.2")
        else:
            rep.ok("B2-intensity",
                   f"强度起伏 {min(vals):.2f}–{max(vals):.2f}（落差 {spread:.2f}）")
        if abs(mean - 0.5) < 0.03 and len(set(round(v, 2) for v in vals)) <= 2:
            rep.warn("B2-intensity-flat",
                     f"强度值几乎只有 {sorted(set(round(v,2) for v in vals))} 两档",
                     "看起来像没设计过", "拉开成 5–6 档不同值")

    # 转场多样性
    trans = [s.get("transition_out") for s in scenes if s.get("transition_out")]
    if trans:
        uniq = set(trans)
        if uniq == {"cut"} and len(trans) >= 4:
            rep.warn("B2-transition", f"{len(trans)} 场全部用硬切",
                     "硬切连着硬切会显得生硬",
                     "至少 1/3 换成 dissolve-soft / match-cut")
        else:
            rep.ok("B2-transition", f"转场 {len(uniq)} 种：{', '.join(sorted(uniq))}")

    # 时长 vs 场景数
    durs = [s.get("duration_sec") for s in scenes if s.get("duration_sec")]
    if durs:
        shortest = min(durs)
        tot = sum(durs)
        if shortest < MIN_SEC_PER_SCENE:
            rep.fail("B2-duration",
                     f"最短场景仅 {shortest:.2f}s（低于 {MIN_SEC_PER_SCENE}s）",
                     "每场不足 2s 什么也讲不清",
                     "砍场景数，或加时长")
        else:
            rep.ok("B2-duration", f"最短场景 {shortest:.2f}s，全片约 {tot:.1f}s")


def check_camera_and_carry(rep: Report, proj: str, plan: dict | None) -> None:
    """判据 3（运镜）与判据 4（承接）需要分镜文本，单独查。"""
    sb_path = None
    for cand in ("script/storyboard.md", "storyboard.md"):
        p = os.path.join(proj, cand)
        if os.path.isfile(p):
            sb_path = p
            break
    if not sb_path:
        rep.info("B2-storyboard", "没有找到 script/storyboard.md，运镜/承接判据跳过",
                 "这两条判据需读分镜文本", "分镜写好后重跑本脚本")
        return

    with open(sb_path, encoding="utf-8") as f:
        text = f.read()

    scenes = (plan or {}).get("scenes") or []
    n_scenes = len(scenes) or len(re.findall(r"^\|\s*\d+\s*\|", text, re.M))
    if n_scenes == 0:
        rep.info("B2-camera", "场景数未知，跳过运镜统计", "", "")
        return

    # 运镜：数分镜表里出现运镜关键词的行数
    rows = [ln for ln in text.splitlines() if ln.strip().startswith("|")]
    cam_rows = [ln for ln in rows if CAMERA_HINTS.search(ln)]
    ratio = len(cam_rows) / n_scenes if n_scenes else 0
    if ratio < 1.0:
        rep.fail("B2-camera",
                 f"运镜场次比 {len(cam_rows)}/{n_scenes}（{ratio:.0%}）",
                 "每场应有 ≥1 次可测运镜；不足 100% 就是 PPT 苗头",
                 "每场补 slowPush(长镜头) / camTrack(有焦点移动) / whipPan(快切前)，"
                 "并让 window.__motion(t0,t1) 报出非零屏幕位移 px")
    else:
        rep.ok("B2-camera", f"运镜场次比 {len(cam_rows)}/{n_scenes}（100%）")

    # 承接：全片承接数
    carry_n = len(CARRY_HINTS.findall(text))
    if carry_n == 0:
        rep.fail("B2-carry", "分镜里没有任何承接设计（跨边界继续动的元素）",
                 "相邻场之间若无元素跨越边界，全片会读成幻灯片",
                 "用 morphBox / irisOpen / diveInto / arcHop 串场，"
                 "每相邻两场至少一处")
    elif carry_n < n_scenes // 3:
        rep.warn("B2-carry", f"承接处仅 {carry_n} 处，相对 {n_scenes} 场偏少",
                 "承接不足仍会读成一组画面而非一条动作链",
                 "补到至少每 3 场一处")
    else:
        rep.ok("B2-carry", f"承接处 {carry_n} 处")


# ── B4 契约一致性 ──────────────────────────────────────────────────────
def check_contract(rep: Report, consent: dict | None) -> None:
    if consent is None:
        rep.fail("B4-consent-missing", "缺少 consent.json",
                 "html-explainer 的 gate_check.py 会拒绝放行",
                 "跑 brief_init.py 生成，或写 consent.json（七项）")
        return
    if "__error__" in consent:
        rep.fail("B4-consent-broken", f"consent.json 解析失败：{consent['__error__']}",
                 "", "修好 JSON 语法")
        return

    missing, notuser, empty = [], [], []
    for key in REQUIRED_CONSENT:
        item = consent.get(key)
        if not isinstance(item, dict):
            missing.append(key)
            continue
        if not str(item.get("choice") or "").strip():
            empty.append(key)
        if str(item.get("decided_by") or "").strip().lower() != "user":
            notuser.append(key)

    if missing:
        rep.fail("B4-consent-keys", f"consent.json 缺少字段：{', '.join(missing)}",
                 "gate_check.py 要求七项齐全", "补上这些键")
    if empty:
        rep.fail("B4-consent-empty", f"以下确认项 choice 为空：{', '.join(empty)}",
                 "空 choice 会被闸门拒绝", "A4 轮逐项问用户并填入")
    if notuser:
        rep.fail("B4-consent-user", f"以下项 decided_by != 'user'：{', '.join(notuser)}",
                 "必须由用户拍板，不许 agent 代填",
                 "把这些候选摆给用户，拿到答复后改 decided_by 为 'user'")
    if not (missing or empty or notuser):
        rep.ok("B4-consent", f"consent.json 七项齐全且均由用户拍板")

    # 与 html-explainer 的结构兼容性（键名必须一致）
    extra = [k for k in consent if k not in REQUIRED_CONSENT and not k.startswith("_")]
    if extra:
        rep.info("B4-consent-extra", f"consent.json 含额外键：{', '.join(extra)}",
                 "gate_check.py 只查七项，多余键不影响", "")


# ── 主流程 ─────────────────────────────────────────────────────────────
def main() -> int:
    ap = argparse.ArgumentParser(description="video-director 阶段 B 机械体检")
    ap.add_argument("--project", required=True, help="项目目录")
    ap.add_argument("--json", action="store_true", help="输出 JSON")
    ap.add_argument("--no-style-plan", action="store_true", help="不读 style-plan.json")
    args = ap.parse_args()

    proj = os.path.abspath(args.project)
    if not os.path.isdir(proj):
        print(f"[spec_review] 目录不存在：{proj}", file=sys.stderr)
        return 2

    brief = _load_json(os.path.join(proj, "brief.json"))
    consent = _load_json(os.path.join(proj, "consent.json"))
    plan = None if args.no_style_plan else _load_json(os.path.join(proj, "style-plan.json"))

    rep = Report()

    if brief is None:
        rep.fail("B1-brief-missing", "缺少 brief.json",
                 "style_director.py 读它决定情绪/节奏/受众/画幅",
                 "跑：python scripts/brief_init.py --project <目录>")
        brief = {}
    elif "__error__" in brief:
        rep.fail("B1-brief-broken", f"brief.json 解析失败：{brief['__error__']}", "",
                 "修好 JSON 语法")
        brief = {}

    if brief:
        check_self_consistency(rep, brief, consent)
        check_monotony(rep, plan, brief)
        check_camera_and_carry(rep, proj, plan)
    check_contract(rep, consent)

    n_fail = rep.count("FAIL")
    n_warn = rep.count("WARN")
    n_info = rep.count("INFO")

    if args.json:
        print(json.dumps({"project": proj, "summary":
                          {"fail": n_fail, "warn": n_warn, "info": n_info},
                          "items": rep.items}, ensure_ascii=False, indent=2))
        return 1 if n_fail else 0

    icon = {"FAIL": "!!", "WARN": " ~", "INFO": " i", "OK": "OK"}
    print("=" * 72)
    print(f" video-director · 阶段 B 机械体检")
    print(f" 项目：{proj}")
    print("=" * 72)
    for it in rep.items:
        print(f"[{icon.get(it['level'], '??')}] {it['code']}: {it['what']}")
        if it["why"]:
            print(f"      判据：{it['why']}")
        if it["fix"]:
            print(f"      改法：{it['fix']}")
    print("-" * 72)
    print(f" FAIL {n_fail} / WARN {n_warn} / INFO {n_info}")
    if n_fail:
        print(" → 有 FAIL，改完再开工（见 review-rubric.md 的处方）")
    else:
        print(" → 无 FAIL，可以进 B3 可行性复核与人工评审")
    print("=" * 72)
    return 1 if n_fail else 0


if __name__ == "__main__":
    raise SystemExit(main())
