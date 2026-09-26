import importlib.util

collect_ignore = []
if importlib.util.find_spec("frappe") is None:
    collect_ignore.append("test_integration.py")
