"use client";

import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Play, Upload } from "lucide-react";
import { useRef, useState, type ComponentType } from "react";

export type Choice = "example" | "create";

export interface UseCaseChooserProps {
  /** Which way is open at first: the built-in example, so the demo opens ready to try. */
  initialChoice?: Choice;
  exampleLabel?: string;
  exampleDescription: string;
  createLabel?: string;
  createDescription: string;
  /** Shown when the example is open. `onCreate` switches to the other section. */
  ExampleSection: ComponentType<{ onCreate: () => void }>;
  CreateSection: ComponentType;
}

/**
 * The two ways into a demo as one switch: the built-in example, or the user's own
 * data. Both labels stay in view, so neither section hides the other, and one line
 * under the switch says what the open one does.
 */
export function UseCaseChooser({
  initialChoice = "example",
  exampleLabel = "Built-in example",
  exampleDescription,
  createLabel = "Your own data",
  createDescription,
  ExampleSection,
  CreateSection,
}: UseCaseChooserProps) {
  const [open, setOpen] = useState<Choice>(initialChoice);
  const rootRef = useRef<HTMLDivElement>(null);

  const openCreate = () => {
    setOpen("create");
    requestAnimationFrame(() =>
      rootRef.current?.scrollIntoView({ behavior: "smooth", block: "start" }),
    );
  };

  return (
    <Tabs
      ref={rootRef}
      value={open}
      onValueChange={(value) => setOpen(value as Choice)}
      className="scroll-mt-24 gap-4 pt-2"
    >
      <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:gap-4">
        <TabsList
          aria-label="What would you like to do?"
          className="grid h-10 w-full grid-cols-2 sm:inline-flex sm:w-fit"
        >
          <TabsTrigger value="example" className="gap-2 px-4">
            <Play aria-hidden />
            {exampleLabel}
          </TabsTrigger>
          <TabsTrigger value="create" className="gap-2 px-4">
            <Upload aria-hidden />
            {createLabel}
          </TabsTrigger>
        </TabsList>
        <p className="text-muted-foreground text-sm">
          {open === "example" ? exampleDescription : createDescription}
        </p>
      </div>
      <TabsContent value="example">
        <ExampleSection onCreate={openCreate} />
      </TabsContent>
      <TabsContent value="create">
        <CreateSection />
      </TabsContent>
    </Tabs>
  );
}
