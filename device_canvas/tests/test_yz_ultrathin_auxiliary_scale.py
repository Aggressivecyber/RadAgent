from browser_helpers import evaluate_in_page


def main():
    values = evaluate_in_page(
        """() => {
      loadExample();
      setViewAxes('y','z');
      selectedIds = new Set(['top_contact']);
      primaryId = 'top_contact';
      polyEditId = null;
      drawComponents();

      const thinMin = Math.min(...sectionComponents(false)
        .map(c => projectionMinPx(c))
        .filter(v => v > 0 && v < 2));
      const grid = bgGroup.children
        .filter(x => x.className === 'Line')
        .map(x => ({strokeWidth: x.strokeWidth(), opacity: x.opacity()}));
      const guides = thinSelectionGroup.children
        .map(x => ({strokeWidth: x.strokeWidth(), opacity: x.opacity()}));
      const componentStrokes = [...rectNodes.values()]
        .filter(n => n.shape.getAttr('cid') !== 'world_volume')
        .map(n => ({id: n.shape.getAttr('cid'), strokeWidth: n.shape.strokeWidth()}));

      return {thinMin, grid, guides, componentStrokes};
    }"""
    )

    assert values["thinMin"] < 0.1, values
    assert values["grid"], values
    assert values["guides"], values
    assert all(item["strokeWidth"] <= values["thinMin"] for item in values["grid"]), values
    assert all(item["strokeWidth"] <= values["thinMin"] for item in values["guides"]), values
    assert all(item["strokeWidth"] <= values["thinMin"] for item in values["componentStrokes"]), values
    assert all(item["opacity"] <= 0.35 for item in values["grid"]), values
    assert all(item["opacity"] <= 0.55 for item in values["guides"]), values
    print(values)


if __name__ == "__main__":
    main()
