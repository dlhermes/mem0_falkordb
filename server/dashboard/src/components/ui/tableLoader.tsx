import React from "react";
import { Loader2 } from "lucide-react";

export const renderLoader = (
  condition: boolean,
  className: string = "",
  showLoader: boolean = true,
) => {
  if (condition) {
    return (
      <div
        className={`flex justify-center items-center size-full absolute opacity-80 bg-surface-default-primary min-h-full ${className}`}
      >
        {showLoader && (
          <Loader2 className="animate-spin size-7 text-onSurface-default-secondary" />
        )}
      </div>
    );
  }
  return null;
};
