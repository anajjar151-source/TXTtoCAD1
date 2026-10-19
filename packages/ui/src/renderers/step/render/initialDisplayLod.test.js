import assert from "node:assert/strict";
import test from "node:test";

import {
  COARSE_SURF_DECODE_EXPANSION_ESTIMATE,
  COARSE_SURF_INDEX_DECODE_EXPANSION_ESTIMATE,
  DEFAULT_SURF_DECODE_EXPANSION_ESTIMATE,
  DEFAULT_SURF_INDEX_DECODE_EXPANSION_ESTIMATE,
  INITIAL_DECODE_ESTIMATE_FLOOR_BYTES,
  LARGE_ASSEMBLY_INITIAL_COARSE_COMPONENTS,
  SURF_HEADER_BYTES,
  estimateInitialSurfDecodeBytes,
  initialDisplayLodPlan,
  probeInitialDisplayLod,
  surfDecodeSourceBytes,
  surfIndexBytesFromHeader,
} from "./initialDisplayLod.js";

const MIB = 1024 * 1024;

function cachedProbes(standard, coarse) {
  const requested = [];
  return {
    requested,
    probeEntries: async ([input], options) => {
      const level = options ? 0 : 1;
      requested.push(level);
      const row = level ? standard : coarse;
      return new Map(row ? [[input, row]] : []);
    },
  };
}

test("warm assemblies choose standard before coarse without requiring a SURF URL", async () => {
  const standard = { surfaceObject: "exact", byteLength: MIB, decodedBytes: 3 * MIB };
  const cache = cachedProbes(standard, { ...standard, decodedBytes: MIB });
  const hit = await probeInitialDisplayLod({ surfaceInput: "input", maxInFlightBytes: 256 * MIB, ...cache });
  assert.equal(hit.plan.level, 1);
  assert.equal(hit.cacheProbe, standard);
  assert.equal(hit.plan.estimatedBytes, 4 * MIB);
  assert.deepEqual(cache.requested, [1]);
});

test("a missing, mismatched, or oversized standard entry can fall back to admitted coarse", async () => {
  const coarse = { surfaceObject: "exact", byteLength: MIB, decodedBytes: 3 * MIB };
  for (const standard of [null, { ...coarse, surfaceObject: "different" },
    { ...coarse, decodedBytes: 256 * MIB }, { ...coarse, decodedBytes: NaN }]) {
    const cache = cachedProbes(standard, coarse);
    const hit = await probeInitialDisplayLod({ surfaceInput: "input", surfaceObject: "exact",
      maxInFlightBytes: 256 * MIB, ...cache });
    assert.equal(hit.plan.level, 0);
    assert.equal(hit.cacheProbe, coarse);
    assert.deepEqual(cache.requested, [1, 0]);
  }
});

test("a standard body rejected after admission falls back to coarse metadata", async () => {
  const standard = { object: "standard", surfaceObject: "exact", byteLength: MIB, decodedBytes: 3 * MIB };
  const coarse = { object: "coarse", surfaceObject: "exact", byteLength: MIB, decodedBytes: MIB };
  const cache = cachedProbes(standard, coarse);
  const hit = await probeInitialDisplayLod({
    surfaceInput: "input",
    maxInFlightBytes: 256 * MIB,
    rejectedCacheObjects: new Set(["standard"]),
    ...cache,
  });
  assert.equal(hit.plan.level, 0);
  assert.equal(hit.cacheProbe, coarse);
  assert.deepEqual(cache.requested, [1, 0]);
});

test("unusable cache metadata leaves cold-load admission in charge", async () => {
  const row = { surfaceObject: "exact", byteLength: MIB, decodedBytes: 256 * MIB };
  assert.equal(await probeInitialDisplayLod({ surfaceInput: "input", maxInFlightBytes: 256 * MIB,
    ...cachedProbes(row, row) }), null);
  const controller = new AbortController();
  controller.abort();
  await assert.rejects(probeInitialDisplayLod({ surfaceInput: "input", maxInFlightBytes: 256 * MIB,
    signal: controller.signal, probeEntries: async (_inputs, _options, { signal }) => signal.throwIfAborted() }),
  { name: "AbortError" });
});

test("large assemblies start coarse while small and medium packages keep the default", () => {
  assert.equal(initialDisplayLodPlan({ componentCount: 9, maxInFlightBytes: 256 * MIB }).level, 1);
  const large = initialDisplayLodPlan({
    componentCount: LARGE_ASSEMBLY_INITIAL_COARSE_COMPONENTS,
    maxInFlightBytes: 256 * MIB,
  });
  assert.equal(large.level, 0);
  assert.equal(large.reason, "large-assembly");
  assert.equal(large.sourceExpansionRatio, COARSE_SURF_DECODE_EXPANSION_ESTIMATE);
});

test("any oversized leaf tries coarse only when its independent estimate fits", () => {
  assert.equal(initialDisplayLodPlan({
    componentCount: 9,
    surfBytes: 1 * MIB,
    maxInFlightBytes: 256 * MIB,
  }).level, 1, "the other leaves in the same small assembly stay at the default");
  const coarse = initialDisplayLodPlan({
    componentCount: 9,
    surfBytes: 5 * MIB,
    maxInFlightBytes: 256 * MIB,
  });
  assert.equal(coarse.level, 0);
  assert.equal(coarse.reason, "component-admission");
  assert.equal(coarse.estimatedBytes, 160 * MIB);
  assert.equal(coarse.fitsDecodeCap, true);

  const refused = initialDisplayLodPlan({
    componentCount: 9,
    surfBytes: 9 * MIB,
    maxInFlightBytes: 256 * MIB,
  });
  assert.equal(refused.level, 0);
  assert.equal(refused.estimatedBytes, 288 * MIB);
  assert.equal(refused.fitsDecodeCap, false);
  assert.equal(
    estimateInitialSurfDecodeBytes(5 * MIB, DEFAULT_SURF_DECODE_EXPANSION_ESTIMATE),
    320 * MIB,
  );
});

function surfHeader(indexBytes, { magic = 0x46525553, version = 2 } = {}) {
  const header = new ArrayBuffer(SURF_HEADER_BYTES);
  const view = new DataView(header);
  view.setUint32(0, magic, true);
  view.setUint32(4, version, true);
  view.setUint32(8, indexBytes, true);
  return header;
}

test("a SURF header's JSON index length is read only from a real, consistent header", () => {
  assert.equal(surfIndexBytesFromHeader(surfHeader(6_876_569), 7_817_349), 6_876_569);
  assert.equal(surfIndexBytesFromHeader(surfHeader(500)), 500, "an unknown total does not reject it");
  assert.equal(surfIndexBytesFromHeader(surfHeader(500, { magic: 0x46546c67 })), null, "not a SURF");
  assert.equal(surfIndexBytesFromHeader(surfHeader(500).slice(0, 8)), null, "a short read");
  assert.equal(surfIndexBytesFromHeader(surfHeader(1_000), 1_000), null, "more index than the SURF holds");
  assert.equal(surfIndexBytesFromHeader(null), null);
});

test("the split estimate charges the float payload at the tier ratio and the index at its own", () => {
  const floats = 3 * MIB;
  const index = 20 * MIB;
  const surfBytes = SURF_HEADER_BYTES + index + floats;
  assert.equal(
    estimateInitialSurfDecodeBytes(surfBytes, COARSE_SURF_DECODE_EXPANSION_ESTIMATE, {
      indexBytes: index, indexExpansionRatio: COARSE_SURF_INDEX_DECODE_EXPANSION_ESTIMATE,
    }),
    floats * COARSE_SURF_DECODE_EXPANSION_ESTIMATE + index * COARSE_SURF_INDEX_DECODE_EXPANSION_ESTIMATE,
  );
  // The loader multiplies these bytes by the same ratio, so they carry the split through.
  const sourceBytes = surfDecodeSourceBytes(surfBytes, {
    indexBytes: index,
    sourceExpansionRatio: DEFAULT_SURF_DECODE_EXPANSION_ESTIMATE,
    indexExpansionRatio: DEFAULT_SURF_INDEX_DECODE_EXPANSION_ESTIMATE,
  });
  assert.equal(sourceBytes * DEFAULT_SURF_DECODE_EXPANSION_ESTIMATE,
    floats * DEFAULT_SURF_DECODE_EXPANSION_ESTIMATE + index * DEFAULT_SURF_INDEX_DECODE_EXPANSION_ESTIMATE);
  // An index is never charged above the float multiple; small parts keep the floor.
  assert.equal(surfDecodeSourceBytes(surfBytes, { indexBytes: index, sourceExpansionRatio: 4, indexExpansionRatio: 32 }),
    surfBytes - SURF_HEADER_BYTES);
  assert.equal(estimateInitialSurfDecodeBytes(64 * 1024, 64, { indexBytes: 60 * 1024 }), INITIAL_DECODE_ESTIMATE_FLOOR_BYTES);
});

test("without a usable index length the whole SURF is charged at the tier ratio, as before", () => {
  for (const indexBytes of [null, undefined, -1, 1.5, 10 * MIB]) {
    assert.equal(surfDecodeSourceBytes(5 * MIB, { indexBytes }), 5 * MIB, String(indexBytes));
    assert.equal(estimateInitialSurfDecodeBytes(5 * MIB, DEFAULT_SURF_DECODE_EXPANSION_ESTIMATE, { indexBytes }), 320 * MIB);
  }
  assert.equal(surfDecodeSourceBytes(null), null);
  assert.equal(initialDisplayLodPlan({ componentCount: 9, surfBytes: 5 * MIB, maxInFlightBytes: 256 * MIB }).sourceBytes, 5 * MIB);
});

// The dense PCB of #626 (models/tests/dense_pcb, DENSE_PCB_GRID=85): a 22.6 MB SURF, 19.9 MB of it
// JSON index. Charged whole at 32x it asked for 690 MiB, reserved twice over the 1280 MiB envelope.
test("an index-heavy board is planned coarse within the in-flight cap instead of oversized", () => {
  const surfBytes = 22_600_481;
  const indexBytes = 19_883_101;
  const whole = initialDisplayLodPlan({ componentCount: 1, surfBytes, maxInFlightBytes: 256 * MIB });
  assert.equal(whole.fitsDecodeCap, false);
  assert.ok(whole.estimatedBytes > 640 * MIB);

  const split = initialDisplayLodPlan({ componentCount: 1, surfBytes, indexBytes, maxInFlightBytes: 256 * MIB });
  assert.equal(split.level, 0, "its standard estimate still exceeds the cap");
  assert.equal(split.reason, "component-admission");
  assert.equal(split.fitsDecodeCap, true);
  const floats = surfBytes - SURF_HEADER_BYTES - indexBytes;
  assert.equal(split.estimatedBytes,
    floats * COARSE_SURF_DECODE_EXPANSION_ESTIMATE + indexBytes * COARSE_SURF_INDEX_DECODE_EXPANSION_ESTIMATE);
  assert.equal(split.sourceBytes * split.sourceExpansionRatio, split.estimatedBytes);

  // The 2,500-hole board (7.8 MB, 6.9 MB index): 239 MiB charged whole, 81 MiB split.
  const small = initialDisplayLodPlan({ componentCount: 1, surfBytes: 7_817_349, indexBytes: 6_876_569, maxInFlightBytes: 256 * MIB });
  assert.equal(small.level, 0);
  assert.ok(small.estimatedBytes < 82 * MIB);
});
