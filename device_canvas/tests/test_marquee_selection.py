from browser_helpers import evaluate_in_page


def main():
    values = evaluate_in_page(
        """() => {
      loadModel({
        components:[
          {component_id:'world_volume',display_name:'World',component_type:'world',geometry_type:'box',dimensions:{dx:240,dy:240,dz:240},material_id:'Air',placement:{position:[0,0,0]}},
          {component_id:'left_box',display_name:'Left',component_type:'layer',geometry_type:'box',dimensions:{dx:20,dy:20,dz:20},material_id:'Silicon',placement:{position:[-45,0,0]},mother_volume:'world_volume'},
          {component_id:'right_box',display_name:'Right',component_type:'layer',geometry_type:'box',dimensions:{dx:20,dy:20,dz:20},material_id:'Silicon',placement:{position:[45,0,0]},mother_volume:'world_volume'},
          {component_id:'top_box',display_name:'Top',component_type:'layer',geometry_type:'box',dimensions:{dx:20,dy:20,dz:20},material_id:'Silicon',placement:{position:[0,0,55]},mother_volume:'world_volume'},
          {component_id:'hidden_box',display_name:'Hidden',component_type:'layer',geometry_type:'box',dimensions:{dx:20,dy:20,dz:20},material_id:'Silicon',placement:{position:[-45,0,55]},mother_volume:'world_volume',hidden:true},
        ]
      });
      setViewAxes('x','z');
      const left = shapeBBoxPx(model.components.find(c => c.component_id === 'left_box'));
      const right = shapeBBoxPx(model.components.find(c => c.component_id === 'right_box'));
      const top = shapeBBoxPx(model.components.find(c => c.component_id === 'top_box'));

      const hasApi = typeof selectByMarqueeRect === 'function';
      const first = selectByMarqueeRect({
        x1:left.x - 4,
        y1:Math.min(left.y, right.y) - 4,
        x2:right.x + right.w + 4,
        y2:Math.max(left.y + left.h, right.y + right.h) + 4,
      });
      const afterFirst = [...selectedIds].sort();
      const primaryAfterFirst = primaryId;
      const topOnly = selectByMarqueeRect({
        x1:top.x - 4,
        y1:top.y - 4,
        x2:top.x + top.w + 4,
        y2:top.y + top.h + 4,
      }, {additive:true});
      const afterAdditive = [...selectedIds].sort();
      const empty = selectByMarqueeRect({
        x1:0,
        y1:0,
        x2:4,
        y2:4,
      });
      const afterEmpty = [...selectedIds];
      const renderedAfterEmpty = [...rectNodes.entries()].filter(([,n]) => n.shape.stroke() === ACCENT).map(([id]) => id).sort();
      const rect = stage.container().getBoundingClientRect();
      function evtFor(layerPoint, type) {
        const screenX = stage.x() + layerPoint.x * stage.scaleX();
        const screenY = stage.y() + layerPoint.y * stage.scaleY();
        return {
          type,
          button:0,
          clientX:rect.left + screenX,
          clientY:rect.top + screenY,
          shiftKey:false,
          ctrlKey:false,
          metaKey:false,
          preventDefault(){},
        };
      }
      const dragStart = {x:left.x - 6, y:left.y - 6};
      const dragEnd = {x:right.x + right.w + 6, y:right.y + right.h + 6};
      let evt = evtFor(dragStart, 'mousedown');
      stage.setPointersPositions(evt);
      stage.fire('mousedown', {target:stage, evt});
      evt = evtFor(dragEnd, 'mousemove');
      stage.setPointersPositions(evt);
      stage.fire('mousemove', {target:stage, evt});
      const marqueeDuringDrag = marqueeGroup.children.length;
      evt = evtFor(dragEnd, 'mouseup');
      stage.setPointersPositions(evt);
      stage.fire('mouseup', {target:stage, evt});
      const afterDrag = [...selectedIds].sort();
      return {
        hasApi,
        first,
        afterFirst,
        primaryAfterFirst,
        topOnly,
        afterAdditive,
        empty,
        afterEmpty,
        renderedSelected:renderedAfterEmpty,
        marqueeDuringDrag,
        marqueeAfterDrag:marqueeGroup.children.length,
        afterDrag,
      };
    }"""
    )

    assert values["hasApi"], values
    assert values["first"] == ["left_box", "right_box"], values
    assert values["afterFirst"] == ["left_box", "right_box"], values
    assert values["primaryAfterFirst"] == "left_box", values
    assert values["topOnly"] == ["top_box"], values
    assert values["afterAdditive"] == ["left_box", "right_box", "top_box"], values
    assert values["empty"] == [], values
    assert values["afterEmpty"] == [], values
    assert values["renderedSelected"] == [], values
    assert values["marqueeDuringDrag"] == 1, values
    assert values["marqueeAfterDrag"] == 0, values
    assert values["afterDrag"] == ["left_box", "right_box"], values
    print(values)


if __name__ == "__main__":
    main()
