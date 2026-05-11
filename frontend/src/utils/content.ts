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
    try {
      const jsonified = raw
        .replace(/datetime\.datetime\([^)]+\)/g, (match) => {
          const numbers = match.match(/\d+/g);
          if (numbers && numbers.length >= 3) {
            const [year, month, day, hour = '0', minute = '0', second = '0'] = numbers;
            return `"${year}-${month.padStart(2, '0')}-${day.padStart(2, '0')}T${hour.padStart(2, '0')}:${minute.padStart(2, '0')}:${second.padStart(2, '0')}"`;
          }
          return `"${match}"`;
        })
        .replace(/'/g, '"')
        .replace(/\bTrue\b/g, 'true')
        .replace(/\bFalse\b/g, 'false')
        .replace(/\bNone\b/g, 'null');
      return JSON.stringify(JSON.parse(jsonified), null, 2);
    } catch {
      return raw;
    }
  }
}

export function convertFrameworkContentItems(items: Array<Record<string, unknown>> | undefined): ContentItem[] {
  if (!Array.isArray(items)) return [];

  const converted: ContentItem[] = [];
  for (const item of items) {
    if (item.type === 'text') {
      converted.push({ type: 'text', text: (item.text as string) || '' });
    } else if (item.type === 'data') {
      const uri = (item.uri as string) || '';
      if (uri.startsWith('data:image/')) {
        const commaIndex = uri.indexOf(',');
        const header = uri.slice(0, commaIndex);
        const data = uri.slice(commaIndex + 1);
        const mimeType = header.split(';')[0].replace('data:', '');
        if (data && mimeType) {
          converted.push({ type: 'image', data, mimeType });
        }
      }
    } else if (item.type === 'image' && item.data && item.mimeType) {
      converted.push(item as unknown as ContentItem);
    }
  }
  return converted;
}