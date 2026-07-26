import React from "react";
import ReactDOM from "react-dom/client";
import { BrowserRouter } from "react-router-dom";

import App from "./App.jsx";
import { AuthProvider } from "./context/AuthContext.jsx";
import { FileProvider } from "./context/FileContext.jsx";
import { NetworkDatasetProvider } from "./context/NetworkDatasetContext.jsx";
import "./index.css";

ReactDOM.createRoot(document.getElementById("root")).render(
  <React.StrictMode>
    <BrowserRouter>
      <AuthProvider>
        <FileProvider>
          <NetworkDatasetProvider>
            <App />
          </NetworkDatasetProvider>
        </FileProvider>
      </AuthProvider>
    </BrowserRouter>
  </React.StrictMode>
);
