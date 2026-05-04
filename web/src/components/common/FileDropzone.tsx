import CloudUploadOutlinedIcon from "@mui/icons-material/CloudUploadOutlined";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import FormHelperText from "@mui/material/FormHelperText";
import Stack from "@mui/material/Stack";
import Typography from "@mui/material/Typography";
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
    <Box>
      <Stack
        component="label"
        htmlFor={inputId}
        role="button"
        tabIndex={disabled ? -1 : 0}
        aria-disabled={disabled}
        aria-label={label}
        className={`mui-file-dropzone${isDragging ? " dragging" : ""}${disabled ? " disabled" : ""}`}
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
        <CloudUploadOutlinedIcon color={disabled ? "disabled" : "primary"} />
        <Typography fontWeight={800}>{label}</Typography>
        {helperText ? <Typography color="text.secondary">{helperText}</Typography> : null}
        <Button component="span" variant="outlined" disabled={disabled}>
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
      </Stack>
      {errorText ? <FormHelperText error>{errorText}</FormHelperText> : null}
    </Box>
  );
}
