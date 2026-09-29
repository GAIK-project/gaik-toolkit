"use client";

import {
  Accordion,
  AccordionContent,
  AccordionItem,
  AccordionTrigger,
} from "@/components/ui/accordion";
import type { ReactNode } from "react";

/** One collapsed section that opens with a height animation. */
export function Disclosure({
  label,
  children,
}: {
  label: string;
  children: ReactNode;
}) {
  return (
    <Accordion type="single" collapsible>
      <AccordionItem value="item" className="border-b-0">
        <AccordionTrigger className="text-muted-foreground hover:text-foreground w-fit flex-none items-center gap-1.5 py-1 font-normal hover:no-underline">
          {label}
        </AccordionTrigger>
        <AccordionContent>
          <div className="pt-2">{children}</div>
        </AccordionContent>
      </AccordionItem>
    </Accordion>
  );
}
