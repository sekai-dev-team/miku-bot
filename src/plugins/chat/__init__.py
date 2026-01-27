from nonebot import get_plugin_config
from .config import Config

# Load Plugin Config
plugin_config = get_plugin_config(Config)

# Register Matchers by importing handlers
from .handlers import admin
from .handlers import user
from .handlers import events
from .handlers import chat

# Optional: expose critical components if other plugins need them
# but for now, this is enough to make the plugin work.
