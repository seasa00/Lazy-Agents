import { Workspace } from '@/features/workspace/Workspace';
export default async function Page({
  params,
}: {
  params: Promise<{ projectId: string }>;
}) {
  const { projectId } = await params;
  return <Workspace key={projectId} id={projectId} />;
}
