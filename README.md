# ai-video-workflow

> **让 AI 视频不再"单调、像 PPT、图画草率"的那一段前置链路。**
> 把「我想要的是一种感觉」捋成**可执行的参数**，再做**分段验收**与**多层审美审查**，
> 最后插进你自己的渲染管线出片。

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

---

## 解决什么问题

这不是又一个"帮我生成视频"的工具。它补的是**生成之前那一段**——大多数 AI 视频工作流都缺的那一段。

| 症状 | 真实原因 | 本仓库的对应件 |
|---|---|---|
| 动效单调、像 PPT | 提示词里只有 `opacity` + `translateY`，没有运动词汇 | 感觉→参数翻译表 + 单调度五判据 |
| 图画几乎没有 / 很草率 | 策划期"画面主体是什么"是空的 | 片型剧本 + 可行性矩阵 |
| **说不清自己想要什么** | 没人问过"你想要什么感觉"，直接跳到写文案 | 五轮结构化访谈（**每问给候选**） |
| 提示词水平不够 | 形容词没落成机器能执行的字段 | ★ **感觉→参数翻译表** |
| 一版跑到底才发现不对 | 没有中间验收点，改动成本已指数上升 | ★ **16 道分段验收闸门** |
| **要发社交平台、要流量** | 把长视频逻辑直接搬过来，钩子太慢、CTA 不对 | ★ **社交钩子引擎**（钩子三重奏 + 黄金三拍） |
| 主观觉得"不好看"但说不清 | 审美没有分层，人眼在干机器该干的活 | ★ **8 层审美审查** |

**核心立场**：前五层机械审查全绿 ≠ 好看，但**下层不全绿就不该进上层**——用 10 秒的机器层，换掉你几分钟的人眼。

---

## 这是什么

`video-director` 是一个 **Agent Skill**（`SKILL.md` + `references/` + `scripts/` + `assets/`），
运行在 `/video-director` 这类技能入口上，分三个阶段：

```
用户一句模糊需求
      │
      ▼
【A · 策划】结构化访谈 → 感觉翻译 → 候选收敛 → 可行性判定
      │        产出：brief.json · consent.json · creative-brief.md（人话版策划书）
      ▼
【B · 审查】自洽性 / 单调度(PPT 度) / 可行性 / 机械体检
      │        产出：review.md（分级问题 + 参数级改法）
      ▼
【C · 优化】成片后复盘 → 归因到参数层 → 写回 lessons.md → 下次默认更好
      │
      ▼
交给你的渲染管线（见下方「依赖」）
```

三个阶段的共同纪律：**不替用户拍板**、**不给开放题**（一律给 2–4 个候选让人挑）、
**问题必须可执行到参数级**（说不出改哪个字段 = 还没诊断完）。

---

## 核心：感觉 → 参数

这是整个仓库最重要的一张表。用户说不清要什么，不是他的问题——**是缺一张翻译表**。

| 用户会说的话 | 翻译成 | 具体参数落法 |
|---|---|---|
| **「高级感」** | 低饱和 + 大留白 + 慢而稳的运镜 | `mood:calm`；`pace:slow`；动效强度 0.35–0.5；每场 `slowPush` 0.04–0.07 |
| **「别像 PPT」** | 承接 + 运镜 + 禁纯淡入 | 相邻场**至少一个元素跨边界继续动**；**每场 ≥1 可测运镜**；慢动作**禁用纯 `opacity` 淡入** |
| **「要燃」** | 强冲击 + 强过冲 + 快切 | `mood:high`；强度 0.75–0.95；过冲曲线 `back(2.2)`；**必开快门**；且**中段留一拍慢的做落差** |
| **「卡点」** | 硬切锚在重音 + 高密度节拍 | 画面节拍与**音乐重音必须同源**——不同源就不叫卡点 |
| **「电影感」** | 胶片质感 + 强景深 + 慢推 | 低对比 + 颗粒；`depthBlur` 强；长镜头 `slowPush` |
| **「干净」** | 单一强调色 + 大网格 | accent **只给当前重点**；背景只有幕底 + 网格；文字 ≥22px |

完整表（含反面案例与自洽性红线）见 [`video-director/references/feeling-to-params.md`](video-director/references/feeling-to-params.md)。

> **一句话记忆法**：感觉是形容词，参数是数字。
> 说不出数字 = 还没想清楚；说不出感觉 = 让他**挑**，别让他**想**。

---

## 分段验收：16 道闸门

**每生成一段，就停下来验收一段。** 不是"做完给你看"，是逐段签字放行。

关键洞察：**改动成本随阶段指数上升**——所以验收点要顺着它排，越早的关卡越严。

```
A1─A5 策划  B1 体检  V0 钩子  V1 解说词  V2 配音  V3 分镜  V4 参考帧  V5 全帧  V6 打样  V7 混音  V8 全片  V9 封面
  0成本     0       0       低        低       0       30秒     中      中     零重渲   高      低
```

| 关卡 | 产出物 | 你怎么验收 |
|---|---|---|
| A1–A5 策划 | `creative-brief.md` | 读**一页纸**（故意写成人话，不是 JSON），逐行改 |
| B1 机械体检 | `review.md` | FAIL 清零 |
| **V0 钩子与文案** | `script/copy.md` | **读文案 + 自问三题**（第 1 帧抓眼吗 / 第 1 句抛结论吗 / 结尾给了一个动作吗） |
| V1 解说词 | `narration.json` | 读全文 + 时长预估 |
| **V2 配音** | `audio/<id>.mp3`（**一声一文件**） | **逐段听** |
| V3 分镜+风格 | `storyboard.md` + `style-plan.json` | 看表 + 看 `why` 列 |
| **V4 参考帧** | 4–5 张静帧 | **看图**（风格错了只浪费 30 秒） |
| V5 全片静帧 | `frames/*.html` | 三条静态体检全绿 |
| V6 打样 | `preview.mp4` | **看片子**（风格/字号/语速/节奏一次定稿） |
| V7 混音 | `audio/mix.wav` | **听**（音效贴帧 / 说话时音乐让位） |
| V8 全片 | `out/*.mp4` | **连看一遍** |
| V9 封面 | `cover_*.png` | 看图 + 几何实测 |

**闸门是机械的**，不是纸面协议——前置未过、产出物缺失、skip 不写理由，一律拒绝放行：

```console
$ python video-director/scripts/accept.py --project . --pass V2
✗ 拒绝放行 V2：前置未完成
   缺：V1(pending)

$ python video-director/scripts/accept.py --project . --pass A5
✗ 拒绝通过 A5：找不到产出物证据
   缺失：creative-brief.md
```

```bash
python video-director/scripts/accept.py --project . --list        # 进度 + 下一关
python video-director/scripts/accept.py --project . --show V2     # 这关该验什么
python video-director/scripts/accept.py --project . --pass V2 --note "..."
```

详见 [`acceptance-protocol.md`](video-director/references/acceptance-protocol.md)。

---

## 多层审美审查：8 层

把"审美"拆成机器能查的与只能人看的。**越往下越机械、越便宜；下层不全绿，不许进上层。**

| 层 | 名称 | 谁执行 | 管什么 | 它**看不见**什么 |
|---|---|---|---|---|
| L1 | 契约层 | 脚本 | 外链字体 / 色值字面量 / 字幕带压内容 | **几何** |
| L2 | 几何层 | 脚本 | 遮挡 / 越界 / 侵入字幕带 | **家族一致** |
| **L3** | **结构层** | 脚本 | **单调度五判据** | 风格是否协调 |
| L4 | 节拍层 | 脚本 | 节拍引用能否解析 | — |
| L5 | 声画层 | 脚本 | 时长差 / 音量 / 字幕块 | 视觉审美 |
| **L6** | **视觉层** | 视觉模型 | 焦点 / 光 / 碎屑 / 版式平衡 | 跨帧一致性 |
| **L7** | **一致性层** | 模型 + 人 | 家族一致 / 风格轮换协调 | 像不像你要的 |
| L8 | 终审层 | **人** | 好不好看 / 抓不抓人 | — |

**L1–L5 全跑完约 10 秒**，且全在渲染之前。这是最划算的顺序。

### L3 单调度五判据（治"单调"的机械层）

| # | 判据 | 红线 |
|---|---|---|
| 1 | 风格数 | <2 单调 / >4 花 |
| 2 | 同风格连场 | 连续 ≥3 场 |
| 3 | **运镜场次比** | **必须 100%**（不足即 PPT 苗头） |
| 4 | **承接连律** | **为 0 = 幻灯片**（相邻场无元素跨边界） |
| 5 | 动效强度起伏 | 落差 <0.2 = 平 |

**判据 3、4 是核心**。4 成立时，即使每拍只做一个动作，全片也不会读成幻灯片。

> **实测**：一支真实的 10 场讲解片跑下来，抓出 **运镜 0/10、承接 0 处**——
> 这正是主观上"单调、像 PPT"的量化根因。**旧管线从不检查这两条**，所以问题一路带到成片才发现。

详见 [`aesthetic-review-layers.md`](video-director/references/aesthetic-review-layers.md)。

---

## 社交钩子：流量向

社交平台和长视频是**两套引擎**，钩子写法相反。

| | 长视频（B站/YouTube） | 社交平台（抖音/小红书） |
|---|---|---|
| 生死线 | 前 30 秒 | **前 3 秒** |
| 结构 | 黄金七段式 | **黄金三拍** |
| CTA | 三连 + 下次再见 | **平台原生**（评论/收藏/转发） |
| 字数 | 2500–4500 | **60–400** |

### 钩子三重奏（三个通道同时开火，缺一掉完播）

| 通道 | 时机 | 要什么 |
|---|---|---|
| **视觉钩子** | 第 1 帧 | 反常识画面 / 极端特写 / 结果前置（**不能是 logo 或标题卡**） |
| **文字钩子** | 0–3s 同屏 | 与口播**不同角度**（重复 = 浪费一个通道） |
| **声音钩子** | 0–3s | 直接开讲，句首就是结论或疑问 |

### 黄金三拍

```
拍 1 · 钩子（0–3s）    三重奏齐开；抛结论 / 反常识 / 冲突，不是背景介绍
拍 2 · 兑现（3–25s）   每 5–8 秒一个新信息点；分点砍到 1–2 个
拍 3 · 收尾（25–35s）  回扣开头 + 一句可复述结论（转发理由）+ 一个 CTA
```

### 文案三件套串起来用

```
mediastorm-copywriter  出底稿（内容厚度：钩子库 / 数据换算 / 类比）
        ↓
social-hook-engine.md  改写为社交版（黄金三拍 + 平台原生 CTA）
        ↓
humanizer-zh           去 AI 味（排比 / 破折号 / 夸大意义 / 句式等长）
        ↓
spec_review.py B5      机械验收（开场禁语 / 字数 / CTA / 数字）
```

> ⚠️ **一个真实冲突**：飓风要求「结尾落一句金句」，`humanizer-zh` 要求「删除金句」。
> **长视频听飓风的；社交平台听 humanizer 的**——短视频里金句显得说教，掉完播率。
> 判据：读出来像**演讲结尾** → 删；像**跟朋友聊天的随口总结** → 留。

机械可查部分（`spec_review.py` 的 B5 段）：第 1 句含「大家好」→ **FAIL**；
字数超平台区间 → **FAIL**；CTA 含「下次再见」→ **FAIL**。

详见 [`social-hook-engine.md`](video-director/references/social-hook-engine.md)。

---

## 完整链路（11 环节）

仓库里有一份逐环节的完整制作链路，含命令、判据、踩坑：

**建项目 → ① 调研 → ② 时效刷新 → ③ 解说词 → ④ 配音 → ⑤ 时间轴+字幕 →
⑥ 混音(音效/配乐) → ⑦ 分镜+风格编排 → ⑧ 场景构建 → ⑨ 静态体检 → ⑩ 渲染 → ⑪ QC+封面+交付**

其中几处容易踩的：
- **② 时效刷新必须在写解说词之前** —— 改词会让**全部节拍引用的秒数一起位移**
- **④ 配音**支持本地克隆音色（VoiceStudio）与云端 TTS，两者产出**逐字段同构**，下游零改动
- **⑥ 混音**可以 `--mux-only` **零重渲**换音轨——是所有关卡里退回成本最低的
- **⑧ 场景构建**先写 4–5 个**参考帧**再批量派单：**风格错了只浪费 30 秒**
- **⑩ 渲染**前必须确认渲染通道（无损 PNG 对满幅照片是 582ms/帧，换通道可快 4.4–14×）

详见 [`pipeline-full.md`](video-director/references/pipeline-full.md)。

---

## 安装

**方式 1 · 直接复制**（技能是标准 `SKILL.md` 结构，无依赖、无构建步骤）

```bash
git clone https://github.com/<you>/ai-video-workflow.git
cp -r ai-video-workflow/video-director ~/.claude/skills/        # 换成你的技能目录
```

**方式 2 · skills CLI**

```bash
npx skills add <you>/ai-video-workflow
```

装完**新开一个会话**，让 agent 重新扫描技能目录。

## 快速开始

```bash
# 1) 生成三份骨架（不替你填任何选择）
python video-director/scripts/brief_init.py --project <项目目录> --slug 我的片子

# 2) 走访谈（五轮，一轮一问，每问给候选）——照 SKILL.md 与 interview-bank.md
#    产出：brief.json / consent.json / creative-brief.md

# 3) 机械体检
python video-director/scripts/spec_review.py --project <项目目录>

# 4) 逐段验收
python video-director/scripts/accept.py --project <项目目录> --list
```

三个脚本**零第三方依赖**（纯标准库），Windows / macOS / Linux 通用。

---

## 依赖与生态

本仓库**只管"要做什么 + 会不会难看/做不到"**，渲染与执行交给你的管线。
下面这些是**独立项目**，请从各自上游安装——本仓库只做衔接与链接，**不包含它们的代码**：

| 项目 | 作用 | 与本仓库的关系 |
|---|---|---|
| [imfangli/mediastorm-copywriter](https://github.com/imfangli/mediastorm-copywriter) | 影视飓风式中文口播稿（钩子库 / 黄金七段 / 数据换算 / 类比） | **文案层（上游）**：长视频直接可用；短视频取其素材后再压缩 |
| [blader/humanizer](https://github.com/blader/humanizer) | 去 AI 写作痕迹（基于维基百科 AI 写作特征） | **文案层（收尾）**：定稿前最后一道 |
| [OneMoh/html-explainer](https://github.com/OneMoh/html-explainer) | HTML+GSAP 逐帧渲染管线（调研→配音→渲染→QC→封面） | 本仓库的**主要下游**：`brief.json` / `consent.json` 直接喂给它 |
| [Vincentwei1021/video-shotcraft](https://github.com/Vincentwei1021/video-shotcraft) | 125 张镜头配方卡 / 150 shots | 分镜期查卡、写帧时抄动作 |
| [iart-ai/motion-design-skills](https://github.com/iart-ai/motion-design-skills) | 动画原理 / 色彩 / 构图 / 卡点 / 背景 | 参数拿不准时的查证来源 |
| [howseen-ai/claude-motion-design](https://github.com/howseen-ai/claude-motion-design) | `seek(t)` 引擎、运动模糊、SFX 峰值落点 | 同构参考实现 |
| [debpalash/VoiceStudio](https://github.com/debpalash/VoiceStudio) | 全本地语音克隆/TTS（AGPL-3.0） | 配音引擎之一（可选） |

> 本仓库对 `html-explainer` 的契约（`brief.json` 五字段、`consent.json` 七项）做了适配，
> 但**不包含也不重新分发**它的任何代码。

---

## 设计原则

1. **不替用户拍板。** 记忆里"上次挺好用"不构成这次的选择。
2. **不给开放题。** 弱模型 + 用户说不清 = 必须给候选。开放式问题在这里是缺陷，不是礼貌。
3. **先前置，后执行。** 参数没定就不写文案，等于用错误的规格生产。
4. **审查前置。** 简报期改一个词是 0 成本，渲完再改是整片重来。
5. **问题必须可执行到参数级。** "节奏有点平"不合格；"第 4–7 场强度都是 0.5，改成 0.45/0.72/0.38/0.65"合格。
6. **闸门要机械。** 纸面规则会被静默跳过——凡是"必须停下"的地方，都要有一个**退出码非 0** 的脚本。
7. **复盘要落到闸门。** 教训能机械查的就写进脚本，别只写在文档里。
8. **下层不全绿不进上层。** 用机器能查的东西去耗人眼，是浪费。

---

## 仓库结构

```
ai-video-workflow/
├── README.md
├── LICENSE
└── video-director/                    ← 技能本体，拷进技能目录即可用
    ├── SKILL.md                       技能入口（三阶段 + 纪律）
    ├── references/
    │   ├── feeling-to-params.md       ★ 感觉→参数翻译表
    │   ├── social-hook-engine.md       ★ 社交钩子引擎（流量向）
    │   ├── acceptance-protocol.md     ★ 16 道分段验收
    │   ├── aesthetic-review-layers.md ★ 8 层审美审查
    │   ├── pipeline-full.md           ★ 完整链路 11 环节
    │   ├── interview-bank.md          访谈问题库（分轮次、带候选）
    │   ├── genre-playbooks.md         五种片型剧本
    │   ├── feasibility.md             可行性矩阵 + 替代话术
    │   ├── review-rubric.md           审查评分表
    │   └── lessons.md                 复盘台账（可优化入口）
    ├── scripts/
    │   ├── brief_init.py              生成骨架，不代填
    │   ├── spec_review.py             机械体检（自洽性 + 单调度五判据）
    │   └── accept.py                  分段验收闸门
    └── assets/                        三份模板（brief / consent / 策划书）
```

---

## 许可与致谢

本仓库原创内容（技能、文档、脚本）采用 **MIT**，见 [LICENSE](LICENSE)。

文档中的方法论参考并衔接了若干优秀的开源项目（见上方「依赖与生态」），
**它们的代码不包含在本仓库内**，各自适用其原有许可证。特别致谢
[html-explainer](https://github.com/OneMoh/html-explainer)（Moh, MIT）——
本仓库的验收与审查面向它的产出物设计。

---

<sub>English: **ai-video-workflow** — the missing pre-production layer for AI video: turn "I want it to feel premium" into executable parameters, gate every segment with human acceptance, and review aesthetics in 8 layers from mechanical to human. Ships as the `video-director` agent skill.</sub>
