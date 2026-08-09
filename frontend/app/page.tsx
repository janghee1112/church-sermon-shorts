"use client";

import { useEffect, useState } from "react";
import { getCandidates, getProject, getTranscript, startAnalysis, uploadProject } from "@/lib/api";
import type { CandidateResults, Project, Transcript } from "@/types";
import { UploadPanel } from "@/components/UploadPanel";
import { ProgressPanel } from "@/components/ProgressPanel";
import { VideoWorkspace } from "@/components/VideoWorkspace";
import { clearProjectStorage, PROJECT_STORAGE_KEY } from "@/lib/projectStorage";

export default function Home() {
  const [project, setProject] = useState<Project | null>(null);
  const [transcript, setTranscript] = useState<Transcript | null>(null);
  const [results, setResults] = useState<CandidateResults | null>(null);
  const [uploading, setUploading] = useState(false);
  const [uploadProgress, setUploadProgress] = useState(0);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const saved = window.localStorage.getItem(PROJECT_STORAGE_KEY);
    if (!saved) return;
    getProject(saved).then(setProject).catch(clearProjectStorage);
  }, []);

  useEffect(() => {
    if (!project || project.status === "completed" || project.status === "failed" || project.status === "uploaded") return;
    const timer = window.setInterval(() => {
      getProject(project.project_id).then(setProject).catch((reason: unknown) => setError(reason instanceof Error ? reason.message : "상태를 확인하지 못했습니다."));
    }, 1500);
    return () => window.clearInterval(timer);
  }, [project]);

  useEffect(() => {
    if (project?.status !== "completed") return;
    Promise.all([getTranscript(project.project_id), getCandidates(project.project_id)])
      .then(([nextTranscript, nextResults]) => { setTranscript(nextTranscript); setResults(nextResults); })
      .catch((reason: unknown) => setError(reason instanceof Error ? reason.message : "결과를 불러오지 못했습니다."));
  }, [project?.project_id, project?.status]);

  async function handleUpload(file: File) {
    setUploading(true); setError(null); setUploadProgress(0);
    try {
      const created = await uploadProject(file, setUploadProgress);
      window.localStorage.setItem(PROJECT_STORAGE_KEY, created.project_id);
      setProject(await startAnalysis(created.project_id));
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "업로드에 실패했습니다.");
    } finally { setUploading(false); }
  }

  async function retry() {
    if (!project) return;
    setProject(await startAnalysis(project.project_id));
  }

  function reset() {
    clearProjectStorage();
    setProject(null); setTranscript(null); setResults(null); setError(null); setUploadProgress(0);
  }

  if (project?.status === "completed" && transcript && results) return <VideoWorkspace project={project} transcript={transcript} results={results} onNewProject={reset} />;
  if (project) return <ProgressPanel project={project} onRetry={retry} />;
  return <UploadPanel busy={uploading} progress={uploadProgress} error={error} onSubmit={handleUpload} />;
}
