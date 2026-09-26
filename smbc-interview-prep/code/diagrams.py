"""Render the three chat diagrams as PNGs (light theme, explicit colours)."""
import cairosvg

C = {
    "gray":   ("#F1EFE8", "#5F5E5A", "#444441", "#5F5E5A"),
    "purple": ("#EEEDFE", "#534AB7", "#3C3489", "#534AB7"),
    "teal":   ("#E1F5EE", "#0F6E56", "#085041", "#0F6E56"),
}
ARROW = "#888780"
FONT = "DejaVu Sans"

def head(h, title):
    return (f'<svg xmlns="http://www.w3.org/2000/svg" width="680" height="{h}" viewBox="0 0 680 {h}">'
            f'<title>{title}</title><rect width="680" height="{h}" fill="#FFFFFF"/>'
            '<defs><marker id="a" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="6" markerHeight="6" '
            f'orient="auto-start-reverse"><path d="M2 1L8 5L2 9" fill="none" stroke="{ARROW}" '
            'stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/></marker></defs>')

def box(x, y, w, h, title, sub, col, extra_lines=None):
    fill, stroke, tc, sc = C[col]
    s = f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="8" fill="{fill}" stroke="{stroke}" stroke-width="0.8"/>'
    cx = x + w / 2
    if extra_lines:  # custom multi-line layout: list of (text, is_title, y)
        for t, is_t, ty in extra_lines:
            s += (f'<text x="{cx}" y="{ty}" text-anchor="middle" dominant-baseline="central" font-family="{FONT}" '
                  f'font-size="{14 if is_t else 12}" font-weight="{"bold" if is_t else "normal"}" '
                  f'fill="{tc if is_t else sc}">{t}</text>')
        return s
    if sub:
        s += (f'<text x="{cx}" y="{y + h/2 - 10}" text-anchor="middle" dominant-baseline="central" '
              f'font-family="{FONT}" font-size="14" font-weight="bold" fill="{tc}">{title}</text>')
        s += (f'<text x="{cx}" y="{y + h/2 + 10}" text-anchor="middle" dominant-baseline="central" '
              f'font-family="{FONT}" font-size="12" fill="{sc}">{sub}</text>')
    else:
        s += (f'<text x="{cx}" y="{y + h/2}" text-anchor="middle" dominant-baseline="central" '
              f'font-family="{FONT}" font-size="14" font-weight="bold" fill="{tc}">{title}</text>')
    return s

def line(x1, y1, x2, y2, head=True):
    m = ' marker-end="url(#a)"' if head else ""
    return f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" stroke="{ARROW}" stroke-width="1.5"{m}/>'

def path(d, head=True):
    m = ' marker-end="url(#a)"' if head else ""
    return f'<path d="{d}" fill="none" stroke="{ARROW}" stroke-width="1.5"{m}/>'

def legend(items, y):
    s = ""
    for x, col, label in items:
        fill, stroke, _, _ = C[col]
        s += f'<rect x="{x}" y="{y}" width="14" height="14" rx="3" fill="{fill}" stroke="{stroke}" stroke-width="0.8"/>'
        s += (f'<text x="{x + 22}" y="{y + 7}" dominant-baseline="central" font-family="{FONT}" '
              f'font-size="12" fill="#5F5E5A">{label}</text>')
    return s

def render(svg, name):
    cairosvg.svg2png(bytestring=svg.encode(), write_to=name, scale=3)
    print("wrote", name)

# 1. LLM evolution -----------------------------------------------------------
stages = [
    ("1990s–2012 · Statistical models", "N-grams, count-based prediction", "gray"),
    ("2013 · Word embeddings", "Word2vec: meaning as vectors", "gray"),
    ("2014–16 · RNNs and LSTMs", "Seq2seq, first attention", "gray"),
    ("2017 · Transformer", "Attention replaces recurrence", "purple"),
    ("2018–19 · Pretrained models", "BERT, GPT-1/2, T5", "purple"),
    ("2020 · Scale: GPT-3", "Few-shot, scaling laws", "purple"),
    ("2022 · Alignment: ChatGPT", "Instruction tuning, RLHF", "purple"),
    ("2023 · Multimodal and open weights", "GPT-4, Llama, RAG, tools", "purple"),
    ("2024–25 · Reasoning models", "o1, DeepSeek-R1, long context", "purple"),
    ("2025–26 · Agentic AI", "Tools, MCP, computer use", "purple"),
]
svg = head(840, "Evolution of LLMs")
for i, (t, s, c) in enumerate(stages):
    y = 40 + i * 76
    svg += box(140, y, 400, 56, t, s, c)
    if i < len(stages) - 1:
        svg += line(340, y + 58, 340, y + 73)
svg += legend([(190, "gray", "Pre-transformer"), (360, "purple", "Transformer era")], 802)
svg += "</svg>"
render(svg, "diagram_llm_evolution.png")

# 2. Platform layers ---------------------------------------------------------
svg = head(530, "Bank AI platform reference architecture")
layers = [
    ("Use cases", "Copilots, RAG, agents, doc extraction", "teal"),
    ("AI gateway", "Auth, PII redaction, routing, logging", "teal"),
    ("AI services", "Foundry / Gemini Agent Platform", "teal"),
    ("Data and retrieval", "Vector search, lakes, entitlements", "teal"),
    ("Secure landing zone", "Private network, identity, keys, IaC", "gray"),
]
for i, (t, s, c) in enumerate(layers):
    y = 30 + i * 90
    svg += box(40, y, 440, 64, t, s, c)
    if i < len(layers) - 1:
        svg += line(260, y + 66, 260, y + 86)
svg += box(510, 30, 130, 424, "", "", "purple", extra_lines=[
    ("LLMOps and", True, 220), ("governance", True, 242),
    ("CI/CD, evals,", False, 270), ("monitoring, audit", False, 288)])
svg += legend([(150, "teal", "Runtime layers"), (290, "gray", "Foundation"), (410, "purple", "Cross-cutting")], 486)
svg += "</svg>"
render(svg, "diagram_platform_layers.png")

# 3. Credit memo copilot -----------------------------------------------------
svg = head(575, "Credit memo copilot architecture")
svg += box(60, 30, 260, 56, "Source systems", "Financials, rating, prior memos", "gray")
svg += box(360, 30, 260, 56, "Policy and research", "Credit policy, sector reports", "gray")
svg += line(190, 88, 190, 118) + line(490, 88, 490, 118)
svg += box(60, 122, 260, 56, "Extract and reconcile", "Doc intelligence, rule checks", "teal")
svg += box(360, 122, 260, 56, "Entitled retrieval", "Hybrid search, rerank", "teal")
svg += path("M190 180 L190 200 L340 200 L340 214") + path("M490 180 L490 200 L340 200", head=False)
svg += box(170, 218, 340, 56, "Gateway and section drafting", "Workflow, cited drafts per section", "teal")
svg += line(340, 276, 340, 306)
svg += box(170, 310, 340, 56, "Automated checks", "Numbers tie out, citations, faithfulness", "teal")
svg += line(340, 368, 340, 398)
svg += box(170, 402, 340, 56, "RM edits, credit decides", "Human owns every word", "purple")
svg += line(340, 460, 340, 490)
svg += box(170, 494, 340, 56, "Credit system and audit log", "Final memo, full lineage", "gray")
svg += "</svg>"
render(svg, "diagram_credit_memo.png")
