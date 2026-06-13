from browser_helpers import evaluate_in_page


def main():
    values = evaluate_in_page(
        """() => {
      loadModel({components:[
        {component_id:'world_volume', display_name:'World', component_type:'world', geometry_type:'box', dimensions:{dx:1000,dy:1000,dz:1000}, material_id:'Air', placement:{position:[0,0,0]}},
        {component_id:'base', display_name:'Base', component_type:'layer', geometry_type:'box', dimensions:{dx:100,dy:100,dz:20}, material_id:'Silicon', placement:{position:[0,0,0]}, mother_volume:'world_volume'},
        {component_id:'near', display_name:'Near', component_type:'layer', geometry_type:'box', dimensions:{dx:100,dy:100,dz:10}, material_id:'SiO2', placement:{position:[0,0,16]}, mother_volume:'world_volume'}
      ]}, 'drc-rule-deck');
      setViewAxes('x','y');
      const deck = document.getElementById('drcRuleDeck');
      deck.value = 'detector_default';
      deck.dispatchEvent(new Event('change', {bubbles:true}));
      const afterPreset = {
        deckValue: deck.value,
        minGap: drcSettings.minGap,
        input: document.getElementById('minGapDrc').value,
        issueCodes: collectModelIssues().issues.map(i => i.code),
        report: modelHealthReportText(),
      };
      const minGapInput = document.getElementById('minGapDrc');
      minGapInput.value = '7.5';
      minGapInput.dispatchEvent(new Event('change', {bubbles:true}));
      const exportedState = buildDeviceCanvasState();
      const saved = JSON.parse(JSON.stringify(exportedState));
      drcSettings.minGap = 0;
      drcSettings.ruleDeck = 'loose_assembly';
      updateDrcUI();
      applyDeviceCanvasState(saved);
      updateDrcUI();
      return {
        afterPreset,
        afterCustom: {
          ruleDeck: drcSettings.ruleDeck,
          minGap: drcSettings.minGap,
          selectValue: document.getElementById('drcRuleDeck').value,
          exported: exportedState.drc,
        },
        afterRestore: {
          ruleDeck: drcSettings.ruleDeck,
          minGap: drcSettings.minGap,
          selectValue: document.getElementById('drcRuleDeck').value,
          input: document.getElementById('minGapDrc').value,
        }
      };
    }"""
    )

    assert values["afterPreset"]["deckValue"] == "detector_default", values
    assert abs(values["afterPreset"]["minGap"] - 2) < 1e-9, values
    assert "small_gap3d" in values["afterPreset"]["issueCodes"], values
    assert "规则: Detector default" in values["afterPreset"]["report"], values
    assert values["afterCustom"]["ruleDeck"] == "custom", values
    assert abs(values["afterCustom"]["minGap"] - 7.5) < 1e-9, values
    assert values["afterCustom"]["selectValue"] == "custom", values
    assert values["afterCustom"]["exported"]["ruleDeck"] == "custom", values
    assert abs(values["afterCustom"]["exported"]["minGap"] - 7.5) < 1e-9, values
    assert values["afterRestore"]["ruleDeck"] == "custom", values
    assert values["afterRestore"]["selectValue"] == "custom", values
    assert values["afterRestore"]["input"] == "7.5", values
    print(values)


if __name__ == "__main__":
    main()
