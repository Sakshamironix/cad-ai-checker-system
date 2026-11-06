"""Dashboard presentation, kept separate from dimensional measurement."""
from dataclasses import replace
from html import escape
from pathlib import Path
import base64
import numpy as np
import streamlit as st
import streamlit.components.v1 as components
from app.geometry_check import bounds, svg_overlay

def header(version):
    art=base64.b64encode((Path(__file__).parent/'assets/exploded-superbike.png').read_bytes()).decode()
    st.markdown('''<style>
    :root {color-scheme:dark;}
    .stApp,[data-testid="stAppViewContainer"] {background:#0b2233;color:#e9f3fa;}
    [data-testid="stHeader"] {background:#0b2233;}
    .block-container {max-width:1440px;padding:1rem 1.25rem 3rem;}
    h1,h2,h3,h4,p,label,[data-testid="stWidgetLabel"],.stCaption {color:#e9f3fa!important;}
    [data-testid="stCaptionContainer"] {color:#a2bece!important;}
    [data-testid="stFileUploader"] {padding:0;background:transparent;}
    [data-testid="stFileUploaderDropzone"] {background:#14354b;border:1px dashed #578198;border-radius:6px;}
    [data-testid="stFileUploaderDropzone"] * {color:#d1e4ef;}
    [data-baseweb="input"],[data-baseweb="select"]>div {background:#14354b!important;color:#e9f3fa!important;border-color:#426981!important;}
    input {color:#e9f3fa!important;}
    [data-testid="stExpander"] {background:#0e293c;border:1px solid #294d63;border-radius:6px;}
    [data-testid="stMetric"] {background:#123247;border:1px solid #294d63;border-radius:6px;padding:15px;}
    [data-testid="stBaseButton-primary"] {background:#1685ef;border:1px solid #40a1f9;color:white;min-height:46px;}
    [data-testid="stBaseButton-secondary"],[data-testid="stBaseButton-secondaryFormSubmit"] {background:#123247;color:#e9f3fa;border:1px solid #39657f;}
    [data-baseweb="tab-list"] {background:#102e42;border-bottom:1px solid #365b70;gap:0;}
    [data-baseweb="tab"] {color:#d3e5ef;padding:12px 18px;}
    [data-baseweb="tab-highlight"] {background:#25c6e9;}
    .cad-hero {position:relative;min-height:255px;overflow:hidden;background:#0d293b;margin:-1rem -1.25rem 0;padding:24px 20px;}
    .cad-hero img {position:absolute;right:0;top:0;height:100%;width:47%;object-fit:cover;object-position:center;}
    .cad-hero .copy {position:relative;z-index:1;width:54%;}
    .cad-hero h1 {font-size:clamp(30px,4.5vw,55px);line-height:1.12;margin:0 0 12px;letter-spacing:-2px;font-weight:850;}
    .cad-hero h1 span {color:#22c9ee;}
    .cad-hero .badge {color:#23c5e7;font-size:13px;font-weight:700;margin:6px 0 18px;}
    .cad-hero p {font-size:14px;color:#acc5d3!important;margin:0;line-height:1.65;max-width:640px;}
    h3 {border-left:2px solid #2bd1e5;padding-left:12px;}
    @media(max-width:700px){.cad-hero{min-height:230px}.cad-hero .copy{width:100%}.cad-hero img{width:55%;opacity:.2}.cad-hero h1{letter-spacing:-1px}.block-container{padding-left:12px;padding-right:12px}}
    </style>''',unsafe_allow_html=True)
    st.markdown(f'''<header class="cad-hero"><img src="data:image/png;base64,{art}" alt="Exploded blue motorcycle engineering illustration"><div class="copy"><h1>CAD <span>AI</span> Checker</h1><div class="badge">Geometry verification workspace · {escape(version)}<br>2D図面と3Dモデルの寸法照合</div><p>Compare 2D engineering drawings with 3D CAD models using matched views, real sections and measured features.<br>2D図面と3Dモデルを、対応する図と寸法で比較します。</p></div></header>''',unsafe_allow_html=True)

def comparison_panels(drawing,projection,checks=()):
    """Separate source views from the intentional comparison overlay."""
    a,b=st.columns(2)
    with a:
        st.caption('2D DXF drawing / 2D図面')
        blank=replace(projection,primitives=())
        components.html(svg_overlay(drawing,blank).replace('height="380"','height="230"'),height=255)
    with b:
        st.caption('Selected STEP view / 選択した3D投影')
        components.html(svg_overlay((),projection).replace('height="380"','height="230"'),height=255)
    st.caption('Comparison overlay / 重ね合わせ · Grey: DXF · Amber: STEP. Matching outlines overlap intentionally.')
    components.html(svg_overlay(drawing,projection,checks),height=400)

def projection_sheet_layout(projections,gap=None):
    """Centre each view in a disjoint cell, at one common model-space scale.

    tx = column * (max_width + gap) + (max_width - width)/2 - xmin
    ty = -row * (max_height + gap) + (max_height - height)/2 - ymin
    Transforms are for the contact sheet only, never measurement coordinates.
    """
    extents=[bounds(p.primitives) for p in projections]
    sizes=[hi-lo for lo,hi in extents]
    mw=max(float(s[0]) for s in sizes);mh=max(float(s[1]) for s in sizes)
    gap=max(mw,mh)*.25+1 if gap is None else float(gap)
    if gap<=0:raise ValueError('Projection sheet spacing must be positive.')
    placements=[]
    for i,(p,(lo,hi),size) in enumerate(zip(projections,extents,sizes)):
        x=(i%3)*(mw+gap)+(mw-size[0])/2-lo[0]
        y=-(i//3)*(mh+gap)+(mh-size[1])/2-lo[1]
        placements.append((p,x,y))
    return placements,mw,mh,gap

def svg_projection_sheet(projections):
    placements,mw,mh,gap=projection_sheet_layout(projections)
    parts=[]
    for p,dx,dy in placements:
        def move(q):return replace(q,x=q.x+dx,y=q.y+dy)
        primitives=tuple(replace(q,points=tuple(move(v) for v in q.points),center=move(q.center) if q.center else None) for q in p.primitives)
        parts.extend(primitives)
    combined=replace(projections[0],primitives=tuple(parts))
    svg=svg_overlay((),combined)
    # Reserve a label strip in the existing inter-cell space.
    labels=[];fs=max(mw,mh)*.055
    for i,(p,dx,dy) in enumerate(placements):
        lo,hi=bounds(p.primitives)
        labels.append(f'<text x="{lo[0]+dx}" y="{-hi[1]-dy-gap*.14}" fill="#334155" font-size="{fs}">{escape(p.view)} · {p.width:.3g} × {p.height:.3g} mm</text>')
    return svg.replace('height="380"','height="540"').replace('</svg>',''.join(labels)+'</svg>')
