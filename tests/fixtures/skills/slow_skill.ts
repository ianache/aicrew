// slow_skill.ts
// Sleeps for 10 seconds before writing output.
// Used by timeout and zombie-cleanup tests — must be killed by DenoRunner.
await new Promise<void>((resolve) => setTimeout(resolve, 10_000));
console.log(JSON.stringify({ result: "never reached" }));
