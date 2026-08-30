import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import test from 'node:test';

import ts from 'typescript';

const source = await readFile(new URL('../src/lib/navigation.ts', import.meta.url), 'utf8');
const compiled = ts.transpileModule(source, {
  fileName: 'navigation.ts',
  compilerOptions: {
    module: ts.ModuleKind.ESNext,
    target: ts.ScriptTarget.ES2022,
  },
});
const moduleUrl = `data:text/javascript;base64,${Buffer.from(compiled.outputText).toString('base64')}`;
const { resolveJoinReturnTo } = await import(moduleUrl);

const origin = 'https://festaflow.example';

test('accepts a same-origin destination inside the current festival journey', () => {
  assert.equal(
    resolveJoinReturnTo('/join/3/experience/mission/42?from=scan#details', '3', origin),
    '/join/3/experience/mission/42?from=scan#details',
  );
});

test('rejects external, protocol-relative, and backslash destinations', () => {
  for (const destination of [
    'https://evil.example/join/3/flow',
    '//evil.example/join/3/flow',
    '\\evil.example\\join\\3\\flow',
    '/join/3/\\\\evil.example',
  ]) {
    assert.equal(resolveJoinReturnTo(destination, '3', origin), null);
  }
});

test('rejects traversal and destinations belonging to another festival', () => {
  assert.equal(resolveJoinReturnTo('/join/3/../4/flow', '3', origin), null);
  assert.equal(resolveJoinReturnTo('/join/4/flow', '3', origin), null);
  assert.equal(resolveJoinReturnTo('/login', '3', origin), null);
});
