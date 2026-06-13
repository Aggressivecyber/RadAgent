from browser_helpers import evaluate_in_page


def main():
    values = evaluate_in_page(
        """() => {
      loadModel({components:[
        {component_id:'world_volume', display_name:'World', component_type:'world', geometry_type:'box', dimensions:{dx:160,dy:160,dz:160}, material_id:'Air', placement:{position:[0,0,0]}},
        {component_id:'poly', display_name:'Editable Poly', component_type:'layer', geometry_type:'polycone', dimensions:{dx:40,dy:30,dz:10}, material_id:'Silicon', placement:{position:[0,0,0]}, mother_volume:'world_volume',
          cross_section_polygon:[[-20,-10,0],[0,-20,0],[20,-10,0],[20,10,0],[-20,10,0]], cross_section_polygon_axes:{lateral:'x',depth:'y'}}
      ]}, 'polygon-vertex-commands');
      setViewAxes('x','y');
      selectOnly('poly');
      const c = model.components.find(x => x.component_id === 'poly');

      const hasFns = {
        select: typeof selectPolygonVertex === 'function',
        move: typeof movePolygonVertex === 'function',
        reverse: typeof reversePolygonVertices === 'function',
        remove: typeof removeSelectedPolygonVertex === 'function',
      };
      const hasButtons = {
        up: !!document.querySelector('[data-action="poly-vertex-up"]'),
        down: !!document.querySelector('[data-action="poly-vertex-down"]'),
        reverse: !!document.querySelector('[data-action="poly-vertex-reverse"]'),
        remove: !!document.querySelector('[data-action="poly-vertex-remove"]'),
      };

      selectPolygonVertex(2);
      const selectedBefore = {
        state: selectedPolygonVertexIndex,
        row: document.querySelector('[data-role="polygon-vertex-row"][data-vertex-index="2"]')?.classList.contains('selected'),
        anchor: uiLayer.find('.anchor').find(a => Number(a.getAttr('pidx')) === 2)?.fill(),
      };

      const before = c.polygon.map(p => p.slice());
      movePolygonVertex(-1);
      const afterUp = {
        selected: selectedPolygonVertexIndex,
        polygon: c.polygon.map(p => p.slice()),
        rowSelected: document.querySelector('[data-role="polygon-vertex-row"][data-vertex-index="1"]')?.classList.contains('selected'),
      };
      movePolygonVertex(1);
      const afterDown = {
        selected: selectedPolygonVertexIndex,
        polygon: c.polygon.map(p => p.slice()),
      };
      reversePolygonVertices();
      const afterReverse = {
        selected: selectedPolygonVertexIndex,
        polygon: c.polygon.map(p => p.slice()),
      };
      removeSelectedPolygonVertex();
      const afterRemove = {
        selected: selectedPolygonVertexIndex,
        count: c.polygon.length,
        polygon: c.polygon.map(p => p.slice()),
        rows: Array.from(document.querySelectorAll('[data-role="polygon-vertex-row"]')).map(row => row.dataset.vertexIndex),
      };

      selectedPolygonVertexIndex = 0;
      c.polygon = [[-20,-10,0],[20,-10,0],[0,20,0]];
      renderEdit();
      const removeTriangle = removeSelectedPolygonVertex();
      const afterTriangleRemove = {removed: removeTriangle, count: c.polygon.length};

      return {hasFns, hasButtons, selectedBefore, before, afterUp, afterDown, afterReverse, afterRemove, afterTriangleRemove};
    }"""
    )

    assert all(values["hasFns"].values()), values
    assert all(values["hasButtons"].values()), values
    assert values["selectedBefore"] == {"state": 2, "row": True, "anchor": "#155eef"}, values
    assert values["afterUp"]["selected"] == 1, values
    assert values["afterUp"]["polygon"][1] == values["before"][2], values
    assert values["afterUp"]["polygon"][2] == values["before"][1], values
    assert values["afterUp"]["rowSelected"] is True, values
    assert values["afterDown"]["selected"] == 2, values
    assert values["afterDown"]["polygon"] == values["before"], values
    assert values["afterReverse"]["selected"] == 2, values
    assert values["afterReverse"]["polygon"] == list(reversed(values["before"])), values
    assert values["afterRemove"]["count"] == 4, values
    assert values["afterRemove"]["selected"] == 2, values
    assert values["afterRemove"]["rows"] == ["0", "1", "2", "3"], values
    assert values["afterTriangleRemove"] == {"removed": False, "count": 3}, values
    print(values)


if __name__ == "__main__":
    main()
