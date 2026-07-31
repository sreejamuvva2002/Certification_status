"""Render the full research report to PDF via XeLaTeX.

No pandoc is available, so this converts the authored Markdown sections to LaTeX
directly. That is workable because the Markdown is ours and uses a known, small
set of constructs.

Two decisions worth stating:

* **The 25-column literature table cannot fit any page.** Rather than truncate it,
  the body carries a landscape summary of the columns a reader scans, and an
  appendix carries every paper as a full record with all 25 fields. Nothing is
  dropped; it is re-laid-out.
* **Tables are generated from the CSVs, not from the Markdown.** The assembled
  Markdown report renders them as pipe tables, which lose column-width control.
  Reading the source data directly gives proper longtables that break across
  pages with repeated headers.

XeLaTeX with DejaVu is used because this text is full of α-cyclodextrin, °C,
mg·g⁻¹ and µL·L⁻¹ — pdfLaTeX would mangle all of it.
"""
from __future__ import annotations

import csv
import os
import re
import shutil
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
SECTIONS = os.path.join(HERE, "sections")
TABLES = os.path.join(HERE, "tables")
ARTIFACTS = os.path.join(REPO, "outputs", "1mcp")
BUILD = os.path.join(HERE, "_pdfbuild")
OUT_PDF = os.path.join(HERE, "1-MCP-research-report.pdf")

ORDER = [
    "01_executive_conclusion", "02_novelty_correction", "03_methodology",
    "04_literature_table", "05_commercial", "06_patent_landscape",
    "07_compatibility", "07b_antimicrobial_selection", "08_architecture_matrix",
    "09_recommended_architecture", "10_formulation_manufacturing",
    "11_release_kinetics", "12_characterization", "13_produce_experiment",
    "14_regulatory", "15_technoeconomic", "16_failure_modes",
    "17_patent_evidence", "18_roadmap", "19_open_questions", "20_references",
]

# Characters LaTeX treats specially, plus a few that XeLaTeX renders badly.
_ESCAPES = {
    "\\": r"\textbackslash{}", "&": r"\&", "%": r"\%", "$": r"\$", "#": r"\#",
    "_": r"\_", "{": r"\{", "}": r"\}", "~": r"\textasciitilde{}",
    "^": r"\textasciicircum{}",
}


# Chinese, Japanese and Korean assignees and titles appear throughout the patent
# corpus, and DejaVu has no CJK coverage — those glyphs would silently vanish.
# Runs are wrapped in fallback families instead. Hangul needs a different font
# from Han/Kana: Droid Sans Fallback covers CJK but not Hangul.
_CJK_RE = re.compile(
    r"[\u3000-\u303f\u3040-\u30ff\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff\uff00-\uffef]+")
_HANGUL_RE = re.compile(r"[\u1100-\u11ff\u3130-\u318f\uac00-\ud7af]+")


def _cjk_wrap(s: str) -> str:
    s = _HANGUL_RE.sub(lambda m: r"{\korfont " + m.group(0) + "}", s)
    return _CJK_RE.sub(lambda m: r"{\cjkfont " + m.group(0) + "}", s)


def esc(s: str) -> str:
    """Escape LaTeX specials in plain text."""
    return "".join(_ESCAPES.get(c, c) for c in (s or ""))


def inline(s: str) -> str:
    """Markdown inline formatting → LaTeX. Order matters: links, code, bold, italic."""
    if not s:
        return ""
    out: list[str] = []
    i = 0
    # Protect fragments that must not be re-escaped.
    tokens: dict[str, str] = {}

    def stash(latex: str) -> str:
        # A printable sentinel: control characters are invalid in a LaTeX source
        # file, so a leaked one is a hard compile error rather than a cosmetic
        # blemish. "@" survives escaping untouched and cannot occur in this text.
        key = f"@@TOK{len(tokens)}@@"
        tokens[key] = latex
        return key

    s = re.sub(r"<sup>(.*?)</sup>", lambda m: stash(r"\textsuperscript{" + esc(m.group(1)) + "}"), s)
    s = re.sub(r"<em>(.*?)</em>", lambda m: stash(r"\emph{" + esc(m.group(1)) + "}"), s)
    s = re.sub(r"<strong>(.*?)</strong>", lambda m: stash(r"\textbf{" + esc(m.group(1)) + "}"), s)
    s = re.sub(r"<[^>]+>", "", s)  # drop any other stray HTML

    def link(m: re.Match) -> str:
        text, url = m.group(1), m.group(2)
        return stash(r"\href{" + url.replace("%", r"\%").replace("#", r"\#")
                     + "}{" + inline(text) + "}")

    s = re.sub(r"\[([^\]]+)\]\((https?://[^)\s]+)\)", link, s)
    s = re.sub(r"`([^`]+)`", lambda m: stash(r"\texttt{" + esc(m.group(1)) + "}"), s)
    s = re.sub(r"\*\*([^*]+)\*\*", lambda m: stash(r"\textbf{" + inline(m.group(1)) + "}"), s)
    s = re.sub(r"(?<![\w*])\*([^*\n]+)\*(?![\w*])",
               lambda m: stash(r"\emph{" + inline(m.group(1)) + "}"), s)

    out_s = esc(s)
    # Resolve to a fixed point. A construct nested inside another — a link inside
    # bold, say — is stashed by the outer pass, but the recursive inline() call
    # that formats the bold returns that token unresolved inside its own output.
    # A single substitution pass would leave the inner token stranded, so repeat
    # until nothing changes.
    for _ in range(8):
        before = out_s
        for key, latex in tokens.items():
            out_s = out_s.replace(esc(key), latex).replace(key, latex)
        if out_s == before:
            break
    # Bare URLs left in text
    out_s = re.sub(r"(?<!\{)(https?://[^\s{}]+)", r"\\url{\1}", out_s)
    # Control characters are invalid in LaTeX source; drop any that reached here
    # from source PDFs or model output.
    out_s = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", "", out_s)
    return _cjk_wrap(out_s)


def _split_row(line: str) -> list[str]:
    line = line.strip()
    if line.startswith("|"):
        line = line[1:]
    if line.endswith("|"):
        line = line[:-1]
    # Respect escaped pipes inside cells
    parts = re.split(r"(?<!\\)\|", line)
    return [p.replace(r"\|", "|").strip() for p in parts]


def md_table(rows: list[str]) -> str:
    """Convert a Markdown pipe table to a LaTeX longtable that breaks across pages."""
    header = _split_row(rows[0])
    body = [_split_row(r) for r in rows[2:] if r.strip()]
    n = len(header)
    # Give every column an equal share of the text width; ragged right avoids
    # the overfull-box warnings that dense technical prose otherwise produces.
    colspec = " ".join([r">{\RaggedRight\arraybackslash}p{%.3f\linewidth}" % (0.93 / n)] * n)
    out = [r"\begingroup\footnotesize",
           r"\setlength{\tabcolsep}{3pt}\renewcommand{\arraystretch}{1.15}",
           r"\begin{longtable}{" + colspec + "}",
           r"\toprule",
           " & ".join(r"\textbf{" + inline(h) + "}" for h in header) + r" \\",
           r"\midrule\endfirsthead",
           r"\toprule",
           " & ".join(r"\textbf{" + inline(h) + "}" for h in header) + r" \\",
           r"\midrule\endhead",
           r"\bottomrule\endfoot"]
    for r in body:
        cells = (r + [""] * n)[:n]
        out.append(" & ".join(inline(c) for c in cells) + r" \\")
    out += [r"\bottomrule", r"\end{longtable}", r"\endgroup"]
    return "\n".join(out)


def convert(md: str) -> str:
    """Markdown → LaTeX for the constructs used in these sections."""
    lines = md.split("\n")
    out: list[str] = []
    i = 0
    in_list: str | None = None

    def close_list() -> None:
        nonlocal in_list
        if in_list:
            out.append(r"\end{" + in_list + "}")
            in_list = None

    while i < len(lines):
        line = lines[i]
        stripped = line.strip()

        # table
        if stripped.startswith("|") and i + 1 < len(lines) and re.match(r"^\|[\s:|-]+\|?$", lines[i + 1].strip()):
            close_list()
            block = []
            while i < len(lines) and lines[i].strip().startswith("|"):
                block.append(lines[i])
                i += 1
            out.append(md_table(block))
            continue

        if not stripped:
            close_list()
            out.append("")
            i += 1
            continue

        if re.match(r"^-{3,}$", stripped):
            close_list()
            i += 1
            continue

        m = re.match(r"^(#{1,4})\s+(.*)$", stripped)
        if m:
            close_list()
            level, text = len(m.group(1)), m.group(2)
            # Strip the leading numbering; LaTeX numbers sections itself.
            text = re.sub(r"^\d+[a-z]?(\.\d+)*\.?\s+", "", text)
            cmd = {1: "section", 2: "subsection", 3: "subsubsection", 4: "paragraph"}[level]
            out.append("\\" + cmd + "{" + inline(text) + "}")
            i += 1
            continue

        if stripped.startswith(">"):
            close_list()
            quote = []
            while i < len(lines) and lines[i].strip().startswith(">"):
                quote.append(lines[i].strip().lstrip(">").strip())
                i += 1
            out.append(r"\begin{quoteblock}" + inline(" ".join(quote)) + r"\end{quoteblock}")
            continue

        # List items wrap onto indented continuation lines. Those must be joined
        # into the item, not treated as new paragraphs — otherwise a bold span
        # split across two lines loses its closing ** and renders as literal
        # asterisks.
        def take_item(first: str, start: int) -> tuple[str, int]:
            parts = [first]
            j = start
            while j < len(lines):
                nxt = lines[j]
                if not nxt.strip():
                    break
                if re.match(r"^\s*([-*]\s|\d+\.\s|#{1,4}\s|\||>)", nxt):
                    break
                if not nxt.startswith((" ", "\t")):
                    break
                parts.append(nxt.strip())
                j += 1
            return " ".join(parts), j

        m = re.match(r"^[-*]\s+(.*)$", stripped)
        if m:
            if in_list != "itemize":
                close_list()
                out.append(r"\begin{itemize}")
                in_list = "itemize"
            text, i = take_item(m.group(1), i + 1)
            out.append(r"\item " + inline(text))
            continue

        m = re.match(r"^\d+\.\s+(.*)$", stripped)
        if m:
            if in_list != "enumerate":
                close_list()
                out.append(r"\begin{enumerate}")
                in_list = "enumerate"
            text, i = take_item(m.group(1), i + 1)
            out.append(r"\item " + inline(text))
            continue

        # paragraph (join continuation lines)
        close_list()
        para = [stripped]
        i += 1
        while i < len(lines) and lines[i].strip() and not re.match(
                r"^(\||#{1,4}\s|[-*]\s|\d+\.\s|>|-{3,}$)", lines[i].strip()):
            para.append(lines[i].strip())
            i += 1
        out.append(inline(" ".join(para)))

    close_list()
    return "\n".join(out)


# --------------------------------------------------------------------------
# data-driven tables
# --------------------------------------------------------------------------
def read_csv(path: str) -> list[dict]:
    if not os.path.exists(path):
        return []
    with open(path, encoding="utf-8", newline="") as fh:
        return list(csv.DictReader(fh))


def trim(s: str, n: int) -> str:
    s = " ".join((s or "").split())
    return (s[: n - 1] + "…") if len(s) > n else s


def landscape_table(rows: list[dict], cols: list[tuple[str, str, float]], caption: str) -> str:
    """A wide summary table on its own landscape pages."""
    spec = " ".join(r">{\RaggedRight\arraybackslash}p{%.3f\linewidth}" % w for _, _, w in cols)
    head = " & ".join(r"\textbf{" + esc(lbl) + "}" for _, lbl, _ in cols) + r" \\"
    out = [r"\begin{landscape}", r"\begingroup\scriptsize",
           r"\setlength{\tabcolsep}{3pt}\renewcommand{\arraystretch}{1.2}",
           r"\begin{longtable}{" + spec + "}",
           r"\caption{" + esc(caption) + r"}\\", r"\toprule", head,
           r"\midrule\endfirsthead", r"\toprule", head, r"\midrule\endhead",
           r"\bottomrule\endfoot"]
    for r in rows:
        out.append(" & ".join(inline(trim(r.get(k, ""), 90)) for k, _, _ in cols) + r" \\")
    out += [r"\bottomrule", r"\end{longtable}", r"\endgroup", r"\end{landscape}"]
    return "\n".join(out)


def record_cards(rows: list[dict], fields: list[tuple[str, str]], title_key,
                 heading: str, intro: str) -> str:
    """Every field of every record, laid out as readable per-record blocks.

    This is how the 25-column table stays complete: it is re-laid-out rather
    than truncated.
    """
    out = [r"\section{" + esc(heading) + "}", inline(intro), ""]
    for idx, r in enumerate(rows, 1):
        out.append(r"\needspace{6\baselineskip}")
        out.append(r"\recordhead{" + str(idx) + r"}{" + inline(trim(title_key(r), 210)) + "}")
        out.append(r"\begingroup\footnotesize")
        out.append(r"\begin{recordlist}")
        for key, label in fields:
            val = " ".join((r.get(key) or "").split())
            if not val:
                continue
            out.append(r"\item[" + esc(label) + r"] " + inline(trim(val, 900)))
        out.append(r"\end{recordlist}")
        out.append(r"\endgroup")
        out.append("")
    return "\n".join(out)


LIT_FIELDS = [
    ("doi", "DOI"), ("year", "Year"), ("venue", "Venue"), ("pub_type", "Type"),
    ("substrate_polymer", "Substrate"), ("mcp_carrier", "1-MCP carrier"),
    ("antimicrobial", "Antimicrobial"), ("prep_method", "Preparation"),
    ("manufacturing_temp_c", "Mfg. temp."), ("trigger_mechanism", "Trigger"),
    ("rh_conditions_pct", "RH conditions"), ("storage_temp_c", "Storage temp."),
    ("mcp_loading", "1-MCP loading"), ("release_method", "Release method"),
    ("release_duration", "Release duration"), ("kinetic_model", "Kinetic model"),
    ("release_result", "Release result"), ("produce_tested", "Produce"),
    ("package_vol_mass", "Package vol/mass"), ("quality_outcomes", "Quality outcomes"),
    ("mechanical_props", "Mechanical"), ("barrier_props", "Barrier"),
    ("antimicrobial_outcomes", "AM outcomes"), ("limitations", "Limitations"),
    ("scaleup_relevance", "Scale-up"), ("concept_relevance", "Relevance"),
    ("fulltext_source", "Full text"), ("row_confidence", "Confidence"),
]

PAT_FIELDS = [
    ("pub_number", "Publication"), ("priority_date", "Priority date"),
    ("publication_date", "Publication date"), ("assignee", "Assignee"),
    ("inventors", "Inventors"), ("jurisdictions", "Jurisdictions"),
    ("family_members_seen", "Family seen"),
    ("independent_claim_gist", "Claim 1"), ("packaging_format", "Packaging format"),
    ("mcp_carrier", "1-MCP carrier"), ("release_trigger", "Release trigger"),
    ("release_control", "Release control"), ("antimicrobial_component", "Antimicrobial"),
    ("manufacturing_method", "Manufacturing"), ("claim_limitations", "Claim limits"),
    ("overlap_with_concept", "Overlap"), ("design_around", "Design-around"),
    ("uncertainty", "Uncertainty"), ("row_confidence", "Confidence"),
]


def references() -> str:
    lit = sorted(read_csv(os.path.join(TABLES, "literature.csv")),
                 key=lambda r: (r.get("reference") or "").lower())
    pat = sorted(read_csv(os.path.join(TABLES, "patents.csv")),
                 key=lambda r: (r.get("priority_date") or "9999"))
    out = [r"\subsection*{Peer-reviewed sources (" + str(len(lit)) + ")}",
           r"\begingroup\small\begin{refslist}"]
    for r in lit:
        ref = inline(" ".join((r.get("reference") or "").split()))
        doi = (r.get("doi") or "").strip()
        if doi:
            ref += r" \href{https://doi.org/" + doi.replace("%", r"\%") + "}{" \
                   + r"\texttt{" + esc(doi) + "}}"
        kind = (r.get("pub_type") or "").replace("_", " ")
        ft = "full text retrieved" if (r.get("fulltext_chars") or "0") not in ("", "0") \
            else "abstract only"
        ref += r" \emph{[" + esc(kind) + "; " + esc(ft) + "]}"
        out.append(r"\item " + ref)
    out += [r"\end{refslist}\endgroup", "",
            r"\subsection*{Patent documents (" + str(len(pat)) + " families)}",
            r"\begingroup\small\begin{refslist}"]
    for r in pat:
        num = r.get("pub_number") or ""
        line = (r"\textbf{" + esc(num) + "} — " + inline(trim(r.get("title") or
                "[title not established]", 160)))
        asg = " ".join((r.get("assignee") or "").split())
        if asg:
            line += " (" + inline(trim(asg, 90)) + ")"
        line += ". Priority: " + esc(r.get("priority_date") or "not established") + ". "
        line += r"\href{https://patents.google.com/patent/" + esc(num) + "/en}{" \
                + r"\texttt{patents.google.com/" + esc(num) + "}}"
        out.append(r"\item " + line)
    out += [r"\end{refslist}\endgroup"]
    return "\n".join(out)


PREAMBLE = r"""
\documentclass[10pt,a4paper]{article}
\usepackage{fontspec}
\usepackage[a4paper,margin=22mm,bottom=24mm]{geometry}
\usepackage{pdflscape}
\usepackage{longtable,booktabs,array,tabularx,colortbl}
\usepackage{ragged2e}
\usepackage{enumitem}
\usepackage{xcolor}
\usepackage{titlesec}
\usepackage{fancyhdr}
\usepackage{needspace}
\usepackage{microtype}
\usepackage[hidelinks,breaklinks=true]{hyperref}

\setmainfont{DejaVu Serif}[Scale=0.92, Ligatures=TeX]
\setsansfont{DejaVu Sans}[Scale=0.88]
\setmonofont{DejaVu Sans Mono}[Scale=0.82]
\newfontfamily\cjkfont{Droid Sans Fallback}[Scale=0.90]
\newfontfamily\korfont{UnBatang}[Scale=0.95]

\definecolor{hold}{HTML}{1A6B52}
\definecolor{ripe}{HTML}{A8501E}
\definecolor{inkm}{HTML}{3D4D47}
\definecolor{rule}{HTML}{DDE2DE}

\hypersetup{colorlinks=true, linkcolor=hold, urlcolor=hold, citecolor=hold,
  pdftitle={Humidity-responsive controlled-release 1-MCP packaging},
  pdfsubject={Literature, commercial and patent-landscape assessment}}

\titleformat{\section}{\sffamily\Large\bfseries\color{hold}}{\thesection}{0.7em}{}
\titleformat{\subsection}{\sffamily\large\bfseries}{\thesubsection}{0.6em}{}
\titleformat{\subsubsection}{\sffamily\normalsize\bfseries\color{inkm}}{}{0em}{}
\titlespacing*{\section}{0pt}{2.2ex plus 1ex minus .2ex}{1.2ex plus .2ex}

\setlist[itemize]{leftmargin=1.3em,itemsep=0.15ex,topsep=0.5ex}
\setlist[enumerate]{leftmargin=1.6em,itemsep=0.15ex,topsep=0.5ex}
\newlist{recordlist}{description}{1}
\setlist[recordlist]{style=multiline, leftmargin=8.4em, labelwidth=8.0em,
  font=\normalfont\sffamily\bfseries\footnotesize\color{inkm},
  itemsep=0.15ex, topsep=0.4ex, parsep=0pt}
\newlist{refslist}{enumerate}{1}
% A list created with \newlist{...}{enumerate} has no default label; enumitem
% raises "Undefined label" unless one is given explicitly.
\setlist[refslist]{label=\arabic*., leftmargin=2.2em, itemsep=0.35ex, topsep=0.5ex}

\newenvironment{quoteblock}
  {\begin{list}{}{\leftmargin=1.2em\rightmargin=0.8em}\item[]\itshape\color{inkm}}
  {\end{list}}

\newcommand{\recordhead}[2]{%
  \par\vspace{1.1ex}\noindent\textcolor{hold}{\rule{\linewidth}{0.6pt}}\par
  \noindent{\sffamily\bfseries\small\textcolor{hold}{#1.}~#2}\par\vspace{0.3ex}}

\pagestyle{fancy}\fancyhf{}
\renewcommand{\headrulewidth}{0.3pt}
\fancyhead[L]{\sffamily\scriptsize\color{inkm}1-MCP humidity-responsive packaging}
\fancyhead[R]{\sffamily\scriptsize\color{inkm}\leftmark}
\fancyfoot[C]{\sffamily\scriptsize\thepage}
\renewcommand{\sectionmark}[1]{\markboth{#1}{}}

\setcounter{secnumdepth}{0}
\setcounter{tocdepth}{1}
\sloppy
\emergencystretch=3em
\begin{document}
"""


def main() -> int:
    os.makedirs(BUILD, exist_ok=True)
    lit = read_csv(os.path.join(TABLES, "literature.csv"))
    pat = read_csv(os.path.join(TABLES, "patents.csv"))
    cov = read_csv(os.path.join(ARTIFACTS, "20_coverage.csv"))

    doc = [PREAMBLE]

    # ---- title page
    doc.append(r"""
\begin{titlepage}\centering\vspace*{2.2cm}
{\sffamily\scriptsize\color{hold}\MakeUppercase{Evidence dossier}\par}
\vspace{5mm}
{\sffamily\huge\bfseries Humidity-responsive controlled-release\\[2mm] 1-MCP packaging\par}
\vspace{5mm}
{\large\itshape A literature, technology, commercial and patent-landscape assessment\par}
\vspace{12mm}
\begin{minipage}{0.82\textwidth}\small\color{inkm}
Whether a humidity-triggered 1-MCP packaging material --- optionally carrying an
essential-oil antimicrobial --- is novel, buildable, and worth pursuing for
climacteric fruit.\par\vspace{3mm}
Every value in the evidence tables is traceable to a quote in a document that was
actually retrieved. Values that could not be verified are marked, never guessed.
This report expresses \textbf{no freedom-to-operate or patentability opinion};
those require claim-by-claim review by qualified counsel. Proposed formulations
are labelled as experimental hypotheses, not literature-established facts.
\end{minipage}
\vfill
\begin{minipage}{0.82\textwidth}\centering\sffamily\footnotesize\color{inkm}
""" + r"\textbf{%d} papers \quad\textbullet\quad \textbf{%d} patent families \quad\textbullet\quad \textbf{%s} evidence cells"
        % (len(lit), len(pat), "2,810") + r"""
\end{minipage}
\vspace{12mm}
\end{titlepage}
\tableofcontents\clearpage
""")

    # ---- authored sections
    for name in ORDER:
        path = os.path.join(SECTIONS, f"{name}.md")
        if not os.path.exists(path):
            continue
        with open(path, encoding="utf-8") as fh:
            md = fh.read()

        if name == "04_literature_table":
            md = md.replace("<!-- TABLE: coverage -->", "@@COVERAGE@@")
            md = md.replace("<!-- TABLE: literature -->", "@@LITSUMMARY@@")
        if name == "06_patent_landscape":
            md = md.replace("<!-- TABLE: patents -->", "@@PATSUMMARY@@")
        if name == "20_references":
            md = md.replace("<!-- REFERENCES -->", "@@REFERENCES@@")
        md = re.sub(r"<!--.*?-->", "", md, flags=re.DOTALL)

        tex = convert(md)

        if "@@COVERAGE@@" in tex:
            tex = tex.replace("@@COVERAGE@@", landscape_table(
                cov, [("column", "Column", 0.20), ("n", "n", 0.05),
                      ("full_text_verified", "Full text", 0.09),
                      ("abstract_only", "Abstract", 0.09),
                      ("metadata_only", "Metadata", 0.09),
                      ("not_stated", "Not stated", 0.09),
                      ("unverifiable", "Unverifiable", 0.10),
                      ("blanked", "Blanked", 0.08)],
                "Evidence coverage per column of the literature table"))
        if "@@LITSUMMARY@@" in tex:
            tex = tex.replace("@@LITSUMMARY@@", landscape_table(
                lit, [("reference", "Reference", 0.22), ("substrate_polymer", "Substrate", 0.11),
                      ("mcp_carrier", "1-MCP carrier", 0.10), ("antimicrobial", "Antimicrobial", 0.09),
                      ("trigger_mechanism", "Trigger", 0.08), ("mcp_loading", "Loading", 0.07),
                      ("release_result", "Release result", 0.15),
                      ("produce_tested", "Produce", 0.09)],
                "Literature summary. Every field for every paper appears in Appendix A.")
                + "\n\n" + inline(
                    "The full 25-column record for every paper — including manufacturing "
                    "temperature, RH conditions, release duration, kinetic model, package "
                    "volume, mechanical and barrier properties — is in **Appendix A**. "
                    "A 25-column table cannot be set on any page width, so it is "
                    "re-laid-out rather than truncated."))
        if "@@PATSUMMARY@@" in tex:
            tex = tex.replace("@@PATSUMMARY@@", landscape_table(
                pat, [("pub_number", "Publication", 0.10), ("priority_date", "Priority", 0.08),
                      ("assignee", "Assignee", 0.16),
                      ("independent_claim_gist", "Claim 1", 0.31),
                      ("release_trigger", "Trigger", 0.09), ("mcp_carrier", "Carrier", 0.11)],
                "Patent families by priority date. Full records in Appendix B.")
                + "\n\n" + inline(
                    "All 19 fields for every family — jurisdictions, family members observed, "
                    "claim limitations, overlap, design-around and remaining uncertainty — "
                    "are in **Appendix B**."))
        if "@@REFERENCES@@" in tex:
            tex = tex.replace("@@REFERENCES@@", references())

        doc.append(r"\clearpage" + "\n" + tex)

    # ---- appendices
    doc.append(r"\clearpage")
    doc.append(record_cards(
        lit, LIT_FIELDS,
        lambda r: (r.get("reference") or r.get("work_id") or ""),
        "Appendix A — Literature records (all 25 fields)",
        "One block per paper, carrying every field of the 25-column table. Fields that "
        "are absent were either not stated in the source or could not be verified from "
        "what was retrievable; the per-cell evidence level and supporting quote for each "
        "is in `tables/literature_evidence.csv`."))
    doc.append(r"\clearpage")
    doc.append(record_cards(
        pat, PAT_FIELDS,
        lambda r: f"{r.get('pub_number','')} — {r.get('title','')}",
        "Appendix B — Patent family records (all 19 fields)",
        "One block per family. This is technical description only: no freedom-to-operate, "
        "infringement, validity or patentability conclusion is expressed or implied."))

    doc.append(r"\end{document}")

    tex_path = os.path.join(BUILD, "report.tex")
    with open(tex_path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(doc))
    print(f"  wrote {tex_path} ({os.path.getsize(tex_path):,} bytes)")

    if not shutil.which("xelatex"):
        print("  xelatex not found", file=sys.stderr)
        return 1
    for run in (1, 2, 3):  # passes for TOC and cross-references
        proc = subprocess.run(
            ["xelatex", "-interaction=nonstopmode", "-halt-on-error", "report.tex"],
            cwd=BUILD, capture_output=True, text=True, timeout=900)
        if proc.returncode != 0:
            log = os.path.join(BUILD, "report.log")
            tail = ""
            if os.path.exists(log):
                with open(log, encoding="utf-8", errors="ignore") as fh:
                    lines = fh.read().split("\n")
                tail = "\n".join(l for l in lines if l.startswith("!") or "Error" in l)[:2500]
            print(f"  xelatex failed on pass {run}:\n{tail or proc.stdout[-2500:]}", file=sys.stderr)
            return 1
        print(f"  pass {run} ok")

    shutil.copy(os.path.join(BUILD, "report.pdf"), OUT_PDF)
    print(f"  wrote {OUT_PDF} ({os.path.getsize(OUT_PDF) / 1e6:.1f} MB)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
