import { simpleRun } from '../../src/index.js';

const result = await simpleRun(async (_ctx, state) => ({ message: 'hello from typescript', input: state.input }), {
  initialState: { input: 'world' },
});

console.log(JSON.stringify({ run_id: result.run_id, output: result.output, state: result.state }, null, 2));
