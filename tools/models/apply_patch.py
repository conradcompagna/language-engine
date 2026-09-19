import os
import zipfile
import shutil
from pathlib import Path


def apply_segmenter_patch(zip_path_str, target_dir_str):
    """
    Extracts files from a zip, backing up existing files with a .bak extension first.
    """
    zip_path = Path(zip_path_str)
    target_dir = Path(target_dir_str)

    if not zip_path.exists():
        print(f"Error: Patch zip not found at {zip_path}")
        return

    if not target_dir.exists():
        print(f"Error: Target directory not found at {target_dir}")
        return

    print(f"Processing patch: {zip_path.name}...")

    with zipfile.ZipFile(zip_path, "r") as zf:
        # Filter out directory entries from the zip
        files_to_extract = [m for m in zf.infolist() if not m.is_dir()]

        for member in files_to_extract:
            target_file = target_dir / member.filename

            # Ensure the subdirectories exist in the target
            target_file.parent.mkdir(parents=True, exist_ok=True)

            # If the file exists, back it up first
            if target_file.exists():
                backup_path = target_file.with_suffix(target_file.suffix + ".bak")
                print(f"Backing up: {member.filename} -> {backup_path.name}")
                shutil.copy2(target_file, backup_path)

            # Extract and replace the file
            try:
                zf.extract(member, target_dir)
                print(f"Successfully replaced: {member.filename}")
            except Exception as e:
                print(f"Error extracting {member.filename}: {e}")


if __name__ == "__main__":
    # Define paths based on your request
    PATCH_ZIP = r"C:\Users\conra\Desktop\universal\segmenter_reconnect_patch.zip"
    TARGET_ROOT = r"C:\Users\conra\Desktop\universal"  # Change this if your project files are in a different subfolder
    apply_segmenter_patch(PATCH_ZIP, TARGET_ROOT)
