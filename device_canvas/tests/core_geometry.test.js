const fs = require("fs");
const vm = require("vm");

const code = fs.readFileSync("device_canvas/cad_core.js", "utf8");
const ctx = { console };
vm.createContext(ctx);
vm.runInContext(code, ctx);

function comp(id, pos, dims, material = "Silicon") {
  return {
    component_id: id,
    display_name: id,
    component_type: "layer",
    geometry_type: "box",
    dimensions: { dx: dims[0], dy: dims[1], dz: dims[2] },
    material_id: material,
    placement: { position: pos },
    mother_volume: "world_volume",
  };
}
function pairKey([a, b]) {
  return [a.component_id, b.component_id].sort().join("|");
}
function bruteOverlapKeys(components, includeWorld = false) {
  const comps = (components || []).filter((c) => includeWorld || c.component_type !== "world");
  const boxes = new Map(comps.map((c) => [c.component_id, ctx.bbox3D(c)]));
  const keys = [];
  for (let i = 0; i < comps.length; i++) {
    for (let j = i + 1; j < comps.length; j++) {
      const a = comps[i], b = comps[j];
      if (!ctx.sameMotherScope(a, b)) continue;
      if (ctx.aabbOverlap3D(boxes.get(a.component_id), boxes.get(b.component_id))) {
        keys.push(pairKey([a, b]));
      }
    }
  }
  return keys.sort();
}

const base = comp("base", [0, 0, 0], [100, 100, 40]);
const near = comp("near", [0, 0, 23], [100, 100, 4], "SiO2");
const overlap = comp("overlap", [0, 0, 10], [50, 50, 12], "Aluminum");
const offAxis = comp("off_axis", [200, 0, 23], [50, 50, 4], "Gold");

const overlaps = ctx.detectOverlaps3D([base, near, overlap, offAxis]).pairs
  .map(([a, b]) => [a.component_id, b.component_id]);
if (!overlaps.some(([a, b]) => a === "base" && b === "overlap")) {
  throw new Error(`expected base/overlap collision, got ${JSON.stringify(overlaps)}`);
}

const gaps = ctx.detectSmallGaps3DCore([base, near, overlap, offAxis], "z", 2);
if (gaps.length !== 1 || gaps[0].a.component_id !== "base" || gaps[0].b.component_id !== "near") {
  throw new Error(`expected one z small gap for near layer, got ${JSON.stringify(gaps)}`);
}

const relations = ctx.stackRelations3D([base, offAxis, near], "z", { minGap: 2, format: ctx.fmt });
const kinds = relations.map((rel) => [rel.a.component.component_id, rel.b.component.component_id, rel.kind]);
if (!kinds.some(([a, b, kind]) => a === "base" && b === "near" && kind === "small_gap")) {
  throw new Error(`expected footprint-aware small gap relation, got ${JSON.stringify(kinds)}`);
}

const stroke = ctx.cadStrokeWidth(100, 0.24, {});
const hit = ctx.cadHitWidth(100, 0.24);
if (stroke !== 0 || hit < 6) {
  throw new Error(`expected hairline stroke suppression with usable hit area, got stroke=${stroke}, hit=${hit}`);
}
const subTwoStroke = ctx.cadStrokeWidth(100, 1.4, { selected: true });
if (subTwoStroke !== 0) {
  throw new Error(`expected sub-2px projected thickness to suppress selected stroke, got ${subTwoStroke}`);
}
const thinOpacity = ctx.cadFillOpacity(100, 0.24, {});
if (!(thinOpacity > 0 && thinOpacity <= 0.2)) {
  throw new Error(`expected ultrathin fills to keep low visual weight, got ${thinOpacity}`);
}

const many = [];
for (let i = 0; i < 80; i++) {
  many.push(comp(`far_${i}`, [i * 30, 0, 0], [5, 5, 5]));
}
many.push(comp("dense_a", [0, 40, 0], [20, 20, 20]));
many.push(comp("dense_b", [5, 40, 0], [20, 20, 20]));
const otherMotherA = comp("other_mother_a", [100, 40, 0], [20, 20, 20]);
const otherMotherB = comp("other_mother_b", [100, 40, 0], [20, 20, 20]);
otherMotherA.mother_volume = "mother_a";
otherMotherB.mother_volume = "mother_b";
many.push(otherMotherA, otherMotherB);
many.push({
  component_id: "world_volume",
  display_name: "World",
  component_type: "world",
  geometry_type: "box",
  dimensions: { dx: 5000, dy: 5000, dz: 5000 },
  material_id: "Air",
  placement: { position: [0, 0, 0] },
});
const stats = {};
const sweepKeys = ctx.detectOverlaps3D(many, { stats }).pairs.map(pairKey).sort();
const bruteKeys = bruteOverlapKeys(many, false);
const brutePairCount = (many.length - 1) * (many.length - 2) / 2;
if (JSON.stringify(sweepKeys) !== JSON.stringify(bruteKeys)) {
  throw new Error(`sweep overlap keys differ from brute force: ${JSON.stringify({ sweepKeys, bruteKeys })}`);
}
if (!(stats.candidates > 0 && stats.candidates < brutePairCount / 4)) {
  throw new Error(`expected sweep candidates to be far below brute force ${brutePairCount}, got ${JSON.stringify(stats)}`);
}
const withWorldKeys = ctx.detectOverlaps3D(many, { includeWorld: true }).pairs.map(pairKey);
if (!withWorldKeys.some((key) => key.includes("world_volume"))) {
  throw new Error("expected includeWorld=true to report world overlaps");
}

console.log({ overlaps, gaps: gaps.map((g) => [g.a.component_id, g.b.component_id, g.gap]), kinds, stroke, subTwoStroke, hit, thinOpacity, stats });
