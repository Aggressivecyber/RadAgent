from browser_helpers import evaluate_in_page


def main():
    values = evaluate_in_page(
        """() => {
      loadModel({components:[
        {component_id:'world_volume', display_name:'World', component_type:'world', geometry_type:'box', dimensions:{dx:400,dy:300,dz:200}, material_id:'Air', placement:{position:[0,0,0]}},
        {component_id:'sensor', display_name:'Sensor', component_type:'layer', geometry_type:'box', dimensions:{dx:100,dy:80,dz:20}, material_id:'Silicon', placement:{position:[10,0,5]}, mother_volume:'world_volume'}
      ]}, 'component-dimensions');
      setViewAxes('x','z');
      selectOnly('sensor');

      const hasFn = typeof createDimensionsForSelection === 'function';
      const hasGeom = typeof annotationGeometry === 'function';
      const hasButton = !!document.querySelector('[data-action="annotate-selection-dimensions"]');
      createDimensionsForSelection();

      const annotationsBefore = dimensionAnnotations.map(a => ({
        kind: a.kind,
        componentId: a.component_id,
        dimension: a.dimension,
        axes: a.axes,
      }));
      const geomsBefore = dimensionAnnotations.map(a => {
        const g = annotationGeometry(a);
        return {dimension: a.dimension, dist: g && g.dist, label: g && g.label};
      });
      const panelBefore = Array.from(document.querySelectorAll('#annotationList .annotation-row b')).map(n => n.textContent);
      const lineCountBefore = annotationGroup.children.filter(n => n.className === 'Line').length;

      const sensor = model.components.find(c => c.component_id === 'sensor');
      sensor.dimensions.dx = 120;
      sensor.dimensions.dz = 30;
      sensor.placement.position[0] = 20;
      sensor.placement.position[2] = 15;
      drawComponents();
      renderAnnotationsPanel();

      const geomsAfter = dimensionAnnotations.map(a => {
        const g = annotationGeometry(a);
        return {
          dimension: a.dimension,
          dist: g && g.dist,
          start: g && g.start,
          end: g && g.end,
          label: g && g.label,
        };
      });
      const panelAfter = Array.from(document.querySelectorAll('#annotationList .annotation-row b')).map(n => n.textContent);
      const exported = buildDeviceCanvasState().annotations.map(a => ({
        kind: a.kind,
        componentId: a.component_id,
        dimension: a.dimension,
      }));

      setViewAxes('y','z');
      const inactive = dimensionAnnotations.map(a => annotationGeometry(a));

      return {hasFn, hasGeom, hasButton, annotationsBefore, geomsBefore, panelBefore, lineCountBefore, geomsAfter, panelAfter, exported, inactive};
    }"""
    )

    assert values["hasFn"], values
    assert values["hasGeom"], values
    assert values["hasButton"], values
    assert len(values["annotationsBefore"]) == 2, values
    assert {a["kind"] for a in values["annotationsBefore"]} == {"component_dimension"}, values
    assert {a["componentId"] for a in values["annotationsBefore"]} == {"sensor"}, values
    assert {a["dimension"] for a in values["annotationsBefore"]} == {"lateral", "depth"}, values
    assert all(a["axes"] == {"lateral": "x", "depth": "z"} for a in values["annotationsBefore"]), values
    assert sorted(round(g["dist"], 6) for g in values["geomsBefore"]) == [20, 100], values
    assert values["lineCountBefore"] >= 6, values
    assert any("100" in text for text in values["panelBefore"]), values
    assert any("20" in text for text in values["panelBefore"]), values

    after_by_dim = {g["dimension"]: g for g in values["geomsAfter"]}
    assert round(after_by_dim["lateral"]["dist"], 6) == 120, values
    assert round(after_by_dim["depth"]["dist"], 6) == 30, values
    assert after_by_dim["lateral"]["start"]["lat"] == -40, values
    assert after_by_dim["lateral"]["end"]["lat"] == 80, values
    assert after_by_dim["depth"]["start"]["dep"] == 0, values
    assert after_by_dim["depth"]["end"]["dep"] == 30, values
    assert any("120" in text for text in values["panelAfter"]), values
    assert any("30" in text for text in values["panelAfter"]), values
    assert {a["kind"] for a in values["exported"]} == {"component_dimension"}, values
    assert values["inactive"] == [None, None], values
    print(values)


if __name__ == "__main__":
    main()
