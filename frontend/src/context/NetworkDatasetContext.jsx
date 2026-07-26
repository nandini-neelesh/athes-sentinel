import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";

import { getNetworkDatasets } from "../api/network.js";
import { useAuth } from "./AuthContext.jsx";

const NetworkDatasetContext = createContext(null);
const NETWORK_DATASET_STORAGE_KEY = "athes_network_dataset_id";

function getDatasetErrorMessage(error) {
  const detail = error.response?.data?.detail;

  if (typeof detail === "string") {
    return detail;
  }

  if (Array.isArray(detail)) {
    return detail
      .map((item) => item.msg || item.message || JSON.stringify(item))
      .join(", ");
  }

  if (detail) {
    return JSON.stringify(detail);
  }

  return "Could not load uploaded network datasets.";
}

function readPersistedDatasetId() {
  const storedDatasetId = localStorage.getItem(NETWORK_DATASET_STORAGE_KEY);

  if (!storedDatasetId) {
    return null;
  }

  const datasetId = Number(storedDatasetId);

  return Number.isInteger(datasetId) && datasetId > 0 ? datasetId : null;
}

export function NetworkDatasetProvider({ children }) {
  const { isAuthenticated, isLoading: isLoadingAuth } = useAuth();
  const [datasets, setDatasets] = useState([]);
  const [selectedDatasetId, setSelectedDatasetIdState] = useState(
    readPersistedDatasetId
  );
  const [isLoadingDatasets, setIsLoadingDatasets] = useState(false);
  const [datasetsError, setDatasetsError] = useState("");
  const datasetsRef = useRef([]);
  const isMountedRef = useRef(false);
  const requestSequenceRef = useRef(0);

  useEffect(() => {
    isMountedRef.current = true;

    return () => {
      isMountedRef.current = false;
      requestSequenceRef.current += 1;
    };
  }, []);

  const clearNetworkState = useCallback(() => {
    requestSequenceRef.current += 1;
    datasetsRef.current = [];
    setDatasets([]);
    setSelectedDatasetIdState(null);
    setIsLoadingDatasets(false);
    setDatasetsError("");
    localStorage.removeItem(NETWORK_DATASET_STORAGE_KEY);
  }, []);

  const refreshDatasets = useCallback(async (preferredDatasetId = null) => {
    if (isLoadingAuth || !isAuthenticated) {
      return [];
    }

    const requestSequence = requestSequenceRef.current + 1;
    requestSequenceRef.current = requestSequence;
    setIsLoadingDatasets(true);
    setDatasetsError("");

    try {
      const response = await getNetworkDatasets();
      const nextDatasets = Array.isArray(response?.items) ? response.items : [];

      if (
        !isMountedRef.current ||
        requestSequenceRef.current !== requestSequence
      ) {
        return nextDatasets;
      }

      datasetsRef.current = nextDatasets;
      setDatasets(nextDatasets);
      setSelectedDatasetIdState((currentDatasetId) => {
        const persistedDatasetId = readPersistedDatasetId();
        const requestedDatasetId = Number(preferredDatasetId);
        const preferredSelection =
          Number.isInteger(requestedDatasetId) && requestedDatasetId > 0
            ? requestedDatasetId
            : currentDatasetId || persistedDatasetId;
        const selectionStillExists = nextDatasets.some(
          (dataset) => dataset.id === preferredSelection
        );

        if (selectionStillExists) {
          return preferredSelection;
        }

        localStorage.removeItem(NETWORK_DATASET_STORAGE_KEY);
        return nextDatasets[0]?.id ?? null;
      });

      return nextDatasets;
    } catch (error) {
      if (
        isMountedRef.current &&
        requestSequenceRef.current === requestSequence
      ) {
        setDatasetsError(getDatasetErrorMessage(error));
      }

      return [];
    } finally {
      if (
        isMountedRef.current &&
        requestSequenceRef.current === requestSequence
      ) {
        setIsLoadingDatasets(false);
      }
    }
  }, [isAuthenticated, isLoadingAuth]);

  useEffect(() => {
    if (isLoadingAuth) {
      return;
    }

    if (!isAuthenticated) {
      clearNetworkState();
      return;
    }

    refreshDatasets();
  }, [
    clearNetworkState,
    isAuthenticated,
    isLoadingAuth,
    refreshDatasets,
  ]);

  useEffect(() => {
    if (selectedDatasetId) {
      localStorage.setItem(
        NETWORK_DATASET_STORAGE_KEY,
        String(selectedDatasetId)
      );
    } else if (!isLoadingAuth) {
      localStorage.removeItem(NETWORK_DATASET_STORAGE_KEY);
    }
  }, [isLoadingAuth, selectedDatasetId]);

  const setSelectedDatasetId = useCallback(
    (datasetId, knownDataset = null) => {
      if (!datasetId) {
        setSelectedDatasetIdState(null);
        return;
      }

      const numericDatasetId = Number(datasetId);
      let selectionExists = datasetsRef.current.some(
        (dataset) => dataset.id === numericDatasetId
      );

      if (
        !selectionExists &&
        knownDataset &&
        Number(knownDataset.id) === numericDatasetId
      ) {
        const nextDatasets = [
          knownDataset,
          ...datasetsRef.current.filter(
            (dataset) => dataset.id !== numericDatasetId
          ),
        ];
        datasetsRef.current = nextDatasets;
        setDatasets(nextDatasets);
        selectionExists = true;
      }

      setSelectedDatasetIdState(selectionExists ? numericDatasetId : null);
    },
    []
  );

  const selectedDataset = useMemo(
    () =>
      datasets.find((dataset) => dataset.id === selectedDatasetId) || null,
    [datasets, selectedDatasetId]
  );

  const value = useMemo(
    () => ({
      datasets,
      selectedDatasetId,
      selectedDataset,
      isLoadingDatasets,
      datasetsError,
      setSelectedDatasetId,
      refreshDatasets,
    }),
    [
      datasets,
      datasetsError,
      isLoadingDatasets,
      refreshDatasets,
      selectedDataset,
      selectedDatasetId,
      setSelectedDatasetId,
    ]
  );

  return (
    <NetworkDatasetContext.Provider value={value}>
      {children}
    </NetworkDatasetContext.Provider>
  );
}

export function useNetworkDataset() {
  const context = useContext(NetworkDatasetContext);

  if (!context) {
    throw new Error(
      "useNetworkDataset must be used inside NetworkDatasetProvider"
    );
  }

  return context;
}
