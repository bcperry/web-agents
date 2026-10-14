import type { ContentItem, ToolInvocation } from '../types/api';

export const ALLOWED_IMAGE_MIMES = new Set(['image/jpeg', 'image/png', 'image/gif', 'image/webp']);

export type ImageContentItem = Extract<ContentItem, { type: 'image' }>;

export function isSupportedImageItem(item: ContentItem): item is ImageContentItem {
  return item.type === 'image' && ALLOWED_IMAGE_MIMES.has(item.mimeType);
}

export function imageDataUri(item: ImageContentItem): string {
  return `data:${item.mimeType};base64,${item.data}`;
}

export function toolImages(invocation: ToolInvocation): ImageContentItem[] {
  return (invocation.content_items ?? []).filter(isSupportedImageItem);
}

export function hasToolImages(invocations: ToolInvocation[] | undefined): boolean {
  return Boolean(invocations?.some((invocation) => toolImages(invocation).length > 0));
}

export function formatToolResult(raw: string): string {
  try {
    return JSON.stringify(JSON.parse(raw), null, 2);
  } catch {
    return raw;
  }
}
