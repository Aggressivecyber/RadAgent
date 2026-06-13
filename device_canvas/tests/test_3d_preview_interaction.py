from browser_helpers import evaluate_in_page


def main():
    values = evaluate_in_page(
        """() => {
      loadModel({components:[
        {component_id:'world_volume', display_name:'World', component_type:'world', geometry_type:'box', dimensions:{dx:300,dy:300,dz:180}, material_id:'Air', placement:{position:[0,0,0]}},
        {component_id:'left_block', display_name:'Left block', component_type:'layer', geometry_type:'box', dimensions:{dx:40,dy:40,dz:30}, material_id:'Silicon', placement:{position:[-70,0,0]}, mother_volume:'world_volume'},
        {component_id:'right_block', display_name:'Right block', component_type:'layer', geometry_type:'box', dimensions:{dx:40,dy:40,dz:30}, material_id:'Aluminum', placement:{position:[70,0,0]}, mother_volume:'world_volume'},
        {component_id:'upper_block', display_name:'Upper block', component_type:'layer', geometry_type:'box', dimensions:{dx:35,dy:35,dz:30}, material_id:'SiO2', placement:{position:[0,70,20]}, mother_volume:'world_volume'}
      ]}, '3d-preview-interaction');

      toggle3DPreview();
      const hasFns = {
        preset: typeof set3DViewPreset === 'function',
        hit: typeof select3DHitAt === 'function',
        pointInPoly: typeof pointInPolygon2D === 'function',
      };
      const hasButtons = ['iso','top','front','side'].every(name => !!document.querySelector(`[data-view-preset="${name}"]`));

      set3DViewPreset('top');
      const top = {
        view: preview3DView,
        label: document.getElementById('preview3dViewLabel').textContent,
        regions: last3DHitRegions.map(r => ({id:r.id, center:r.center, hull:r.hull.length})),
      };
      const rightRegion = last3DHitRegions.find(r => r.id === 'right_block');
      const selectedRight = select3DHitAt(rightRegion.center.x, rightRegion.center.y);
      const afterRight = {
        selectedRight,
        selected: Array.from(selectedIds).sort(),
        primaryId,
        labelNodes: last3DHitRegions.length,
      };

      set3DViewPreset('front');
      const frontRegion = last3DHitRegions.find(r => r.id === 'upper_block');
      const frontBefore = {view: preview3DView, region: !!frontRegion, center: frontRegion && frontRegion.center};
      const selectedUpper = select3DHitAt(frontRegion.center.x, frontRegion.center.y, true);
      const afterAdditive = {
        selectedUpper,
        selected: Array.from(selectedIds).sort(),
        primaryId,
      };

      set3DViewPreset('iso');
      rotate3D(18);
      const afterIsoRotate = {
        view: preview3DView,
        angle: preview3DAngle,
        label: document.getElementById('preview3dViewLabel').textContent,
        regions: last3DHitRegions.map(r => r.id).sort(),
      };

      const miss = select3DHitAt(-100, -100);
      return {hasFns, hasButtons, top, afterRight, frontBefore, afterAdditive, afterIsoRotate, miss};
    }"""
    )

    assert all(values["hasFns"].values()), values
    assert values["hasButtons"], values
    assert values["top"]["view"] == "top", values
    assert values["top"]["label"] == "Top", values
    assert {r["id"] for r in values["top"]["regions"]} == {"left_block", "right_block", "upper_block"}, values
    assert all(r["hull"] >= 4 for r in values["top"]["regions"]), values
    assert values["afterRight"]["selectedRight"] == "right_block", values
    assert values["afterRight"]["selected"] == ["right_block"], values
    assert values["afterRight"]["primaryId"] == "right_block", values

    assert values["frontBefore"]["view"] == "front", values
    assert values["frontBefore"]["region"], values
    assert values["afterAdditive"]["selectedUpper"] == "upper_block", values
    assert values["afterAdditive"]["selected"] == ["right_block", "upper_block"], values
    assert values["afterAdditive"]["primaryId"] == "upper_block", values

    assert values["afterIsoRotate"]["view"] == "iso", values
    assert values["afterIsoRotate"]["angle"] == 53, values
    assert values["afterIsoRotate"]["label"] == "Iso", values
    assert values["afterIsoRotate"]["regions"] == ["left_block", "right_block", "upper_block"], values
    assert values["miss"] is None, values
    print(values)


if __name__ == "__main__":
    main()
