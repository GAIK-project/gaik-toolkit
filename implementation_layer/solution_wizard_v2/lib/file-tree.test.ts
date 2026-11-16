import { describe, expect, it } from "vitest";
import { fileTree, type FileTreeNode } from "./file-tree";

/** The tree as indented lines, folders ending in "/". */
function lines(nodes: FileTreeNode[], depth = 0): string[] {
  return nodes.flatMap((node) => [
    `${"  ".repeat(depth)}${node.name}${node.kind === "folder" ? "/" : ""}`,
    ...(node.kind === "folder" ? lines(node.children, depth + 1) : []),
  ]);
}

describe("fileTree", () => {
  it("opens the deployment package's names into its folders, folders first, in name order", () => {
    const tree = fileTree([
      "poc/run_poc.py",
      "poc/schemas/output_schema.py",
      "poc/.env.example",
      "poc/README.md",
      "poc/evals/ground_truth/.gitkeep",
      "poc/evals/run_basic_eval.py",
      "poc/AI-GENERATED.json",
      "poc/schemas/output_schema_requirements.json",
      "poc/schemas/output_schema.json",
    ]);
    expect(lines(tree)).toEqual([
      "poc/",
      "  evals/",
      "    ground_truth/",
      "      .gitkeep",
      "    run_basic_eval.py",
      "  schemas/",
      "    output_schema.json",
      "    output_schema.py",
      "    output_schema_requirements.json",
      "  .env.example",
      "  AI-GENERATED.json",
      "  README.md",
      "  run_poc.py",
    ]);
  });

  it("keeps each node's full path, and files beside a folder at the top", () => {
    const tree = fileTree(["poc/run_poc.py", "workflow.bpmn", "docs/user_guide.md"]);
    expect(lines(tree)).toEqual(["docs/", "  user_guide.md", "poc/", "  run_poc.py", "workflow.bpmn"]);
    const docs = tree[0];
    expect(docs.kind === "folder" && docs.children[0].path).toBe("docs/user_guide.md");
  });

  it("lists a name once, skips empty paths and reads a name ending in / as a folder", () => {
    expect(lines(fileTree(["poc/a.py", "poc/a.py", "", "poc/"]))).toEqual(["poc/", "  a.py"]);
    expect(lines(fileTree(["poc/output/"]))).toEqual(["poc/", "  output/"]);
  });
});
