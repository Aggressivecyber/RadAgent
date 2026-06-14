from browser_helpers import evaluate_in_page


def main():
    values = evaluate_in_page(
        """() => {
      loadModel({components:[
        {component_id:'world_volume', display_name:'World', component_type:'world', geometry_type:'box', dimensions:{dx:200,dy:200,dz:200}, material_id:'Air', placement:{position:[0,0,0]}},
        {component_id:'poly_box', display_name:'Poly Box', component_type:'layer', geometry_type:'box', dimensions:{dx:100,dy:100,dz:20}, material_id:'Silicon', placement:{position:[0,0,0]}, mother_volume:'world_volume'}
      ]}, 'polygon-node-editing');
      setViewAxes('x','y');
      snapSettings.thresholdPx = 4;
      updateSnapUI();

      const c = model.components.find(x => x.component_id === 'poly_box');
      c.polygon = makeRectPolygon(c);
      c.polygonAxes = {lateral:'x', depth:'y'};
      c.geometry_type = 'polycone';
      polyEditId = c.component_id;
      selectedIds = new Set([c.component_id]);
      primaryId = c.component_id;
      drawComponents();

      const before = c.polygon.length;
      const box = polyBBox(c);
      const tooFarGap = 12 / camera.sDep;
      const tooFar = insertPolyNodeNear(c, 0, box.minDep + tooFarGap);
      const afterTooFar = c.polygon.length;

      const nearGap = 3 / camera.sDep;
      const near = insertPolyNodeNear(c, 0, box.minDep + nearGap);
      const insertedIndex = c.polygon.findIndex(p => Math.abs(p[0]) < 1e-9 && Math.abs(p[1] - box.minDep) < 1e-9);
      const insertedPointBeforeDrag = c.polygon[insertedIndex].slice();
      drawComponents();
      const anchors = uiLayer.find('.anchor');
      const anchor = anchors.find(a => Number(a.getAttr('pidx')) === insertedIndex);
      const style = anchor ? {
        radius: anchor.radius(),
        fill: anchor.fill(),
        stroke: anchor.stroke(),
        strokeWidth: anchor.strokeWidth(),
        hitStrokeWidth: anchor.hitStrokeWidth(),
        strokeScale: anchor.strokeScaleEnabled(),
      } : null;

      const dragTarget = {lat: 15, dep: box.minDep + 10};
      anchor.x(X(dragTarget.lat));
      anchor.y(Y(dragTarget.dep));
      anchor.fire('dragmove');
      anchor.fire('dragend');
      const draggedPoint = c.polygon[insertedIndex].slice();
      const shapePoints = rectNodes.get(c.component_id).shape.points();
      const renderedAtDragTarget = shapePoints.some((v, idx) => idx % 2 === 0 &&
        Math.abs(v - X(dragTarget.lat)) < 1e-6 &&
        Math.abs(shapePoints[idx + 1] - Y(dragTarget.dep)) < 1e-6);

      snapSettings.enabled = true;
      snapSettings.grid = true;
      snapSettings.components = false;
      snapSettings.canvas = false;
      snapSettings.gridStep = 10;
      snapSettings.thresholdPx = 80;
      updateSnapUI();
      drawComponents();
      const anchorAfterSnapRedraw = uiLayer.find('.anchor').find(a => Number(a.getAttr('pidx')) === insertedIndex);
      anchorAfterSnapRedraw.x(X(23));
      anchorAfterSnapRedraw.y(Y(-36));
      anchorAfterSnapRedraw.fire('dragmove');
      anchorAfterSnapRedraw.fire('dragend');
      const snappedPoint = c.polygon[insertedIndex].slice();

      return {
        before,
        tooFar,
        afterTooFar,
        near,
        afterNear: c.polygon.length,
        insertedPointBeforeDrag,
        insertedIndex,
        anchorCount: anchors.length,
        style,
        draggedPoint,
        renderedAtDragTarget,
        snappedPoint,
      };
    }"""
    )

    assert values["before"] == 4, values
    assert values["tooFar"] is False, values
    assert values["afterTooFar"] == 4, values
    assert values["near"] is True, values
    assert values["afterNear"] == 5, values
    assert values["insertedIndex"] >= 0, values
    assert values["insertedPointBeforeDrag"] == [0, -50, 0], values
    assert values["anchorCount"] == 5, values
    assert values["style"]["radius"] <= 3, values
    assert values["style"]["fill"] == "#8f2924", values
    assert values["style"]["stroke"] == "#ffffff", values
    assert 0 < values["style"]["strokeWidth"] <= 1, values
    assert values["style"]["hitStrokeWidth"] >= 12, values
    assert values["style"]["strokeScale"] is False, values
    assert abs(values["draggedPoint"][0] - 15) < 1e-6, values
    assert abs(values["draggedPoint"][1] + 40) < 1e-6, values
    assert values["draggedPoint"][2] == 0, values
    assert values["renderedAtDragTarget"], values
    assert values["snappedPoint"] == [20, -40, 0], values
    print(values)


if __name__ == "__main__":
    main()
