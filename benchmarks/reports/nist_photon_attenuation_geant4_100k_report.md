# nist-photon-attenuation-v1

Reference-only photon attenuation benchmark for RadAgent-generated Geant4 projects. The benchmark uses NIST mass attenuation coefficients and evaluates observed transmission when RadAgent simulation or laboratory measurements are added.

## Aggregate

- Cases: 18
- Observed cases: 18
- Reference-only cases: 0
- Pass count: 18
- Pass rate: 1.0
- Median relative error: 0.004537
- Max relative error: 0.011678

## Cases

| Case | Material | Energy MeV | Thickness cm | T_ref | T_obs | Relative error | Status |
|---|---|---:|---:|---:|---:|---:|---|
| pb-0p5mev-0p5cm | Pb | 0.5 | 0.5 | 0.400461 | 0.4004 | 0.000167 | evaluated |
| pb-0p5mev-1cm | Pb | 0.5 | 1.0 | 0.160369 | 0.1603 | 0.000236 | evaluated |
| pb-0p5mev-2cm | Pb | 0.5 | 2.0 | 0.025718 | 0.02529 | 0.004588 | evaluated |
| pb-1mev-0p5cm | Pb | 1.0 | 0.5 | 0.668524 | 0.66686 | 0.006188 | evaluated |
| pb-1mev-1cm | Pb | 1.0 | 1.0 | 0.446924 | 0.44494 | 0.005524 | evaluated |
| pb-1mev-2cm | Pb | 1.0 | 2.0 | 0.199741 | 0.19604 | 0.011611 | evaluated |
| al-0p5mev-1cm | Al | 0.5 | 1.0 | 0.79618 | 0.79514 | 0.005732 | evaluated |
| al-0p5mev-3cm | Al | 0.5 | 3.0 | 0.5047 | 0.50341 | 0.003742 | evaluated |
| al-0p5mev-6cm | Al | 0.5 | 6.0 | 0.254722 | 0.25291 | 0.00522 | evaluated |
| al-1mev-1cm | Al | 1.0 | 1.0 | 0.847147 | 0.84718 | 0.000232 | evaluated |
| al-1mev-3cm | Al | 1.0 | 3.0 | 0.607963 | 0.60444 | 0.011678 | evaluated |
| al-1mev-6cm | Al | 1.0 | 6.0 | 0.369619 | 0.36656 | 0.008349 | evaluated |
| water-0p5mev-5cm | Water | 0.5 | 5.0 | 0.616098 | 0.61631 | 0.000712 | evaluated |
| water-0p5mev-10cm | Water | 0.5 | 10.0 | 0.379576 | 0.37793 | 0.004487 | evaluated |
| water-0p5mev-20cm | Water | 0.5 | 20.0 | 0.144078 | 0.14327 | 0.002903 | evaluated |
| water-1mev-5cm | Water | 1.0 | 5.0 | 0.702156 | 0.7026 | 0.001789 | evaluated |
| water-1mev-10cm | Water | 1.0 | 10.0 | 0.493023 | 0.49151 | 0.004345 | evaluated |
| water-1mev-20cm | Water | 1.0 | 20.0 | 0.243071 | 0.24079 | 0.006667 | evaluated |
