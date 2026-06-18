"""Antivirus scanner."""

import json
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

class Antivirus:
    def __init__(self):
        self.signatures = []
        self._load_signatures()

    def _load_signatures(self):
        """Load signatures from governance.json."""
        try:
            governance_path = Path(__file__).resolve().parents[4] / "governance.json"
            with governance_path.open("r") as f:
                data = json.load(f)
            self.signatures = data.get("signatures", [])
        except Exception as e:
            logger.warning(f"Failed to load signatures: {e}")
            self.signatures = []

    def scan(self, file_path: Path) -> bool:
        """
        Scan a file for known malware signatures.
        Returns True if clean, False if malware detected.
        """
        try:
            content = file_path.read_bytes()
            for sig in self.signatures:
                if sig.encode() in content:
                    logger.info(f"Malware signature detected: {sig}")
                    return False
            return True
        except Exception as e:
            logger.error(f"Error scanning {file_path}: {e}")
            return True