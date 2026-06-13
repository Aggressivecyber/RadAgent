from browser_helpers import evaluate_in_page


def main():
    values = evaluate_in_page(
        """() => {
      loadModel({components:[
        {component_id:'world_volume', display_name:'World', component_type:'world', geometry_type:'box', dimensions:{dx:500,dy:500,dz:500}, material_id:'Air', placement:{position:[0,0,0]}}
      ]}, 'dxf-import');
      setViewAxes('y','z');
      const dxf = [
        '0','SECTION','2','ENTITIES',
        '0','LWPOLYLINE',
        '8','PAD_LAYER',
        '90','4',
        '70','1',
        '10','20','20','-20',
        '10','45','20','-20',
        '10','45','20','5',
        '10','20','20','5',
        '0','ENDSEC','0','EOF'
      ].join('\\n');

      const hasFns = {
        parse: typeof parseDXFLWPolylines === 'function',
        importText: typeof importDXFText === 'function',
        importFile: typeof readDXFFile === 'function',
      };
      const hasUi = {
        button: !!document.querySelector('[data-action="import-dxf"]'),
        input: !!document.getElementById('dxfFile'),
      };

      const parsed = hasFns.parse ? parseDXFLWPolylines(dxf) : [];
      const added = hasFns.importText ? importDXFText(dxf, {namePrefix:'CAD'}) : [];
      const imported = model.components.find(c => c.component_id.startsWith('dxf_pad_layer'));
      const exported = imported ? serializeComp(imported) : null;

      return {
        hasFns,
        hasUi,
        parsed,
        addedIds: added.map(c => c.component_id),
        selected: Array.from(selectedIds),
        primaryId,
        imported: imported ? {
          id: imported.component_id,
          name: imported.display_name,
          type: imported.geometry_type,
          material: imported.material_id,
          mother: imported.mother_volume,
          dims: imported.dimensions,
          pos: imported.placement.position,
          polygon: imported.polygon,
          axes: imported.polygonAxes,
          evidence: imported.source_evidence,
          rendered: rectNodes.has(imported.component_id),
        } : null,
        exported,
        issueCodes: collectModelIssues().issues.map(i => i.code),
      };
    }"""
    )

    assert all(values["hasFns"].values()), values
    assert all(values["hasUi"].values()), values
    assert len(values["parsed"]) == 1, values
    assert values["parsed"][0]["layer"] == "PAD_LAYER", values
    assert values["parsed"][0]["closed"] is True, values
    assert values["parsed"][0]["points"] == [[20, -20], [45, -20], [45, 5], [20, 5]], values
    assert len(values["addedIds"]) == 1, values
    assert values["selected"] == values["addedIds"], values
    assert values["primaryId"] == values["addedIds"][0], values

    imported = values["imported"]
    assert imported["name"] == "CAD PAD_LAYER", values
    assert imported["type"] == "polycone", values
    assert imported["material"] == "Silicon", values
    assert imported["mother"] == "world_volume", values
    assert imported["dims"] == {"dx": 1, "dy": 25, "dz": 25}, values
    assert imported["pos"] == [0, 32.5, -7.5], values
    assert imported["polygon"] == [[0, 20, -20], [0, 45, -20], [0, 45, 5], [0, 20, 5]], values
    assert imported["axes"] == {"lateral": "y", "depth": "z"}, values
    assert "dxf_import:PAD_LAYER" in imported["evidence"], values
    assert imported["rendered"] is True, values
    assert values["exported"]["cross_section_polygon_axes"] == {"lateral": "y", "depth": "z"}, values
    assert "bad_dimensions" not in values["issueCodes"], values
    print(values)


if __name__ == "__main__":
    main()
