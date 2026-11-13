"use client";

import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import {
  HELPDESK_EXAMPLES,
  getHelpdeskExample,
} from "@/lib/helpdesk-chatbot/examples";
import { OWN_ID } from "@/lib/helpdesk-chatbot/own-knowledge";
import { Building2, FileUp, Laptop, type LucideIcon } from "lucide-react";
import { useState } from "react";
import { HelpdeskChat } from "./helpdesk-chat";
import { HelpdeskOwnData } from "./helpdesk-own-data";

const ICONS: Record<string, LucideIcon> = {
  "ai-hub": Building2,
  "it-hr": Laptop,
};

/**
 * One chat, three sources: two ready-made helpdesks and the visitor's own
 * documents. A ready-made helpdesk is open at first, so there is something to
 * ask straight away.
 */
export function HelpdeskDemo() {
  const [source, setSource] = useState<string>(HELPDESK_EXAMPLES[0].id);
  const example = getHelpdeskExample(source);

  return (
    <div className="space-y-4">
      <Tabs value={source} onValueChange={setSource}>
        <TabsList
          aria-label="Helpdesk"
          className="h-auto w-full flex-wrap justify-start gap-1 group-data-[orientation=horizontal]/tabs:h-auto sm:w-fit"
        >
          {HELPDESK_EXAMPLES.map((item) => {
            const Icon = ICONS[item.id] ?? Building2;
            return (
              <TabsTrigger
                key={item.id}
                value={item.id}
                className="h-10 flex-none justify-start gap-2 px-3 max-sm:w-full sm:h-9"
              >
                <Icon />
                {item.title}
              </TabsTrigger>
            );
          })}
          <TabsTrigger
            value={OWN_ID}
            className="h-10 flex-none justify-start gap-2 px-3 max-sm:w-full sm:h-9"
          >
            <FileUp />
            Your own documents
          </TabsTrigger>
        </TabsList>
      </Tabs>

      {/* A new key gives each helpdesk a fresh conversation. */}
      {example && <HelpdeskChat key={example.id} example={example} />}

      {/* Kept mounted, so added documents survive a look at an example. */}
      <div hidden={source !== OWN_ID}>
        <HelpdeskOwnData />
      </div>
    </div>
  );
}
