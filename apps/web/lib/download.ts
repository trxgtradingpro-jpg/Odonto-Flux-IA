export function triggerBlobDownload(blob: Blob, filename: string) {
  const url = window.URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = filename;
  anchor.style.display = "none";
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();

  // Some browsers may produce empty/corrupted downloads if the object URL
  // is revoked immediately after the click event.
  window.setTimeout(() => {
    window.URL.revokeObjectURL(url);
  }, 60_000);
}
