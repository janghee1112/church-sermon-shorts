import { ShortsEditorPage } from "@/components/editor/ShortsEditorPage";

export default async function EditorRoute({ params }: { params: Promise<{ draftId: string }> }) {
  const { draftId } = await params;
  return <ShortsEditorPage draftId={Number(draftId)} />;
}
