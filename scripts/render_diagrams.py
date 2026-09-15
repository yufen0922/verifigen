"""Render the hand-laid-out documentation diagrams using only the standard library.

Coordinates are deliberately explicit: the feedback loop and outcome routes must
remain readable at GitHub's article width. See docs/assets/README.md for sources.
"""

from __future__ import annotations

import argparse
from html import escape
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FONT = "Inter,Segoe UI,PingFang SC,Microsoft YaHei,Arial,sans-serif"
PALETTES = {
    "light": {
        "bg": "#ffffff",
        "panel": "#f6f8fa",
        "ink": "#182230",
        "muted": "#586779",
        "line": "#d7dfe7",
        "route": "#7a899a",
        "blue": "#245dc1",
        "blue_bg": "#edf3ff",
        "teal": "#087d78",
        "teal_bg": "#eaf8f5",
        "amber": "#a35a08",
        "amber_bg": "#fff5e6",
        "green": "#1b7947",
        "green_bg": "#eaf6ee",
        "red": "#b74350",
        "red_bg": "#fff0f2",
    },
    "dark": {
        "bg": "#0d1117",
        "panel": "#161b22",
        "ink": "#edf2f7",
        "muted": "#a5b3c2",
        "line": "#34404e",
        "route": "#91a0b2",
        "blue": "#88b2ff",
        "blue_bg": "#182844",
        "teal": "#70d8ca",
        "teal_bg": "#142f2c",
        "amber": "#edbd70",
        "amber_bg": "#34291a",
        "green": "#83d8a3",
        "green_bg": "#173125",
        "red": "#f099a5",
        "red_bg": "#361e26",
    },
}


class Drawing:
    def __init__(self, theme: str, language: str, title: str, description: str, height: int):
        self.p = PALETTES[theme]
        self.language = language
        self.parts = [
            f'<svg xmlns="http://www.w3.org/2000/svg" width="1280" height="{height}" '
            f'viewBox="0 0 1280 {height}" role="img" aria-labelledby="title desc" '
            f'xml:lang="{language}">',
            f'<title id="title">{escape(title)}</title><desc id="desc">{escape(description)}</desc>',
            "<defs>",
        ]
        for name in ("route", "blue", "teal", "amber", "green", "red"):
            self.parts.append(
                f'<marker id="arrow-{name}" markerWidth="8" markerHeight="8" refX="6" '
                f'refY="4" orient="auto" markerUnits="userSpaceOnUse">'
                f'<path d="M1 1 L6 4 L1 7" fill="none" stroke="{self.p[name]}" '
                'stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/></marker>'
            )
        self.parts.append("</defs>")
        self.rect(0, 0, 1280, height, "bg", radius=0)

    def choose(self, en: str, zh: str) -> str:
        return zh if self.language == "zh" else en

    def rect(self, x, y, width, height, fill="bg", stroke=None, radius=8):
        border = f' stroke="{self.p[stroke]}" stroke-width="1.2"' if stroke else ""
        self.parts.append(
            f'<rect x="{x}" y="{y}" width="{width}" height="{height}" rx="{radius}" '
            f'fill="{self.p[fill]}"{border}/>'
        )

    def text(self, x, y, lines, size=20, color="ink", weight=400, width=1200, anchor="start"):
        if isinstance(lines, str):
            lines = [lines]
        spans = "".join(
            f'<tspan x="{x}" dy="{0 if i == 0 else size * 1.4}">{escape(line)}</tspan>'
            for i, line in enumerate(lines)
        )
        self.parts.append(
            f'<text x="{x}" y="{y}" font-family="{FONT}" font-size="{size}" '
            f'font-weight="{weight}" fill="{self.p[color]}" text-anchor="{anchor}" '
            f'data-max-width="{width}">{spans}</text>'
        )

    def path(self, d, color="route", arrow=True, dashed=False):
        marker = f' marker-end="url(#arrow-{color})"' if arrow else ""
        dash = ' stroke-dasharray="5 5"' if dashed else ""
        self.parts.append(
            f'<path d="{d}" fill="none" stroke="{self.p[color]}" stroke-width="2" '
            f'stroke-linecap="round" stroke-linejoin="round"{marker}{dash}/>'
        )

    def header(self, number, title, subtitle):
        self.rect(40, 34, 7, 20, "teal", radius=2)
        self.text(59, 50, "VERIFIGEN", 17, weight=700, width=200)
        self.text(1240, 50, number, 15, "muted", width=300, anchor="end")
        self.text(40, 98, title, 34, weight=650, width=1200)
        self.text(40, 131, subtitle, 19, "muted", width=1200)
        self.path("M40 158 H1240", "line", arrow=False)

    def node(self, x, title, subtitle, number, color):
        self.rect(x, 284, 156, 126, f"{color}_bg", "line")
        self.rect(x + 16, 300, 26, 24, color, radius=4)
        self.text(x + 29, 317, number, 14, "bg", 700, 24, "middle")
        self.text(x + 16, 350, title, 23, color, 650, 124)
        self.text(x + 16, 377, subtitle, 17, "muted", width=128)

    def finish(self) -> str:
        return "\n".join(self.parts + ["</svg>", ""])


def overview(theme: str, language: str) -> str:
    d = Drawing(
        theme,
        language,
        "VerifiGen architecture",
        "Scenario adapters supply a shared task. "
        "Generator, Judge, deterministic gates and policy form a bounded loop. "
        "Repair returns to Judge; only reviewed output or fallback reaches the caller.",
        824,
    )
    t = d.choose
    d.header(
        "01 / ARCHITECTURE",
        t("One quality loop. Multiple scenarios.", "一套质量闭环，复用到多个场景。"),
        t(
            "Explicit context. Structured feedback. Controlled output.",
            "显式业务上下文 · 结构化修复反馈 · 受控输出",
        ),
    )
    d.text(40, 196, t("SCENARIOS", "场景适配层"), 15, "muted", 650, 196)
    for y, label in [
        (236, t("RAG answers", "RAG 问答")),
        (266, t("Customer replies", "客服回复")),
        (296, t("Data reports", "数据报告")),
    ]:
        d.rect(40, y - 11, 5, 5, "teal", radius=1)
        d.text(57, y, label, 19, width=180)
    d.path("M40 314 H226", "line", False)
    d.text(40, 348, "QualityTask", 23, "ink", 650, 188)
    d.text(
        40,
        383,
        [
            t("Task + evidence", "原始任务与业务证据"),
            t("Review criteria", "逐项质量规则"),
            t("Output schema", "输出 Schema"),
            t("Renderer + fallback", "渲染器与兜底文案"),
        ],
        18,
        "muted",
        width=190,
    )
    d.text(40, 581, t("Replace the adapter.", "替换场景适配器"), 17, "teal", 600, 190)
    d.text(40, 606, t("Reuse the runtime.", "复用同一运行时"), 17, "muted", width=190)

    d.rect(264, 196, 728, 432, "panel", "line")
    d.text(284, 228, "QualityLoop", 23, weight=650, width=290)
    d.text(972, 227, t("BOUNDED AGENT LOOP", "有界 Agent Loop"), 15, "teal", 650, 270, "end")
    d.text(
        284,
        258,
        t(
            "Each role receives an isolated task snapshot.",
            "每个角色接收独立的任务快照，复用相同证据与约束。",
        ),
        17,
        "muted",
        width=688,
    )
    d.path("M226 344 H284")
    for start, end in [(440, 464), (620, 644), (800, 824)]:
        d.path(f"M{start} 344 H{end}")
    d.node(
        284, "Generator", [t("New draft", "生成候选"), t("or initial", "或接收初稿")], "01", "blue"
    )
    d.node(
        464,
        "Judge",
        [t("Score + status", "分数与判定"), t("Issue list", "结构化问题")],
        "02",
        "blue",
    )
    d.node(
        644,
        "Gates",
        [t("JSON Schema", "JSON Schema"), t("Business rules", "业务校验关卡")],
        "03",
        "teal",
    )
    d.node(
        824, "Policy", [t("Release / stop", "输出 / 修复"), t("or repair", "或终止")], "04", "teal"
    )
    d.path("M980 344 H1016", "green")
    d.text(1016, 227, t("OUTPUT", "输出边界"), 15, "muted", 650, 224)
    d.rect(1016, 284, 224, 126, "green_bg", "line")
    d.text(1034, 320, t("Reviewed output", "审核后输出"), 21, "green", 650, 190)
    d.text(
        1034,
        353,
        [t("Pass + score threshold", "判定通过且评分达标"), t("All gates clear", "全部关卡通过")],
        17,
        "muted",
        width=192,
    )

    # Keep the repair cycle inside the runtime; route termination outside it.
    d.path("M902 410 V536 H800", "amber")
    d.text(822, 514, t("issues", "问题反馈"), 16, "amber", width=78)
    d.path("M902 444 H1000 V548 H1016", "red")
    d.text(938, 436, t("stop", "终止"), 16, "red", width=55)
    d.path("M542 488 V410", "amber")
    d.text(556, 458, t("re-judge", "重新校验"), 17, "amber", 600, 160)
    d.rect(464, 488, 336, 96, "amber_bg", "line")
    d.text(484, 522, "LLM Repair", 23, "amber", 650, 296)
    d.text(
        484,
        554,
        t("Context + structured issue list", "结合上下文，按问题清单定向修复"),
        18,
        "muted",
        width=296,
    )
    d.text(
        284,
        608,
        t(
            "unknown skips gates and stops; changed repairs return to Judge.",
            "unknown 跳过关卡并终止；修改后的候选必须复检。",
        ),
        16,
        "muted",
        width=688,
    )
    d.rect(1016, 488, 224, 126, "red_bg", "line")
    d.text(1034, 525, t("Fallback", "场景化兜底"), 23, "red", 650, 188)
    d.text(
        1034,
        558,
        [
            t("Reason-specific text", "按终止原因选择文案"),
            t("No candidate released", "不发布未通过的候选"),
        ],
        17,
        "muted",
        width=192,
    )

    d.rect(40, 654, 1200, 100, "panel", "line")
    d.text(60, 689, "Harness", 22, weight=650, width=200)
    d.text(60, 720, t("Runtime controls", "运行时控制层"), 17, "muted", width=200)
    controls = [
        (284, t("Budgets", "执行预算"), t("Calls / rounds / tokens", "调用次数 / 轮次 / Token")),
        (
            606,
            t("Termination", "终止控制"),
            t("Timeout / repeat / plateau", "超时 / 重复 / 评分停滞"),
        ),
        (
            956,
            t("Run-local state", "独立运行状态"),
            t("Snapshots / reports / trace", "快照 / 关卡报告 / Trace"),
        ),
    ]
    for x, title, body in controls:
        d.path(f"M{x - 18} 676 V732", "line", False)
        d.text(x, 689, title, 20, weight=600, width=276)
        d.text(x, 720, body, 17, "muted", width=276)
    d.text(40, 790, t("EVALUATION", "独立评测"), 14, "teal", 650, 190)
    d.text(
        208,
        790,
        t(
            "Scenario oracles + model verdicts + gate ablations. Evaluation stays outside the loop.",
            "场景 Oracle、模型原始判定与关卡消融；评测真值不参与运行时修复。",
        ),
        17,
        "muted",
        width=1032,
    )
    return d.finish()


def workflow(theme: str, language: str) -> str:
    d = Drawing(
        theme,
        language,
        "VerifiGen output decisions",
        "Assessment feeds three decisions: "
        "release when status, score and gates pass; repair actionable failures within limits; "
        "otherwise return fallback. Every changed repair is reviewed again.",
        860,
    )
    t = d.choose
    d.header(
        "02 / DECISION FLOW",
        t("Score. Repair. Stop.", "评分、修复与兜底，各有明确条件。"),
        t(
            "The policy owns the next action. The model supplies evidence and feedback.",
            "模型提供判定与反馈，运行时决定下一步行动。",
        ),
    )
    for x, label in [
        (40, t("01 / ASSESS", "01 / 获取有效判定")),
        (424, t("02 / APPLY POLICY", "02 / 策略决策")),
        (944, t("03 / EXECUTE", "03 / 执行动作")),
    ]:
        d.text(x, 194, label, 15, "muted", 650, 330)

    d.rect(40, 220, 312, 400, "panel", "line")
    d.text(60, 257, t("Candidate + context", "候选内容 + 业务上下文"), 23, weight=650, width=274)
    d.text(
        60,
        288,
        t("Generated or supplied draft", "来自生成器，或调用方传入初稿"),
        17,
        "muted",
        width=274,
    )
    d.path("M60 310 H332", "line", False)
    d.text(60, 347, "LLM Judge", 23, "blue", 650, 272)
    d.text(
        60,
        378,
        [
            t("Status + score + issue list", "判定状态 + 评分 + 问题清单"),
            t("Original verdict kept for audit", "保留模型原始判定，便于审计"),
        ],
        17,
        "muted",
        width=272,
    )
    d.path("M60 425 H332", "line", False)
    d.text(60, 461, t("Deterministic gates", "确定性校验关卡"), 22, "teal", 650, 272)
    d.text(
        60,
        493,
        [
            t("Schema first, business rules next", "先校验 Schema，再检查业务规则"),
            t("Violations become repair issues", "违规项合并到本轮修复反馈"),
        ],
        17,
        "muted",
        width=272,
    )
    d.text(
        60,
        584,
        t("unknown: skip gates, then stop", "unknown：跳过关卡，直接终止"),
        17,
        "red",
        width=272,
    )

    d.path("M352 420 H384", arrow=False)
    d.path("M384 278 V580", arrow=False)
    for y in [278, 434, 590]:
        if y == 590:
            d.path("M384 580 V590", arrow=False)
        d.path(f"M384 {y} H424")

    rows = [
        (
            220,
            "green",
            t("All release conditions met", "满足全部输出条件"),
            [
                t("pass + score at or above threshold", "pass 且评分达到阈值"),
                t("Schema and business gates are clear", "Schema 与业务关卡均通过"),
            ],
            t("Render + release", "渲染并输出"),
            [
                t("Reviewed candidate", "已审核的候选内容"),
                t("result.output + result.text", "result.output + result.text"),
            ],
        ),
        (
            376,
            "amber",
            t("Actionable failure, within limits", "存在可修复问题，且允许继续"),
            [
                t("fail + issues + remaining repair rounds", "fail + 问题清单 + 剩余修复轮次"),
                t("Optional score plateau stop not reached", "未触发可选的评分停滞终止"),
            ],
            t("Repair", "定向修复"),
            [
                t("Same evidence, new draft", "依据相同证据修复问题"),
                t("Re-check the changed draft", "修改后的候选重新校验"),
            ],
        ),
        (
            532,
            "red",
            t("Cannot release or continue", "无法输出，或无法继续修复"),
            [
                t("unknown / low-score pass", "unknown / 低分通过"),
                t("Repair limit / optional score plateau", "修复轮次耗尽 / 可选评分停滞"),
            ],
            t("Fallback", "返回兜底"),
            [
                t("Text selected by stop reason", "按原因返回场景文案"),
                t("result.output = None", "result.output = None"),
            ],
        ),
    ]
    for y, color, title, body, action, detail in rows:
        d.rect(424, y, 452, 116, f"{color}_bg", "line")
        d.rect(424, y + 16, 3, 84, color, radius=1)
        d.text(444, y + 34, title, 22, color, 600, 412)
        d.text(444, y + 66, body, 18, "muted", width=410)
        d.path(f"M876 {y + 58} H944", color)
        d.rect(944, y, 280, 116, f"{color}_bg", "line")
        d.text(964, y + 34, action, 23, color, 650, 240)
        d.text(964, y + 66, detail, 17, "muted", width=240)

    d.path("M1224 434 H1252 V700 H196 V620", "amber")
    d.rect(443, 682, 477, 35, "bg", radius=0)
    d.text(
        682,
        706,
        t("Changed candidate returns to Judge + Gates", "候选发生变化 → 重新经过 Judge 与关卡"),
        20,
        "amber",
        600,
        470,
        "middle",
    )
    d.path("M1084 492 V532", "red")
    d.text(1098, 517, t("repeat", "候选重复"), 16, "red", width=118)
    d.rect(40, 746, 1200, 74, "panel", "line")
    d.text(60, 778, t("AT ANY STAGE", "任意阶段"), 15, "red", 650, 180)
    d.text(
        256,
        778,
        t(
            "Call / token limit, timeout, provider error or unavailable gate → fallback.",
            "调用或 Token 限制、超时、模型异常、校验不可用 → 兜底。",
        ),
        18,
        "muted",
        width=960,
    )
    d.text(
        256,
        804,
        t(
            "Renderer errors also fall back. The best historical candidate is diagnostic only.",
            "渲染失败同样兜底；历史最高分候选仅供诊断，不绕过输出门禁。",
        ),
        17,
        "muted",
        width=960,
    )
    return d.finish()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="Check committed SVGs without writing")
    args = parser.parse_args()
    destination = ROOT / "docs" / "assets"
    stale = []
    for name, render in (("architecture", overview), ("decision-flow", workflow)):
        for language in ("en", "zh"):
            for theme in ("light", "dark"):
                path = destination / f"{name}-{language}-{theme}.svg"
                source = render(theme, language)
                if args.check:
                    if not path.exists() or path.read_text(encoding="utf-8") != source:
                        stale.append(str(path.relative_to(ROOT)))
                else:
                    destination.mkdir(parents=True, exist_ok=True)
                    path.write_text(source, encoding="utf-8")
    if stale:
        parser.exit(1, "Stale diagrams: " + ", ".join(stale) + "\n")
    print("8 SVG diagrams verified." if args.check else "8 SVG diagrams generated.")


if __name__ == "__main__":
    main()
