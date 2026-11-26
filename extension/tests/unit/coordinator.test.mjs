import test from 'node:test';
import assert from 'node:assert/strict';
import { createSuggestCoordinator } from '../../background/coordinator.js';

const tick = (ms = 0) => new Promise((resolve) => setTimeout(resolve, ms));

function deferredRun() {
  const calls = [];
  const run = (payload, signal) =>
    new Promise((resolve, reject) => {
      calls.push({ payload, signal, resolve, reject });
    });
  return { calls, run };
}

test('debounces: only the latest request for a chat reaches the backend', async () => {
  const { calls, run } = deferredRun();
  const coordinator = createSuggestCoordinator({ run, debounceMs: 20 });
  const first = coordinator.request('chat-a', 1);
  const second = coordinator.request('chat-a', 2);
  assert.deepEqual(await first, { aborted: true });
  await tick(40);
  assert.equal(calls.length, 1);
  assert.equal(calls[0].payload, 2);
  calls[0].resolve('done');
  assert.deepEqual(await second, { value: 'done' });
  assert.equal(coordinator.pending(), 0);
});

test('a newer request aborts the in-flight one for the same chat', async () => {
  const { calls, run } = deferredRun();
  const coordinator = createSuggestCoordinator({ run, debounceMs: 0 });
  const first = coordinator.request('chat-a', 'old');
  await tick();
  assert.equal(calls.length, 1);
  const second = coordinator.request('chat-a', 'new', { immediate: true });
  assert.equal(calls[0].signal.aborted, true);
  assert.deepEqual(await first, { aborted: true });
  calls[0].resolve('stale result must be ignored');
  await tick();
  calls[1].resolve('fresh');
  assert.deepEqual(await second, { value: 'fresh' });
});

test('different chats do not abort each other; cancelAllExcept drops the rest', async () => {
  const { calls, run } = deferredRun();
  const coordinator = createSuggestCoordinator({ run, debounceMs: 0 });
  const a = coordinator.request('chat-a', 'a');
  const b = coordinator.request('chat-b', 'b');
  await tick();
  assert.equal(calls.length, 2);
  assert.equal(calls[0].signal.aborted, false);
  coordinator.cancelAllExcept('chat-b');
  assert.deepEqual(await a, { aborted: true });
  assert.equal(calls[0].signal.aborted, true);
  calls[1].resolve('b done');
  assert.deepEqual(await b, { value: 'b done' });
});

test('errors are reported as outcomes, cancel settles the caller', async () => {
  const coordinator = createSuggestCoordinator({
    run: async () => {
      throw new Error('boom');
    },
    debounceMs: 0,
  });
  const outcome = await coordinator.request('chat-a', 1);
  assert.equal(outcome.error.message, 'boom');

  const { run } = deferredRun();
  const other = createSuggestCoordinator({ run, debounceMs: 50 });
  const pending = other.request('chat-a', 1);
  other.cancel('chat-a');
  assert.deepEqual(await pending, { aborted: true });
});
