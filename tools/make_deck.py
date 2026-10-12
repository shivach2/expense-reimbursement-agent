"""Build the 10-slide PowerPoint deck (docs/Expense_Agent_Deck.pptx) with python-pptx.

    pip install python-pptx
    python tools/make_deck.py

Screenshots in docs/screenshots/ are optional: a missing screenshot is replaced by a grey placeholder note, so
the deck still builds on a machine where the screenshots were not copied. Take fresh screenshots of the running
app and save them under the same names to fill the placeholders.
"""

from __future__ import annotations

from pathlib import Path

from PIL import Image
from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.enum.shapes import MSO_SHAPE
from pptx.enum.text import MSO_ANCHOR, PP_ALIGN
from pptx.util import Inches, Pt

ROOT = Path(__file__).resolve().parents[1]
SS = ROOT / "docs" / "screenshots"
OUT = ROOT / "docs" / "Expense_Agent_Deck.pptx"

INK, MUTE, BLUE = RGBColor(0x1C, 0x23, 0x30), RGBColor(0x66, 0x70, 0x85), RGBColor(0x1D, 0x4E, 0xD8)
LIGHT, LIGHTER, AMBER = RGBColor(0xEE, 0xF2, 0xFF), RGBColor(0xDB, 0xE4, 0xFF), RGBColor(0xB5, 0x47, 0x08)
WHITE = RGBColor(255, 255, 255)

prs = Presentation()
prs.slide_width, prs.slide_height = Inches(13.333), Inches(7.5)
BLANK = prs.slide_layouts[6]


def text(slide, x, y, w, h, content, size=18, bold=False, color=INK, align=PP_ALIGN.LEFT, anchor=MSO_ANCHOR.TOP):
    tb = slide.shapes.add_textbox(Inches(x), Inches(y), Inches(w), Inches(h))
    tf = tb.text_frame
    tf.word_wrap = True
    tf.vertical_anchor = anchor
    for i, line in enumerate(content if isinstance(content, list) else [content]):
        p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        p.alignment = align
        p.space_after = Pt(8)
        r = p.add_run()
        r.text, r.font.size, r.font.bold, r.font.color.rgb, r.font.name = line, Pt(size), bold, color, "Calibri"
    return tb


def bullets(slide, x, y, w, h, items, size=18):
    """Items written as 'Bold lead — grey detail' render the lead in bold."""
    tf = slide.shapes.add_textbox(Inches(x), Inches(y), Inches(w), Inches(h)).text_frame
    tf.word_wrap = True
    for i, item in enumerate(items):
        p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        p.space_after = Pt(10)
        head, _, rest = item.partition(" — ")
        r = p.add_run()
        r.text, r.font.size, r.font.bold, r.font.color.rgb, r.font.name = (
            "•  " + head,
            Pt(size),
            bool(rest),
            INK,
            "Calibri",
        )
        if rest:
            r2 = p.add_run()
            r2.text, r2.font.size, r2.font.color.rgb, r2.font.name = " — " + rest, Pt(size), MUTE, "Calibri"


def title(slide, t, sub=None):
    bar = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, 0, 0, Inches(0.25), prs.slide_height)
    bar.fill.solid()
    bar.fill.fore_color.rgb = BLUE
    bar.line.fill.background()
    text(slide, 0.7, 0.4, 12, 0.9, t, 32, True)
    if sub:
        text(slide, 0.7, 1.15, 12, 0.5, sub, 16, False, MUTE)


def panel(slide, x, y, w, h, fill=LIGHT):
    box = slide.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, Inches(x), Inches(y), Inches(w), Inches(h))
    box.fill.solid()
    box.fill.fore_color.rgb = fill
    box.line.fill.background()
    return box


def picture(slide, name, x, y, w, h, caption=None):
    path = SS / name
    if not path.exists():
        panel(slide, x, y, w, h, RGBColor(0xF2, 0xF4, 0xF7))
        text(
            slide,
            x + 0.3,
            y + h / 2 - 0.4,
            w - 0.6,
            1,
            f"[screenshot placeholder: {name}]",
            14,
            False,
            MUTE,
            PP_ALIGN.CENTER,
        )
        return
    iw, ih = Image.open(path).size
    s = min(w / iw, h / ih)
    pw, ph = iw * s, ih * s
    pic = slide.shapes.add_picture(str(path), Inches(x + (w - pw) / 2), Inches(y), Inches(pw), Inches(ph))
    pic.line.color.rgb = RGBColor(0xD0, 0xD5, 0xDD)
    if caption:
        text(slide, x, y + ph + 0.05, w, 0.4, caption, 12, False, MUTE, PP_ALIGN.CENTER)


def table(slide, x, y, w, rows, col_w, size=14, row_h=0.5):
    t = slide.shapes.add_table(
        len(rows), len(rows[0]), Inches(x), Inches(y), Inches(w), Inches(row_h * len(rows))
    ).table
    for j, cw in enumerate(col_w):
        t.columns[j].width = Inches(cw)
    for i, row in enumerate(rows):
        for j, val in enumerate(row):
            c = t.cell(i, j)
            c.text = val
            c.margin_left = c.margin_right = Inches(0.08)
            for p in c.text_frame.paragraphs:
                for r in p.runs:
                    r.font.size, r.font.name, r.font.bold = Pt(size), "Calibri", i == 0
                    r.font.color.rgb = WHITE if i == 0 else INK
            c.fill.solid()
            c.fill.fore_color.rgb = BLUE if i == 0 else (RGBColor(0xF8, 0xF9, 0xFC) if i % 2 else WHITE)


# 1 ---- title
s = prs.slides.add_slide(BLANK)
bg = s.shapes.add_shape(MSO_SHAPE.RECTANGLE, 0, 0, prs.slide_width, prs.slide_height)
bg.fill.solid()
bg.fill.fore_color.rgb = BLUE
bg.line.fill.background()
text(s, 0.9, 2.2, 11.5, 1.2, "Expense & Reimbursement Agent", 46, True, WHITE)
text(
    s,
    0.9,
    3.5,
    11.5,
    1,
    "An AI that reads the bills and reads the policy — from a pile of receipts to ready to submit",
    22,
    False,
    LIGHTER,
)
text(
    s,
    0.9,
    6.3,
    11.5,
    0.6,
    "Competition prototype · all data synthetic · Pydantic AI + Claude · FastAPI",
    14,
    False,
    LIGHTER,
)

# 2 ---- problem
s = prs.slides.add_slide(BLANK)
title(s, "The problem", "Reimbursement is a tax on every employee and every finance reviewer")
bullets(
    s,
    0.7,
    1.9,
    7.2,
    4.8,
    [
        "Collect and key in bills — photos, PDFs, foreign currency, crumpled paper",
        "Categorise each one — and guess which policy bucket it belongs in",
        "Look up the limits — policies live in long documents that change",
        "Avoid duplicates and missing details — or the claim bounces back",
        "Re-submit after rejection — the employee finds out too late",
    ],
    20,
)
panel(s, 8.4, 2.1, 4.4, 3.8)
box = text(
    s,
    8.7,
    2.3,
    3.9,
    3.4,
    [
        "Our goal",
        "Drop in the bills. Get a policy-checked, explained, submission-ready claim — "
        "answering only what the system cannot work out itself.",
    ],
    18,
)
box.text_frame.paragraphs[0].runs[0].font.bold = True
box.text_frame.paragraphs[0].runs[0].font.color.rgb = BLUE

# 3 ---- flow
s = prs.slides.add_slide(BLANK)
title(s, "How it works", "Six steps, three of them use AI")
steps = [
    ("1", "Drop bills", "photos, PDFs"),
    ("2", "AI reads bills", "vendor, date, total, items"),
    ("3", "AI reads policy", "limits, grades, clauses"),
    ("4", "Classify & check", "category, eligible amount, duplicates"),
    ("5", "Ask only gaps", "5 questions, not 24 forms"),
    ("6", "Submit", "mock finance system"),
]
for i, (n, h, sub) in enumerate(steps):
    x = 0.7 + i * 2.07
    panel(s, x, 2.4, 1.9, 2.6, LIGHTER if i in (1, 2, 3) else LIGHT)
    text(s, x + 0.1, 2.5, 1.7, 0.6, n, 30, True, BLUE, PP_ALIGN.CENTER)
    text(s, x + 0.1, 3.2, 1.7, 0.7, h, 17, True, INK, PP_ALIGN.CENTER)
    text(s, x + 0.1, 3.95, 1.7, 1.0, sub, 13, False, MUTE, PP_ALIGN.CENTER)
text(
    s,
    0.7,
    5.5,
    12,
    1.2,
    "Steps 2–4 use LLMs; every amount is computed by deterministic code, and every AI-extracted rule "
    "must quote the policy verbatim.",
    17,
)

# 4 ---- AI vs deterministic
s = prs.slides.add_slide(BLANK)
title(s, "Where AI is used — and where it is not", "LLMs interpret and judge; plain code does the money")
table(
    s,
    0.7,
    1.9,
    11.9,
    [
        ["Component", "Technique", "Why"],
        ["Receipt extraction", "LLM (vision)", "Messy photos and PDFs"],
        [
            "Policy interpretation",
            "LLM + grounding check",
            "Prose in, structured limits out; quotes stop invented rules",
        ],
        ["Clause lookup for answers", "RAG (BM25 over clauses)", "Cites the exact clause; offline and free"],
        ["Bill classification", "LLM with reasoning", "A judgement call that must be explained"],
        ["Eligible amount, caps, partial pay", "Deterministic", "Financial accuracy, reproducible"],
        ["Duplicates, grouping, claim state", "Deterministic", "Auditable (image hashing was tested and rejected)"],
        ["Chat assistant", "Agent with tools", "Open-ended follow-ups; reads decisions, never makes them"],
    ],
    [3.7, 3.0, 5.2],
    15,
    0.58,
)

# 5 ---- policy as documents
s = prs.slides.add_slide(BLANK)
title(s, "Policy is a document, not code", "Edit one sentence — the claim updates, no release needed")
bullets(
    s,
    0.7,
    1.9,
    5.0,
    4.8,
    [
        "AI reads the policy files — limits, grades, units, partial-pay rules",
        "Each rule carries a verbatim quote — checked against the clause; numbers must appear in the quote",
        "Hotel limit 5,000 → 7,000 — reimbursable total moves ₹23,053 → ₹26,549",
        "No code changed — interpretation is cached by document hash",
    ],
    17,
)
picture(
    s,
    "04_policy_changed_no_code.jpg",
    6.0,
    1.8,
    6.9,
    5.0,
    "Policy tab: the AI-extracted limit now reads ₹7,000 per night",
)

# 6 ---- explainable
s = prs.slides.add_slide(BLANK)
title(s, "Every decision is explained", "Category, clause, quote, arithmetic and what is still needed")
picture(s, "02_explainable_decision.jpg", 0.7, 1.8, 7.6, 5.0)
bullets(
    s,
    8.6,
    1.9,
    4.4,
    4.8,
    [
        "Why this category — the AI's reasoning",
        "Which clause — TEP-2.1 and GE-2.2, with quotes",
        "What is eligible — ₹5,000 of ₹7,168; excess not reimbursable",
        "What is needed — shown as a question, once",
    ],
    16,
)

# 7 ---- experience
s = prs.slides.add_slide(BLANK)
title(s, "The experience", "Chat on the left, claim on the right")
picture(s, "01_claim_and_chat.jpg", 0.5, 1.8, 6.4, 4.6, "24 bills read; 5 questions; submit disabled until ready")
picture(s, "05_submitted.jpg", 7.1, 1.8, 5.8, 4.6, "Submitted to the mock finance system, with a reference")

# 8 ---- results
s = prs.slides.add_slide(BLANK)
title(s, "Results on 24 synthetic receipts", "Measured with Claude Sonnet 5.5; 133 automated tests pass, 100% coverage")
table(
    s,
    0.7,
    1.9,
    8.0,
    [
        ["Measure", "Result"],
        ["Vendor, date, total, currency extracted", "24 / 24"],
        ["Category classification", "23 / 24"],
        ["Duplicates found (incl. re-photographed)", "3 / 3, no false alarms"],
        ["Bills auto-excluded with clause", "3 (expired, personal, over limit)"],
        ["Questions asked", "5 for 24 receipts"],
        ["Policy edit applied without code", "Yes"],
    ],
    [5.0, 3.0],
    16,
    0.56,
)
panel(s, 9.2, 1.9, 3.6, 3.9)
box = text(
    s,
    9.4,
    2.1,
    3.2,
    3.6,
    [
        "Free-tier check",
        "Gemini 3.8 Flash interpreted the policy identically; the 5 receipts it processed were "
        "all correct. 3 hit HTTP 503 overload, so no full-set figure is claimed.",
    ],
    14,
)
box.text_frame.paragraphs[0].runs[0].font.bold = True
box.text_frame.paragraphs[0].runs[0].font.size = Pt(18)

# 9 ---- impact
s = prs.slides.add_slide(BLANK)
title(s, "Business impact", "Illustrative model — assumptions are stated and editable")
table(
    s,
    0.7,
    1.9,
    7.2,
    [
        ["24 receipts", "Time"],
        ["Manual (assume 4 min per receipt)", "~96 min"],
        ["With the agent (5 answers + 3 min review)", "~7 min"],
        ["Saved per claim", "~89 min (≈90%)"],
    ],
    [4.6, 2.6],
    16,
    0.62,
)
bullets(
    s,
    8.3,
    1.9,
    4.6,
    4.8,
    [
        "Fewer rejected claims — employees see the eligible amount first",
        "Reviewers stop re-checking limits and duplicates",
        "Policy changes ship as a document edit",
        "Full audit trail — clause, quote and maths per item",
    ],
    16,
)
text(
    s,
    0.7,
    5.0,
    7.2,
    1.5,
    "Time figures come from an assumption (4 min per receipt by hand, 30 s per question), "
    "not from measurement. See docs/BUSINESS_IMPACT.md.",
    13,
    False,
    AMBER,
)

# 10 --- limits
s = prs.slides.add_slide(BLANK)
title(s, "Honest limits and next steps")
bullets(
    s,
    0.7,
    1.7,
    6.0,
    5,
    [
        "Synthetic bills only — real receipts are messier",
        "One employee profile and one policy set",
        "Static illustrative FX rates; no authentication",
        "Policy parsing assumes numbered clauses",
        "Free LLM tiers rate-limit; results are cached",
    ],
    18,
)
bullets(
    s,
    7.0,
    1.7,
    5.8,
    5,
    [
        "Next — real HRMS grades and location tiers",
        "Next — embeddings RAG for large policy libraries",
        "Next — multi-category bills and trip-level caps",
        "Next — approval workflow and finance integration",
    ],
    18,
)

OUT.parent.mkdir(parents=True, exist_ok=True)
prs.save(OUT)
print(f"saved {OUT.relative_to(ROOT)} ({len(prs.slides)} slides)")
