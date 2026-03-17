import {
  Accordion,
  AccordionContent,
  AccordionItem,
  AccordionTrigger,
} from "@/components/ui/accordion";
import { Card } from "@/components/ui/card";
import type { ReactNode } from "react";

interface HowItWorksCardProps {
  description?: string;
  children: ReactNode;
}

export function HowItWorksCard({ description, children }: HowItWorksCardProps) {
  return (
    <Card>
      <Accordion type="single" collapsible className="w-full">
        <AccordionItem value="how-it-works" className="border-none">
          <AccordionTrigger className="px-6 py-4 text-left hover:no-underline">
            <div>
              <span className="text-base font-semibold">How It Works</span>
              {description && (
                <p className="text-muted-foreground mt-1 text-sm font-normal">
                  {description}
                </p>
              )}
            </div>
          </AccordionTrigger>
          <AccordionContent className="px-6 pb-6">
            <div className="text-muted-foreground space-y-3 text-sm leading-6">
              {children}
            </div>
          </AccordionContent>
        </AccordionItem>
      </Accordion>
    </Card>
  );
}
