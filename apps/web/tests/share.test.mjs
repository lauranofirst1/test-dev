import assert from 'node:assert/strict';
import { File } from 'node:buffer';
import { readFile } from 'node:fs/promises';
import test from 'node:test';

import ts from 'typescript';

const source = await readFile(new URL('../src/lib/share.ts', import.meta.url), 'utf8');
const compiled = ts.transpileModule(source, {
  fileName: 'share.ts',
  compilerOptions: {
    module: ts.ModuleKind.ESNext,
    target: ts.ScriptTarget.ES2022,
  },
});
const shareModuleUrl = `data:text/javascript;base64,${Buffer.from(compiled.outputText).toString('base64')}`;
const { buildExperienceShareUrl, performShare } = await import(shareModuleUrl);

test('Experience share URL preserves the exact destination and source identity', () => {
  assert.equal(
    buildExperienceShareUrl('https://festaflow.example', 3, 'lecture', 42),
    'https://festaflow.example/join/3/experience/lecture/42?from=shared_link',
  );
});

test('supported Web Share resolves as a native share without copying', async () => {
  let shared;
  let copyCalls = 0;
  const result = await performShare(
    { data: { title: 'Experience', text: '같이 갈래?', url: 'https://festaflow.example/join/3' } },
    {
      share: async (data) => { shared = data; },
      copyText: async () => { copyCalls += 1; return true; },
    },
  );

  assert.equal(result.kind, 'shared');
  assert.equal(shared.url, 'https://festaflow.example/join/3');
  assert.equal(copyCalls, 0);
});

test('unsupported Web Share copies the fallback text', async () => {
  const copied = [];
  const result = await performShare(
    { data: { url: 'https://festaflow.example/join/3' }, fallbackText: 'share me' },
    { copyText: async (value) => { copied.push(value); return true; } },
  );

  assert.equal(result.kind, 'copied');
  assert.deepEqual(copied, ['share me']);
});

test('AbortError is a user cancellation and does not trigger fallback', async () => {
  let copyCalls = 0;
  const cancelled = new Error('closed');
  cancelled.name = 'AbortError';
  const result = await performShare(
    { data: { url: 'https://festaflow.example/join/3' } },
    {
      share: async () => { throw cancelled; },
      copyText: async () => { copyCalls += 1; return true; },
    },
  );

  assert.equal(result.kind, 'cancelled');
  assert.equal(copyCalls, 0);
});

test('native share failure falls back to clipboard', async () => {
  const copied = [];
  const result = await performShare(
    { data: { text: 'My Flow', url: 'https://festaflow.example/join/3/flow' } },
    {
      share: async () => { throw new Error('not allowed'); },
      copyText: async (value) => { copied.push(value); return true; },
    },
  );

  assert.equal(result.kind, 'copied');
  assert.equal(copied[0], 'My Flow\nhttps://festaflow.example/join/3/flow');
});

test('failed clipboard returns a visible manual-copy payload', async () => {
  const result = await performShare(
    { data: { url: 'https://festaflow.example/join/3/flow' } },
    { copyText: async () => false },
  );

  assert.deepEqual(result, {
    kind: 'failed',
    fallbackText: 'https://festaflow.example/join/3/flow',
  });
});

test('Flow file share includes files only after canShare approves them', async () => {
  const flowImage = new File(['flow image'], 'my-flow.png', { type: 'image/png' });
  let checked;
  let shared;
  const result = await performShare(
    { data: { text: 'My Flow', url: 'https://festaflow.example/join/3/flow', files: [flowImage] } },
    {
      canShare: (data) => { checked = data; return true; },
      share: async (data) => { shared = data; },
      copyText: async () => false,
    },
  );

  assert.equal(result.kind, 'shared');
  assert.equal(flowImage.name, 'my-flow.png');
  assert.equal(flowImage.type, 'image/png');
  assert.deepEqual(checked.files, [flowImage]);
  assert.deepEqual(shared.files, [flowImage]);
});

test('Flow share drops unsupported files but still shares its URL and text', async () => {
  const flowImage = new File(['flow image'], 'my-flow.png', { type: 'image/png' });
  let shared;
  const result = await performShare(
    { data: { text: 'My Flow', url: 'https://festaflow.example/join/3/flow', files: [flowImage] } },
    {
      canShare: () => false,
      share: async (data) => { shared = data; },
      copyText: async () => false,
    },
  );

  assert.equal(result.kind, 'shared');
  assert.equal('files' in shared, false);
  assert.equal(shared.url, 'https://festaflow.example/join/3/flow');
  assert.equal(shared.text, 'My Flow');
});
