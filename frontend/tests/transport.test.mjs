import assert from 'node:assert/strict';
import { after, test } from 'node:test';
import { createServer } from 'vite';
import { parse } from 'yaml';

const server = await createServer({
  root: new URL('../', import.meta.url).pathname,
  configFile: false,
  optimizeDeps: { noDiscovery: true, include: [] },
  server: { middlewareMode: true, hmr: false, watch: null },
});
after(() => server.close());
const helpers = await server.ssrLoadModule('/src/api/helpers.ts');
const client = await server.ssrLoadModule('/src/api/client.ts');
const { generateStandardAgentCandidate } = await server.ssrLoadModule('/src/utils/standardAgentCandidate.ts');
const { formatToolResult } = await server.ssrLoadModule('/src/utils/content.ts');
const { disambiguateToolNames, deriveSubAgentToolSurface } = await server.ssrLoadModule('/src/utils/agentToolValidation.ts');

test('tool preview names match runtime fallbacks and stay within the name limit', () => {
  assert.deepEqual(deriveSubAgentToolSurface('', '', ''), {
    toolName: 'sub_agent', toolDescription: 'Delegate to the sub_agent agent.',
    argDescription: 'Request for the sub_agent agent.',
  });
  assert.equal(deriveSubAgentToolSurface('!!!', 'description', '123___name').toolName, 'a_123_name');
  const name = 'x'.repeat(64);
  const reserved = `${'x'.repeat(62)}_2`;
  const result = disambiguateToolNames([name, reserved, ...Array(12).fill(name)]);
  assert.deepEqual(result.slice(0, 3), [name, reserved, `${'x'.repeat(62)}_3`]);
  assert.equal(new Set(result).size, result.length);
  assert.ok(result.every(value => value.length <= 64));
});

test('tool result formatting pretty-prints JSON without rewriting non-JSON text', () => {
  assert.equal(formatToolResult('{"ok":true}'), '{\n  "ok": true\n}');
  for (const raw of ["{'text': 'True None False'}", "{'date': datetime.datetime(2026, 9, 10)}", "plain text"]) {
    assert.equal(formatToolResult(raw), raw);
  }
});

test('standard agent YAML round-trips without flattening values or trimming prompts', () => {
  const override = {
    baseProfileId: 'search', baseProfileName: 'Search: customized',
    description: 'true', icon: '', tools: [], skills: ['table-usage'],
    mcpServers: [{ name: 'lookup', transport: 'http', url: 'https://example.com',
      allowed_tools: ['first', 'second'], request_timeout: 30, auth: false }],
    useSearchContext: false, temperature: 0,
    starters: [{ label: 'A: "question"', prompt: 'First\nSecond' }],
    systemPrompt: 'Keep this prompt.\n\nAnd this trailing newline.\n', updatedAt: 'now',
  };
  const candidate = generateStandardAgentCandidate(override);
  assert.deepEqual(parse(candidate.yaml), { [candidate.profileId]: candidate.profile });
  const withoutTemperature = generateStandardAgentCandidate({ ...override, temperature: undefined });
  assert.equal('temperature' in parse(withoutTemperature.yaml)[withoutTemperature.profileId], false);
});

test('requests acquire a fresh token and preserve JSON bodies', async context => {
  let acquired = 0;
  helpers.setTokenProvider(async () => `fresh-${++acquired}`);
  const authorizations = [];
  context.mock.method(globalThis, 'fetch', async (_url, init) => {
    authorizations.push(init.headers.get('Authorization'));
    assert.equal(init.headers.get('Content-Type'), 'application/json');
    assert.deepEqual(JSON.parse(init.body), { name: 'saved' });
    return Response.json({ ok: true });
  });
  for (let count = 0; count < 2; count++) {
    await helpers.requestJson('/api/test', { method: 'PUT', body: JSON.stringify({ name: 'saved' }) }, 'Save');
  }
  assert.deepEqual(authorizations, ['Bearer fresh-1', 'Bearer fresh-2']);
});

test('conversation loading follows opaque cursors until exhausted', async context => {
  helpers.setTokenProvider(async () => null);
  const cursors = [];
  context.mock.method(globalThis, 'fetch', async url => {
    const cursor = new URL(url, 'http://localhost').searchParams.get('cursor');
    cursors.push(cursor);
    return Response.json({ conversations: [{ id: cursor ? 'second' : 'first' }], nextCursor: cursor ? null : 'opaque+/=' });
  });
  assert.deepEqual((await client.listConversations(1)).map(entry => entry.id), ['first', 'second']);
  assert.deepEqual(cursors, [null, 'opaque+/=']);
});

test('validation details remain visible to callers', async context => {
  context.mock.method(globalThis, 'fetch', async () => Response.json({
    detail: [{ field: 'tools[0]', reason: 'Tool is not available.' }],
  }, { status: 422 }));
  await assert.rejects(helpers.request('/api/test', {}, 'Save'), /tools\[0\]: Tool is not available/);
});

test('network errors are reported but deliberate aborts are preserved', async context => {
  const failure = new TypeError('network unavailable');
  context.mock.method(globalThis, 'fetch', async () => { throw failure; });
  await assert.rejects(helpers.request('/api/test', {}, 'Save'), helpers.RequestError);
  const controller = new AbortController();
  controller.abort();
  await assert.rejects(helpers.request('/api/test', { signal: controller.signal }, 'Save'), error => error === failure);
});

test('SSE handles split frames and rejects incomplete or malformed responses', async context => {
  let chunks = ['event: text\r\nda', 'ta: {"content":\r\ndata: "Hello"}\r\n\r\n', 'event: done\ndata: {}\n\n'];
  context.mock.method(globalThis, 'fetch', async () => new Response(new ReadableStream({
    start(controller) {
      for (const chunk of chunks) controller.enqueue(new TextEncoder().encode(chunk));
      controller.close();
    },
  })));
  const received = [];
  await client.sendMessage('session', 'hello', null, {
    onText: payload => received.push(payload.content), onDone: () => received.push('done'),
  });
  assert.deepEqual(received, ['Hello', 'done']);
  chunks = ['event: text\ndata: {"content":"partial"}\n\n'];
  await assert.rejects(client.sendMessage('session', 'hello', null, {}), /ended before completion/);
  chunks = ['event: text\ndata: invalid-json\n\n'];
  await assert.rejects(client.sendMessage('session', 'hello', null, {}), SyntaxError);
  chunks = ['event: text\ndata: {"content":"hello"}\n\n'];
  await assert.rejects(client.sendMessage('session', 'hello', null, {
    onText: () => { throw new Error('callback failure'); },
  }), /callback failure/);
});

test('view data shares authentication while preserving structured refusals', async context => {
  let acquired = 0;
  helpers.setTokenProvider(async () => `view-${++acquired}`);
  let status = 403;
  context.mock.method(globalThis, 'fetch', async (_url, init) => {
    assert.equal(init.headers.get('Authorization'), `Bearer view-${acquired}`);
    assert.equal(init.headers.get('Content-Type'), 'application/json');
    assert.deepEqual(JSON.parse(init.body), { tool: 'lookup', arguments: { id: 1 } });
    return status === 403
      ? Response.json({ error: { code: 'tool_not_allowed', message: 'Denied' } }, { status })
      : new Response('', { status });
  });
  assert.deepEqual(await client.requestAgentViewData('session', 'view', 'lookup', { id: 1 }), {
    ok: false, error: { code: 'tool_not_allowed', message: 'Denied' },
  });
  status = 401;
  assert.equal((await client.requestAgentViewData('session', 'view', 'lookup', { id: 1 })).error.message, 'Your session has expired.');
  assert.equal(acquired, 2);
  helpers.setTokenProvider(async () => { throw new helpers.AuthError('Sign in'); });
  await assert.rejects(helpers.request('/api/test', {}, 'Load'), helpers.AuthError);
  helpers.setTokenProvider(async () => null);
});