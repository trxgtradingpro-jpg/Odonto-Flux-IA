"use client";

import * as Dialog from "@radix-ui/react-dialog";
import { X } from "lucide-react";

import { cn } from "@odontoflux/ui";

export function RightDrawer({
  open,
  onOpenChange,
  title,
  description,
  children,
  widthClassName = "w-full max-w-xl",
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  title: string;
  description?: string;
  children: React.ReactNode;
  widthClassName?: string;
}) {
  return (
    <Dialog.Root open={open} onOpenChange={onOpenChange}>
      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 z-40 bg-black/40 backdrop-blur-[1px]" />
        <Dialog.Content
          className={cn(
            "fixed right-0 top-0 z-50 h-full overflow-y-auto border-l border-stone-200 bg-white p-5 shadow-2xl",
            widthClassName,
          )}
        >
          <div className="mb-4 flex items-start justify-between gap-3">
            <div>
              <Dialog.Title className="text-lg font-semibold text-stone-900">{title}</Dialog.Title>
              {description ? <Dialog.Description className="text-sm text-stone-600">{description}</Dialog.Description> : null}
            </div>
            <Dialog.Close className="rounded-md p-2 text-stone-500 hover:bg-stone-100">
              <X size={16} />
            </Dialog.Close>
          </div>
          <div>{children}</div>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}
