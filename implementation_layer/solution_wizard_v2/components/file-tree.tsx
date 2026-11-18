import { FileIcon } from "@/components/file-icon";
import { Icon } from "@/components/icons";
import { fileTree, type FileTreeNode } from "@/lib/file-tree";

/**
 * Paths drawn as the folders and files they open into, the way a zip shows
 * them: every folder open, its contents under a guide line. Plain nested
 * lists, so a screen reader announces each folder's count and depth.
 */
export function FileTree({
  paths,
  testId,
  open,
}: {
  paths: readonly string[];
  testId?: string;
  /**
   * Makes the files that can be opened buttons: `canOpen` says which, `onOpen`
   * is given the path, and `label` names the button ("{name}" is the file).
   */
  open?: FileOpener;
}) {
  return (
    <ul className="font-mono text-xs text-text-muted" data-testid={testId}>
      {fileTree(paths).map((node) => (
        <Node key={node.path} node={node} open={open} />
      ))}
    </ul>
  );
}

export type FileOpener = {
  canOpen: (path: string) => boolean;
  onOpen: (path: string) => void;
  label: string;
};

function Node({ node, open }: { node: FileTreeNode; open?: FileOpener }) {
  if (node.kind === "file") {
    if (open?.canOpen(node.path)) {
      return (
        <li data-path={node.path}>
          <button
            type="button"
            onClick={() => open.onOpen(node.path)}
            title={open.label.replace("{name}", node.path)}
            className="flex max-w-full cursor-pointer items-center gap-1.5 rounded-sm py-px text-left text-text-secondary underline-offset-2 transition-colors hover:text-brand-text hover:underline"
            data-testid="file-tree-open"
          >
            <FileIcon name={node.name} size={13} />
            <span className="min-w-0 truncate">{node.name}</span>
          </button>
        </li>
      );
    }
    return (
      <li className="flex items-center gap-1.5 py-px" title={node.path} data-path={node.path}>
        <FileIcon name={node.name} size={13} />
        <span className="min-w-0 truncate">{node.name}</span>
      </li>
    );
  }
  return (
    <li data-path={`${node.path}/`}>
      <span className="flex items-center gap-1.5 py-px text-text-secondary" title={`${node.path}/`}>
        <Icon name="folderOpen" size={13} className="shrink-0 text-text-muted" />
        <span className="min-w-0 truncate">{node.name}/</span>
      </span>
      <ul className="ml-[6px] border-l border-border pl-3">
        {node.children.map((child) => (
          <Node key={child.path} node={child} open={open} />
        ))}
      </ul>
    </li>
  );
}
