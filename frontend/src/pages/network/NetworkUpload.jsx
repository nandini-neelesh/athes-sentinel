import { Link } from "react-router-dom";

import { NetworkPageScaffold } from "./NetworkOverview.jsx";

export default function NetworkUpload() {
  return (
    <NetworkPageScaffold
      eyebrow="Network dataset ingestion"
      title="Upload Network Dataset"
      description="NSL-KDD-compatible upload support is connected at the API foundation; the detailed upload interface arrives in the next phase."
    >
      <p className="text-sm leading-6 text-[#849396]">
        This temporary page does not submit files yet. Return to the{" "}
        <Link
          className="font-semibold text-[#9cf0ff] hover:text-[#c3f5ff]"
          to="/network"
        >
          network overview
        </Link>{" "}
        or continue through the network workspace navigation.
      </p>
    </NetworkPageScaffold>
  );
}
