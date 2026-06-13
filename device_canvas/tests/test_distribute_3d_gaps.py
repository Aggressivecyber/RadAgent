from browser_helpers import evaluate_in_page


def main():
    values = evaluate_in_page(
        """() => {
      loadModel({components:[
        {component_id:'world_volume', display_name:'World', component_type:'world', geometry_type:'box', dimensions:{dx:120,dy:120,dz:120}, material_id:'Air', placement:{position:[0,0,0]}},
        {component_id:'left', display_name:'Left', component_type:'layer', geometry_type:'box', dimensions:{dx:10,dy:10,dz:10}, material_id:'Silicon', placement:{position:[-30,0,0]}, mother_volume:'world_volume'},
        {component_id:'mid', display_name:'Middle', component_type:'layer', geometry_type:'box', dimensions:{dx:10,dy:10,dz:10}, material_id:'SiO2', placement:{position:[-5,0,0]}, mother_volume:'world_volume'},
        {component_id:'right', display_name:'Right', component_type:'layer', geometry_type:'box', dimensions:{dx:10,dy:10,dz:10}, material_id:'Aluminum', placement:{position:[35,0,0]}, mother_volume:'world_volume'},
        {component_id:'locked', display_name:'Locked', component_type:'layer', geometry_type:'box', dimensions:{dx:10,dy:10,dz:10}, material_id:'Gold', placement:{position:[10,30,0]}, mother_volume:'world_volume', locked:true}
      ]}, 'distribute-3d-gaps');
      setViewAxes('x','z');
      selectedIds = new Set(['left','mid','right']);
      primaryId = 'left';
      renderEdit();

      const hasFns = {
        plan: typeof distributeSelection3DGapsPlan === 'function',
        apply: typeof distributeSelection3DGaps === 'function',
        axis: !!document.getElementById('distribute3dAxis'),
        button: !!document.querySelector('[data-action="distribute-3d-gaps"]'),
      };
      const plan = hasFns.plan ? distributeSelection3DGapsPlan('x') : null;
      const applied = hasFns.apply ? distributeSelection3DGaps('x') : {ok:false};
      const positionsAfter = Object.fromEntries(model.components.filter(c => ['left','mid','right'].includes(c.component_id)).map(c => [c.component_id, c.placement.position.slice()]));
      const boxesAfter = Object.fromEntries(model.components.filter(c => ['left','mid','right'].includes(c.component_id)).map(c => [c.component_id, bbox3D(c)]));
      const gapLeftMid = boxesAfter.mid.min[0] - boxesAfter.left.max[0];
      const gapMidRight = boxesAfter.right.min[0] - boxesAfter.mid.max[0];
      const reportText = selectionReportText();

      selectedIds = new Set(['left','locked','right']);
      primaryId = 'left';
      const lockedPlan = hasFns.plan ? distributeSelection3DGapsPlan('x') : {ok:false};
      const lockedResult = hasFns.apply ? distributeSelection3DGaps('x') : {ok:false};

      selectedIds = new Set(['left','mid','right']);
      primaryId = 'left';
      model.components.find(c => c.component_id === 'left').placement.position[0] = -5;
      model.components.find(c => c.component_id === 'mid').placement.position[0] = 0;
      model.components.find(c => c.component_id === 'right').placement.position[0] = 5;
      const negativePlan = hasFns.plan ? distributeSelection3DGapsPlan('x') : {ok:false};
      const negativeResult = hasFns.apply ? distributeSelection3DGaps('x') : {ok:false};

      return {
        hasFns,
        plan,
        applied,
        positionsAfter,
        gapLeftMid,
        gapMidRight,
        reportText,
        lockedPlan,
        lockedResult,
        negativePlan,
        negativeResult,
      };
    }"""
    )

    assert all(values["hasFns"].values()), values
    assert values["plan"]["ok"] is True, values
    assert values["plan"]["axis"] == "x", values
    assert values["plan"]["gap"] == 22.5, values
    assert values["plan"]["moves"] == [{"id": "mid", "delta": [7.5, 0, 0], "targetMin": -2.5}], values
    assert values["applied"]["ok"] is True, values
    assert values["applied"]["moved"] == 1, values
    assert values["positionsAfter"]["left"] == [-30, 0, 0], values
    assert values["positionsAfter"]["right"] == [35, 0, 0], values
    assert values["positionsAfter"]["mid"] == [2.5, 0, 0], values
    assert values["gapLeftMid"] == 22.5, values
    assert values["gapMidRight"] == 22.5, values
    assert "组件: left, mid, right" in values["reportText"], values
    assert values["lockedPlan"]["ok"] is False and values["lockedPlan"]["reason"] == "locked", values
    assert values["lockedResult"]["ok"] is False and values["lockedResult"]["reason"] == "locked", values
    assert values["negativePlan"]["ok"] is False and values["negativePlan"]["reason"] == "negative_gap", values
    assert values["negativeResult"]["ok"] is False and values["negativeResult"]["reason"] == "negative_gap", values
    print(values)


if __name__ == "__main__":
    main()
