from browser_helpers import evaluate_in_page


def main():
    values = evaluate_in_page(
        """() => {
      loadModel({components:[
        {component_id:'world_volume', display_name:'World', component_type:'world', geometry_type:'box', dimensions:{dx:500,dy:500,dz:500}, material_id:'Air', placement:{position:[0,0,0]}}
      ]}, 'dxf-import-curves');
      setViewAxes('x','z');
      const dxf = [
        '0','SECTION','2','ENTITIES',
        '0','CIRCLE',
        '8','ROUND_HOLE',
        '10','12','20','-4','40','5',
        '0','ARC',
        '8','ARC_EDGE',
        '10','80','20','0','40','10','50','0','51','90',
        '0','ENDSEC','0','EOF'
      ].join('\\n');

      const hasFns = {
        parseCurves: typeof parseDXFCurves === 'function',
        parseEntities: typeof parseDXFImportEntities === 'function',
        importText: typeof importDXFText === 'function',
      };
      const parsed = hasFns.parseEntities ? parseDXFImportEntities(dxf) : [];
      const added = hasFns.importText ? importDXFText(dxf, {namePrefix:'CAD'}) : [];
      const circle = added.find(c => c.source_evidence.includes('dxf_import:ROUND_HOLE'));
      const arc = added.find(c => c.source_evidence.includes('dxf_import:ARC_EDGE'));
      const circleXs = circle ? circle.polygon.map(p => p[0]) : [];
      const circleZs = circle ? circle.polygon.map(p => p[2]) : [];
      const arcXs = arc ? arc.polygon.map(p => p[0]) : [];
      const arcZs = arc ? arc.polygon.map(p => p[2]) : [];

      return {
        hasFns,
        parsed: parsed.map(e => ({
          kind:e.kind,
          layer:e.layer,
          closed:e.closed,
          pointCount:e.points.length,
          first:e.points[0],
          last:e.points[e.points.length-1],
        })),
        addedIds: added.map(c => c.component_id),
        selected: Array.from(selectedIds),
        primaryId,
        circle: circle ? {
          name:circle.display_name,
          dims:circle.dimensions,
          pos:circle.placement.position,
          pointCount:circle.polygon.length,
          minX:Math.min(...circleXs),
          maxX:Math.max(...circleXs),
          minZ:Math.min(...circleZs),
          maxZ:Math.max(...circleZs),
          issues:circle.open_issues,
          rendered:rectNodes.has(circle.component_id),
        } : null,
        arc: arc ? {
          name:arc.display_name,
          dims:arc.dimensions,
          pos:arc.placement.position,
          pointCount:arc.polygon.length,
          first:arc.polygon[0],
          last:arc.polygon[arc.polygon.length-1],
          minX:Math.min(...arcXs),
          maxX:Math.max(...arcXs),
          minZ:Math.min(...arcZs),
          maxZ:Math.max(...arcZs),
          issues:arc.open_issues,
          rendered:rectNodes.has(arc.component_id),
        } : null,
        issueCodes: collectModelIssues().issues.map(i => i.code),
      };
    }"""
    )

    assert all(values["hasFns"].values()), values
    assert [item["kind"] for item in values["parsed"]] == ["circle", "arc"], values
    assert values["parsed"][0]["layer"] == "ROUND_HOLE", values
    assert values["parsed"][0]["closed"] is True, values
    assert values["parsed"][0]["pointCount"] >= 32, values
    assert values["parsed"][1]["layer"] == "ARC_EDGE", values
    assert values["parsed"][1]["closed"] is False, values
    assert values["parsed"][1]["pointCount"] >= 8, values
    assert len(values["addedIds"]) == 2, values
    assert values["selected"] == values["addedIds"], values
    assert values["primaryId"] == values["addedIds"][0], values

    circle = values["circle"]
    assert circle["name"] == "CAD ROUND_HOLE", values
    assert circle["dims"] == {"dx": 10, "dy": 1, "dz": 10}, values
    assert circle["pos"] == [12, 0, -4], values
    assert circle["pointCount"] >= 32, values
    assert abs(circle["minX"] - 7) < 1e-6 and abs(circle["maxX"] - 17) < 1e-6, values
    assert abs(circle["minZ"] + 9) < 1e-6 and abs(circle["maxZ"] - 1) < 1e-6, values
    assert any("CIRCLE" in issue for issue in circle["issues"]), values
    assert circle["rendered"], values

    arc = values["arc"]
    assert arc["name"] == "CAD ARC_EDGE", values
    assert arc["dims"] == {"dx": 10, "dy": 1, "dz": 10}, values
    assert arc["pos"] == [85, 0, 5], values
    assert arc["pointCount"] >= 8, values
    assert arc["first"] == [90, 0, 0], values
    assert abs(arc["last"][0] - 80) < 1e-6 and abs(arc["last"][2] - 10) < 1e-6, values
    assert abs(arc["minX"] - 80) < 1e-6 and abs(arc["maxX"] - 90) < 1e-6, values
    assert abs(arc["minZ"] - 0) < 1e-6 and abs(arc["maxZ"] - 10) < 1e-6, values
    assert any("ARC" in issue for issue in arc["issues"]), values
    assert arc["rendered"], values
    assert "bad_dimensions" not in values["issueCodes"], values
    print(values)


if __name__ == "__main__":
    main()
