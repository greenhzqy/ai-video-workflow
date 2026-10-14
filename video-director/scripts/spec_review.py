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


# ── B5 社交钩子层（流量向，见 social-hook-engine.md）────────────────────
# 平台画像：字数区间 / 画幅 / 节奏 / 强度建议
PLATFORM_PROFILE = {
    "抖音":   dict(chars=(60, 200),  aspect="9:16", pace="fast",   inten=(0.75, 0.95), hook_win=1),
    "小红书": dict(chars=(150, 400), aspect="9:16", pace="medium", inten=(0.60, 0.80), hook_win=3),
    "视频号": dict(chars=(120, 350), aspect="16:9", pace="medium", inten=(0.55, 0.75), hook_win=3),
    "b站":    dict(chars=(0, 0),     aspect="16:9", pace="medium", inten=(0.45, 0.65), hook_win=30),
    "bilibili": dict(chars=(0, 0),   aspect="16:9", pace="medium", inten=(0.45, 0.65), hook_win=30),
    "youtube": dict(chars=(0, 0),    aspect="16:9", pace="medium", inten=(0.45, 0.65), hook_win=30),
}

# 开场禁语（社交平台：前 3 秒出现即掉完播）
BANNED_OPENERS = ["大家好", "今天我们", "这期视频", "今天我们来聊", "哈喽", "hello everyone",
                  "欢迎来到", "我是", "咱们今天"]

# 社交平台禁用的 CTA（B站话术，在短视频里是完播率杀手）
BANNED_CTA = ["下次再见", "我们下次见", "下期再见"]

# 平台原生 CTA 关键词（至少要命中一个才算有 CTA）
NATIVE_CTA = ["评论区", "收藏", "关注", "转发", "点赞", "蹲一个", "告诉我", "你站哪边",
              "留言", "三连", "投币", "分享给"]


def _load_copy(proj: str) -> tuple[str, str]:
    """取文案全文。优先 script/copy.md，退回 narration.json 拼接。
    返回 (全文, 来源说明)。"""
    p = os.path.join(proj, "script", "copy.md")
    if os.path.isfile(p):
        with open(p, encoding="utf-8-sig") as f:
            return f.read(), "script/copy.md"

    p = os.path.join(proj, "narration.json")
    data = _load_json(p)
    if isinstance(data, list) and data:
        parts = []
        for item in data:
            t = str((item or {}).get("text") or "")
            parts.append(t.replace("|", ""))
        return "\n".join(parts), "narration.json"
    return "", ""


def check_social_hooks(rep: Report, proj: str, brief: dict, consent: dict | None) -> None:
    """社交平台钩子与文案体检。只在平台判定为社交平台时启用严格判据。"""
    director = brief.get("director") or {}
    platforms = director.get("platform") or []
    if isinstance(platforms, str):
        platforms = [platforms]
    plat = ""
    for p in platforms:
        key = str(p).strip().lower()
        if key in PLATFORM_PROFILE:
            plat = key
            break
    # 也允许从 consent 的 form/cover 反推
    if not plat and consent:
        blob = json.dumps(consent, ensure_ascii=False).lower()
        for k in PLATFORM_PROFILE:
            if k in blob:
                plat = k
                break

    prof = PLATFORM_PROFILE.get(plat) if plat else None
    is_social = bool(prof and prof["chars"] != (0, 0))

    text, src = _load_copy(proj)
    if not text:
        rep.info("B5-copy", "未找到文案（script/copy.md 或 narration.json），钩子体检跳过",
                 "社交平台文案必须单独过一遍钩子判据",
                 "写好文案后重跑本脚本")
        return

    flat = re.sub(r"\s+", "", text)
    # 去掉 markdown 标记与标题行，抓"第一句"
    lines = [ln.strip() for ln in text.splitlines()
             if ln.strip() and not ln.strip().startswith("#")]
    first_raw = re.sub(r"^[\-\*\d\.\)\s]+", "", lines[0]) if lines else ""
    # 句边界：中英文句号/问号/感叹号/分号/冒号/逗号都算（前 3 秒只看第一口气）
    first = re.split(r"[。！？；：，,.!?;:]", first_raw)[0].strip()

    # 判据 1：开场禁语（社交平台才严格）
    hit = [w for w in BANNED_OPENERS if w.lower() in first.lower()]
    if hit:
        lvl = "FAIL" if is_social else "WARN"
        rep.add(lvl, "B5-opener",
                f"第一句含开场禁语：{', '.join(hit)}",
                "前 3 秒出现铺垫语会直接掉完播率" + ("（社交平台硬红线）" if is_social else ""),
                "第 1 句直接抛结论/反常识/冲突，删掉所有铺垫")

    # 判据 2：第 1 句长度
    if len(first) > 20:
        rep.warn("B5-first-len", f"第一句 {len(first)} 字（>20）",
                 "前 3 秒读不完，文字钩子失效", "压到 20 字内，把修饰全砍")

    # 判据 3：字数落在平台区间
    if is_social:
        lo, hi = prof["chars"]
        n = len(flat)
        if n < lo:
            rep.warn("B5-length", f"文案 {n} 字，低于 {plat} 建议下限 {lo}",
                     "太短撑不起信息量，容易被判定低质",
                     f"扩到 {lo}–{hi} 字，或换更短的发布形式（图文/短钩子）")
        elif n > hi:
            rep.fail("B5-length", f"文案 {n} 字，超出 {plat} 上限 {hi}",
                     "超出会把视频拖长，完播率崩",
                     "砍到 1–2 个信息点；把次要内容拆成下一条")
        else:
            rep.ok("B5-length", f"文案 {n} 字（{plat} 区间 {lo}–{hi}）")
    else:
        rep.info("B5-length", f"文案 {len(flat)} 字",
                 "未判定为社交平台，跳过平台字数判据",
                 "若发抖音/小红书，在 brief.director.platform 里写明")

    # 判据 4：CTA
    banned = [w for w in BANNED_CTA if w in text]
    if banned and is_social:
        rep.fail("B5-cta", f"CTA 含 B站话术：{', '.join(banned)}",
                 "社交平台说「下次再见」是完播率杀手",
                 "换成平台原生 CTA：评论引导（抖音）/ 收藏引导（小红书）/ 转发引导（视频号）")
    native = [w for w in NATIVE_CTA if w in text]
    if is_social:
        if not native:
            rep.warn("B5-cta-missing", "未见平台原生 CTA",
                     "没有 CTA = 放弃互动权重（评论/收藏直接影响推流）",
                     "结尾 3 秒加一个动作：" + " / ".join(NATIVE_CTA[:6]))
        elif len(native) > 2:
            rep.warn("B5-cta-many", f"CTA 出现 {len(native)} 个动作：{', '.join(native)}",
                     "给两个以上动作，用户一个都不做",
                     "只保留一个最主要的动作")
        else:
            rep.ok("B5-cta", f"平台原生 CTA：{', '.join(native)}")

    # 判据 6：数字或具体名词
    if not re.search(r"\d", text):
        rep.warn("B5-specific", "全文没有任何数字",
                 "含具体数字的标题/句子完播与点击显著更高",
                 "至少加一个数字（时间/数量/价格/比例）")

    # 判据 7：结尾回扣开头（闭环）—— 粗判：结尾 60 字与前 60 字有无共同实词
    if len(flat) > 120:
        head, tail = flat[:60], flat[-60:]
        common = set(re.findall(r"[\u4e00-\u9fa5]{2}", head)) & \
                 set(re.findall(r"[\u4e00-\u9fa5]{2}", tail))
        if not common:
            rep.info("B5-closure", "结尾与开头没有明显回扣",
                     "闭环能提升完播与记忆点",
                     "结尾用开头那个词/意象收一下")

    # 平台参数自洽（画幅/节奏/强度）
    if prof:
        aspect = (brief.get("aspect") or "").strip()
        if aspect and prof["aspect"] not in aspect.replace("：", ":"):
            rep.warn("B5-aspect", f"brief.aspect={aspect}，与 {plat} 常用 {prof['aspect']} 不一致",
                     "画幅不符会被平台裁切或留黑边",
                     f"改成 {prof['aspect']}，封面张数也要跟着调整")
        lo_i, hi_i = prof["inten"]
        curve = director.get("intensity_curve") or []
        vals = [_as_intensity(v) for v in curve]
        vals = [v for v in vals if v is not None]
        if vals:
            mx = max(vals)
            if mx < lo_i:
                rep.warn("B5-intensity", f"最高强度 {mx:.2f}，低于 {plat} 建议 {lo_i}–{hi_i}",
                         "社交平台需要更强的动势抓注意力",
                         f"开场强度提到 {lo_i}+（钩子段落）")


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
        check_social_hooks(rep, proj, brief, consent)
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
