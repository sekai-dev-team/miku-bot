import re
from pathlib import Path
from nonebot.log import logger

def load_menu_structure():
    """Parses the help_menu.md file to build the menu structure."""
    # src/plugins/chat/help_menu.py -> src/common/resources/help_menu.md
    current_dir = Path(__file__).parent
    resource_path = current_dir.parent.parent / "common" / "resources" / "help_menu.md"
    
    if not resource_path.exists():
        logger.error(f"Help menu file not found: {resource_path}")
        return []
    
    try:
        content = resource_path.read_text(encoding="utf-8")
        
        # Regex to find headers like "# 1. Name"
        # We capture ID, Name, and the Start Position
        matches = list(re.finditer(r"^# (\d+)\. (.*)$", content, re.MULTILINE))
        
        structure = []
        for i, match in enumerate(matches):
            item_id = match.group(1)
            name = match.group(2).strip()
            
            # Content starts after the header line
            start_pos = match.end()
            # Content ends at the start of the next header, or end of file
            end_pos = matches[i+1].start() if i + 1 < len(matches) else len(content)
            
            body = content[start_pos:end_pos].strip()
            
            # Parse Description (Expected format: "Description: ...")
            desc = ""
            details = body
            
            # Split into lines to find description
            lines = body.split('\n', 1)
            if lines and lines[0].startswith("Description:"):
                desc = lines[0].replace("Description:", "").strip()
                # The rest is details
                details = lines[1].strip() if len(lines) > 1 else ""
            
            structure.append({
                "id": item_id,
                "name": name,
                "desc": desc,
                "details": details
            })
            
        return structure
        
    except Exception as e:
        logger.error(f"Failed to parse help menu: {e}")
        return []

def get_main_menu_text() -> str:
    menu_structure = load_menu_structure()
    if not menu_structure:
        return "⚠️ 帮助菜单加载失败，请联系管理员检查资源文件。"

    msg = "✨ **Miku 功能导航** ✨\n------------------\n请发送 `/help <序号>` 查看详情：\n\n"
    for item in menu_structure:
        msg += f"{item['id']}. {item['name']}\n   └ {item['desc']}\n"
    msg += "\n💡 例：发送 `/help 2` 查看新闻功能"
    return msg

def get_plugin_help_text(query: str) -> str:
    menu_structure = load_menu_structure()
    for item in menu_structure:
        # Match ID or partial Name
        if query == item['id'] or query in item['name']:
            return item['details']
    return None
