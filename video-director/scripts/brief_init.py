#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""brief_init.py —— video-director 阶段 A 脚手架

在项目目录里生成三份骨架，并打印访谈轮次清单。
**绝不替用户填任何 choice** —— 这是本技能的纪律之一（见 SKILL.md §7）。

用法：
    python brief_init.py --project <项目目录> [--slug 名字] [--topic "主题"] [--force]

产出：
    <项目>/brief.json            -> style_director.py 读
    <项目>/consent.json          -> gate_check.py 读（七项确认）
    <项目>/creative-brief.md     -> 给人看的策划书
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime

try:  # Windows 控制台中文
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
except Exception:
    pass

SKILL_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ASSETS = os.path.join(SKILL_ROOT, "assets")


def _read_asset(name: str) -> str:
    path = os.path.join(ASSETS, name)
    if not os.path.isfile(path):
        raise SystemExit(f"[brief_init] 缺少模板文件：{path}")
    with open(path, encoding="utf-8") as f:
        return f.read()


def _write(path: str, content: str, force: bool) -> str:
    if os.path.exists(path) and not force:
        return f"跳过（已存在）：{path}"
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write(content)
    return f"写入：{path}"


ROUNDS = """
════════════════════════════════════════════════════════════════
  video-director · 阶段 A 访谈轮次（一轮一问，每问给候选）
════════════════════════════════════════════════════════════════

  A1 意图       3 问：观众反应 / 投放平台 / 一句话主题
                └ 读 references/interview-bank.md §1

  A2 参照锚定   2 问：像什么 / 明确不像什么（后者最容易跳过，最值钱）
                └ 读 references/interview-bank.md §2

  A3 感觉翻译   ★ 核心。不给开放题，只给参数表让用户逐行挑
                └ 读 references/feeling-to-params.md（主表 + 三组候选）

  A4 硬约束     凑齐 consent.json 七项，每项都给候选
                └ 读 references/interview-bank.md §3

  A5 可行性     三段式话术：能做到 / 有代价 / 做不到+替代
                └ 读 references/feasibility.md，然后请用户签策划书

────────────────────────────────────────────────────────────────
  逐轮把答案落进 brief.json 的 director 段与 consent.json 的 choice。
  决定人一律写 decided_by = "user"（用户说"你决定"时，回报选择+理由+代价，仍记 user）。
  A5 收尾后跑：python scripts/spec_review.py --project <目录>
════════════════════════════════════════════════════════════════
"""


def main() -> int:
    ap = argparse.ArgumentParser(description="video-director 阶段 A 脚手架")
    ap.add_argument("--project", required=True, help="项目目录（不存在则创建）")
    ap.add_argument("--slug", default=None, help="项目名，用于策划书标题")
    ap.add_argument("--topic", default="", help="主题（可留空，A1 问完再填）")
    ap.add_argument("--force", action="store_true", help="覆盖已存在的文件")
    args = ap.parse_args()

    proj = os.path.abspath(args.project)
    os.makedirs(proj, exist_ok=True)
    slug = args.slug or os.path.basename(proj)
    now = datetime.now().astimezone().isoformat(timespec="seconds")

    # brief.json
    brief = json.loads(_read_asset("brief.template.json"))
    brief["topic"] = args.topic
    brief["director"]["_generated_at"] = now

    # consent.json
    consent = json.loads(_read_asset("consent.template.json"))

    # creative-brief.md
    md = _read_asset("creative-brief.template.md")
    md = md.replace("<项目名>", slug).replace("<ISO>", now)

    print(f"项目目录：{proj}")
    print(_write(os.path.join(proj, "brief.json"),
                 json.dumps(brief, ensure_ascii=False, indent=2) + "\n", args.force))
    print(_write(os.path.join(proj, "consent.json"),
                 json.dumps(consent, ensure_ascii=False, indent=2) + "\n", args.force))
    print(_write(os.path.join(proj, "creative-brief.md"), md, args.force))
    print(ROUNDS)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
