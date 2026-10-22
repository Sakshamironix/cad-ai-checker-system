"""Stateless CAD operations used by the Sites API subprocess."""
from dataclasses import replace
from datetime import datetime, timezone
import hashlib
from app.geometry_check import (ENGINE_VERSION, DimensionCheck, load_drawing, load_solid,
    drawing_primitives, project_visible, align_projection, check_dimension, overall_result, svg_overlay)
from app.dxf_reader import analyze_dxf_bytes
from app.view_segmentation import segment_views
from app.step_section import section_shape
from app.runtime_limits import load_runtime_limits


def process(operation, dxf_data, step_data, settings, names):
    doc, solid = load_drawing(dxf_data), load_solid(step_data)
    limits = load_runtime_limits()
    if len(solid.Faces()) > limits.max_step_faces or len(solid.Edges()) > limits.max_step_edges:
        raise ValueError('STEP exceeds the configured geometry complexity limit.')
    analysis = analyze_dxf_bytes(dxf_data, names['drawing'])
    excluded = settings.get('excluded_layers')
    if excluded is None:
        excluded = [x for x in analysis.layers if any(s in x.upper() for s in ['DEFPOINTS','CENTER','CENTRE','BORDER','TITLE'])]
    filtered = replace(analysis, entity_locations=tuple(x for x in analysis.entity_locations
        if x.layer not in excluded and x.entity_type in {'LINE','ARC','CIRCLE','LWPOLYLINE','POLYLINE','SPLINE','ELLIPSE'}))
    views = segment_views(filtered, gap_mm=settings['gap'])
    if not views or len(views) > 50:
        raise ValueError('Expected 1–50 isolated drawing views. Adjust layers and view separation.')
    entities = list(doc.modelspace())
    dimensions = {f'DIM-{i:03d}': e for i,e in enumerate((e for e in entities if e.dxftype()=='DIMENSION'),1)}
    if not dimensions:
        raise ValueError('No native DXF DIMENSION entities. Exploded annotations cannot be verified.')
    entity_dim = {i:key for i,e in enumerate(entities,1) for key,d in dimensions.items() if e is d}
    unitless = int(doc.header.get('$INSUNITS',0)) == 0
    if operation == 'analyze':
        box = solid.BoundingBox()
        return {'engine':ENGINE_VERSION,'unitless':unitless,'layers':list(analysis.layers),'excluded_layers':excluded,
            'settings':{**settings,'excluded_layers':excluded},'dimensions':list(dimensions),'bounds':{'X':[box.xmin,box.xmax],'Y':[box.ymin,box.ymax],'Z':[box.zmin,box.zmax]},
            'views':[{'view_id':v.view_id,'dimensions':[entity_dim[i] for i in v.dimension_indexes if i in entity_dim],
                      'geometry_count':v.geometry_count} for v in views]}
    lookup = {v.view_id:v for v in views}
    selections = settings['views']
    if len({v['view_id'] for v in selections}) != len(selections):
        raise ValueError('Duplicate drawing view selection.')
    assigned = [key for v in selections for key in v['dimensions']]
    if any(key not in dimensions for key in assigned):
        raise ValueError('Unknown dimension selected.')
    previews, checks = [], []
    for selection in selections:
        if selection['view_id'] not in lookup:
            raise ValueError('Drawing views changed. Analyze the files again.')
        view = lookup[selection['view_id']]
        drawing = drawing_primitives(doc, set(view.entity_indexes), excluded)
        if not drawing:
            raise ValueError('No comparable geometry in '+view.view_id)
        projection = project_visible(solid, selection['source'], selection['hidden']) if selection['mode']=='Projection' else section_shape(solid, selection['axis'], selection['offset'])
        projection = align_projection(projection, drawing, selection['rotation']//90, selection['dx'], selection['dy'])
        local = []
        if operation == 'check':
            confirmed = selection['confirmed'] and (not unitless or settings['units_confirmed'])
            for key in selection['dimensions']:
                if assigned.count(key)==1:
                    local.append(check_dimension(dimensions[key],key,view.view_id,projection,drawing,
                        settings['association'],settings['general_tolerance'],confirmed))
            checks.extend(local)
        previews.append({'view_id':view.view_id,'svg':svg_overlay(drawing,projection,local)})
    if operation == 'preview':
        return {'previews':previews}
    checked = {c.dimension for c in checks}
    for key in dimensions:
        if key not in checked:
            reason = 'Assigned to multiple views.' if assigned.count(key)>1 else 'Not assigned to a usable drawing view.'
            checks.append(DimensionCheck(key,'Unassigned','unknown',None,None,None,None,'NG','Cannot verify: '+reason))
    return {'previews':previews,'report':{'engine':ENGINE_VERSION,'generated_at':datetime.now(timezone.utc).isoformat(),
        **names,'drawing_sha256':hashlib.sha256(dxf_data).hexdigest(),'model_sha256':hashlib.sha256(step_data).hexdigest(),
        'result':overall_result(checks),'scope':'Native assigned dimensions only; not full-shape or GD&T certification.',
        'general_tolerance_mm':settings['general_tolerance'],'association_mm':settings['association'],
        'views':selections,'checks':[c.to_dict() for c in sorted(checks,key=lambda c:c.dimension)]}}


if __name__ == '__main__':
    import json, sys
    from pathlib import Path
    folder = Path(sys.argv[1])
    request = json.loads((folder/'request.json').read_text())
    try:
        result = process(request['operation'],(folder/'drawing.dxf').read_bytes(),(folder/'model.step').read_bytes(),request['settings'],request['names'])
        output = {'data':result}
    except Exception as exc:
        output = {'error':str(exc)[:1000]}
    (folder/'response.json').write_text(json.dumps(output,allow_nan=False))
