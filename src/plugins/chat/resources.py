from pathlib import Path
from nonebot import logger

class ResourceManager:
    _instance = None
    _manual_content = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(ResourceManager, cls).__new__(cls)
        return cls._instance

    @staticmethod
    def get_common_resource_path(filename: str) -> Path:
        """
        Get the path to a resource file in src/common/resources/
        """
        # src/plugins/chat/resources.py -> src/common/resources/
        current_dir = Path(__file__).parent
        return current_dir.parent.parent / "common" / "resources" / filename

    def load_resource(self, filename: str) -> str:
        try:
            path = self.get_common_resource_path(filename)
            if path.exists():
                return path.read_text(encoding="utf-8")
            else:
                logger.error(f"Resource file not found: {path}")
                return f"Error: {filename} not found."
        except Exception as e:
            logger.error(f"Failed to load resource {filename}: {e}")
            return f"Error loading {filename}."

    def get_manual_content(self) -> str:
        if self._manual_content is None:
            self._manual_content = self.load_resource("manual.md")
        return self._manual_content

    def update_manual_content(self, content: str) -> None:
        path = self.get_common_resource_path("manual.md")
        path.write_text(content, encoding="utf-8")
        self._manual_content = content

resource_manager = ResourceManager()
