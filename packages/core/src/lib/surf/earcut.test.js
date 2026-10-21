import assert from "node:assert/strict";
import test from "node:test";

import { ShapeUtils, Vector2 } from "three";

import { triangulateShape } from "./earcut.js";

const ring = (points) => points.map(([x, y]) => new Vector2(x, y));

// Both triangulators mutate their input (end-point dedup), so each gets its own.
function bothWays(contour, holes) {
  const expected = ShapeUtils.triangulateShape(ring(contour), holes.map(ring));
  const actual = triangulateShape(ring(contour), holes.map(ring));
  return { expected, actual };
}

function polygon(cx, cy, r, sides, phase = 0) {
  const points = [];
  for (let k = 0; k < sides; k += 1) {
    const a = phase + (2 * Math.PI * k) / sides;
    points.push([cx + r * Math.cos(a), cy + r * Math.sin(a)]);
  }
  return points;
}

function signedArea(points) {
  let sum = 0;
  for (let i = 0, j = points.length - 1; i < points.length; j = i, i += 1) {
    sum += (points[j][0] - points[i][0]) * (points[i][1] + points[j][1]);
  }
  return sum / 2;
}

function coveredArea(contour, holes, faces) {
  const all = [contour, ...holes].flat();
  let total = 0;
  for (const [a, b, c] of faces) {
    const [ax, ay] = all[a];
    const [bx, by] = all[b];
    const [cx, cy] = all[c];
    total += Math.abs((bx - ax) * (cy - ay) - (cx - ax) * (by - ay)) / 2;
  }
  return total;
}

test("a PCB-like grid of round holes triangulates exactly as earcut does", () => {
  const size = 40;
  const contour = [[0, 0], [size, 0], [size, size], [0, size]];
  const holes = [];
  for (let i = 0; i < 12; i += 1) {
    for (let j = 0; j < 12; j += 1) holes.push(polygon(2 + 3 * i, 2 + 3 * j, 0.6, 16));
  }
  const { expected, actual } = bothWays(contour, holes);
  assert.deepEqual(actual, expected);
  const area = Math.abs(signedArea(contour)) - holes.reduce((sum, h) => sum + Math.abs(signedArea(h)), 0);
  assert.ok(Math.abs(coveredArea(contour, holes, actual) - area) < area * 1e-9);
});

test("scattered holes of mixed shapes and windings triangulate exactly as earcut does", () => {
  let seed = 12345;
  const random = () => ((seed = (seed * 1103515245 + 12345) % 2 ** 31) / 2 ** 31);
  const contour = polygon(50, 50, 48, 40);
  const holes = [];
  for (let i = 0; i < 9; i += 1) {
    for (let j = 0; j < 9; j += 1) {
      const cx = 18 + 8 * i + (random() - 0.5) * 3;
      const cy = 18 + 8 * j + (random() - 0.5) * 3;
      const hole = polygon(cx, cy, 1 + random() * 2, 3 + Math.floor(random() * 12), random() * 6);
      holes.push(random() < 0.5 ? hole : hole.reverse());
    }
  }
  const { expected, actual } = bothWays(contour, holes);
  assert.deepEqual(actual, expected);
});

test("holes that touch the outer ring or each other at a vertex take earcut's ordered bridge", () => {
  // Squares in a row, each one's leftmost corner on the previous one's right
  // corner, the first one's on the outer left side: every bridge is a vertex the
  // hole already shares, which only the ring-order scan can pick.
  const contour = [[0, -10], [60, -10], [60, 10], [0, 10]];
  const holes = [];
  for (let i = 0; i < 40; i += 1) holes.push([[i, 0], [i + 0.5, -0.5], [i + 1, 0], [i + 0.5, 0.5]]);
  const { expected, actual } = bothWays(contour, holes);
  assert.deepEqual(actual, expected);
});

test("one hole, or none, goes through the same code earcut does", () => {
  const contour = [[0, 0], [4, 0], [4, 4], [0, 4], [0, 0]];
  for (const holes of [[], [[[1, 1], [1, 2], [2, 2], [2, 1], [1, 1]]]]) {
    const { expected, actual } = bothWays(contour, holes);
    assert.deepEqual(actual, expected);
  }
});
