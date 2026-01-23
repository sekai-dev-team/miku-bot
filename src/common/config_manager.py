import yaml
from pathlib import Path
from typing import Any, Dict, Optional
from nonebot import logger

# Try to find the config file in typical locations
# 1. Environment variable (optional, skip for now)
# 2. Current Working Directory (for Docker /app/plugin_configs.yaml)
# 3. Relative to this file (fallback)

CONFIG_FILENAME = "plugin_configs.yaml"

class ConfigManager:
    _instance = None
    _config_data: Dict[str, Any] = {}
    _config_path: Path = Path(CONFIG_FILENAME)

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(ConfigManager, cls).__new__(cls)
            cls._instance._locate_config()
            cls._instance.load_config()
        return cls._instance

    def _locate_config(self):
        """Locates the configuration file."""
        # Search paths priority:
        # 1. CWD/configs/plugin_configs.yaml (Docker volume mount /app/configs)
        # 2. CWD/plugin_configs.yaml (Docker root mount)
        # 3. Project Root/plugin_configs.yaml (Dev env)
        
        search_paths = [
            Path.cwd() / "configs" / CONFIG_FILENAME,
            Path.cwd() / CONFIG_FILENAME,
        ]

        # Check relative to src/common (dev env fallback)
        current_file = Path(__file__).resolve()
        project_root = current_file.parent.parent.parent
        search_paths.append(project_root / CONFIG_FILENAME)
        
        for path in search_paths:
            if path.exists():
                self._config_path = path
                return
            
        logger.warning(f"Config file {CONFIG_FILENAME} not found in searched paths: {[str(p) for p in search_paths]}. Defaulting to CWD/configs/ path.")
        self._config_path = Path.cwd() / "configs" / CONFIG_FILENAME

    def load_config(self):
        """Loads the YAML configuration file."""
        if self._config_path.exists():
            try:
                with open(self._config_path, "r", encoding="utf-8") as f:
                    self._config_data = yaml.safe_load(f) or {}
                logger.info(f"Loaded configuration from {self._config_path.absolute()}")
            except Exception as e:
                logger.error(f"Failed to load configuration: {e}")
                # Don't clear old config on failure, might be better to keep stale than empty? 
                # For now, let's keep stale if load fails, or empty if init.
                if not self._config_data:
                    self._config_data = {}
        else:
            logger.warning(f"Configuration file not found at {self._config_path.absolute()}. Using empty defaults.")
            self._config_data = {}

    def get_config(self, module_name: str) -> Dict[str, Any]:
        """Returns the configuration dict for a specific module."""
        return self._config_data.get(module_name, {})

    def save_config(self, module_name: str, data: Dict[str, Any]):
        """Updates a module's config and saves to disk."""
        self._config_data[module_name] = data
        try:
            with open(self._config_path, "w", encoding="utf-8") as f:
                yaml.dump(self._config_data, f, allow_unicode=True, default_flow_style=False)
            logger.info(f"Saved configuration to {self._config_path}")
        except Exception as e:
            logger.error(f"Failed to save configuration: {e}")

    def reload(self):
        """Reloads the configuration from disk."""
        logger.info("Reloading configuration...")
        self.load_config()

# Global Instance
config_manager = ConfigManager()
