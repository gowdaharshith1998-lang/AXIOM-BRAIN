export function hasWebGPU(): boolean {
  const n = navigator as unknown as { gpu?: unknown };
  return typeof n.gpu !== "undefined";
}

export type RendererKind = "webgpu" | "webgl";

export function preferredRendererKind(opts: {
  navigatorHasWebGpu: boolean;
  threeHasWebGpuRenderer: boolean;
}): RendererKind {
  return opts.navigatorHasWebGpu && opts.threeHasWebGpuRenderer ? "webgpu" : "webgl";
}

