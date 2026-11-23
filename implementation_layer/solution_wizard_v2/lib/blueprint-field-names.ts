/**
 * The blueprint's fields in plain words, for a refused edit: wizard_api names
 * the field it refused (`operations[2].step_id`, `after`), and the user reads
 * "the previous step" instead. The words are in the dictionary
 * (`blueprintFieldNames`, lib/i18n), keyed by the field's last name. Step
 * fields for now; later edits add their own keys there.
 *
 * `fieldName` names a whole path of the blueprint (`workflow.steps[3].depends_on`)
 * for the full blueprint view and its refused saves.
 */
import type { Dict, Locale } from "@/lib/i18n";

/** The last name of a refused field: `operations[0].step_id` → `step_id`; null without one. */
export function blueprintFieldKey(field: string | null | undefined): string | null {
  if (!field) return null;
  const last = field.split(".").pop() ?? "";
  const key = last.replace(/\[\d+\]$/, "");
  return /^[a-z_]+$/.test(key) && !/\[/.test(last) ? key : null;
}

/** The field in the UI language, or null when there are no words for it. */
export function fieldInPlainWords(field: string | null | undefined, t: Pick<Dict, "blueprintFieldNames">): string | null {
  const key = blueprintFieldKey(field);
  if (!key) return null;
  return Object.prototype.hasOwnProperty.call(t.blueprintFieldNames, key) ? t.blueprintFieldNames[key] : null;
}

type PathWords = {
  /** The blueprint's top-level sections. */
  sections: Record<string, string>;
  /** An item of a list, keyed by the list's path without indexes; "{n}" is its number from 1. */
  items: Record<string, string>;
  /** An entry of a map keyed by the user's own ids; "{id}" is the key. */
  entries: Record<string, string>;
  /** A field of a section or an item, keyed by its own name. */
  fields: Record<string, string>;
};

/**
 * The words of `fieldName`. Kept here, not in lib/i18n: that module reads the
 * request's cookies, and the full blueprint view runs in the browser.
 */
const PATH_WORDS: Record<Locale, PathWords> = {
  en: {
    sections: {
      blueprint_version: "Blueprint version",
      metadata: "Metadata",
      use_case: "Use case",
      business_spec: "Business requirements",
      technical_spec: "Technical requirements",
      target_output_spec: "Target output",
      assumptions: "Assumptions",
      artifacts: "Data objects",
      inputs: "Inputs",
      outputs: "Outputs",
      schemas: "Schemas",
      components: "Components",
      workflow: "Workflow",
      business_process: "Business process",
      prompts: "Prompts",
      models: "Models",
      validation: "Validation",
      evaluation: "Evaluation",
      governance: "Governance",
      runtime: "Runtime",
      package: "Package",
      visualizations: "Visualizations",
      traceability: "Traceability",
      change_log: "Change log",
    },
    items: {
      "workflow.steps": "Step {n}",
      assumptions: "Assumption {n}",
      traceability: "Trace {n}",
      change_log: "Change {n}",
      "business_process.participants": "Lane {n}",
      "business_process.manual_steps": "Manual step {n}",
      "business_process.external_parties": "External party {n}",
      "business_process.message_flows": "Message flow {n}",
      "business_process.exceptions": "Path {n}",
      "business_process.decision_points": "Decision {n}",
      "business_process.decision_points.branches": "branch {n}",
      "components.selected_modules": "Module {n}",
      "components.selected_building_blocks": "Building block {n}",
      "components.custom_components": "Custom component {n}",
      "technical_spec.external_services": "External service {n}",
    },
    entries: {
      artifacts: 'Data object "{id}"',
    },
    fields: {
      id: "id",
      name: "name",
      label: "name",
      type: "type",
      description: "description",
      domain: "domain",
      knowledge_processes: "knowledge processes",
      component: "component",
      inputs: "inputs",
      outputs: "outputs",
      parameters: "settings",
      depends_on: "comes after",
      loop: "loop",
      max_iterations: "most rounds",
      loop_condition_ref: "loop condition",
      performed_by: "lane",
      steps: "steps",
      source: "source",
      optional: "optional",
      final_output: "final output",
      externally_visible: "visible outside",
      produced_by: "made by",
      schema_ref: "schema",
      overwrite: "overwrite",
      kind: "kind",
      default_lane_for: "lane for step types",
      participants: "lanes",
      manual_steps: "manual steps",
      external_parties: "external parties",
      message_flows: "message flows",
      exceptions: "paths",
      decision_points: "decisions",
      consumes: "uses",
      produces: "makes",
      sends: "sends",
      to_step: "to step",
      from: "from",
      from_: "from",
      to: "to",
      attached_to: "step the path is on",
      condition: "condition",
      outcome: "where the path leads",
      after: "comes after",
      branches: "branches",
      target: "leads to",
      text: "text",
      status: "status",
      impact: "impact",
      recorded_by: "recorded by",
      recorded_at: "recorded at",
      selected_modules: "modules",
      selected_building_blocks: "building blocks",
      custom_components: "custom components",
      reason: "reason",
      data_handling: "data handling",
      external_model_api_allowed: "external model API allowed",
      local_processing_required: "local processing required",
      stores_input_data: "stores input data",
      stores_outputs: "stores outputs",
      retention_policy: "retention policy",
      contains_personal_data: "contains personal data",
      output_sensitivity: "output sensitivity",
      audit_log_required: "audit log required",
      interface: "interface",
      entrypoint: "entry point",
      env_file: "environment file",
      blueprint_id: "blueprint id",
      created_by: "created by",
      created_at: "created at",
      last_updated_at: "last updated at",
      output_dir: "output folder",
      include_tests: "include tests",
      include_evals: "include evaluations",
      include_docs: "include documentation",
      required_by: "required by",
      version: "version",
      date: "date",
      change: "change",
      changed_by: "changed by",
      external_services: "external services",
      input_types: "input types",
      output_types: "output types",
    },
  },
  fi: {
    sections: {
      blueprint_version: "Blueprintin versio",
      metadata: "Metatiedot",
      use_case: "Käyttötapaus",
      business_spec: "Liiketoiminnan vaatimukset",
      technical_spec: "Tekniset vaatimukset",
      target_output_spec: "Tavoiteltu tulos",
      assumptions: "Oletukset",
      artifacts: "Dataobjektit",
      inputs: "Syötteet",
      outputs: "Tulokset",
      schemas: "Skeemat",
      components: "Komponentit",
      workflow: "Työnkulku",
      business_process: "Liiketoimintaprosessi",
      prompts: "Kehotteet",
      models: "Mallit",
      validation: "Validointi",
      evaluation: "Arviointi",
      governance: "Hallinta",
      runtime: "Ajoympäristö",
      package: "Paketti",
      visualizations: "Visualisoinnit",
      traceability: "Jäljitettävyys",
      change_log: "Muutosloki",
    },
    items: {
      "workflow.steps": "Vaihe {n}",
      assumptions: "Oletus {n}",
      traceability: "Jälki {n}",
      change_log: "Muutos {n}",
      "business_process.participants": "Kaista {n}",
      "business_process.manual_steps": "Käsin tehtävä vaihe {n}",
      "business_process.external_parties": "Ulkopuolinen osapuoli {n}",
      "business_process.message_flows": "Viestivirta {n}",
      "business_process.exceptions": "Polku {n}",
      "business_process.decision_points": "Päätös {n}",
      "business_process.decision_points.branches": "haara {n}",
      "components.selected_modules": "Moduuli {n}",
      "components.selected_building_blocks": "Rakennuspalikka {n}",
      "components.custom_components": "Oma komponentti {n}",
      "technical_spec.external_services": "Ulkoinen palvelu {n}",
    },
    entries: {
      artifacts: 'Dataobjekti "{id}"',
    },
    fields: {
      id: "tunniste",
      name: "nimi",
      label: "nimi",
      type: "tyyppi",
      description: "kuvaus",
      domain: "toimiala",
      knowledge_processes: "tietoprosessit",
      component: "komponentti",
      inputs: "syötteet",
      outputs: "tulokset",
      parameters: "asetukset",
      depends_on: "tulee jälkeen",
      loop: "silmukka",
      max_iterations: "kierroksia enintään",
      loop_condition_ref: "silmukan ehto",
      performed_by: "kaista",
      steps: "vaiheet",
      source: "lähde",
      optional: "valinnainen",
      final_output: "lopputulos",
      externally_visible: "näkyy ulos",
      produced_by: "tuottaja",
      schema_ref: "skeema",
      overwrite: "korvaa",
      kind: "laji",
      default_lane_for: "kaista vaihetyypeille",
      participants: "kaistat",
      manual_steps: "käsin tehtävät vaiheet",
      external_parties: "ulkopuoliset osapuolet",
      message_flows: "viestivirrat",
      exceptions: "polut",
      decision_points: "päätökset",
      consumes: "käyttää",
      produces: "tuottaa",
      sends: "lähettää",
      to_step: "vaiheeseen",
      from: "mistä",
      from_: "mistä",
      to: "mihin",
      attached_to: "vaihe, jolla polku on",
      condition: "ehto",
      outcome: "polun jatko",
      after: "tulee jälkeen",
      branches: "haarat",
      target: "johtaa",
      text: "teksti",
      status: "tila",
      impact: "vaikutus",
      recorded_by: "kirjaaja",
      recorded_at: "kirjattu",
      selected_modules: "moduulit",
      selected_building_blocks: "rakennuspalikat",
      custom_components: "omat komponentit",
      reason: "peruste",
      data_handling: "tietojen käsittely",
      external_model_api_allowed: "ulkoinen malli-API sallittu",
      local_processing_required: "paikallinen käsittely vaaditaan",
      stores_input_data: "tallentaa syötteet",
      stores_outputs: "tallentaa tulokset",
      retention_policy: "säilytysaika",
      contains_personal_data: "sisältää henkilötietoja",
      output_sensitivity: "tulosten luottamuksellisuus",
      audit_log_required: "audit-loki vaaditaan",
      interface: "käyttöliittymä",
      entrypoint: "käynnistyspiste",
      env_file: "ympäristötiedosto",
      blueprint_id: "blueprintin tunniste",
      created_by: "luoja",
      created_at: "luotu",
      last_updated_at: "päivitetty viimeksi",
      output_dir: "tuloskansio",
      include_tests: "mukana testit",
      include_evals: "mukana arvioinnit",
      include_docs: "mukana dokumentaatio",
      required_by: "tarvitsija",
      version: "versio",
      date: "päivä",
      change: "muutos",
      changed_by: "muuttaja",
      external_services: "ulkoiset palvelut",
      input_types: "syötteiden tyypit",
      output_types: "tulosten tyypit",
    },
  },
};

/** Sections whose keys are the user's own (a model's name, a prompt's): kept as written. */
const FREE_FORM: ReadonlySet<string> = new Set([
  "business_spec",
  "target_output_spec",
  "inputs",
  "outputs",
  "schemas",
  "prompts",
  "models",
  "validation",
  "evaluation",
  "visualizations",
]);

const has = (words: Record<string, string>, key: string) => Object.prototype.hasOwnProperty.call(words, key);

/** `workflow.steps[3].depends_on` and pydantic's `workflow.steps.3.depends_on` alike, as segments. */
function pathSegments(path: string): string[] {
  return path
    .replace(/\[(\d+)\]/g, ".$1")
    .split(".")
    .filter((s) => s !== "");
}

/**
 * A blueprint path in plain words, for a refused save of the full draft
 * (wizard_api's `field`) and the full blueprint view's section titles:
 * `workflow.steps[3].depends_on` is "Step 4: comes after" ("Vaihe 4: tulee
 * jälkeen"). A path outside the blueprint's sections is returned as written;
 * inside one, what has no words (a model's own key) is kept as written.
 */
export function fieldName(path: string, locale: Locale): string {
  const words = PATH_WORDS[locale] ?? PATH_WORDS.en;
  const segments = pathSegments(path);
  const section = segments[0];
  if (section === undefined || !has(words.sections, section)) return path;
  const freeForm = FREE_FORM.has(section);
  // The items named so far (Decision 2, branch 1), and the fields after the last of them.
  const items: string[] = [];
  let tail: string[] = [words.sections[section]];
  // The list or map the next segment is in, without indexes: `business_process.decision_points.branches`.
  let at = section;
  for (const segment of segments.slice(1)) {
    if (/^\d+$/.test(segment)) {
      const n = String(Number(segment) + 1);
      if (!freeForm && has(words.items, at)) {
        items.push(words.items[at].replace("{n}", n));
        tail = [];
      } else {
        tail[tail.length - 1] = `${tail[tail.length - 1] ?? ""} [${n}]`.trim();
      }
      continue;
    }
    if (has(words.entries, at)) {
      items.push(words.entries[at].replace("{id}", segment));
      tail = [];
      at = `${at}.*`;
      continue;
    }
    const known = !freeForm && has(words.fields, segment);
    tail.push(known ? words.fields[segment] : segment);
    at = `${at}.${segment}`;
  }
  const head = items.length > 0 ? items.join(", ") : tail.shift();
  return tail.length > 0 ? `${head}: ${tail.join(" › ")}` : (head ?? path);
}
