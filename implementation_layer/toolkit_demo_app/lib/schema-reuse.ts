// Which schema a run of a pipeline demo may use: the ready-made one of an example, the one
// made in the last run, or none (a new one is made). Used by the demos that make a schema
// from a task written in plain words.

/** The schema of the last run, to reuse while the task stays the same. */
export interface MadeSchema {
  id: string;
  task: string;
}

/** The id of the schema to reuse: only for exactly the task it was made from. */
export function reusableSchemaId(
  made: MadeSchema | null,
  task: string,
): string | null {
  return made && made.task.trim() === task.trim() ? made.id : null;
}

/**
 * The key of the ready-made schema to send: the example's own, and only while the task is
 * exactly the example's. Once the text is edited, a new schema is made.
 */
export function savedSchemaKey(
  example: { schemaKey?: string; task: string } | null,
  task: string,
): string {
  return example?.schemaKey && task.trim() === example.task.trim()
    ? example.schemaKey
    : "";
}
