from browser_helpers import evaluate_in_page


def main():
    values = evaluate_in_page(
        """() => {
      loadModel({components:[
        {component_id:'world_volume', display_name:'World', component_type:'world', geometry_type:'box', dimensions:{dx:500,dy:500,dz:500}, material_id:'Air', placement:{position:[0,0,0]}}
      ]}, 'dxf-import-bulge');
      setViewAxes('x','z');
      const dxf = [
        '0','SECTION','2','ENTITIES',
        '0','LWPOLYLINE',
        '8','ROUNDED_TRACE',
        '90','4',
        '70','1',
        '10','0','20','0','42','1',
        '10','10','20','0',
        '10','10','20','10',
        '10','0','20','10',
        '0','ENDSEC','0','EOF'
      ].join('\\n');

      const parsed = parseDXFLWPolylines(dxf)[0];
      const added = importDXFText(dxf, {namePrefix:'CAD'});
      const imported = added[0];
      const ys = parsed.points.map(p => p[1]);
      const inserted = parsed.points.slice(1, -3);
      return {
        layer: parsed.layer,
        closed: parsed.closed,
        hasBulge: parsed.hasBulge,
        pointCount: parsed.points.length,
        first: parsed.points[0],
        second: parsed.points[1],
        minY: Math.min(...ys),
        maxY: Math.max(...ys),
        insertedCount: inserted.length,
        insertedNonChord: inserted.some(p => Math.abs(p[1]) > 0.5),
        dims: imported.dimensions,
        pos: imported.placement.position,
        polygonCount: imported.polygon.length,
        polygonHasArcPoint: imported.polygon.some(p => p[2] < -0.5),
        issues: imported.open_issues,
        rendered: rectNodes.has(imported.component_id),
      };
    }"""
    )

    assert values["layer"] == "ROUNDED_TRACE", values
    assert values["closed"] is True, values
    assert values["hasBulge"] is True, values
    assert values["pointCount"] > 4, values
    assert values["first"] == [0, 0], values
    assert values["second"] != [10, 0], values
    assert values["insertedCount"] >= 5, values
    assert values["insertedNonChord"], values
    assert values["minY"] < -4.5, values
    assert values["maxY"] == 10, values
    assert values["dims"] == {"dx": 10, "dy": 1, "dz": 15}, values
    assert values["pos"] == [5, 0, 2.5], values
    assert values["polygonCount"] == values["pointCount"], values
    assert values["polygonHasArcPoint"], values
    assert any("bulge" in issue.lower() for issue in values["issues"]), values
    assert values["rendered"] is True, values
    print(values)


if __name__ == "__main__":
    main()
