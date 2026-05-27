import React from "react";
import ReactDOM from "react-dom/client";

import { EventStudyPage } from "@/pages/EventStudyPage";
import "@/styles.css";

ReactDOM.createRoot(document.getElementById("root") as HTMLElement).render(
  <React.StrictMode>
    <EventStudyPage />
  </React.StrictMode>,
);
