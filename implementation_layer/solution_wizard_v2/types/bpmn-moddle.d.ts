declare module "bpmn-moddle" {
  /** The part of bpmn-moddle the unit tests use to read a BPMN document. */
  export class BpmnModdle {
    constructor(packages?: Record<string, unknown>);
    fromXML(xml: string, typeName?: string): Promise<{ rootElement: unknown; warnings: unknown[] }>;
  }
}
