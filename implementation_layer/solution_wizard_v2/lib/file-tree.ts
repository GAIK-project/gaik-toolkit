/**
 * Paths as the folders and files a zip opens into: the PoC tab shows the
 * deployment package this way, so the list reads like the download.
 */

export type FileTreeNode =
  | { kind: "folder"; name: string; path: string; children: FileTreeNode[] }
  | { kind: "file"; name: string; path: string };

// Case aside, character by character, as the zip orders its names: "." before
// "_", so output_schema.json comes before output_schema_requirements.json.
const byName = (a: FileTreeNode, b: FileTreeNode) => {
  const [x, y] = [a.name.toLowerCase(), b.name.toLowerCase()];
  return x < y ? -1 : x > y ? 1 : a.name < b.name ? -1 : a.name > b.name ? 1 : 0;
};

/** Folders before files at every level, each in name order, as a file manager lists them. */
export function fileTree(paths: readonly string[]): FileTreeNode[] {
  type Folder = { folders: Map<string, Folder>; files: Set<string> };
  const root: Folder = { folders: new Map(), files: new Set() };
  for (const path of paths) {
    const parts = path.split("/").filter(Boolean);
    // A name ending in "/" is a folder, as a zip lists one.
    const name = path.endsWith("/") ? null : parts.pop();
    let at = root;
    for (const part of parts) {
      let next = at.folders.get(part);
      if (!next) {
        next = { folders: new Map(), files: new Set() };
        at.folders.set(part, next);
      }
      at = next;
    }
    if (name) at.files.add(name);
  }
  const nodes = (folder: Folder, prefix: string): FileTreeNode[] => [
    ...[...folder.folders]
      .map(([name, sub]): FileTreeNode => ({
        kind: "folder",
        name,
        path: `${prefix}${name}`,
        children: nodes(sub, `${prefix}${name}/`),
      }))
      .sort(byName),
    ...[...folder.files].map((name): FileTreeNode => ({ kind: "file", name, path: `${prefix}${name}` })).sort(byName),
  ];
  return nodes(root, "");
}
