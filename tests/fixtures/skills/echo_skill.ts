// echo_skill.ts
// Reads all stdin bytes, parses as JSON, writes back to stdout as JSON.
// Used by Phase 1 tests — no network access required.
const decoder = new TextDecoder();
const chunks: Uint8Array[] = [];
for await (const chunk of Deno.stdin.readable) {
  chunks.push(chunk);
}
const totalLength = chunks.reduce((acc, c) => acc + c.length, 0);
const combined = new Uint8Array(totalLength);
let offset = 0;
for (const chunk of chunks) {
  combined.set(chunk, offset);
  offset += chunk.length;
}
const text = decoder.decode(combined);
const json = JSON.parse(text);
console.log(JSON.stringify(json));
