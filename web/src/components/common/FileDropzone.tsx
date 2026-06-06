import { Button } from "@heroui/react";
import { useId, useRef, useState } from "react";

type FileDropzoneProps = {
  label?: string;
  helperText?: string;
  errorText?: string | null;
  accept?: string;
  multiple?: boolean;
  disabled?: boolean;
  onFiles: (files: File[]) => void;
};

export default function FileDropzone({
  label = "选择文件",
  helperText,
  errorText,
  accept,
  multiple = true,
  disabled = false,
  onFiles,
}: FileDropzoneProps) {
  const inputId = useId();
  const inputRef = useRef<HTMLInputElement | null>(null);
  const [isDragging, setIsDragging] = useState(false);

  const emitFiles = (fileList: FileList | null) => {
    if (!fileList || disabled) {
      return;
    }
    onFiles(Array.from(fileList));
  };

  return (
    <div className="finance-file-dropzone-field">
      <label
        htmlFor={inputId}
        role="button"
        tabIndex={disabled ? -1 : 0}
        aria-disabled={disabled}
        aria-label={label}
        className={`finance-file-dropzone${isDragging ? " finance-file-dropzone--dragging" : ""}${disabled ? " finance-file-dropzone--disabled" : ""}`}
        onDragEnter={(event) => {
          event.preventDefault();
          if (!disabled) {
            setIsDragging(true);
          }
        }}
        onDragOver={(event) => event.preventDefault()}
        onDragLeave={() => setIsDragging(false)}
        onDrop={(event) => {
          event.preventDefault();
          setIsDragging(false);
          emitFiles(event.dataTransfer.files);
        }}
        onKeyDown={(event) => {
          if (disabled) {
            return;
          }
          if (event.key === "Enter" || event.key === " ") {
            event.preventDefault();
            inputRef.current?.click();
          }
        }}
      >
        <span aria-hidden="true" className="finance-file-dropzone__icon">
          ↑
        </span>
        <span className="finance-file-dropzone__label">{label}</span>
        {helperText ? <span className="finance-file-dropzone__helper">{helperText}</span> : null}
        <Button className="finance-file-dropzone__browse" isDisabled={disabled} variant="outline">
          浏览文件
        </Button>
        <input
          ref={inputRef}
          id={inputId}
          className="import-file-input"
          accept={accept}
          disabled={disabled}
          multiple={multiple}
          type="file"
          onChange={(event) => {
            emitFiles(event.currentTarget.files);
            event.currentTarget.value = "";
          }}
        />
      </label>
      {errorText ? (
        <p className="finance-file-dropzone__error" role="alert">
          {errorText}
        </p>
      ) : null}
    </div>
  );
}
