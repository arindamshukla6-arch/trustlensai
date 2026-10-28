"""Visual system: deep navy surfaces, white type, a single cyan accent.

Risk bands never rely on colour alone: each badge carries a shape and a word.
"""
from __future__ import annotations

import html

import streamlit as st

CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Archivo:wdth,wght@75..100,500..800&family=Public+Sans:wght@400;500;600&display=swap');
:root{
  --navy-0:#081426; --navy-1:#0F2140; --navy-2:#16305A; --line:#24406B;
  --ink:#EAF1FA; --ink-2:#A9BAD1; --cyan:#22D3EE; --cyan-d:#0E9CB8;
  --low:#34D399; --mod:#FBBF24; --elev:#F87171; --inc:#B7C4D8;
}
html, body, [class*="css"], .stMarkdown, .stText, p, li, label { font-family:'Public Sans', system-ui, 'Segoe UI', sans-serif; }
h1,h2,h3,h4 { font-family:'Archivo', 'Arial Narrow', system-ui, sans-serif !important; font-stretch:88%; letter-spacing:-0.01em; }
.block-container{ padding-top:2.2rem; max-width:1180px; }
section[data-testid="stSidebar"]{ background:linear-gradient(180deg,#0B1A33 0%,#081426 100%); border-right:1px solid var(--line); }

/* Brand lockup: the lens ring is the one bold element in the interface */
.tl-brand{ display:flex; align-items:center; gap:.7rem; margin:.2rem 0 1.1rem; }
.tl-lens{ width:38px; height:38px; border-radius:50%; position:relative;
  background:radial-gradient(circle at 50% 50%, var(--navy-0) 0 38%, transparent 39%),
             conic-gradient(from 210deg, var(--cyan), #7DE9F7, var(--cyan-d), var(--cyan));
  box-shadow:0 0 0 1px rgba(34,211,238,.35), 0 0 24px rgba(34,211,238,.25); }
.tl-lens::after{ content:""; position:absolute; width:9px; height:9px; border-radius:50%;
  background:var(--cyan); top:14.5px; left:14.5px; }
.tl-word{ font-family:'Archivo',sans-serif; font-weight:800; font-size:1.35rem; font-stretch:80%; line-height:1; color:var(--ink); }
.tl-word span{ display:block; font-family:'Public Sans',sans-serif; font-weight:500; font-size:.72rem; color:var(--ink-2); margin-top:.25rem; font-stretch:100%; }

.tl-hero{ border:1px solid var(--line); border-radius:18px; padding:1.6rem 1.8rem; margin-bottom:1.2rem;
  background:radial-gradient(120% 140% at 100% 0%, rgba(34,211,238,.13) 0%, transparent 55%), var(--navy-1); }
.tl-hero h1{ font-size:2.35rem; margin:0 0 .35rem; font-weight:800; font-stretch:78%; line-height:1.05; }
.tl-hero p{ color:var(--ink-2); max-width:62ch; margin:0; font-size:1rem; }

.tl-metric{ background:var(--navy-1); border:1px solid var(--line); border-radius:12px; padding:1rem 1.1rem; height:100%; }
.tl-metric .v{ font-family:'Archivo',sans-serif; font-size:2.2rem; font-weight:700; font-stretch:80%; line-height:1; color:var(--ink); }
.tl-metric .l{ font-weight:600; margin-top:.35rem; color:var(--ink); font-size:.95rem; }
.tl-metric .e{ color:var(--ink-2); font-size:.82rem; margin-top:.3rem; line-height:1.35; }

.tl-badge{ display:inline-flex; align-items:center; gap:.4rem; padding:.22rem .65rem; border-radius:999px;
  font-weight:600; font-size:.85rem; border:1px solid currentColor; background:rgba(255,255,255,.03); white-space:nowrap; }
.tl-badge.low{ color:var(--low);} .tl-badge.moderate{ color:var(--mod);} .tl-badge.elevated{ color:var(--elev);} .tl-badge.inconclusive{ color:var(--inc);}
.tl-chip{ display:inline-block; padding:.12rem .5rem; border-radius:6px; font-size:.8rem; font-weight:600; }
.tl-chip.no_concern{ background:rgba(52,211,153,.12); color:var(--low);} .tl-chip.concern{ background:rgba(248,113,113,.14); color:var(--elev);}
.tl-chip.inconclusive{ background:rgba(251,191,36,.12); color:var(--mod);} .tl-chip.not_run{ background:rgba(183,196,216,.10); color:var(--inc);}
.tl-chip.error{ background:rgba(248,113,113,.10); color:#FCA5A5; border:1px dashed #FCA5A5; }

.tl-demo{ border:1px dashed #F59E0B; color:#FCD34D; background:rgba(245,158,11,.08); border-radius:10px;
  padding:.55rem .9rem; font-size:.9rem; margin:.3rem 0 1rem; }
.tl-note{ border-left:3px solid var(--cyan); background:rgba(34,211,238,.06); padding:.6rem .9rem; border-radius:0 8px 8px 0;
  color:var(--ink-2); font-size:.9rem; margin:.5rem 0 1rem; }
.tl-signal{ border:1px solid var(--line); border-radius:12px; padding:.9rem 1rem; margin-bottom:.7rem; background:var(--navy-1); }
.tl-signal h4{ margin:0 0 .35rem; font-size:1.05rem; }
.tl-signal .m{ color:var(--ink-2); font-size:.8rem; }
.tl-empty{ text-align:left; border:1px dashed var(--line); border-radius:12px; padding:1.4rem; color:var(--ink-2); }
.stButton>button, .stDownloadButton>button{ border-radius:8px; font-weight:600; }
.stButton>button[kind="primary"]{ background:var(--cyan); color:#04202A; border:none; }
.stButton>button:focus-visible, a:focus-visible{ outline:3px solid #7DE9F7 !important; outline-offset:2px; }
@media (prefers-reduced-motion: reduce){ *{ transition:none !important; animation:none !important; } }
</style>
"""

BAND_SHAPES = {"Low": "●", "Moderate": "▲", "Elevated": "◆", "Inconclusive": "?"}
RESULT_TEXT = {"no_concern": "No concern found", "concern": "Indicator found", "inconclusive": "Inconclusive",
               "not_run": "Not run", "error": "Could not complete"}


def inject() -> None:
    st.markdown(CSS, unsafe_allow_html=True)


def e(text) -> str:
    return html.escape(str(text if text is not None else ""))


def brand() -> None:
    st.markdown('<div class="tl-brand"><div class="tl-lens" aria-hidden="true"></div>'
                '<div class="tl-word">TrustLens AI<span>Signals, not verdicts</span></div></div>',
                unsafe_allow_html=True)


def hero(title: str, text: str) -> None:
    st.markdown(f'<div class="tl-hero"><h1>{e(title)}</h1><p>{e(text)}</p></div>', unsafe_allow_html=True)


def badge(band: str | None) -> str:
    if not band:
        return '<span class="tl-badge inconclusive">– Not analysed</span>'
    return f'<span class="tl-badge {e(band.lower())}">{BAND_SHAPES.get(band, "")} {e(band)}</span>'


def chip(result: str) -> str:
    return f'<span class="tl-chip {e(result)}">{e(RESULT_TEXT.get(result, result))}</span>'


def metric(label: str, value, explanation: str) -> None:
    st.markdown(f'<div class="tl-metric"><div class="v">{e(value)}</div><div class="l">{e(label)}</div>'
                f'<div class="e">{e(explanation)}</div></div>', unsafe_allow_html=True)


def note(text: str) -> None:
    st.markdown(f'<div class="tl-note">{e(text)}</div>', unsafe_allow_html=True)


def demo_banner() -> None:
    st.markdown('<div class="tl-demo"><b>Demonstration case.</b> All inputs are synthetic test files generated by code. '
                'The results below are real outputs of the implemented checks on that synthetic data.</div>',
                unsafe_allow_html=True)


def empty(text: str) -> None:
    st.markdown(f'<div class="tl-empty">{e(text)}</div>', unsafe_allow_html=True)


PLOT_LAYOUT = dict(paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                   font=dict(color="#EAF1FA", family="Public Sans, sans-serif"),
                   margin=dict(l=10, r=10, t=30, b=10),
                   xaxis=dict(gridcolor="#1E3760"), yaxis=dict(gridcolor="#1E3760"))
BAND_HEX = {"Low": "#34D399", "Moderate": "#FBBF24", "Elevated": "#F87171", "Inconclusive": "#B7C4D8"}
