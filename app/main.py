"""Focused Streamlit entry point for figure-based dimension verification."""
from __future__ import annotations
import csv
import hashlib
import io
import json
import sys
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import streamlit as st
import streamlit.components.v1 as components
from app.geometry_check import (ENGINE_VERSION, DimensionCheck, align_projection,
    check_dimension, drawing_primitives, load_drawing, load_solid, overall_result,
    project_visible, svg_overlay)
from app.dxf_reader import analyze_dxf_bytes
from app.view_segmentation import segment_views
from app.step_section import section_shape

APP_NAME = 'CAD AI Checker'
APP_STAGE = 'Geometry-based dimension verification / 図形に基づく寸法照合'

def get_app_status():
    return {'application': APP_NAME, 'stage': APP_STAGE, 'version': ENGINE_VERSION}


def pdf_report(payload):
    from reportlab.pdfgen import canvas
    from reportlab.lib.pagesizes import A4
    import textwrap
    buffer = io.BytesIO(); c = canvas.Canvas(buffer, pagesize=A4)
    c.setTitle('CAD dimension verification')
    y = 805
    lines = [f"CAD dimension verification — {payload['result']}",
             f"Engine: {ENGINE_VERSION} | UTC: {payload['generated_at']}",
             f"Drawing: {payload['drawing']} | Model: {payload['model']}",
             'Scope: assigned dimensions only. Not full shape or GD&T certification.',
             f"DXF SHA256: {payload['drawing_sha256']}", f"STEP SHA256: {payload['model_sha256']}", '']
    for row in payload['checks']:
        lines.extend([f"{row['dimension']} | {row['view']} | {row['kind']} | {row['result']}",
                      f"Nominal: {row['nominal']}  Model: {row['measured']}  Limits: {row['lower']} to {row['upper']}",
                      f"Tolerance source: {row['tolerance_source']}",
                      f"Features: {', '.join(row['features'])}", row['reason'], ''])
    lines += ['View and section settings:', json.dumps(payload['views'], ensure_ascii=True)]
    for text in lines:
        for line in textwrap.wrap(text, 100) or ['']:
            if y < 45: c.showPage(); y = 805
            c.setFont('Helvetica', 8); c.drawString(30, y, line); y -= 12
    c.save(); return buffer.getvalue()


def main():
    st.set_page_config(page_title=APP_NAME, layout='wide')
    st.title('CAD dimension checker / CAD寸法照合')
    st.caption('DXF drawing → STEP view or real section → feature measurement → dimension limits')
    st.caption(f'{ENGINE_VERSION} · Checks assigned dimensions only; unsupported evidence is NG — cannot verify.')
    a,b = st.columns(2)
    dxf = a.file_uploader('2D drawing / 2D図面 (.dxf)', type=['dxf'])
    step = b.file_uploader('3D model / 3Dモデル (.step / .stp)', type=['step','stp'])
    with st.expander('Comparison settings / 照合設定'):
        use_general = st.checkbox('Apply project tolerance where the drawing has no explicit limit / 普通公差を適用', value=False)
        general = st.number_input('Project tolerance ± mm / プロジェクト公差', min_value=.0001, value=.1, format='%.4f', disabled=not use_general)
        association = st.number_input('Maximum anchor search distance (mm)', min_value=.001, max_value=10., value=1., format='%.3f')
        st.caption('Anchor search distance locates a nearby feature; it is NOT the pass/fail tolerance. Equally close features remain unresolved.')
    if not (dxf and step):
        st.info('Upload both files. Select the corresponding view or cut plane, inspect alignment, then run the dimension check.')
        return
    drawing_data, model_data = dxf.getvalue(), step.getvalue()
    signature = hashlib.sha256(drawing_data+model_data).hexdigest()
    if st.session_state.get('input_signature') != signature:
        st.session_state.pop('report', None)
        try:
            with st.spinner('Reading geometry…'):
                doc, solid = load_drawing(drawing_data), load_solid(model_data)
                analysis = analyze_dxf_bytes(drawing_data, dxf.name)
            st.session_state.update(input_signature=signature, cad_doc=doc, cad_solid=solid,
                                    cad_analysis=analysis, projection_cache={})
        except Exception as exc:
            st.error(f'Cannot read geometry: {exc}'); return
    doc, solid, analysis = (st.session_state[k] for k in ('cad_doc','cad_solid','cad_analysis'))
    if int(doc.header.get('$INSUNITS', 0)) == 0:
        st.warning('The DXF is unitless. Confirm that its geometry is in millimetres.')
        units_ok = st.checkbox('This DXF is in millimetres', key='units_'+signature)
    else: units_ok = True
    entities = list(doc.modelspace())
    dimensions = {f'DIM-{i:03d}': e for i,e in enumerate((e for e in entities if e.dxftype()=='DIMENSION'),1)}
    entity_dim = {i: key for i,e in enumerate(entities,1) for key,d in dimensions.items() if e is d}
    if not dimensions:
        st.error('NG — cannot verify: no native DXF DIMENSION entities. Exploded text/lines are not treated as dimensions.'); return
    with st.expander('Drawing layers and view separation / レイヤー・ビュー分離'):
        layers = list(analysis.layers)
        excluded = st.multiselect('Exclude annotation, centreline, border, or construction layers', layers,
                                  default=[x for x in layers if any(s in x.upper() for s in ['DEFPOINTS','CENTER','CENTRE','BORDER','TITLE'])])
        gap = st.number_input('View separation gap (mm)', min_value=0., max_value=100., value=2.)
        st.caption('Check each preview. Exploded annotations on a geometry layer must be separated in the DXF before checking.')
    filtered = replace(analysis, entity_locations=tuple(x for x in analysis.entity_locations if x.layer not in excluded and x.entity_type in {'LINE','ARC','CIRCLE','LWPOLYLINE','POLYLINE','SPLINE','ELLIPSE'}))
    views = segment_views(filtered, gap_mm=gap)
    if not views:
        st.error('No comparable drawing views found.'); return
    st.subheader('Views and dimensions / ビューと寸法')
    st.caption('Select the actual projection or section for each view. Dark grey: DXF. Amber: STEP. Alignment is rigid; no automatic resizing.')
    prepared=[]; selections=[]; assigned=[]; errors=[]
    box=solid.BoundingBox()
    for view in views:
        drawing = drawing_primitives(doc, set(view.entity_indexes), excluded)
        if not drawing: continue
        with st.expander(view.view_id, expanded=True):
            default=[entity_dim[i] for i in view.dimension_indexes if i in entity_dim]
            chosen=st.multiselect('Dimensions belonging to this figure',list(dimensions),default=default,key=signature+view.view_id+'dims')
            c1,c2,c3=st.columns(3)
            mode=c1.selectbox('STEP geometry', ['Projection','Section'],key=view.view_id+'mode')
            offset=None; axis=None; hidden=False
            if mode=='Projection':
                name=c2.selectbox('View', ['top','front','right','bottom','rear','left'], key=view.view_id+'source')
                hidden=c3.checkbox('Include hidden edges',key=view.view_id+'hidden')
            else:
                axis=c2.selectbox('Cut normal',list('XYZ'),key=view.view_id+'axis')
                lo,hi={'X':(box.xmin,box.xmax),'Y':(box.ymin,box.ymax),'Z':(box.zmin,box.zmax)}[axis]
                offset=c3.number_input(f'{axis} plane position (STEP mm)',value=float((lo+hi)/2),key=signature+view.view_id+axis+'offset')
                name=f'{axis} section at {offset:g} mm'
                st.caption('A real intersection with the solid at this absolute coordinate. Confirm that it matches the drawing cutting plane. Oblique/stepped sections are not supported.')
            r,t,u=st.columns(3)
            rotation=r.selectbox('Rotation (degrees)', [0,90,180,270],key=view.view_id+'rotation')
            dx=t.number_input('Alignment X offset (mm)',value=0.,key=view.view_id+'dx')
            dy=u.number_input('Alignment Y offset (mm)',value=0.,key=view.view_id+'dy')
            settings={'view':view.view_id,'mode':mode,'source':name,'axis':axis,'offset':offset,'hidden':hidden,'rotation':rotation,'dx':dx,'dy':dy,'dimensions':chosen,'excluded_layers':excluded,'gap':gap}
            confirmation_key=hashlib.sha256((signature+json.dumps(settings,sort_keys=True)).encode()).hexdigest()
            try:
                cache=st.session_state.projection_cache
                key=(mode,name,hidden)
                if key not in cache:
                    cache[key]=project_visible(solid,name,hidden) if mode=='Projection' else section_shape(solid,axis,offset)
                projection=align_projection(cache[key],drawing,rotation//90,dx,dy)
                components.html(svg_overlay(drawing,projection),height=400)
                confirmed=st.checkbox('This view/section and alignment match the drawing / 投影・断面と位置を確認',key=confirmation_key)
                prepared.append((view.view_id,chosen,projection,drawing,confirmed and units_ok))
            except Exception as exc:
                st.error(f'Cannot generate this view: {exc}')
                if chosen: errors.extend(chosen)
            assigned.extend(chosen); selections.append(settings)
    run_signature=hashlib.sha256(json.dumps([signature,selections,use_general,general,association,[(p[0],p[4]) for p in prepared]],sort_keys=True).encode()).hexdigest()
    if st.session_state.get('report_signature') != run_signature: st.session_state.pop('report',None)
    if st.button('Check dimensions / 寸法照合',type='primary'):
        checks=[]
        for view_id,chosen,projection,drawing,confirmed in prepared:
            for key in chosen:
                if assigned.count(key)>1: continue
                checks.append(check_dimension(dimensions[key],key,view_id,projection,drawing,association,general if use_general else None,confirmed))
        checked={c.dimension for c in checks}
        for key in dimensions:
            if key not in checked:
                reason='Assigned to multiple views.' if assigned.count(key)>1 else 'View generation failed.' if key in errors else 'Not assigned to a usable drawing view.'
                checks.append(DimensionCheck(key,'Unassigned','unknown',None,None,None,None,'NG','Cannot verify: '+reason))
        payload={'engine':ENGINE_VERSION,'generated_at':datetime.now(timezone.utc).isoformat(),
                 'drawing':dxf.name,'model':step.name,'drawing_sha256':hashlib.sha256(drawing_data).hexdigest(),
                 'model_sha256':hashlib.sha256(model_data).hexdigest(),'result':overall_result(checks),
                 'scope':'Native assigned dimensions only; not full-shape or GD&T certification.',
                 'general_tolerance_mm':general if use_general else None,'association_mm':association,
                 'views':selections,'checks':[c.to_dict() for c in sorted(checks,key=lambda x:x.dimension)]}
        st.session_state.update(report=payload,report_signature=run_signature)
    report=st.session_state.get('report')
    if report:
        st.subheader('Dimension result / 寸法判定: '+report['result'])
        st.caption('NG distinguishes a measured mismatch from evidence that could not be verified. Undimensioned geometry is outside this result.')
        st.dataframe([{k:v for k,v in row.items() if k not in {'anchors','features'}} for row in report['checks']],use_container_width=True,hide_index=True)
        with st.expander('Matched features / 照合箇所'):
            for view_id,chosen,projection,drawing,confirmed in prepared:
                evidence=[DimensionCheck(**row) for row in report['checks'] if row['view']==view_id]
                st.write(view_id); components.html(svg_overlay(drawing,projection,evidence),height=400)
            st.json(report)
        output=io.StringIO(); writer=csv.DictWriter(output,fieldnames=list(report['checks'][0]))
        writer.writeheader(); writer.writerows(report['checks'])
        x,y,z=st.columns(3)
        x.download_button('Download CSV',output.getvalue().encode('utf-8-sig'),'dimension-check.csv','text/csv')
        y.download_button('Download JSON',json.dumps(report,indent=2),'dimension-check.json','application/json')
        z.download_button('Download PDF',pdf_report(report),'dimension-check.pdf','application/pdf')

if __name__=='__main__':
    main()
