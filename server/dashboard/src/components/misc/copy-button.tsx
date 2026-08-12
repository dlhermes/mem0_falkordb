import { useState } from "react";

import { CheckIcon, CopyIcon } from "@radix-ui/react-icons";
import { CopyToClipboard } from "react-copy-to-clipboard";

interface CopyButtonProps {
  textToCopy: string;
  label?: string;
  className?: string;
}

const CopyButton: React.FC<CopyButtonProps> = ({
  textToCopy,
  label,
  className = "",
}) => {
  const [copied, setCopied] = useState(false);

  const handleCopy = () => {
    setCopied(true);
    setTimeout(() => {
      setCopied(false);
    }, 2000);
  };

  return (
    <CopyToClipboard text={textToCopy} onCopy={handleCopy}>
      <button
        type="button"
        className={
          label
            ? `inline-flex shrink-0 items-center gap-1 rounded-md border border-memBorder-primary bg-surface-default-primary px-2 py-1 text-xs text-onSurface-default-secondary hover:bg-surface-default-primary-hover ${className}`
            : `absolute top-2 right-2 bg-surface-default-primary hover:bg-surface-default-primary-hover p-2 text-onSurface-default-secondary rounded-md border border-memBorder-primary ${className}`
        }
      >
        {copied ? (
          <CheckIcon className="size-3" />
        ) : (
          <CopyIcon className="size-3" />
        )}
        {label && <span>{copied ? "已复制" : label}</span>}
      </button>
    </CopyToClipboard>
  );
};

export default CopyButton;
