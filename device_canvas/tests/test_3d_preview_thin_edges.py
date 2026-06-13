from browser_helpers import evaluate_in_page


def main():
    values = evaluate_in_page(
        """() => {
      loadExample();
      toggle3DPreview();
      set3DViewPreset('front');
      selectOnly('top_contact');
      draw3DPreview();
      const sample = last3DStrokeSamples.find(x => x.id === 'top_contact');
      const substrate = last3DStrokeSamples.find(x => x.id === 'si_substrate');
      return {
        hasSamples: Array.isArray(last3DStrokeSamples),
        sample,
        substrate,
      };
    }"""
    )

    assert values["hasSamples"], values
    assert values["sample"], values
    assert values["sample"]["projectedMinPx"] < 0.2, values
    assert values["sample"]["lineWidth"] <= values["sample"]["projectedMinPx"], values
    assert values["substrate"]["projectedMinPx"] > 5, values
    assert values["substrate"]["lineWidth"] > 0, values
    print(values)


if __name__ == "__main__":
    main()
