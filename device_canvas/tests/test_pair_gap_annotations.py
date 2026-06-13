from browser_helpers import evaluate_in_page


def main():
    values = evaluate_in_page(
        """() => {
      loadModel({components:[
        {component_id:'world_volume', display_name:'World', component_type:'world', geometry_type:'box', dimensions:{dx:200,dy:200,dz:200}, material_id:'Air', placement:{position:[0,0,0]}},
        {component_id:'a', display_name:'Sensor A', component_type:'layer', geometry_type:'box', dimensions:{dx:10,dy:20,dz:10}, material_id:'Silicon', placement:{position:[0,0,0]}, mother_volume:'world_volume'},
        {component_id:'b', display_name:'Sensor B', component_type:'electrode', geometry_type:'box', dimensions:{dx:10,dy:20,dz:10}, material_id:'Aluminum', placement:{position:[20,0,0]}, mother_volume:'world_volume'}
      ]}, 'pair-gap-annotations');
      setViewAxes('x','z');
      selectedIds = new Set(['a','b']);
      primaryId = 'a';
      renderEdit();
      const hasFns = {
        create: typeof createPairGapAnnotation === 'function',
        geom: typeof pairGapAnnotationGeometry === 'function',
        axis: typeof selectedPairDominantAxis === 'function',
      };
      const hasButton = !!document.querySelector('[data-action="annotate-pair-gap"]');
      const created = hasFns.create ? createPairGapAnnotation() : false;
      const ann = dimensionAnnotations.find(a => a.kind === 'pair_gap');
      const before = ann && annotationGeometry(ann);
      const panelBefore = document.getElementById('annotationList')?.textContent || '';
      const exported = buildDeviceCanvasState().annotations.find(a => a.kind === 'pair_gap') || null;
      const svgBefore = typeof buildSectionSVG === 'function' ? buildSectionSVG() : '';
      const dxfBefore = typeof buildSectionDXF === 'function' ? buildSectionDXF() : '';

      model.components.find(c => c.component_id === 'b').placement.position[0] = 25;
      drawComponents();
      renderAnnotationsPanel();
      const after = annotationGeometry(ann);
      const panelAfter = document.getElementById('annotationList')?.textContent || '';

      let restored = null;
      let restoredGeom = null;
      if(exported){
        loadModel({
          components:[
            {component_id:'world_volume', display_name:'World', component_type:'world', geometry_type:'box', dimensions:{dx:200,dy:200,dz:200}, material_id:'Air', placement:{position:[0,0,0]}},
            {component_id:'a', display_name:'Sensor A', component_type:'layer', geometry_type:'box', dimensions:{dx:10,dy:20,dz:10}, material_id:'Silicon', placement:{position:[0,0,0]}, mother_volume:'world_volume'},
            {component_id:'b', display_name:'Sensor B', component_type:'electrode', geometry_type:'box', dimensions:{dx:10,dy:20,dz:10}, material_id:'Aluminum', placement:{position:[25,0,0]}, mother_volume:'world_volume'}
          ],
          device_canvas_state:{annotations:[exported]}
        }, 'pair-gap-restored');
        setViewAxes('x','z');
        restored = dimensionAnnotations.find(a => a.kind === 'pair_gap');
        restoredGeom = restored && annotationGeometry(restored);
      }

      return {
        hasFns,
        hasButton,
        created,
        annotation: ann,
        before: before && {
          kind: before.kind,
          label: before.label,
          meta: before.meta,
          dist: before.dist,
          axis: before.axis,
          start: before.start,
          end: before.end,
        },
        after: after && {label: after.label, dist: after.dist, start: after.start, end: after.end},
        panelBefore,
        panelAfter,
        exported,
        restored: restored && {
          annotation: restored,
          geom: restoredGeom && {label: restoredGeom.label, dist: restoredGeom.dist, axis: restoredGeom.axis},
        },
        svgHasPairGap: svgBefore.includes('data-annotation-kind="pair_gap"') && svgBefore.includes('pair_gap:a:b:x'),
        dxfHasPairGap: dxfBefore.includes('1\\nx gap 10 um') || dxfBefore.includes('1\\nx overlap'),
      };
    }"""
    )

    assert all(values["hasFns"].values()), values
    assert values["hasButton"], values
    assert values["created"] is True, values
    ann = values["annotation"]
    assert ann["kind"] == "pair_gap", values
    assert ann["a_id"] == "a" and ann["b_id"] == "b", values
    assert ann["axis"] == "x", values
    assert ann["axes"] == {"lateral": "x", "depth": "z"}, values
    assert values["before"]["kind"] == "pair_gap", values
    assert values["before"]["label"] == "x gap 10 μm", values
    assert values["before"]["dist"] == 10, values
    assert values["before"]["start"]["lat"] == 5, values
    assert values["before"]["end"]["lat"] == 15, values
    assert "x gap 10" in values["panelBefore"], values
    assert values["after"]["label"] == "x gap 15 μm", values
    assert values["after"]["dist"] == 15, values
    assert "x gap 15" in values["panelAfter"], values
    assert values["exported"]["kind"] == "pair_gap", values
    assert values["restored"]["annotation"]["axis"] == "x", values
    assert values["restored"]["geom"]["label"] == "x gap 15 μm", values
    assert values["svgHasPairGap"], values
    assert values["dxfHasPairGap"], values
    print(values)


if __name__ == "__main__":
    main()
