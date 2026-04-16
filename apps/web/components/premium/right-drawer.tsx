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
  widthClassName = "w-full sm:max-w-xl",
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
            "fixed inset-y-0 right-0 z-50 h-full max-w-full overflow-y-auto overscroll-contain border-l border-stone-200 bg-white p-4 shadow-2xl sm:p-5 lg:p-6",
            widthClassName,
          )}
        >
          <div className="sticky top-0 z-10 -mx-4 mb-4 border-b border-stone-200 bg-white/95 px-4 pb-3 pt-1 backdrop-blur sm:-mx-5 sm:px-5 lg:-mx-6 lg:px-6">
            <div className="flex items-start justify-between gap-3">
              <div>
                <Dialog.Title className="text-lg font-semibold text-stone-900">{title}</Dialog.Title>
                {description ? <Dialog.Description className="text-sm text-stone-600">{description}</Dialog.Description> : null}
              </div>
              <Dialog.Close className="rounded-md p-2 text-stone-500 transition hover:bg-stone-100 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/30">
                <X size={16} />
              </Dialog.Close>
            </div>
          </div>
          <div>{children}</div>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}
