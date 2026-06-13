from browser_helpers import evaluate_in_page


def main():
    values = evaluate_in_page(
        """() => {
      loadModel({components:[
        {component_id:'world_volume', display_name:'World', component_type:'world', geometry_type:'box', dimensions:{dx:200,dy:200,dz:200}, material_id:'Air', placement:{position:[0,0,0]}},
        {component_id:'a', display_name:'Sensor A', component_type:'layer', geometry_type:'box', dimensions:{dx:10,dy:20,dz:10}, material_id:'Silicon', placement:{position:[0,0,0]}, mother_volume:'world_volume'},
        {component_id:'b', display_name:'Sensor B', component_type:'electrode', geometry_type:'box', dimensions:{dx:10,dy:20,dz:10}, material_id:'Aluminum', placement:{position:[20,5,0]}, mother_volume:'world_volume'},
        {component_id:'c', display_name:'Sensor C', component_type:'layer', geometry_type:'box', dimensions:{dx:10,dy:10,dz:10}, material_id:'SiO2', placement:{position:[0,40,0]}, mother_volume:'world_volume'}
      ]}, 'selection-pair-probe');
      setViewAxes('x','z');
      selectedIds = new Set(['a','b']);
      primaryId = 'a';
      renderEdit();

      const report = buildSelectionReport();
      const text = selectionReportText(report);
      const pairEl = document.getElementById('selectionPairProbe');
      const hasFns = {
        pairProbe: typeof pairwiseBBoxProbe === 'function',
        pairText: typeof pairProbeText === 'function',
      };

      selectedIds = new Set(['a']);
      primaryId = 'a';
      renderEdit();
      const singleReport = buildSelectionReport();

      return {
        hasFns,
        pairProbe: report.pairProbe,
        pairText: report.pairProbe && pairProbeText(report.pairProbe),
        panelText: pairEl ? pairEl.textContent : '',
        reportText: text,
        hasPanel: !!pairEl,
        singlePairProbe: singleReport.pairProbe || null,
      };
    }"""
    )

    assert all(values["hasFns"].values()), values
    assert values["hasPanel"], values
    probe = values["pairProbe"]
    assert probe["ids"] == ["a", "b"], values
    axes = {item["axis"]: item for item in probe["axes"]}
    assert axes["x"]["state"] == "gap", values
    assert axes["x"]["signedGap"] == 10, values
    assert axes["x"]["gap"] == 10, values
    assert axes["y"]["state"] == "overlap", values
    assert axes["y"]["signedGap"] == -15, values
    assert axes["y"]["overlap"] == 15, values
    assert axes["z"]["state"] == "overlap", values
    assert axes["z"]["signedGap"] == -10, values
    assert axes["z"]["overlap"] == 10, values
    assert probe["centerDelta"] == [20, 5, 0], values
    assert round(probe["centerDistance"], 6) == 20.615528, values
    assert "x: 间隙 10" in values["pairText"], values
    assert "y: 重叠 15" in values["panelText"], values
    assert "两组件关系" in values["reportText"], values
    assert "center Δ [20, 5, 0]" in values["reportText"], values
    assert "center distance 20.615528" in values["reportText"], values
    assert values["singlePairProbe"] is None, values
    print(values)


if __name__ == "__main__":
    main()
