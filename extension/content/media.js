// Reads media that WhatsApp has already loaded in the page. No clicks, no downloads.
(() => {
  'use strict';
  const NS = (globalThis.EcQuote = globalThis.EcQuote || {});

  const MAX_BYTES = 15 * 1024 * 1024;
  const EXTENSIONS = { 'image/jpeg': 'jpg', 'image/png': 'png', 'image/webp': 'webp', 'application/pdf': 'pdf' };

  async function fetchBlob(url) {
    const response = await fetch(url);
    if (!response.ok) throw new Error('fetch_failed');
    return response.blob();
  }

  // Fallback: redraw the loaded <img> (same-origin blob, so the canvas is not tainted).
  function imageToBlob(img) {
    return new Promise((resolve, reject) => {
      if (!img || !img.naturalWidth) return reject(new Error('not_loaded'));
      const canvas = document.createElement('canvas');
      canvas.width = img.naturalWidth;
      canvas.height = img.naturalHeight;
      canvas.getContext('2d').drawImage(img, 0, 0);
      canvas.toBlob((blob) => (blob ? resolve(blob) : reject(new Error('encode_failed'))), 'image/png');
    });
  }

  // attachment: { type, name, src, el } from the reader. Returns { blob, fileName }.
  async function readAttachment(attachment) {
    if (!attachment || !attachment.src || !attachment.src.startsWith('blob:')) throw new Error('unavailable');
    let blob;
    try {
      blob = await fetchBlob(attachment.src);
    } catch (error) {
      if (attachment.type !== 'image') throw error;
      blob = await imageToBlob(attachment.el);
    }
    if (!blob.size) throw new Error('empty');
    if (blob.size > MAX_BYTES) throw new Error('too_large');
    const extension = EXTENSIONS[blob.type] || (attachment.type === 'image' ? 'jpg' : 'bin');
    const fileName = attachment.name || `${attachment.type === 'image' ? 'imagine' : 'document'}.${extension}`;
    return { blob, fileName };
  }

  function blobToBase64(blob) {
    return new Promise((resolve, reject) => {
      const reader = new FileReader();
      reader.onerror = () => reject(new Error('read_failed'));
      reader.onload = () => resolve(String(reader.result).split(',', 2)[1] || '');
      reader.readAsDataURL(blob);
    });
  }

  function base64ToBlob(base64, mime) {
    const binary = atob(base64);
    const bytes = new Uint8Array(binary.length);
    for (let i = 0; i < binary.length; i += 1) bytes[i] = binary.charCodeAt(i);
    return new Blob([bytes], { type: mime });
  }

  // Clipboard images must be PNG.
  async function toPng(blob) {
    if (blob.type === 'image/png') return blob;
    const bitmap = await createImageBitmap(blob);
    const canvas = document.createElement('canvas');
    canvas.width = bitmap.width;
    canvas.height = bitmap.height;
    canvas.getContext('2d').drawImage(bitmap, 0, 0);
    bitmap.close?.();
    return new Promise((resolve, reject) => {
      canvas.toBlob((png) => (png ? resolve(png) : reject(new Error('encode_failed'))), 'image/png');
    });
  }

  NS.Media = { MAX_BYTES, readAttachment, blobToBase64, base64ToBlob, toPng };
})();
