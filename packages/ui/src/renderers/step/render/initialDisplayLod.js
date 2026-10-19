import { LOD_DEFAULT_LEVEL, lodTessellationForLevel } from "@text-to-cad/core/lib/surf/lodPolicy.js";
import { TESS_PROBE_MAX_KEYS } from "@text-to-cad/core/lib/surf/tessellationCache.js";

export const LARGE_ASSEMBLY_INITIAL_COARSE_COMPONENTS = 64;
export const DEFAULT_SURF_DECODE_EXPANSION_ESTIMATE = 64;
export const COARSE_SURF_DECODE_EXPANSION_ESTIMATE = 32;
// A SURF's JSON index (face/edge selectors, analytic surface parameters) decodes to far less per
// byte than its float payload: it is parsed once and tessellated a face at a time, where the floats
// are NURBS poles and knots. Calibrated on 188 SURFs from the repo models (see docs/lod.md); the
// worst index-heavy part needed 5x coarse and 22x standard to cover its worker peak at twice the estimate.
export const DEFAULT_SURF_INDEX_DECODE_EXPANSION_ESTIMATE = 32;
export const COARSE_SURF_INDEX_DECODE_EXPANSION_ESTIMATE = 8;
export const INITIAL_DECODE_ESTIMATE_FLOOR_BYTES = 64 * 1024 * 1024;
// `SURF` magic, u32 version, u32 JSON index length (`core/lib/surf/container.js`).
export const SURF_HEADER_BYTES = 12;
const SURF_MAGIC = 0x46525553;
// The tiers a component may open at, in the order they are tried.
const INITIAL_LEVELS = Object.freeze([LOD_DEFAULT_LEVEL, 0]);
// The first probe of a package covers the loader's first publish (`PROGRESSIVE_PUBLISH_FIRST_COMPONENTS`).
export const INITIAL_PROBE_FIRST_CHUNK = 8;

// A large assembly only needs a coarse first pass when standard meshes are
// missing. Prefer the existing standard entry, including when its SURF has
// been reclaimed. Probe metadata before body allocation; the loader still
// reserves memory and verifies the exact object before displaying it.
//
// The rule for one probed row of one tier: a warm plan when the entry is this
// component's surface, not refused before, and admissible; null otherwise.
export function initialDisplayLodFromProbe(cacheProbe, level, {
  surfaceObject, maxInFlightBytes, rejectedCacheObjects = new Set(),
} = {}) {
  if (!cacheProbe || (surfaceObject && surfaceObject !== cacheProbe.surfaceObject)) return null;
  if (rejectedCacheObjects.has(cacheProbe.object)) return null;
  const estimatedBytes = Number(cacheProbe.byteLength) + Number(cacheProbe.decodedBytes);
  if (!Number.isSafeInteger(estimatedBytes) || estimatedBytes <= 0 || estimatedBytes > maxInFlightBytes) return null;
  return {
    cacheProbe,
    plan: {
      level,
      sourceExpansionRatio: level === 0
        ? COARSE_SURF_DECODE_EXPANSION_ESTIMATE : DEFAULT_SURF_DECODE_EXPANSION_ESTIMATE,
      estimatedBytes,
      fitsDecodeCap: true,
      reason: level === 0 ? "warm-coarse-cache" : "warm-standard-cache",
    },
  };
}

export async function probeInitialDisplayLod({
  surfaceInput, surfaceObject, maxInFlightBytes, signal, tessellationCache,
  rejectedCacheObjects = new Set(),
  probeEntries = (...args) => tessellationCache.probeCachedTessellationEntries(...args),
}) {
  for (const level of INITIAL_LEVELS) {
    const hits = await probeEntries([surfaceInput], lodTessellationForLevel(level), { signal });
    const warm = initialDisplayLodFromProbe(hits.get(surfaceInput), level,
      { surfaceObject, maxInFlightBytes, rejectedCacheObjects });
    if (warm) return warm;
  }
  return null;
}

/**
 * A package's initial display plans, a chunk of components at a time in load order: one metadata
 * probe of the standard tier for the whole chunk, then one of the coarse tier for the components
 * the standard tier did not admit. The rule is `probeInitialDisplayLod`'s; the requests are one per
 * chunk and tier where that made one per component and tier. The first chunk is `firstChunk`
 * components (the loader's first publish) and each next one twice the last, up to `maxChunk`: a
 * server answers a probe a key at a time, so the first geometry waits on a probe of what it draws,
 * not of the whole package. Asking about a chunk probes the two after it with it, so neither a load
 * crossing into the next nor a batch read reaching past it waits; past the first chunk, only once
 * `readAheadAfter` settles (the first body read), so nothing competes with the two requests the
 * first geometry waits on. A probe that fails (an older server, a network error) reads as nothing
 * warm, as it did for one component.
 *
 * `plan(cid)`: that component's warm plan (`{ cacheProbe, plan }`), or null when neither tier
 * holds one; undefined for a component this table was not given. `peek(cid)`: the same without
 * waiting, undefined while its chunk is unprobed. `probed(surfaceInput, level)`: the row a probe of
 * that tier answered for that input (null for none), undefined for a tier it was never asked.
 */
export function createInitialDisplayPlans({
  components, probeEntries, maxInFlightBytes, signal, readAheadAfter = null,
  firstChunk = INITIAL_PROBE_FIRST_CHUNK, maxChunk = TESS_PROBE_MAX_KEYS,
}) {
  const chunks = [];
  const chunkOf = new Map();
  for (const [cid, component] of components) {
    const size = Math.min(maxChunk, Math.max(1, firstChunk) * 2 ** Math.min(30, Math.max(0, chunks.length - 1)));
    if (!chunks.length || chunks.at(-1).length >= size) chunks.push([]);
    chunks.at(-1).push([cid, component]);
    chunkOf.set(cid, chunks.length - 1);
  }
  const plans = new Map();
  const answered = new Map();
  const work = new Map();
  const inputOf = component => String(component?.surfaceInput || "");
  const planChunk = (index) => {
    if (!work.has(index)) {
      const planned = (async () => {
        let remaining = chunks[index];
        for (const level of INITIAL_LEVELS) {
          if (!remaining.length) break;
          const inputs = [...new Set(remaining.map(([, component]) => inputOf(component)))];
          const hits = await probeEntries(inputs, lodTessellationForLevel(level), { signal });
          for (const input of inputs) answered.set(`${level}|${input}`, hits.get(input) || null);
          const next = [];
          for (const [cid, component] of remaining) {
            const warm = initialDisplayLodFromProbe(hits.get(inputOf(component)), level,
              { surfaceObject: component?.surfaceObject, maxInFlightBytes });
            if (warm) plans.set(cid, warm); else next.push([cid, component]);
          }
          remaining = next;
        }
        for (const [cid] of remaining) plans.set(cid, null);
      })();
      // Awaited by whoever asked; a chunk probed ahead fails quietly until somebody does.
      planned.catch(() => {});
      work.set(index, planned);
    }
    return work.get(index);
  };
  return {
    async plan(cid) {
      const index = chunkOf.get(cid);
      if (index === undefined) return undefined;
      const planned = planChunk(index);
      const readAhead = () => {
        for (let ahead = index + 1; ahead <= index + 2 && ahead < chunks.length; ahead += 1) planChunk(ahead);
      };
      if (index === 0 && readAheadAfter) Promise.resolve(readAheadAfter).then(readAhead, () => {});
      else readAhead();
      await planned;
      return plans.get(cid) ?? null;
    },
    peek: cid => plans.get(cid),
    probed: (surfaceInput, level) => (INITIAL_LEVELS.includes(level)
      ? answered.get(`${level}|${String(surfaceInput || "")}`) : undefined),
  };
}

// The JSON index length a SURF's first bytes declare; null when they are not a SURF header or
// declare more index than a `surfBytes`-long SURF holds.
export function surfIndexBytesFromHeader(prefix, surfBytes = null) {
  try {
    if (!(prefix instanceof ArrayBuffer) || prefix.byteLength < SURF_HEADER_BYTES) return null;
    const header = new DataView(prefix, 0, SURF_HEADER_BYTES);
    if (header.getUint32(0, true) !== SURF_MAGIC) return null;
    const indexBytes = header.getUint32(8, true);
    const total = Number(surfBytes);
    if (Number.isFinite(total) && total > 0 && SURF_HEADER_BYTES + indexBytes > total) return null;
    return indexBytes;
  } catch {
    return null;
  }
}

// The bytes the tier's expansion ratio applies to: a SURF's float payload plus its JSON index
// weighted down to the index's own multiple, so that `sourceBytes × sourceExpansionRatio` is the
// split estimate. Without a usable index length, the whole SURF at the tier ratio, as before.
export function surfDecodeSourceBytes(surfBytes, {
  indexBytes = null,
  sourceExpansionRatio = DEFAULT_SURF_DECODE_EXPANSION_ESTIMATE,
  indexExpansionRatio = DEFAULT_SURF_INDEX_DECODE_EXPANSION_ESTIMATE,
} = {}) {
  const bytes = Number(surfBytes);
  if (!Number.isFinite(bytes) || bytes <= 0) return null;
  const index = Number(indexBytes);
  if (indexBytes === null || !Number.isSafeInteger(index) || index < 0
      || SURF_HEADER_BYTES + index > bytes) return bytes;
  const ratio = Math.max(1, Number(sourceExpansionRatio) || 1);
  const indexRatio = Math.min(ratio, Math.max(0, Number(indexExpansionRatio) || 0));
  return (bytes - SURF_HEADER_BYTES - index) + index * indexRatio / ratio;
}

export function estimateInitialSurfDecodeBytes(
  surfBytes,
  sourceExpansionRatio,
  { floorBytes = INITIAL_DECODE_ESTIMATE_FLOOR_BYTES, indexBytes = null, indexExpansionRatio } = {},
) {
  const ratio = Math.max(1, Number(sourceExpansionRatio) || 1);
  const bytes = surfDecodeSourceBytes(surfBytes, {
    indexBytes,
    sourceExpansionRatio: ratio,
    ...(indexExpansionRatio === undefined ? {} : { indexExpansionRatio }),
  });
  return Math.max(floorBytes, bytes ? bytes * ratio : 0);
}

// Pure per-component initial display decision. Large assemblies take the
// explicit coarse tier throughout. In a smaller package, any individual leaf
// takes that tier when its conservative default estimate cannot be admitted.
// The caller still applies the independent memory reservation; an unfit coarse
// estimate can run only through the caller's serial, globally reserved
// oversized-component path. With the SURF's `indexBytes` (its header's JSON
// length), the index is charged at its own multiple and only the float payload
// at the tier ratio; `sourceBytes` is what the loader's estimator scales.
export function initialDisplayLodPlan({
  componentCount,
  surfBytes = null,
  indexBytes = null,
  maxInFlightBytes,
} = {}) {
  const count = Math.max(0, Math.trunc(Number(componentCount) || 0));
  const cap = Math.max(1, Number(maxInFlightBytes) || 1);
  const defaultEstimate = estimateInitialSurfDecodeBytes(
    surfBytes,
    DEFAULT_SURF_DECODE_EXPANSION_ESTIMATE,
    { indexBytes, indexExpansionRatio: DEFAULT_SURF_INDEX_DECODE_EXPANSION_ESTIMATE },
  );
  const coarse = count >= LARGE_ASSEMBLY_INITIAL_COARSE_COMPONENTS
    || defaultEstimate > cap;
  const sourceExpansionRatio = coarse
    ? COARSE_SURF_DECODE_EXPANSION_ESTIMATE
    : DEFAULT_SURF_DECODE_EXPANSION_ESTIMATE;
  const indexExpansionRatio = coarse
    ? COARSE_SURF_INDEX_DECODE_EXPANSION_ESTIMATE
    : DEFAULT_SURF_INDEX_DECODE_EXPANSION_ESTIMATE;
  const estimatedBytes = estimateInitialSurfDecodeBytes(surfBytes, sourceExpansionRatio,
    { indexBytes, indexExpansionRatio });
  return {
    level: coarse ? 0 : LOD_DEFAULT_LEVEL,
    sourceExpansionRatio,
    sourceBytes: surfDecodeSourceBytes(surfBytes, { indexBytes, sourceExpansionRatio, indexExpansionRatio }),
    estimatedBytes,
    fitsDecodeCap: estimatedBytes <= cap,
    reason: count >= LARGE_ASSEMBLY_INITIAL_COARSE_COMPONENTS
      ? "large-assembly"
      : coarse ? "component-admission" : "default",
  };
}
