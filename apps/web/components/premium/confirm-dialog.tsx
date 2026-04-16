"use client";

import * as Dialog from "@radix-ui/react-dialog";

import { Button } from "@odontoflux/ui";

export function ConfirmDialog({
  open,
  onOpenChange,
  title,
  description,
  confirmLabel = "Confirmar",
  cancelLabel = "Cancelar",
  onConfirm,
  loading,
  destructive,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  title: string;
  description: string;
  confirmLabel?: string;
  cancelLabel?: string;
  onConfirm: () => void;
  loading?: boolean;
  destructive?: boolean;
}) {
  return (
    <Dialog.Root open={open} onOpenChange={onOpenChange}>
      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 z-40 bg-black/40 backdrop-blur-[1px]" />
        <Dialog.Content className="fixed left-1/2 top-1/2 z-50 w-[92vw] max-w-md -translate-x-1/2 -translate-y-1/2 rounded-2xl border border-stone-200 bg-white p-5 shadow-2xl sm:p-6">
          <Dialog.Title className="text-lg font-semibold text-stone-900">{title}</Dialog.Title>
          <Dialog.Description className="mt-1 text-sm leading-relaxed text-stone-600">{description}</Dialog.Description>
          <div className="mt-5 flex flex-wrap justify-end gap-2 max-sm:[&>*]:w-full">
            <Dialog.Close asChild>
              <Button variant="outline">{cancelLabel}</Button>
            </Dialog.Close>
            <Button variant={destructive ? "destructive" : "default"} onClick={onConfirm} disabled={loading}>
              {loading ? "Processando..." : confirmLabel}
            </Button>
          </div>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}
