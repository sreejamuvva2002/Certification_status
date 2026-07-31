"""Generate the shareable evidence dossier from pipeline output.

Design intent: this is a decision document for a PI and a technology-transfer
office, so it is built as a dossier rather than a landing page. The one thing it
must do that a PDF cannot is make provenance legible — every value carries how
well it is evidenced, so a reader can see at a glance which parts of the table
rest on full text and which rest on an abstract.

Palette is grounded in the subject: 1-MCP arrests ripening, so "held" green is
the accent and ripening rust marks risk. Numbering is used because the brief's
twenty sections are a genuine sequence.
"""
from __future__ import annotations

import csv
import html
import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
TABLES = os.path.join(HERE, "tables")
ARTIFACTS = os.path.join(REPO, "outputs", "1mcp")
OUT = os.path.join(HERE, "dossier.html")

LEVEL_LABEL = {
    "full_text_verified": ("Full text", "lv-full"),
    "abstract_only": ("Abstract only", "lv-abs"),
    "metadata_only": ("Metadata", "lv-meta"),
    "not_stated": ("Not stated", "lv-ns"),
    "unverifiable": ("Unverifiable", "lv-unv"),
}

VERDICTS = [
    ("Is the broad idea novel?", "No", "Anticipated in literature, patents and commercial products."),
    ("Which parts are already known?", "All of them",
     "1-MCP/cyclodextrin complexes, humidity activation, coated-paper and sheet inserts, labels, sachets, dual 1-MCP + essential oil on paper, and delayed release."),
    ("Where is the credible white space?", "Dose specification",
     "A defined RH threshold and coat weight giving reproducible headspace concentration across variable packages. Weak-to-moderate — it is an absence in <em>public</em> material."),
    ("Which format?", "Coated paper insert",
     "Highest score on every project-critical criterion. The right engineering answer, not a novel format."),
    ("1-MCP and essential oil together?", "Separate — omit oil in v1",
     "Cavity competition, oil-phase partitioning, plasticisation and divergent release requirements all argue against co-location."),
    ("Is CNC necessary?", "No", "With no oil phase to stabilise it has no function."),
    ("Is chitosan necessary?", "No",
     "Hygroscopic, needs acidic aqueous processing, and its contact-antimicrobial mechanism cannot operate in a non-contact insert."),
    ("Is the Pickering emulsion justified?", "No",
     "It requires the aqueous phase the design exists to avoid."),
    ("Which antimicrobial?", "Carvacrol, if any",
     "Pure compound, documented against <em>Monilinia</em>, directly comparable to the closest prior art. Deferred to v2."),
    ("Which commodity first?", "Tomato, then peach",
     "Fastest, cheapest, least ambiguous response; peach adds commercial relevance and decay pressure."),
    ("Simplest proof of concept?", "Three materials",
     "1-MCP/α-CD + one binder on paper, Meyer-rod coated, protective overwrap."),
    ("Most scalable route?", "Meyer rod → slot die",
     "Both specified in g·m⁻². Reject extrusion coating (thermal loss) and solvent casting (no scale-up path)."),
    ("Principal patent risk?", "US10212931B2",
     "Kimberly-Clark / Cellresin: a cyclodextrin composition coated on a substrate with a second substrate over it."),
    ("What justifies continuing?", "A sharp RH threshold",
     "Plus a low delivered-dose CV across package volumes — evidence nobody currently publishes."),
    ("What should stop it?", "No threshold, or high CV",
     "Or a blocking claim with no design-around, or a registration requirement beyond project resources."),
]

PRIOR_ART = [
    ("Cao et al. 2024", "10.21203/rs.3.rs-4251760/v1",
     "Carvacrol-β-CD <strong>and</strong> 1-MCP-α-CD on coated paper by a water-free method, validated on peach.",
     "Anticipates the material combination"),
    ("HarvestHold Fresh", "Verdant Technologies",
     "A 1-MCP sheet applied in the box at packing. Commercial since late 2021, with an EPA label expansion.",
     "Anticipates the format"),
    ("Vidre+", "Fresh Inset",
     "Stickers claimed by their owner to release 1-MCP with a delay and gradually, without a sealed room.",
     "Anticipates delayed release"),
    ("US10212931B2", "Kimberly-Clark / Cellresin",
     "Claim 1: a treated laminate — a substrate, a cyclodextrin composition coated on it, and a second substrate over the coating.",
     "Closest granted claim"),
]

ARCH = [
    ("C", "Paper / paperboard insert", 87.7, True),
    ("D", "Label, patch or patterned coating", 77.0, False),
    ("E", "Coated absorbent pad", 73.2, False),
    ("B", "Bilayer coating", 63.0, False),
    ("F", "Compartmentalised dual-active", 53.2, False),
    ("A", "Single homogeneous chitosan/CNC film", 43.4, False),
]


def esc(s: object) -> str:
    return html.escape(str(s or ""))


def read_csv(path: str) -> list[dict]:
    if not os.path.exists(path):
        return []
    with open(path, encoding="utf-8", newline="") as fh:
        return list(csv.DictReader(fh))


def load_json(path: str) -> dict:
    if not os.path.exists(path):
        return {}
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def chip(level: str) -> str:
    label, cls = LEVEL_LABEL.get(level, (level or "—", "lv-unv"))
    return f'<span class="chip {cls}">{esc(label)}</span>'


def build() -> str:
    lit = read_csv(os.path.join(TABLES, "literature.csv"))
    cells = read_csv(os.path.join(TABLES, "literature_evidence.csv"))
    pat = read_csv(os.path.join(TABLES, "patents.csv"))
    cov = read_csv(os.path.join(ARTIFACTS, "20_coverage.csv"))
    rep = load_json(os.path.join(ARTIFACTS, "20_verification.json"))

    by_work: dict[str, dict[str, dict]] = {}
    for c in cells:
        by_work.setdefault(c["work_id"], {})[c["field"]] = c

    n_full = sum(1 for c in cells if c.get("evidence_level") == "full_text_verified")
    n_blank = sum(1 for c in cells if c.get("status") == "ungrounded_blanked")
    stats = [
        (f"{rep.get('rows', len(lit)):,}", "papers in the evidence table"),
        (f"{rep.get('patent_families', len(pat)):,}", "patent families mapped"),
        (f"{len(cells):,}", "cells, each with its quote"),
        (f"{n_full:,}", "verified against full text"),
        (f"{n_blank:,}", "values blanked as ungrounded"),
    ]

    p: list[str] = []
    a = p.append

    a('<div class="wrap">')
    # ---- masthead
    a('<header class="mast">')
    a('<p class="eyebrow">Evidence dossier &middot; literature, commercial &amp; patent landscape</p>')
    a('<h1>Humidity-responsive controlled-release <span class="nowrap">1-MCP</span> packaging</h1>')
    a('<p class="standfirst">Whether a humidity-triggered 1-MCP packaging material — optionally '
      'carrying an essential-oil antimicrobial — is novel, buildable, and worth pursuing. '
      'Every value below is traceable to a quote in a document that was actually retrieved.</p>')
    a('<div class="stats">')
    for big, small in stats:
        a(f'<div class="stat"><span class="n">{esc(big)}</span><span class="l">{esc(small)}</span></div>')
    a('</div>')
    a('</header>')

    # ---- verdict
    a('<section class="sec"><div class="sechead"><span class="num">01</span>'
      '<h2>The verdict</h2></div>')
    a('<p class="lede">The broad idea is <strong>not novel</strong>, and the closest prior art is '
      'closer than the brief assumed. The proposed chitosan/CNC/Pickering formulation scores '
      '<strong>last of six architectures</strong>. What remains defensible is narrow and quantitative.</p>')
    a('<dl class="verdicts">')
    for q, ans, why in VERDICTS:
        a(f'<div class="v"><dt>{esc(q)}</dt><dd><span class="ans">{esc(ans)}</span>'
          f'<span class="why">{why}</span></dd></div>')
    a('</dl></section>')

    # ---- prior art
    a('<section class="sec"><div class="sechead"><span class="num">02</span>'
      '<h2>What already exists</h2></div>')
    a('<p class="lede">Four documents between them anticipate the material combination, the format, '
      'the release behaviour and the closest claim.</p>')
    a('<div class="cards">')
    for name, who, what, role in PRIOR_ART:
        a(f'<article class="card"><p class="role">{esc(role)}</p>'
          f'<h3>{esc(name)}</h3><p class="who">{esc(who)}</p><p>{what}</p></article>')
    a('</div></section>')

    # ---- architectures
    a('<section class="sec"><div class="sechead"><span class="num">03</span>'
      '<h2>Architecture comparison</h2></div>')
    a('<p class="lede">Six architectures scored 1–5 against 20 weighted criteria. '
      '<strong>The ranking is unchanged when every weight is set to 1</strong> — so it is not an '
      'artefact of the weighting.</p>')
    a('<ul class="bars">')
    for key, name, score, win in ARCH:
        cls = " win" if win else ""
        a(f'<li class="bar{cls}"><span class="k">{esc(key)}</span>'
          f'<span class="nm">{esc(name)}</span>'
          f'<span class="track"><span class="fill" style="width:{score}%"></span></span>'
          f'<span class="sc">{score:.1f}</span></li>')
    a('</ul>')
    a('<p class="note">Architecture A is the brief’s own starting formulation. It finishes last because '
      'its aqueous, hygroscopic matrix attacks the one thing the product must protect — a payload that '
      'water discharges.</p>')
    a('</section>')

    # ---- evidence coverage
    if cov:
        a('<section class="sec"><div class="sechead"><span class="num">04</span>'
          '<h2>How well evidenced is each column?</h2></div>')
        a('<p class="lede">Process detail lives in methods sections, and only a minority of this '
          'literature is openly available. Sparse columns are a measurement of what is publishable, '
          'not of effort. <em>Not stated</em> (we hold the full text and it is silent) is never merged '
          'with <em>unverifiable</em> (we could not read enough to know).</p>')
        a('<div class="scroll"><table class="cov"><thead><tr>'
          '<th>Column</th><th class="r">Full text</th><th class="r">Abstract</th>'
          '<th class="r">Not stated</th><th class="r">Unverifiable</th><th>Mix</th>'
          '</tr></thead><tbody>')
        for r in cov:
            n = max(1, int(r.get("n") or 1))
            f_ = int(r.get("full_text_verified") or 0)
            ab = int(r.get("abstract_only") or 0)
            ns = int(r.get("not_stated") or 0)
            uv = int(r.get("unverifiable") or 0)
            mt = int(r.get("metadata_only") or 0)
            seg = "".join(
                f'<span class="s {c}" style="width:{100.0*v/n:.2f}%"></span>'
                for v, c in ((f_, "lv-full"), (mt, "lv-meta"), (ab, "lv-abs"),
                             (ns, "lv-ns"), (uv, "lv-unv")) if v)
            a(f'<tr><td>{esc(r.get("column"))}</td><td class="r">{f_}</td><td class="r">{ab}</td>'
              f'<td class="r">{ns}</td><td class="r">{uv}</td>'
              f'<td class="mixcell"><span class="mix">{seg}</span></td></tr>')
        a('</tbody></table></div>')
        a('<p class="legend">'
          + " ".join(chip(k) for k in
                     ("full_text_verified", "metadata_only", "abstract_only",
                      "not_stated", "unverifiable"))
          + '</p></section>')

    # ---- literature
    if lit:
        a('<section class="sec"><div class="sechead"><span class="num">05</span>'
          '<h2>Literature</h2></div>')
        a(f'<p class="lede">{len(lit)} papers. Hover or tap a value to see the quote it rests on.</p>')
        a('<div class="scroll"><table class="lit"><thead><tr>'
          '<th>Reference</th><th>Substrate</th><th>1-MCP carrier</th><th>Antimicrobial</th>'
          '<th>Trigger</th><th>Loading</th><th>Release result</th><th>Produce</th>'
          '</tr></thead><tbody>')
        for r in lit:
            wid = r.get("work_id", "")
            cm = by_work.get(wid, {})

            def cell(field: str) -> str:
                v = r.get(field) or ""
                c = cm.get(field) or {}
                lvl = c.get("evidence_level", "")
                q = c.get("quote") or ""
                if not v:
                    return f'<td class="empty">{chip(lvl) if lvl in ("not_stated","unverifiable") else "—"}</td>'
                t = f' title="{esc(q[:280])}"' if q else ""
                mark = "" if lvl == "full_text_verified" else '<sup class="abs">a</sup>'
                return f'<td{t}><span class="val">{esc(v)}</span>{mark}</td>'

            doi = r.get("doi") or ""
            ref = esc((r.get("reference") or "")[:160])
            link = (f'<a href="https://doi.org/{esc(doi)}" target="_blank" rel="noopener">{ref}</a>'
                    if doi else ref)
            a(f'<tr><td class="ref">{link}</td>' + "".join(
                cell(f) for f in ("substrate_polymer", "mcp_carrier", "antimicrobial",
                                  "trigger_mechanism", "mcp_loading", "release_result",
                                  "produce_tested")) + "</tr>")
        a('</tbody></table></div>')
        a('<p class="note"><sup class="abs">a</sup> verified against the abstract only — full text was '
          'not openly available, so process detail could not be checked.</p></section>')

    # ---- patents
    if pat:
        a('<section class="sec"><div class="sechead"><span class="num">06</span>'
          '<h2>Patent landscape</h2></div>')
        a(f'<p class="lede">{len(pat)} families. <strong>This is a technical prior-art map, not a legal '
          'analysis.</strong> No freedom-to-operate or patentability opinion is expressed or implied.</p>')
        a('<div class="scroll"><table class="pat"><thead><tr>'
          '<th>Publication</th><th>Priority</th><th>Assignee</th><th>Independent claim</th>'
          '<th>Trigger</th><th>Carrier</th></tr></thead><tbody>')
        for r in pat:
            num = r.get("pub_number") or ""
            a('<tr>'
              f'<td class="mono"><a href="https://patents.google.com/patent/{esc(num)}/en" '
              f'target="_blank" rel="noopener">{esc(num)}</a></td>'
              f'<td class="mono">{esc(r.get("priority_date") or "—")}</td>'
              f'<td>{esc((r.get("assignee") or "—")[:44])}</td>'
              f'<td class="claim">{esc((r.get("independent_claim_gist") or "—")[:230])}</td>'
              f'<td>{esc(r.get("release_trigger") or "—")}</td>'
              f'<td>{esc((r.get("mcp_carrier") or "—")[:34])}</td></tr>')
        a('</tbody></table></div></section>')

    # ---- limits
    a('<section class="sec"><div class="sechead"><span class="num">07</span>'
      '<h2>What this cannot tell you</h2></div>')
    a('<div class="limits">')
    for t, d in [
        ("Four indexes were unreachable",
         "Web of Science, Scopus, CAB Abstracts and AGRICOLA. The last two index the postharvest and "
         "extension literature where a 1-MCP paper insert might well be described."),
        ("Patent coverage rests on one provider",
         "No independent legal-status cross-check was available, families are clustered heuristically, "
         "and unpublished applications are by definition absent."),
        ("No legal opinion",
         "Freedom to operate and patentability require claim-by-claim review by qualified counsel."),
        ("Absence of evidence is weak here",
         "Every statement about what has <em>not</em> been done is limited by the three points above."),
    ]:
        a(f'<div class="limit"><h4>{esc(t)}</h4><p>{d}</p></div>')
    a('</div></section>')

    a('<footer class="foot"><p>Built from a retrieval-first pipeline: identifiers come from OpenAlex, '
      'Crossref, Europe PMC and Google Patents; the local model only ever read text that was actually '
      'fetched; every value was re-checked against that text before it reached a cell.</p></footer>')
    a('</div>')

    return "\n".join(p)


CSS = """
:root{
  --paper:#fbfaf8; --ink:#14201c; --ink-2:#3d4d47; --muted:#6d7d76;
  --rule:#dde2de; --rule-2:#eceeea; --card:#ffffff;
  --hold:#1a6b52;            /* ripening arrested — the accent */
  --hold-soft:#e4efe9;
  --ripe:#a8501e;            /* ripening / risk */
  --ripe-soft:#f6e7dd;
  --amber:#8a6d1f; --slate:#5b6f7a;
  --shadow:0 1px 2px rgba(20,32,28,.05),0 8px 24px rgba(20,32,28,.05);
}
@media (prefers-color-scheme:dark){
  :root{
    --paper:#0d1512; --ink:#e6ece8; --ink-2:#b3c0ba; --muted:#87968f;
    --rule:#22302b; --rule-2:#1a2622; --card:#121d19;
    --hold:#5cc79c; --hold-soft:#16302a; --ripe:#e29a6b; --ripe-soft:#2e211a;
    --amber:#d8b559; --slate:#9ab3c0;
    --shadow:0 1px 2px rgba(0,0,0,.4),0 8px 24px rgba(0,0,0,.3);
  }
}
:root[data-theme="dark"]{
  --paper:#0d1512; --ink:#e6ece8; --ink-2:#b3c0ba; --muted:#87968f;
  --rule:#22302b; --rule-2:#1a2622; --card:#121d19;
  --hold:#5cc79c; --hold-soft:#16302a; --ripe:#e29a6b; --ripe-soft:#2e211a;
  --amber:#d8b559; --slate:#9ab3c0;
  --shadow:0 1px 2px rgba(0,0,0,.4),0 8px 24px rgba(0,0,0,.3);
}
:root[data-theme="light"]{
  --paper:#fbfaf8; --ink:#14201c; --ink-2:#3d4d47; --muted:#6d7d76;
  --rule:#dde2de; --rule-2:#eceeea; --card:#ffffff;
  --hold:#1a6b52; --hold-soft:#e4efe9; --ripe:#a8501e; --ripe-soft:#f6e7dd;
  --amber:#8a6d1f; --slate:#5b6f7a;
  --shadow:0 1px 2px rgba(20,32,28,.05),0 8px 24px rgba(20,32,28,.05);
}
*{box-sizing:border-box}
body{
  margin:0; background:var(--paper); color:var(--ink);
  font-family:Iowan Old Style,"Palatino Linotype",Palatino,Georgia,ui-serif,serif;
  font-size:17px; line-height:1.62; -webkit-font-smoothing:antialiased;
}
.wrap{max-width:1120px;margin:0 auto;padding:clamp(28px,5vw,72px) clamp(18px,4vw,40px) 80px}
.nowrap{white-space:nowrap}
h1,h2,h3,h4{text-wrap:balance;line-height:1.16;margin:0}
.mast{border-bottom:2px solid var(--ink);padding-bottom:28px;margin-bottom:8px}
.eyebrow{
  font-family:ui-sans-serif,-apple-system,"Segoe UI",Roboto,sans-serif;
  text-transform:uppercase;letter-spacing:.14em;font-size:11.5px;font-weight:600;
  color:var(--hold);margin:0 0 14px
}
h1{font-size:clamp(30px,4.6vw,52px);font-weight:600;letter-spacing:-.015em}
.standfirst{max-width:64ch;color:var(--ink-2);font-size:clamp(16px,1.6vw,19px);margin:16px 0 0}
.stats{display:flex;flex-wrap:wrap;gap:8px 34px;margin-top:26px}
.stat{display:flex;flex-direction:column}
.stat .n{
  font-family:ui-monospace,"SF Mono",Menlo,Consolas,monospace;
  font-size:clamp(20px,2.4vw,27px);font-weight:600;color:var(--hold);
  font-variant-numeric:tabular-nums;line-height:1.1
}
.stat .l{
  font-family:ui-sans-serif,-apple-system,"Segoe UI",Roboto,sans-serif;
  font-size:12px;color:var(--muted);letter-spacing:.02em
}
.sec{padding-top:48px}
.sechead{display:flex;align-items:baseline;gap:14px;border-bottom:1px solid var(--rule);padding-bottom:10px;margin-bottom:20px}
.sechead .num{
  font-family:ui-monospace,"SF Mono",Menlo,Consolas,monospace;
  font-size:12px;color:var(--muted);font-weight:600;letter-spacing:.06em
}
.sechead h2{font-size:clamp(21px,2.5vw,28px);font-weight:600;letter-spacing:-.01em}
.lede{max-width:68ch;color:var(--ink-2);margin:0 0 22px}
.note,.legend{max-width:68ch;font-size:14.5px;color:var(--muted);margin:14px 0 0}
.verdicts{display:grid;gap:1px;background:var(--rule);border:1px solid var(--rule);border-radius:3px;margin:0;overflow:hidden}
@media(min-width:760px){.verdicts{grid-template-columns:1fr 1fr}}
.v{background:var(--card);padding:16px 18px}
.v dt{
  font-family:ui-sans-serif,-apple-system,"Segoe UI",Roboto,sans-serif;
  font-size:12.5px;font-weight:600;color:var(--muted);letter-spacing:.01em;margin-bottom:6px
}
.v dd{margin:0}
.ans{display:block;font-weight:600;font-size:18px;color:var(--hold);margin-bottom:4px}
.why{display:block;font-size:14.5px;color:var(--ink-2);line-height:1.5}
.cards{display:grid;gap:14px}
@media(min-width:720px){.cards{grid-template-columns:repeat(2,1fr)}}
.card{background:var(--card);border:1px solid var(--rule);border-left:3px solid var(--ripe);
  border-radius:3px;padding:18px 20px;box-shadow:var(--shadow)}
.card .role{
  font-family:ui-sans-serif,-apple-system,"Segoe UI",Roboto,sans-serif;
  font-size:10.5px;text-transform:uppercase;letter-spacing:.12em;font-weight:700;
  color:var(--ripe);margin:0 0 8px
}
.card h3{font-size:19px;font-weight:600}
.card .who{font-size:13px;color:var(--muted);margin:2px 0 10px;
  font-family:ui-sans-serif,-apple-system,"Segoe UI",Roboto,sans-serif}
.card p{margin:0;font-size:15px;color:var(--ink-2)}
.bars{list-style:none;margin:0;padding:0;display:flex;flex-direction:column;gap:9px}
.bar{display:grid;grid-template-columns:22px minmax(0,1fr) 3fr 52px;align-items:center;gap:12px}
@media(max-width:640px){.bar{grid-template-columns:22px 1fr 46px;row-gap:5px}
  .bar .track{grid-column:1/-1}}
.bar .k{
  font-family:ui-monospace,"SF Mono",Menlo,Consolas,monospace;
  font-size:12px;font-weight:700;color:var(--muted)}
.bar .nm{font-size:15px;color:var(--ink-2)}
.bar .track{background:var(--rule-2);height:9px;border-radius:2px;overflow:hidden}
.bar .fill{display:block;height:100%;background:var(--slate);border-radius:2px}
.bar.win .fill{background:var(--hold)}
.bar.win .nm{color:var(--ink);font-weight:600}
.bar .sc{
  font-family:ui-monospace,"SF Mono",Menlo,Consolas,monospace;
  font-size:13.5px;text-align:right;font-variant-numeric:tabular-nums;color:var(--ink-2)}
.bar.win .sc{color:var(--hold);font-weight:600}
.scroll{overflow-x:auto;border:1px solid var(--rule);border-radius:3px;background:var(--card)}
table{border-collapse:collapse;width:100%;font-size:14px;
  font-family:ui-sans-serif,-apple-system,"Segoe UI",Roboto,sans-serif}
th{
  text-align:left;font-size:11px;text-transform:uppercase;letter-spacing:.09em;
  color:var(--muted);font-weight:700;padding:11px 12px;border-bottom:1px solid var(--rule);
  white-space:nowrap;background:var(--card);position:sticky;top:0;z-index:1
}
td{padding:10px 12px;border-bottom:1px solid var(--rule-2);vertical-align:top;color:var(--ink-2)}
tr:last-child td{border-bottom:none}
th.r,td.r{text-align:right;font-variant-numeric:tabular-nums}
td.ref{min-width:270px;max-width:340px;color:var(--ink)}
td.claim{min-width:280px;max-width:420px}
td.mono,.mono{font-family:ui-monospace,"SF Mono",Menlo,Consolas,monospace;font-size:12.5px;white-space:nowrap}
td.empty{color:var(--muted)}
td .val{color:var(--ink)}
sup.abs{color:var(--amber);font-weight:700;font-size:10px;margin-left:2px}
a{color:var(--hold);text-decoration-thickness:1px;text-underline-offset:2px}
a:hover{text-decoration-thickness:2px}
a:focus-visible,tr:focus-visible{outline:2px solid var(--hold);outline-offset:2px}
.chip{
  display:inline-flex;align-items:center;gap:5px;font-size:11px;padding:2px 8px;border-radius:2px;
  font-family:ui-sans-serif,-apple-system,"Segoe UI",Roboto,sans-serif;font-weight:600;
  letter-spacing:.02em;white-space:nowrap;margin-right:5px
}
.chip::before{content:"";width:7px;height:7px;border-radius:1px;background:currentColor;opacity:.85}
.lv-full{background:var(--hold-soft);color:var(--hold)}
.lv-meta{background:var(--rule-2);color:var(--slate)}
.lv-abs{background:var(--ripe-soft);color:var(--amber)}
.lv-ns{background:var(--rule-2);color:var(--muted)}
.lv-unv{background:var(--ripe-soft);color:var(--ripe)}
.mixcell{min-width:150px}
.mix{display:flex;height:9px;width:100%;border-radius:2px;overflow:hidden;background:var(--rule-2)}
.mix .s{display:block;height:100%}
.mix .lv-full{background:var(--hold)}
.mix .lv-meta{background:var(--slate)}
.mix .lv-abs{background:var(--amber)}
.mix .lv-ns{background:var(--rule)}
.mix .lv-unv{background:var(--ripe)}
.limits{display:grid;gap:14px}
@media(min-width:720px){.limits{grid-template-columns:repeat(2,1fr)}}
.limit{border-top:2px solid var(--ripe);padding-top:12px}
.limit h4{font-size:15.5px;font-weight:600;margin-bottom:5px}
.limit p{margin:0;font-size:14.5px;color:var(--ink-2)}
.foot{margin-top:56px;padding-top:20px;border-top:1px solid var(--rule)}
.foot p{max-width:70ch;font-size:14px;color:var(--muted);margin:0}
@media (prefers-reduced-motion:reduce){*{transition:none!important;animation:none!important}}
"""


def main() -> None:
    body = build()
    doc = (f"<title>1-MCP packaging — evidence dossier</title>\n"
           f"<style>{CSS}</style>\n{body}\n")
    with open(OUT, "w", encoding="utf-8") as fh:
        fh.write(doc)
    print(f"wrote {OUT} ({len(doc):,} bytes)")


if __name__ == "__main__":
    main()
