from browser_helpers import evaluate_in_page


def main():
    values = evaluate_in_page(
        """() => {
      loadModel({components:[
        {component_id:'world_volume', display_name:'World', component_type:'world', geometry_type:'box', dimensions:{dx:200,dy:200,dz:100}, material_id:'Air', placement:{position:[0,0,0]}},
        {component_id:'box_a', display_name:'Box A', component_type:'layer', geometry_type:'box', dimensions:{dx:20,dy:10,dz:10}, material_id:'Silicon', placement:{position:[-20,0,0]}, mother_volume:'world_volume'},
        {component_id:'box_b', display_name:'Box B', component_type:'layer', geometry_type:'box', dimensions:{dx:10,dy:20,dz:10}, material_id:'SiO2', placement:{position:[30,10,0]}, mother_volume:'world_volume'},
        {component_id:'poly', display_name:'Poly', component_type:'layer', geometry_type:'polycone', dimensions:{dx:10,dy:10,dz:10}, material_id:'Aluminum', placement:{position:[20,-30,0]}, mother_volume:'world_volume',
          cross_section_polygon:[[20,-30,0],[40,-30,0],[40,-20,0],[20,-20,0]], cross_section_polygon_axes:{lateral:'x',depth:'y'}}
      ]}, 'mirror-rotate');
      setViewAxes('x','y');
      const hasMirror = typeof mirrorSelection2D === 'function';
      const hasRotate = typeof rotateSelection2D === 'function';
      const hasMirrorBtn = !!document.querySelector('[data-action="mirror-lat"]');
      const hasRotateBtn = !!document.querySelector('[data-action="rotate-cw"]');

      selectedIds = new Set(['box_a','box_b','poly']);
      primaryId = 'box_a';
      mirrorSelection2D('lat');
      const afterMirror = {
        boxA: model.components.find(c => c.component_id === 'box_a').placement.position.slice(),
        boxB: model.components.find(c => c.component_id === 'box_b').placement.position.slice(),
        polyPos: model.components.find(c => c.component_id === 'poly').placement.position.slice(),
        polyPts: model.components.find(c => c.component_id === 'poly').polygon.map(p => p.slice()),
      };

      rotateSelection2D('cw');
      const boxA = model.components.find(c => c.component_id === 'box_a');
      const boxB = model.components.find(c => c.component_id === 'box_b');
      const poly = model.components.find(c => c.component_id === 'poly');
      const afterRotate = {
        boxA: {pos: boxA.placement.position.slice(), dims: {...boxA.dimensions}},
        boxB: {pos: boxB.placement.position.slice(), dims: {...boxB.dimensions}},
        polyBox: bbox3D(poly),
        polyPts: poly.polygon.map(p => p.slice()),
      };

      loadModel({components:[
        {component_id:'world_volume', display_name:'World', component_type:'world', geometry_type:'box', dimensions:{dx:100,dy:100,dz:100}, material_id:'Air', placement:{position:[0,0,0]}},
        {component_id:'edge', display_name:'Edge', component_type:'layer', geometry_type:'box', dimensions:{dx:10,dy:80,dz:10}, material_id:'Silicon', placement:{position:[45,0,0]}, mother_volume:'world_volume'},
        {component_id:'anchor', display_name:'Anchor', component_type:'layer', geometry_type:'box', dimensions:{dx:10,dy:10,dz:10}, material_id:'SiO2', placement:{position:[-5,0,0]}, mother_volume:'world_volume'}
      ]}, 'rotate-blocked');
      setViewAxes('x','y');
      selectedIds = new Set(['edge','anchor']);
      primaryId = 'edge';
      rotateSelection2D('cw');
      const blocked = {
        edge: model.components.find(c => c.component_id === 'edge').placement.position.slice(),
        dims: {...model.components.find(c => c.component_id === 'edge').dimensions},
        issues: collectModelIssues().issues.map(i => i.code),
      };

      return {hasMirror, hasRotate, hasMirrorBtn, hasRotateBtn, afterMirror, afterRotate, blocked};
    }"""
    )

    assert values["hasMirror"], values
    assert values["hasRotate"], values
    assert values["hasMirrorBtn"], values
    assert values["hasRotateBtn"], values
    assert values["afterMirror"]["boxA"] == [30, 0, 0], values
    assert values["afterMirror"]["boxB"] == [-20, 10, 0], values
    assert values["afterMirror"]["polyPos"] == [-10, -30, 0], values
    assert values["afterMirror"]["polyPts"][0] == [-10, -30, 0], values
    assert values["afterMirror"]["polyPts"][1] == [-30, -30, 0], values

    assert values["afterRotate"]["boxA"]["dims"]["dx"] == 10, values
    assert values["afterRotate"]["boxA"]["dims"]["dy"] == 20, values
    assert values["afterRotate"]["boxB"]["dims"]["dx"] == 20, values
    assert values["afterRotate"]["boxB"]["dims"]["dy"] == 10, values
    assert values["afterRotate"]["polyBox"]["min"][:2] == [-20, 10], values
    assert values["afterRotate"]["polyBox"]["max"][:2] == [-10, 30], values

    assert values["blocked"]["edge"] == [45, 0, 0], values
    assert values["blocked"]["dims"] == {"dx": 10, "dy": 80, "dz": 10}, values
    assert values["blocked"]["issues"] == [], values
    print(values)


if __name__ == "__main__":
    main()
