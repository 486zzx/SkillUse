"""pytest 配置：将 scripts 目录加入 path，便于导入脚本模块；可选加载 .env。"""
from pathlib import Path
import sys

# 优先加载 skill 根目录下的 .env，使 Cursor 新 shell 或 CI 也能拿到 JUHE_TRAIN_API_KEY
_root = Path(__file__).resolve().parent.parent
try:
    from dotenv import load_dotenv
    load_dotenv(_root / ".env")
except ImportError:
    pass

_scripts = _root / "scripts"
if str(_scripts) not in sys.path:
    sys.path.insert(0, str(_scripts))
