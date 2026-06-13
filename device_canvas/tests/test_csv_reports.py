from browser_helpers import evaluate_in_page


def main():
    values = evaluate_in_page(
        """() => {
      loadModel({components:[
        {component_id:'world_volume', display_name:'World', component_type:'world', geometry_type:'box', dimensions:{dx:100,dy:100,dz:100}, material_id:'Air', placement:{position:[0,0,0]}},
        {component_id:'outside', display_name:'Outside, quoted', component_type:'layer', geometry_type:'box', dimensions:{dx:30,dy:30,dz:30}, material_id:'Silicon', placement:{position:[50,0,0]}, mother_volume:'world_volume', roles:['edep_region'], locked:true},
        {component_id:'overlap_a', display_name:'Overlap A', component_type:'layer', geometry_type:'box', dimensions:{dx:20,dy:20,dz:20}, material_id:'SiO2', placement:{position:[-20,0,0]}, mother_volume:'world_volume'},
        {component_id:'overlap_b', display_name:'Overlap B', component_type:'electrode', geometry_type:'box', dimensions:{dx:20,dy:20,dz:20}, material_id:'Aluminum', placement:{position:[-15,0,0]}, mother_volume:'world_volume'},
        {component_id:'hidden_probe', display_name:'Hidden Probe', component_type:'electrode', geometry_type:'box', dimensions:{dx:6,dy:6,dz:6}, material_id:'Aluminum', placement:{position:[0,40,0]}, mother_volume:'world_volume', hidden:true}
      ]}, 'csv-reports');
      setViewAxes('x','z');
      updateModelHealth();
      const outsideIssue = collectModelIssues().issues.find(i => i.code === 'outside_world');
      waiveIssue(outsideIssue.id, 'Accepted, fixture envelope');

      const hasFns = {
        csvCell: typeof csvCell === 'function',
        drc: typeof buildDRCReportCSV === 'function',
        components: typeof buildComponentReportCSV === 'function',
        exportDrc: typeof exportDRCReportCSV === 'function',
        exportComponents: typeof exportComponentReportCSV === 'function',
      };
      const hasUi = {
        drcButton: !!document.querySelector('[data-action="export-drc-csv"]'),
        compButton: !!document.querySelector('[data-action="export-component-csv"]'),
      };
      const drcCsv = hasFns.drc ? buildDRCReportCSV() : '';
      const compCsv = hasFns.components ? buildComponentReportCSV() : '';
      return {hasFns, hasUi, drcCsv, compCsv};
    }"""
    )

    assert all(values["hasFns"].values()), values
    assert all(values["hasUi"].values()), values
    drc = values["drcCsv"]
    assert drc.startswith("status,kind,code,message,component_ids,signature,fixable,waiver_reason,waived_at"), values
    assert "waived,err,outside_world" in drc, values
    assert '"Outside, quoted 超出 world 3D 边界"' in drc, values
    assert '"outside;world_volume"' in drc, values
    assert '"Accepted, fixture envelope"' in drc, values
    assert "active,err,overlap3d" in drc, values

    comp = values["compCsv"]
    assert comp.startswith("component_id,display_name,component_type,geometry_type,material_id,mother_volume"), values
    assert '"Outside, quoted"' in comp, values
    assert "outside," in comp, values
    assert ",50,0,0,30,30,30,35,-15,-15,65,15,15," in comp, values
    assert ",true,false,edep_region" in comp, values
    assert "hidden_probe,Hidden Probe,electrode,box,Aluminum,world_volume" in comp, values
    assert ",true,false,false," in comp, values
    print(values)


if __name__ == "__main__":
    main()
