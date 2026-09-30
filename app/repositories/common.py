def like_pattern(term: str) -> str:
    """Шаблон для ILIKE с экранированием спецсимволов (%, _, \\). Использовать с escape='\\\\'."""
    escaped = term.strip().replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{escaped}%"


LIKE_ESCAPE = "\\"
