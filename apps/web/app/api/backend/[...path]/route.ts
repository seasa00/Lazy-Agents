import { proxy } from '@/lib/api/proxy';
export const dynamic = 'force-dynamic';
export const runtime = 'nodejs';
async function forward(
  request: Request,
  context: { params: Promise<{ path: string[] }> },
) {
  const { path } = await context.params;
  return proxy(request, path.join('/'));
}
export const GET = forward;
export const POST = forward;
