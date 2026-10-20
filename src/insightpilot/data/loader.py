from pathlib import Path

import pandas as pd


SUPPORTED_SUFFIXES = {".csv", ".xlsx", ".xls"}


def load_dataset(path: str | Path) -> pd.DataFrame:
    """Đọc dataset CSV hoặc Excel vào một pandas DataFrame.
        
            Phát sinh:
                FileNotFoundError: Khi đường dẫn không tồn tại.
                ValueError: Khi định dạng tệp không được hỗ trợ.
            
        """
    file_path = Path(path)

    if not file_path.exists():
        raise FileNotFoundError(f"Dataset not found: {file_path}")

    if file_path.suffix.lower() not in SUPPORTED_SUFFIXES:
        raise ValueError(
            f"Unsupported file type: {file_path.suffix}. "
            f"Supported types: {sorted(SUPPORTED_SUFFIXES)}"
        )

    suffix = file_path.suffix.lower()
    if suffix == ".csv":
        return pd.read_csv(file_path)

    return pd.read_excel(file_path)
