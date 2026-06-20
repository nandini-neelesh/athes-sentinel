import { createContext, useContext, useEffect, useMemo, useState } from "react";

import { getLogFiles } from "../api/logs.js";

const FileContext = createContext(null);
const SELECTED_FILE_STORAGE_KEY = "athes_selected_file_id";

export function FileProvider({ children }) {
  const [logFiles, setLogFiles] = useState([]);
  const [selectedFileId, setSelectedFileIdState] = useState(() => {
    const storedFileId = localStorage.getItem(SELECTED_FILE_STORAGE_KEY);

    if (!storedFileId) {
      return null;
    }

    return Number(storedFileId);
  });
  const [isLoadingFiles, setIsLoadingFiles] = useState(false);
  const [fileError, setFileError] = useState("");

  async function loadLogFiles() {
    setIsLoadingFiles(true);
    setFileError("");

    try {
      const files = await getLogFiles();
      const sortedFiles = [...files].sort((firstFile, secondFile) => {
        return secondFile.id - firstFile.id;
      });

      setLogFiles(sortedFiles);

      setSelectedFileIdState((currentFileId) => {
        if (currentFileId && sortedFiles.some((file) => file.id === currentFileId)) {
          return currentFileId;
        }

        if (sortedFiles.length > 0) {
          return sortedFiles[0].id;
        }

        return null;
      });
    } catch (error) {
      const detail = error.response?.data?.detail;
      setFileError(detail || "Could not load uploaded log files.");
    } finally {
      setIsLoadingFiles(false);
    }
  }

  function setSelectedFileId(fileId) {
    if (!fileId) {
      setSelectedFileIdState(null);
      return;
    }

    setSelectedFileIdState(Number(fileId));
  }

  useEffect(() => {
    loadLogFiles();
  }, []);

  useEffect(() => {
    if (selectedFileId) {
      localStorage.setItem(SELECTED_FILE_STORAGE_KEY, String(selectedFileId));
    } else {
      localStorage.removeItem(SELECTED_FILE_STORAGE_KEY);
    }
  }, [selectedFileId]);

  const value = useMemo(
    () => ({
      logFiles,
      selectedFileId,
      isLoadingFiles,
      fileError,
      loadLogFiles,
      setSelectedFileId,
    }),
    [logFiles, selectedFileId, isLoadingFiles, fileError]
  );

  return <FileContext.Provider value={value}>{children}</FileContext.Provider>;
}

export function useFileContext() {
  const context = useContext(FileContext);

  if (!context) {
    throw new Error("useFileContext must be used inside FileProvider");
  }

  return context;
}
