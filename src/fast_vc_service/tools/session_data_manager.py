from loguru import logger
from typing import Dict, Optional, List
import base64
import gzip
import zipfile
from pathlib import Path
import io
from datetime import datetime


class SessionDataManager:
    """Manager for session data files.
    
    including searching, zipping, and encoding.
    """
    
    def __init__(self, outputs_dir: str = "outputs"):
        self.outputs_dir = Path(outputs_dir)
    
    def find_session_files(self, 
                           session_id: str, 
                           date_hint: str = None) -> List[Path]:
        """
        retrieve all files related to a specific session_id within the outputs directory.
        
        Args:
            session_id: session ID to search for
            date_hint: optional date hint in the format '2025-06-11' to narrow down the search
        """
        session_files = []
        
        if date_hint:
            folder_date = self._convert_date_to_folder_path(date_hint)
            search_path = self.outputs_dir / folder_date if folder_date else self.outputs_dir
        else:
            search_path = self.outputs_dir
        logger.info(f"{session_id} | Searching path: {search_path}")
        
        if not search_path.exists():
            logger.warning(f"{session_id} | Directory does not exist: {search_path}")
            return session_files
        
        pattern = f"**/{session_id}*"
        
        matches = list(search_path.glob(pattern))
        for file_path in matches:
            if file_path.is_file():
                session_files.append(file_path)
        logger.info(f"{session_id} | Found {len(session_files)} files: {session_files}")
        
        return session_files
    
    def _convert_date_to_folder_path(self, date_str: str) -> Optional[str]:
        """ Convert a date string in the format 'YYYY-MM-DD' to a folder path format 'YYYY/M/D'."""
        try:
            date_obj = datetime.strptime(date_str, "%Y-%m-%d")
            return f"{date_obj.year}/{date_obj.month}/{date_obj.day}"
        except ValueError as e:
            logger.error(f"Invalid date format {date_str}, expected YYYY-MM-DD: {e}")
            return None

    def create_session_zip(self, session_id: str, date_hint: Optional[str] = None) -> bytes:
        """create a ZIP file containing all files related to a specific session_id
        """
        session_files = self.find_session_files(session_id, date_hint)
        
        if not session_files:
            raise Exception(f"No files found for session ID: {session_id}")
        
        # create a ZIP file in memory
        zip_buffer = io.BytesIO()
        
        with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED, compresslevel=9) as zip_file:
            for file_path in session_files:
                if file_path.exists():
                    archive_name = f"{session_id}_{file_path.name}"
                    zip_file.write(file_path, archive_name)
        
        zip_data = zip_buffer.getvalue()
        logger.info(f"{session_id} | Created ZIP, size: {len(zip_data)} bytes")
        return zip_data
    
    def encode(self, session_id: str, date_hint: Optional[str] = None) -> str:
        """Create session ZIP and encode it to base64 string (ZIP -> GZIP -> Base64)
        """
        zip_data = self.create_session_zip(session_id, date_hint)
        compressed = gzip.compress(zip_data, compresslevel=9)
        encoded = base64.b64encode(compressed).decode('utf-8')
        logger.info(f"{session_id} | Encoded to: {len(encoded)} chars")
        return encoded
    
    def decode(self, encoded_data: str, output_path: str) -> Dict[str, str]:
        """
        Decode compressed session data and save files to specified path
        
        Args:
            encoded_data: Base64 encoded compressed session data
            output_path: Directory path where files should be extracted
            
        Returns:
            Dict mapping original filenames to saved file paths
        """
        try:
            compressed = base64.b64decode(encoded_data.encode('utf-8'))
            zip_data = gzip.decompress(compressed)
            
            output_dir = Path(output_path)
            output_dir.mkdir(parents=True, exist_ok=True)
            
            saved_files = {}
            with zipfile.ZipFile(io.BytesIO(zip_data), 'r') as zip_file:
                
                for file_info in zip_file.filelist:
                    file_content = zip_file.read(file_info.filename)
                    file_path = output_dir / file_info.filename
            
                    with open(file_path, 'wb') as f:
                        f.write(file_content)
                    
                    saved_files[file_info.filename] = str(file_path)
                    logger.info(f"Saved file: {file_info.filename} -> {file_path}")
            
            logger.info(f"Successfully decoded and saved {len(saved_files)} files to {output_path}")
            return saved_files
            
        except Exception as e:
            logger.error(f"Failed to decode and save session data: {e}")
            raise
        
if __name__ == "__main__":
    # Example usage
    manager = SessionDataManager()
    
    # encode
    # session_id = "client0_5ad8c298"
    # # date_hint = "2025-06-11"
    # encoded_data = manager.encode(session_id)    
    # print(encoded_data)
        
    # decode
    encoded_data_path = "/root/autodl-tmp/fast-vc-service/dd"
    with open(encoded_data_path, "r") as f:
        encoded_data = f.read().strip()
    saved_files = manager.decode(encoded_data, "outputs/decoded_session")
    print(f"Saved files: {saved_files}")