import datetime
from typing import List, Dict, Any

def calculate_next_retry_time(
    base_time_str: str, 
    policy: str, 
    interval: int, 
    attempt: int
) -> str:
    """
    Calculates the next schedule time based on the retry policy.
    - Fixed: base_time + interval
    - Linear: base_time + (interval * attempt)
    - Exponential: base_time + (interval * 2^(attempt - 1))
    """
    base_time = datetime.datetime.strptime(base_time_str, "%Y-%m-%d %H:%M:%S")
    
    if policy == "Fixed":
        delay = interval
    elif policy == "Linear":
        delay = interval * attempt
    elif policy == "Exponential":
        delay = interval * (2 ** (attempt - 1))
    else:
        delay = interval
        
    next_time = base_time + datetime.timedelta(seconds=delay)
    return next_time.strftime("%Y-%m-%d %H:%M:%S")

def format_table(headers: List[str], rows: List[List[Any]]) -> str:
    """Generates a text-based table with clean borders and column sizing."""
    if not headers:
        return ""
    
    # Stringify all elements
    str_rows = [[str(item) for item in row] for row in rows]
    
    # Determine column widths
    col_widths = [len(h) for h in headers]
    for row in str_rows:
        for idx, val in enumerate(row):
            if idx < len(col_widths):
                col_widths[idx] = max(col_widths[idx], len(val))
            else:
                col_widths.append(len(val))
                
    # Create border strings
    border_line = "+" + "+".join("-" * (w + 2) for w in col_widths) + "+"
    
    output = []
    output.append(border_line)
    
    # Headers row
    header_row = "|" + "|".join(f" {headers[i].ljust(col_widths[i])} " for i in range(len(headers))) + "|"
    output.append(header_row)
    output.append(border_line)
    
    # Data rows
    for row in str_rows:
        # Fill missing values if row is shorter
        while len(row) < len(headers):
            row.append("")
        row_str = "|" + "|".join(f" {row[i].ljust(col_widths[i])} " for i in range(len(headers))) + "|"
        output.append(row_str)
        
    output.append(border_line)
    return "\n".join(output)

def get_current_time_str() -> str:
    """Returns current system time in standard format YYYY-MM-DD HH:MM:SS."""
    return datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
