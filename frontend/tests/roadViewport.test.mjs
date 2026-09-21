import assert from 'node:assert/strict';
import test from 'node:test';
import {
  roadBboxQuery,
  roadRequestBounds,
  viewportIsInside,
} from '../src/roadViewport.ts';

test('district overview does not fetch all safety segments', () => {
  assert.equal(roadRequestBounds({
    west: 126.619,
    south: 37.425,
    east: 126.720,
    north: 37.488,
  }), null);
});

test('neighborhood requests are padded and reusable while panning inside', () => {
  const view = { west: 126.675, south: 37.460, east: 126.685, north: 37.468 };
  const bounds = roadRequestBounds(view);
  assert.ok(bounds);
  assert.equal(viewportIsInside(view, bounds), true);
  assert.equal(viewportIsInside({
    west: 126.676, south: 37.461, east: 126.686, north: 37.469,
  }, bounds), true);
  assert.equal(viewportIsInside({
    west: 126.670, south: 37.461, east: 126.680, north: 37.469,
  }, bounds), false);
  assert.match(roadBboxQuery(bounds), /^-?\d+\.\d{6},-?\d+\.\d{6},-?\d+\.\d{6},-?\d+\.\d{6}$/);
});
