from browser_helpers import evaluate_in_page


def main():
    values = evaluate_in_page(
        """() => {
      loadModel({components:[
        {component_id:'world_volume', display_name:'World', component_type:'world', geometry_type:'box', dimensions:{dx:120,dy:120,dz:120}, material_id:'Air', placement:{position:[0,0,0]}},
        {component_id:'poly', display_name:'Editable Poly', component_type:'layer', geometry_type:'polycone', dimensions:{dx:20,dy:20,dz:10}, material_id:'Silicon', placement:{position:[0,0,0]}, mother_volume:'world_volume',
          cross_section_polygon:[[-10,-10,0],[10,-10,0],[10,10,0],[-10,10,0]], cross_section_polygon_axes:{lateral:'x',depth:'y'}}
      ]}, 'polygon-vertex-inputs');
      setViewAxes('x','y');
      selectOnly('poly');
      const c = model.components.find(x => x.component_id === 'poly');
      const hasTable = !!document.querySelector('[data-role="polygon-vertex-table"]');
      const rowsBefore = Array.from(document.querySelectorAll('[data-role="polygon-vertex-row"]')).map(row => row.dataset.vertexIndex);
      const x0 = document.querySelector('[data-vertex-axis="lat"][data-vertex-index="0"]');
      const y0 = document.querySelector('[data-vertex-axis="dep"][data-vertex-index="0"]');
      const hasInputs = !!x0 && !!y0;

      if (x0) {
        x0.value = '-20';
        x0.dispatchEvent(new Event('input', {bubbles:true}));
        x0.dispatchEvent(new Event('change', {bubbles:true}));
      }
      if (y0) {
        y0.value = '-15';
        y0.dispatchEvent(new Event('input', {bubbles:true}));
        y0.dispatchEvent(new Event('change', {bubbles:true}));
      }
      const afterValid = {
        point: c.polygon[0].slice(),
        box: bbox3D(c),
        shapePoints: rectNodes.get('poly').shape.points(),
        expectedScreen: {x:X(-20), y:Y(-15)},
        xValue: document.querySelector('[data-vertex-axis="lat"][data-vertex-index="0"]')?.value,
        yValue: document.querySelector('[data-vertex-axis="dep"][data-vertex-index="0"]')?.value,
      };

      const x0b = document.querySelector('[data-vertex-axis="lat"][data-vertex-index="0"]');
      if (x0b) {
        x0b.value = '-500';
        x0b.dispatchEvent(new Event('input', {bubbles:true}));
        x0b.dispatchEvent(new Event('change', {bubbles:true}));
      }
      const afterBlocked = {
        point: c.polygon[0].slice(),
        box: bbox3D(c),
        xValue: document.querySelector('[data-vertex-axis="lat"][data-vertex-index="0"]')?.value,
        selected: Array.from(selectedIds),
        historyPtr: history.ptr,
      };

      return {hasTable, rowsBefore, hasInputs, afterValid, afterBlocked};
    }"""
    )

    assert values["hasTable"], values
    assert values["rowsBefore"] == ["0", "1", "2", "3"], values
    assert values["hasInputs"], values
    assert values["afterValid"]["point"] == [-20, -15, 0], values
    assert values["afterValid"]["box"]["min"][:2] == [-20, -15], values
    assert values["afterValid"]["xValue"] == "-20", values
    assert values["afterValid"]["yValue"] == "-15", values
    pts = values["afterValid"]["shapePoints"]
    ex = values["afterValid"]["expectedScreen"]["x"]
    ey = values["afterValid"]["expectedScreen"]["y"]
    assert any(
        idx % 2 == 0 and abs(v - ex) < 1e-6 and abs(pts[idx + 1] - ey) < 1e-6
        for idx, v in enumerate(pts[:-1])
    ), values
    assert values["afterBlocked"]["point"] == [-20, -15, 0], values
    assert values["afterBlocked"]["box"]["min"][:2] == [-20, -15], values
    assert values["afterBlocked"]["xValue"] == "-20", values
    assert values["afterBlocked"]["selected"] == ["poly"], values
    assert values["afterBlocked"]["historyPtr"] >= 0, values
    print(values)


if __name__ == "__main__":
    main()
