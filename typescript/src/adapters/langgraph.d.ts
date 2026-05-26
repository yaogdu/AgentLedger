export class LangGraphCheckpointerAdapter {
  constructor(runtime: any);
  name: string;
  configForRun(runId: string, options?: { threadId?: string | null; checkpointNs?: string }): any;
  checkpointFromRun(runId: string): any;
  put(config: any, checkpoint: any, metadata?: any, newVersions?: any): any;
  get(config: any): any;
  getTuple(config: any): any;
  list(config?: any): any[];
}
export class LangGraphNodeAdapter {
  constructor(node: any, options?: { role?: string });
  name: string;
  role: string;
  mapRunSpec(): any;
  asAgent(options?: { outputKey?: string }): any;
}
export const adapterPackage: { name: string; runtimePackage: string; version: string; category: string };

