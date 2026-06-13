from browser_helpers import evaluate_in_page


def main():
    values = evaluate_in_page(
        """() => {
      loadModel({components:[
        {component_id:'world_volume', display_name:'World', component_type:'world', geometry_type:'box', dimensions:{dx:80,dy:80,dz:80}, material_id:'Air', placement:{position:[0,0,0]}},
        {component_id:'a', display_name:'Sensor A', component_type:'layer', geometry_type:'box', dimensions:{dx:10,dy:20,dz:10}, material_id:'Silicon', placement:{position:[0,0,0]}, mother_volume:'world_volume'},
        {component_id:'b', display_name:'Sensor B', component_type:'electrode', geometry_type:'box', dimensions:{dx:10,dy:20,dz:10}, material_id:'Aluminum', placement:{position:[20,0,0]}, mother_volume:'world_volume'},
        {component_id:'locked', display_name:'Locked', component_type:'layer', geometry_type:'box', dimensions:{dx:10,dy:10,dz:10}, material_id:'SiO2', placement:{position:[0,25,0]}, mother_volume:'world_volume', locked:true}
      ]}, 'selection-pair-gap-adjust');
      setViewAxes('x','z');
      selectedIds = new Set(['a','b']);
      primaryId = 'a';
      renderEdit();

      const hasFns = {
        calc: typeof pairGapAdjustment === 'function',
        apply: typeof setSelectionPairGap === 'function',
        input: !!document.getElementById('pairGapTarget'),
        button: !!document.querySelector('[data-action="set-pair-gap"]'),
      };
      const before = buildSelectionReport().pairProbe.axes.find(item => item.axis === 'x');
      const calc = hasFns.calc ? pairGapAdjustment('x', 15) : null;
      const applied = hasFns.apply ? setSelectionPairGap('x', 15) : {ok:false};
      const afterComp = model.components.find(c => c.component_id === 'b');
      const afterPosition = afterComp.placement.position.slice();
      const after = buildSelectionReport().pairProbe.axes.find(item => item.axis === 'x');
      const reportText = selectionReportText();

      let viaUi = {ok:false};
      let afterUi = null;
      if(hasFns.input && typeof setSelectionPairGapFromUI === 'function'){
        document.getElementById('pairGapTarget').value = '5';
        viaUi = setSelectionPairGapFromUI();
        afterUi = buildSelectionReport().pairProbe.axes.find(item => item.axis === 'x');
      }
      const bAfterUi = model.components.find(c => c.component_id === 'b').placement.position[0];

      selectedIds = new Set(['a','locked']);
      primaryId = 'a';
      const lockedResult = hasFns.apply ? setSelectionPairGap('x', 5) : {ok:false};

      selectedIds = new Set(['a','b']);
      primaryId = 'a';
      model.components.find(c => c.component_id === 'b').placement.position[0] = 35;
      const blockedResult = hasFns.apply ? setSelectionPairGap('x', 40) : {ok:false};
      const bAfterBlocked = model.components.find(c => c.component_id === 'b').placement.position[0];

      return {
        hasFns,
        before,
        calc,
        applied,
        afterPosition,
        after,
        reportText,
        viaUi,
        afterUi,
        bAfterUi,
        lockedResult,
        blockedResult,
        bAfterBlocked,
      };
    }"""
    )

    assert all(values["hasFns"].values()), values
    assert values["before"]["gap"] == 10, values
    assert values["calc"]["ok"] is True, values
    assert values["calc"]["movingId"] == "b", values
    assert values["calc"]["axis"] == "x", values
    assert values["calc"]["delta"] == [5, 0, 0], values
    assert values["applied"]["ok"] is True, values
    assert values["afterPosition"] == [25, 0, 0], values
    assert values["after"]["gap"] == 15, values
    assert "x: 间隙 15" in values["reportText"], values
    assert values["viaUi"]["ok"] is True, values
    assert values["afterUi"]["gap"] == 5, values
    assert values["bAfterUi"] == 15, values
    assert values["lockedResult"]["ok"] is False and values["lockedResult"]["reason"] == "locked", values
    assert values["blockedResult"]["ok"] is False and values["blockedResult"]["reason"] == "no_target", values
    assert values["bAfterBlocked"] == 35, values
    print(values)


if __name__ == "__main__":
    main()
