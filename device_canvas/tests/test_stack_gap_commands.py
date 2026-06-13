from browser_helpers import evaluate_in_page


def main():
    values = evaluate_in_page(
        """() => {
      loadModel({components:[
        {component_id:'world_volume', display_name:'World', component_type:'world', geometry_type:'box', dimensions:{dx:400,dy:400,dz:160}, material_id:'Air', placement:{position:[0,0,0]}},
        {component_id:'base', display_name:'Base', component_type:'layer', geometry_type:'box', dimensions:{dx:100,dy:100,dz:40}, material_id:'Silicon', placement:{position:[0,0,-30]}, mother_volume:'world_volume'},
        {component_id:'gap_layer', display_name:'Gap layer', component_type:'layer', geometry_type:'box', dimensions:{dx:100,dy:100,dz:10}, material_id:'SiO2', placement:{position:[0,0,-2]}, mother_volume:'world_volume'},
        {component_id:'top_layer', display_name:'Top layer', component_type:'layer', geometry_type:'box', dimensions:{dx:100,dy:100,dz:10}, material_id:'Aluminum', placement:{position:[0,0,11]}, mother_volume:'world_volume'}
      ]}, 'stack-gap-commands');
      setViewAxes('x','y');
      drcSettings.minGap = 4;
      drcSettings.ruleDeck = 'custom';
      updateDrcUI();
      renderStackInspector();

      const relationFor = (id) => collectStackRelations('z').find(r => r.b.component.component_id === id);
      const gapBefore = relationFor('gap_layer').rawGap;
      const touchBtn = document.querySelector('.stack-relation[data-kind="small_gap"] .stack-action[data-action="touch"]');
      touchBtn.click();
      const gapAfterTouch = relationFor('gap_layer').rawGap;
      const afterTouchZ = model.components.find(c => c.component_id === 'gap_layer').placement.position[2];

      renderStackInspector();
      const touchRel = relationFor('gap_layer');
      const touchRelEl = Array.from(document.querySelectorAll('.stack-relation'))
        .find(el => el.dataset.rel === stackRelationKey(touchRel));
      const drcBtn = touchRelEl.querySelector('.stack-action[data-action="drc-gap"]');
      drcBtn.click();
      const gapAfterDrc = relationFor('gap_layer').rawGap;
      const afterDrcZ = model.components.find(c => c.component_id === 'gap_layer').placement.position[2];

      model.components.find(c => c.component_id === 'gap_layer').placement.position[2] = 65;
      model.components.find(c => c.component_id === 'top_layer').placement.position[2] = 75;
      renderStackInspector();
      const topRel = relationFor('top_layer');
      const topRelBefore = topRel.rawGap;
      const topRelEl = Array.from(document.querySelectorAll('.stack-relation'))
        .find(el => el.dataset.rel === stackRelationKey(topRel));
      const topDrcBtn = topRelEl.querySelector('.stack-action[data-action="drc-gap"]');
      const historyBeforeFailed = history.ptr;
      topDrcBtn.click();
      const topAfter = model.components.find(c => c.component_id === 'top_layer');
      const topRelAfter = relationFor('top_layer').rawGap;
      const topBox = bbox3D(topAfter);
      const worldBox = bbox3D(model.components.find(c => c.component_id === 'world_volume'));

      return {
        gapBefore,
        gapAfterTouch,
        afterTouchZ,
        gapAfterDrc,
        afterDrcZ,
        topRelBefore,
        topRelAfter,
        topZAfter: topAfter.placement.position[2],
        topInsideWorld: aabbContains(worldBox, topBox),
        selected: Array.from(selectedIds).sort(),
        historyBeforeFailed,
        historyPtr: history.ptr,
      };
    }"""
    )

    assert abs(values["gapBefore"] - 3) < 1e-9, values
    assert abs(values["gapAfterTouch"]) < 1e-9, values
    assert abs(values["afterTouchZ"] - -5) < 1e-9, values
    assert abs(values["gapAfterDrc"] - 4) < 1e-9, values
    assert abs(values["afterDrcZ"] - -1) < 1e-9, values
    assert abs(values["topRelBefore"]) < 1e-9, values
    assert abs(values["topRelAfter"] - values["topRelBefore"]) < 1e-9, values
    assert abs(values["topZAfter"] - 75) < 1e-9, values
    assert values["topInsideWorld"], values
    assert values["selected"] == ["gap_layer"], values
    assert values["historyPtr"] == values["historyBeforeFailed"] >= 2, values
    print(values)


if __name__ == "__main__":
    main()
