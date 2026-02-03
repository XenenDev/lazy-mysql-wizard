import os
import json
import threading
import tkinter as tk
from tkinter import ttk, scrolledtext, messagebox, simpledialog, font
import mysql.connector
from mysql.connector import Error
from openai import OpenAI
from dotenv import load_dotenv
import re
import ctypes

# Enable DPI awareness for sharper text on high-DPI displays (Windows)
try:
    ctypes.windll.shcore.SetProcessDpiAwareness(2)  # PROCESS_PER_MONITOR_DPI_AWARE
except:
    try:
        ctypes.windll.user32.SetProcessDPIAware()  # Fallback for older Windows
    except:
        pass

# Load environment variables (Create a .env file with these keys)
load_dotenv()

# --- CONFIGURATION ---
DB_CONFIG = {
    'host': os.getenv("DB_HOST"),
    'user': os.getenv("DB_USER"),
    'password': os.getenv("DB_PASS"), # Please rotate this password
    'database': os.getenv("DB_NAME"),
    'port': int(os.getenv("DB_PORT")),
    'ssl_disabled': False
}

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

OPENAI_MODEL_ID = os.getenv("OPENAI_MODEL_ID")

# Token pricing (cost per 1M tokens) - optional, set in .env if you want cost tracking
TOKEN_INPUT_PRICE_PER_M = float(os.getenv("TOKEN_INPUT_PRICE_PER_M")) if os.getenv("TOKEN_INPUT_PRICE_PER_M") else None
TOKEN_OUTPUT_PRICE_PER_M = float(os.getenv("TOKEN_OUTPUT_PRICE_PER_M")) if os.getenv("TOKEN_OUTPUT_PRICE_PER_M") else None

# --- STYLES ---
COLORS = {
    "bg": "#1e1e1e",
    "fg": "#d4d4d4",
    "entry_bg": "#252526",
    "border": "#3e3e42",
    "accent": "#007acc",
    "accent_hover": "#0098ff",
    "chat_user": "#264f78",
    "chat_ai": "#3e3e42",
    "success": "#4ec9b0",
    "warning": "#ce9178"
}

# --- DATABASE MANAGER ---
class DatabaseManager:
    def __init__(self, config):
        self.config = config
        self.schema_cache = ""

    def connect(self):
        try:
            # Handle SSL requirement logic if needed
            return mysql.connector.connect(**self.config)
        except Error as e:
            return None

    def get_schema_summary(self):
        """Fetches comprehensive database schema information to give the AI context."""
        conn = self.connect()
        if not conn:
            return "Error: Could not connect to database."
        
        schema_str = "=== DATABASE INFORMATION ===\n"
        try:
            cursor = conn.cursor()
            
            # Get MySQL version
            cursor.execute("SELECT VERSION()")
            version = cursor.fetchone()[0]
            schema_str += f"MySQL Version: {version}\n"
            
            # Get database name and default character set/collation
            cursor.execute("SELECT DATABASE()")
            db_name = cursor.fetchone()[0]
            cursor.execute(f"SELECT DEFAULT_CHARACTER_SET_NAME, DEFAULT_COLLATION_NAME FROM information_schema.SCHEMATA WHERE SCHEMA_NAME = '{db_name}'")
            charset_info = cursor.fetchone()
            if charset_info:
                schema_str += f"Database: {db_name}\n"
                schema_str += f"Default Character Set: {charset_info[0]}\n"
                schema_str += f"Default Collation: {charset_info[1]}\n"
            
            schema_str += "\n=== TABLES ===\n"
            
            # Get all tables
            cursor.execute("SHOW TABLES")
            tables = cursor.fetchall()
            
            for (table_name,) in tables:
                schema_str += f"\n--- Table: {table_name} ---\n"
                
                # Get table metadata (engine, collation, auto_increment, etc.)
                cursor.execute(f"""
                    SELECT ENGINE, TABLE_COLLATION, AUTO_INCREMENT, TABLE_ROWS, 
                           AVG_ROW_LENGTH, DATA_LENGTH, CREATE_TIME, UPDATE_TIME
                    FROM information_schema.TABLES 
                    WHERE TABLE_SCHEMA = '{db_name}' AND TABLE_NAME = '{table_name}'
                """)
                table_info = cursor.fetchone()
                if table_info:
                    schema_str += f"  Engine: {table_info[0]}\n"
                    schema_str += f"  Collation: {table_info[1]}\n"
                    if table_info[2]:
                        schema_str += f"  Auto Increment: {table_info[2]}\n"
                    schema_str += f"  Approx Rows: {table_info[3]}\n"
                
                # Get detailed column information
                cursor.execute(f"DESCRIBE {table_name}")
                columns = cursor.fetchall()
                schema_str += "  Columns:\n"
                for col in columns:
                    col_name, col_type, nullable, key, default, extra = col
                    col_desc = f"    - {col_name} ({col_type})"
                    if key == 'PRI':
                        col_desc += " PRIMARY KEY"
                    if key == 'MUL':
                        col_desc += " INDEXED"
                    if key == 'UNI':
                        col_desc += " UNIQUE"
                    if nullable == 'NO':
                        col_desc += " NOT NULL"
                    if default is not None:
                        col_desc += f" DEFAULT {default}"
                    if extra:
                        col_desc += f" {extra}"
                    schema_str += col_desc + "\n"
                
                # Get indexes
                cursor.execute(f"SHOW INDEX FROM {table_name}")
                indexes = cursor.fetchall()
                if indexes:
                    index_dict = {}
                    for idx in indexes:
                        idx_name = idx[2]
                        col_name = idx[4]
                        if idx_name not in index_dict:
                            index_dict[idx_name] = []
                        index_dict[idx_name].append(col_name)
                    
                    schema_str += "  Indexes:\n"
                    for idx_name, cols in index_dict.items():
                        if idx_name != 'PRIMARY':
                            schema_str += f"    - {idx_name} ({', '.join(cols)})\n"
                
                # Get foreign keys
                cursor.execute(f"""
                    SELECT CONSTRAINT_NAME, COLUMN_NAME, REFERENCED_TABLE_NAME, REFERENCED_COLUMN_NAME
                    FROM information_schema.KEY_COLUMN_USAGE
                    WHERE TABLE_SCHEMA = '{db_name}' 
                    AND TABLE_NAME = '{table_name}'
                    AND REFERENCED_TABLE_NAME IS NOT NULL
                """)
                foreign_keys = cursor.fetchall()
                if foreign_keys:
                    schema_str += "  Foreign Keys:\n"
                    for fk in foreign_keys:
                        schema_str += f"    - {fk[1]} -> {fk[2]}.{fk[3]}\n"
            
            conn.close()
            self.schema_cache = schema_str
            return schema_str
        except Error as e:
            return f"Error getting schema: {e}"

    def execute_query(self, query):
        """Executes a query and returns (columns, rows, error_message)."""
        conn = self.connect()
        if not conn:
            return None, None, "Connection failed."
        
        try:
            cursor = conn.cursor()
            cursor.execute(query)
            
            if cursor.description:
                # SELECT statement
                columns = [desc[0] for desc in cursor.description]
                rows = cursor.fetchall()
                conn.close()
                return columns, rows, None
            else:
                # INSERT/UPDATE/DELETE/DDL
                conn.commit()
                affected = cursor.rowcount
                conn.close()
                return ["Message"], [[f"Success. Rows affected: {affected}"]], None
        except Error as e:
            if conn: conn.close()
            return None, None, str(e)

# --- AI AGENT ---
class Agent:
    def __init__(self, db_manager: DatabaseManager, agency_level: int = 2):
        self.client = OpenAI(api_key=OPENAI_API_KEY)
        self.db = db_manager
        self.model = OPENAI_MODEL_ID
        self.history = []
        self.agency_level = agency_level
        self.system_prompt = self._get_system_prompt()
        # Token tracking
        self.total_input_tokens = 0
        self.total_output_tokens = 0
        # Initialize history with schema context
        self.refresh_context()
    
    def _get_system_prompt(self):
        """Generate system prompt based on agency level."""
        base = (
            "You are an expert Database Reliability Engineer and Data Analyst agent. "
            "Your goal is to assist the user with SQL queries and data analysis.\n"
            "GUIDELINES:\n"
            "1. **Context**: Remember previous questions.\n"
            "2. **Safety**: You have read/write access. Be careful. "
            "3. **Clarification**: If a request is ambiguous (e.g., 'fix the data'), do NOT guess. "
            "Call the `ask_user_clarification` tool.\n"
            "4. **Schema Awareness**: Use the provided schema to write accurate SQL.\n"
        )
        
        if self.agency_level == 1:
            return base + (
                "5. **AGENCY LEVEL 1 - Draft Only**: DO NOT execute queries automatically. "
                "Your role is to DRAFT SQL queries and explain them, but let the user run them manually. "
                "Only use `ask_user_clarification` tool when needed. Do NOT call `run_sql_query`.\n"
            )
        elif self.agency_level == 2:
            return base + (
                "5. **AGENCY LEVEL 2 - Moderate Autonomy**: Execute simple SELECT queries (1-2 steps). "
                "For complex investigations requiring multiple queries, draft the queries and ask user permission first. "
                "Be conservative and clarify when in doubt.\n"
            )
        else:  # Level 3
            return base + (
                "5. **AGENCY LEVEL 3 - Full Autonomy**: Conduct comprehensive investigations. "
                "Execute multiple queries as needed to fully answer user questions. "
                "Search through tables, analyze patterns, and provide detailed insights. "
                "Be proactive and thorough in your analysis.\n"
            )
    
    def set_agency_level(self, level: int):
        """Change the agency level and refresh context."""
        self.agency_level = level
        self.system_prompt = self._get_system_prompt()
        self.refresh_context()

    def refresh_context(self):
        schema = self.db.get_schema_summary()
        self.history = [
            {"role": "system", "content": f"{self.system_prompt}\n\n{schema}"}
        ]

    def chat(self, user_input, tool_handler_callback):
        """
        Main chat loop. 
        tool_handler_callback: function(tool_name, args) -> result
        """
        self.history.append({"role": "user", "content": user_input})

        try:
            # 1. First API Call (Thinking/Tool Selection)
            response = self.client.chat.completions.create(
                model=self.model,
                messages=self.history,
                tools=[
                    {
                        "type": "function",
                        "function": {
                            "name": "run_sql_query",
                            "description": "Execute a SQL query against the database.",
                            "parameters": {
                                "type": "object",
                                "properties": {
                                    "query": {"type": "string", "description": "Valid MySQL query."}
                                },
                                "required": ["query"]
                            }
                        }
                    },
                    {
                        "type": "function",
                        "function": {
                            "name": "ask_user_clarification",
                            "description": "Ask the user for more details if the request is ambiguous.",
                            "parameters": {
                                "type": "object",
                                "properties": {
                                    "question": {"type": "string", "description": "The question to ask the user."}
                                },
                                "required": ["question"]
                            }
                        }
                    }
                ],
                tool_choice="auto"
            )
            
            # Track token usage
            if hasattr(response, 'usage') and response.usage:
                self.total_input_tokens += response.usage.prompt_tokens
                self.total_output_tokens += response.usage.completion_tokens
            
            message = response.choices[0].message
            self.history.append(message)

            # 2. Check for Tool Calls
            if message.tool_calls:
                for tool_call in message.tool_calls:
                    func_name = tool_call.function.name
                    args = json.loads(tool_call.function.arguments)
                    
                    # Execute tool via callback (allows UI interception)
                    tool_result = tool_handler_callback(func_name, args)
                    
                    # Append tool result to history
                    self.history.append({
                        "role": "tool",
                        "tool_call_id": tool_call.id,
                        "content": str(tool_result)
                    })

                # 3. Follow-up API Call (Interpret Results)
                final_response = self.client.chat.completions.create(
                    model=self.model,
                    messages=self.history
                )
                
                # Track token usage
                if hasattr(final_response, 'usage') and final_response.usage:
                    self.total_input_tokens += final_response.usage.prompt_tokens
                    self.total_output_tokens += final_response.usage.completion_tokens
                
                final_msg = final_response.choices[0].message
                self.history.append(final_msg)
                return final_msg.content
            
            else:
                return message.content

        except Exception as e:
            return f"Agent Error: {str(e)}"

# --- MARKDOWN RENDERER ---
class MarkdownRenderer:
    """Renders markdown text into tkinter Text widget with tags."""
    
    @staticmethod
    def render(text_widget, markdown_text, base_tag="ai"):
        """Parse and render markdown text with formatting."""
        lines = markdown_text.split('\n')
        i = 0
        
        while i < len(lines):
            line = lines[i]
            
            # Check for table
            if '|' in line and i + 1 < len(lines) and '|' in lines[i + 1]:
                i = MarkdownRenderer._render_table(text_widget, lines, i)
                continue
            
            # Headers
            if line.startswith('#'):
                level = len(line) - len(line.lstrip('#'))
                text = line.lstrip('#').strip()
                text_widget.insert(tk.END, text + '\n', f"header{level}")
            # Code blocks
            elif line.startswith('```'):
                i, code_block = MarkdownRenderer._extract_code_block(lines, i)
                text_widget.insert(tk.END, code_block + '\n', "code_block")
            # Bullet points
            elif line.strip().startswith(('- ', '* ', '+ ')):
                text = line.strip()[2:]
                text_widget.insert(tk.END, '  • ', base_tag)
                MarkdownRenderer._render_inline(text_widget, text, base_tag)
                text_widget.insert(tk.END, '\n', base_tag)
            # Numbered lists
            elif re.match(r'^\d+\.\s', line.strip()):
                MarkdownRenderer._render_inline(text_widget, line.strip(), base_tag)
                text_widget.insert(tk.END, '\n', base_tag)
            # Regular text
            else:
                MarkdownRenderer._render_inline(text_widget, line, base_tag)
                text_widget.insert(tk.END, '\n', base_tag)
            
            i += 1
    
    @staticmethod
    def _render_inline(text_widget, text, base_tag):
        """Render inline formatting (bold, italic, code)."""
        pos = 0
        
        # Pattern: **bold**, *italic*, `code`
        pattern = r'(\*\*.*?\*\*)|(\*.*?\*)|(`.+?`)'
        
        for match in re.finditer(pattern, text):
            # Insert text before match
            if match.start() > pos:
                text_widget.insert(tk.END, text[pos:match.start()], base_tag)
            
            matched_text = match.group()
            if matched_text.startswith('**'):
                text_widget.insert(tk.END, matched_text[2:-2], "bold")
            elif matched_text.startswith('*'):
                text_widget.insert(tk.END, matched_text[1:-1], "italic")
            elif matched_text.startswith('`'):
                text_widget.insert(tk.END, matched_text[1:-1], "inline_code")
            
            pos = match.end()
        
        # Insert remaining text
        if pos < len(text):
            text_widget.insert(tk.END, text[pos:], base_tag)
    
    @staticmethod
    def _extract_code_block(lines, start_idx):
        """Extract code block content."""
        code_lines = []
        i = start_idx + 1
        while i < len(lines) and not lines[i].startswith('```'):
            code_lines.append(lines[i])
            i += 1
        return i, '\n'.join(code_lines)
    
    @staticmethod
    def _render_table(text_widget, lines, start_idx):
        """Render a markdown table."""
        table_lines = []
        i = start_idx
        
        # Collect table lines
        while i < len(lines) and '|' in lines[i]:
            table_lines.append(lines[i])
            i += 1
        
        if len(table_lines) < 2:
            return i
        
        # Parse table
        rows = []
        for line in table_lines:
            cells = [cell.strip() for cell in line.split('|')]
            cells = [c for c in cells if c]  # Remove empty cells
            rows.append(cells)
        
        # Skip separator row (second row)
        header = rows[0]
        data_rows = rows[2:] if len(rows) > 2 else []
        
        # Calculate column widths
        all_rows = [header] + data_rows
        col_widths = [max(len(str(row[i])) if i < len(row) else 0 for row in all_rows) 
                     for i in range(len(header))]
        
        # Render header
        text_widget.insert(tk.END, '\n', "table")
        header_line = '  '.join(str(header[i]).ljust(col_widths[i]) for i in range(len(header)))
        text_widget.insert(tk.END, header_line + '\n', "table_header")
        
        # Render separator
        separator = '  '.join('─' * col_widths[i] for i in range(len(header)))
        text_widget.insert(tk.END, separator + '\n', "table")
        
        # Render data rows
        for row in data_rows:
            row_line = '  '.join(str(row[i]).ljust(col_widths[i]) if i < len(row) else ' ' * col_widths[i] 
                                for i in range(len(header)))
            text_widget.insert(tk.END, row_line + '\n', "table")
        
        text_widget.insert(tk.END, '\n', "table")
        return i

# --- GUI ---
class ModernSQLApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("LAZY MYSQL WIZARD by XVP Technologies")
        self.geometry("1400x900")
        self.configure(bg=COLORS["bg"])
        
        # Init Subsystems
        self.db = DatabaseManager(DB_CONFIG)
        self.agency_level = tk.IntVar(value=2)  # Default to level 2
        self.agent = Agent(self.db, agency_level=2)
        
        self._setup_styles()
        self._build_layout()
        self._configure_text_tags()
        
        # Focus handling
        self.focus_force()

    def _setup_styles(self):
        style = ttk.Style(self)
        style.theme_use('clam')
        
        # General
        style.configure("TFrame", background=COLORS["bg"])
        style.configure("TLabel", background=COLORS["bg"], foreground=COLORS["fg"], font=("Segoe UI", 11))
        style.configure("TButton", background=COLORS["accent"], foreground="white", borderwidth=0, font=("Segoe UI", 10, "bold"))
        style.map("TButton", background=[("active", COLORS["accent_hover"])])
        
        # Treeview (Results)
        style.configure("Treeview", 
                        background=COLORS["entry_bg"], 
                        foreground=COLORS["fg"], 
                        fieldbackground=COLORS["entry_bg"],
                        borderwidth=0,
                        rowheight=25,
                        font=("Consolas", 10))
        style.configure("Treeview.Heading", background=COLORS["border"], foreground="white", relief="flat")
        style.map("Treeview", background=[("selected", COLORS["accent"])])

    def _build_layout(self):
        # Main Split: Left (Chat) vs Right (SQL + Results)
        main_pane = ttk.PanedWindow(self, orient=tk.HORIZONTAL)
        main_pane.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

        # --- LEFT: CHAT ---
        chat_frame = ttk.Frame(main_pane)
        main_pane.add(chat_frame, weight=1)
        
        # Agency Level Selector
        agency_toolbar = ttk.Frame(chat_frame)
        agency_toolbar.pack(fill=tk.X, pady=(0, 5))
        
        ttk.Label(agency_toolbar, text="AI Agency Level:").pack(side=tk.LEFT, padx=5)
        
        agency_frame = tk.Frame(agency_toolbar, bg=COLORS["bg"])
        agency_frame.pack(side=tk.LEFT, padx=5)
        
        level_descriptions = [
            (1, "Level 1: Draft Only"),
            (2, "Level 2: Moderate"),
            (3, "Level 3: Full Auto")
        ]
        
        for level, desc in level_descriptions:
            rb = tk.Radiobutton(
                agency_frame, text=desc, variable=self.agency_level, value=level,
                bg=COLORS["bg"], fg=COLORS["fg"], selectcolor=COLORS["entry_bg"],
                activebackground=COLORS["bg"], activeforeground=COLORS["accent"],
                font=("Segoe UI", 9), command=self.on_agency_change
            )
            rb.pack(side=tk.LEFT, padx=5)
        
        # Token Counter
        self.token_label = tk.Label(
            agency_toolbar, text="Tokens: In: 0 | Out: 0 | Cost: $0.00",
            bg=COLORS["bg"], fg=COLORS["success"], font=("Segoe UI", 9, "bold")
        )
        self.token_label.pack(side=tk.RIGHT, padx=10)
        
        # Chat History with improved font rendering
        chat_font = font.Font(family="Segoe UI", size=11)
        self.chat_display = scrolledtext.ScrolledText(
            chat_frame, bg=COLORS["entry_bg"], fg=COLORS["fg"], 
            font=chat_font, wrap=tk.WORD, borderwidth=0, padx=10, pady=10
        )
        self.chat_display.pack(fill=tk.BOTH, expand=True, pady=(0, 10))
        self.chat_display.config(state=tk.DISABLED)

        # Chat Input
        input_frame = ttk.Frame(chat_frame)
        input_frame.pack(fill=tk.X)
        
        self.chat_input = tk.Text(input_frame, height=3, bg=COLORS["entry_bg"], fg="white", 
                                  insertbackground="white", font=("Segoe UI", 11), borderwidth=1, relief="solid")
        self.chat_input.pack(side=tk.LEFT, fill=tk.X, expand=True)
        self.chat_input.bind("<Control-Return>", self.on_send_chat)

        send_btn = ttk.Button(input_frame, text="Send", command=self.on_send_chat)
        send_btn.pack(side=tk.RIGHT, padx=5, fill=tk.Y)

        # --- RIGHT: SQL & RESULTS ---
        right_pane = ttk.PanedWindow(main_pane, orient=tk.VERTICAL)
        main_pane.add(right_pane, weight=3)

        # SQL Editor
        sql_frame = ttk.Frame(right_pane)
        right_pane.add(sql_frame, weight=1)
        
        lbl_sql = ttk.Label(sql_frame, text="SQL Editor (Agent Drafts Here)")
        lbl_sql.pack(anchor="w", pady=5)
        
        self.sql_editor = scrolledtext.ScrolledText(
            sql_frame, bg=COLORS["entry_bg"], fg=COLORS["success"], 
            font=("Consolas", 12), insertbackground="white", height=10
        )
        self.sql_editor.pack(fill=tk.BOTH, expand=True)

        btn_toolbar = ttk.Frame(sql_frame)
        btn_toolbar.pack(fill=tk.X, pady=5)
        ttk.Button(btn_toolbar, text="Run SQL Manually", command=self.run_manual_sql).pack(side=tk.RIGHT)
        ttk.Button(btn_toolbar, text="Clear", command=lambda: self.sql_editor.delete("1.0", tk.END)).pack(side=tk.RIGHT, padx=5)

        # Results
        results_frame = ttk.Frame(right_pane)
        right_pane.add(results_frame, weight=3)
        
        self.tree = ttk.Treeview(results_frame, show='headings')
        vsb = ttk.Scrollbar(results_frame, orient="vertical", command=self.tree.yview)
        hsb = ttk.Scrollbar(results_frame, orient="horizontal", command=self.tree.xview)
        self.tree.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)
        
        self.tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        vsb.pack(side=tk.RIGHT, fill=tk.Y)
        hsb.pack(side=tk.BOTTOM, fill=tk.X)

    def _configure_text_tags(self):
        """Configure text tags for markdown rendering."""
        # User/AI message tags
        self.chat_display.tag_config("user", foreground="#ffffff", background=COLORS["chat_user"], 
                                     lmargin1=10, lmargin2=10, rmargin=50, spacing1=5, spacing3=5)
        self.chat_display.tag_config("ai", foreground="#ffffff", background=COLORS["chat_ai"], 
                                     lmargin1=10, lmargin2=10, rmargin=50, spacing1=5, spacing3=5)
        self.chat_display.tag_config("system", foreground=COLORS["warning"], 
                                     font=("Segoe UI", 10, "italic"))
        
        # Markdown formatting tags
        bold_font = font.Font(family="Segoe UI", size=11, weight="bold")
        italic_font = font.Font(family="Segoe UI", size=11, slant="italic")
        code_font = font.Font(family="Consolas", size=10)
        header1_font = font.Font(family="Segoe UI", size=16, weight="bold")
        header2_font = font.Font(family="Segoe UI", size=14, weight="bold")
        header3_font = font.Font(family="Segoe UI", size=12, weight="bold")
        
        self.chat_display.tag_config("bold", font=bold_font, foreground="#ffffff")
        self.chat_display.tag_config("italic", font=italic_font, foreground="#d4d4d4")
        self.chat_display.tag_config("inline_code", font=code_font, 
                                     background="#2d2d30", foreground="#ce9178")
        self.chat_display.tag_config("code_block", font=code_font, 
                                     background="#1e1e1e", foreground="#4ec9b0",
                                     lmargin1=20, lmargin2=20, spacing1=5, spacing3=5)
        
        # Headers
        self.chat_display.tag_config("header1", font=header1_font, foreground="#569cd6", spacing1=10, spacing3=5)
        self.chat_display.tag_config("header2", font=header2_font, foreground="#569cd6", spacing1=8, spacing3=4)
        self.chat_display.tag_config("header3", font=header3_font, foreground="#569cd6", spacing1=6, spacing3=3)
        
        # Table formatting
        table_font = font.Font(family="Consolas", size=10)
        self.chat_display.tag_config("table", font=table_font, foreground="#d4d4d4",
                                     lmargin1=20, lmargin2=20)
        self.chat_display.tag_config("table_header", font=font.Font(family="Consolas", size=10, weight="bold"),
                                     foreground="#4ec9b0", lmargin1=20, lmargin2=20)

    # --- LOGIC HANDLING ---

    def update_token_display(self):
        """Update the token counter display."""
        input_tokens = self.agent.total_input_tokens
        output_tokens = self.agent.total_output_tokens
        total_tokens = input_tokens + output_tokens
        
        # Calculate cost if pricing is configured
        if TOKEN_INPUT_PRICE_PER_M is not None and TOKEN_OUTPUT_PRICE_PER_M is not None:
            input_cost = (input_tokens / 1_000_000) * TOKEN_INPUT_PRICE_PER_M
            output_cost = (output_tokens / 1_000_000) * TOKEN_OUTPUT_PRICE_PER_M
            total_cost = input_cost + output_cost
            cost_text = f"${total_cost:.4f}"
        else:
            cost_text = "?"
        
        self.token_label.config(
            text=f"Tokens: In: {input_tokens:,} | Out: {output_tokens:,} | Cost: {cost_text}"
        )
    
    def on_agency_change(self):
        """Handle agency level change."""
        new_level = self.agency_level.get()
        self.agent.set_agency_level(new_level)
        
        level_names = {1: "Draft Only", 2: "Moderate", 3: "Full Auto"}
        self.append_chat("system", f"Agency level changed to {new_level}: {level_names[new_level]}")

    def append_chat(self, role, text):
        self.chat_display.config(state=tk.NORMAL)
        if role == "user":
            label_font = font.Font(family="Segoe UI", size=9, weight="bold")
            self.chat_display.insert(tk.END, "\n")
            self.chat_display.insert(tk.END, " YOU ", "user")
            self.chat_display.tag_config("user_label", font=label_font)
            self.chat_display.insert(tk.END, "\n")
            self.chat_display.insert(tk.END, f"{text}\n", "user")
        elif role == "agent":
            label_font = font.Font(family="Segoe UI", size=9, weight="bold")
            self.chat_display.insert(tk.END, "\n")
            self.chat_display.insert(tk.END, " AGENT ", "ai")
            self.chat_display.tag_config("ai_label", font=label_font)
            self.chat_display.insert(tk.END, "\n")
            # Render markdown for agent responses
            MarkdownRenderer.render(self.chat_display, text, "ai")
        elif role == "system":
            self.chat_display.insert(tk.END, f"[{text}]\n", "system")
        self.chat_display.see(tk.END)
        self.chat_display.config(state=tk.DISABLED)

    def on_send_chat(self, event=None):
        msg = self.chat_input.get("1.0", tk.END).strip()
        if not msg: return "break"
        
        self.chat_input.delete("1.0", tk.END)
        self.append_chat("user", msg)
        
        # Threading to prevent GUI freeze
        threading.Thread(target=self._run_agent_thread, args=(msg,), daemon=True).start()
        return "break"

    def _run_agent_thread(self, user_msg):
        self.append_chat("system", "Thinking...")
        try:
            response = self.agent.chat(user_msg, self.handle_tool_execution)
            self.after(0, lambda: self.append_chat("agent", response))
            self.after(0, self.update_token_display)
        except Exception as e:
            self.after(0, lambda: self.append_chat("system", f"Critical Error: {e}"))

    def handle_tool_execution(self, name, args):
        """Called by the Agent when it wants to do something."""
        
        if name == "ask_user_clarification":
            # The agent wants to ask the user something before proceeding
            question = args.get('question')
            return f"Ask the user: {question}" # The agent will output this as text

        if name == "run_sql_query":
            query = args.get('query')
            
            # Update the SQL editor so the user sees what's happening
            self.after(0, lambda: self.sql_editor.delete("1.0", tk.END))
            self.after(0, lambda: self.sql_editor.insert(tk.END, query))
            
            # LEVEL 1: Never auto-execute, just draft
            if self.agent.agency_level == 1:
                self.after(0, lambda: self.append_chat("system", "Query drafted. Review and click 'Run SQL Manually' to execute."))
                return "Query has been drafted in the SQL Editor. User will review and execute manually."
            
            # SAFETY CHECK
            is_destructive = any(kw in query.upper() for kw in ["DELETE", "UPDATE", "DROP", "TRUNCATE", "ALTER"])
            
            if is_destructive:
                # Always require manual execution for destructive queries
                return "HALTED: Destructive actions (DELETE/UPDATE/DROP/ALTER) must be reviewed and clicked 'Run SQL Manually' by the user in the interface for safety."
            
            # LEVEL 2: Execute simple queries, but warn on complex ones
            if self.agent.agency_level == 2:
                # Check if this looks like a complex query (JOINs, subqueries, etc.)
                is_complex = any(kw in query.upper() for kw in ["JOIN", "UNION", "SUBQUERY", "EXISTS", "CASE WHEN"])
                if is_complex:
                    self.after(0, lambda: self.append_chat("system", "Complex query detected. Review in SQL Editor."))
            
            # LEVEL 2 & 3: Execute safe queries
            columns, rows, error = self.db.execute_query(query)
            
            if error:
                return f"Database Error: {error}"
            
            # Update UI Table
            self.after(0, lambda: self.populate_results(columns, rows))
            
            # Return summary to AI (don't return huge datasets to LLM token context)
            if len(rows) > 10:
                return f"Success. Retrieved {len(rows)} rows. Columns: {columns}. First 3 rows: {rows[:3]}"
            return f"Success. Data: {rows}"

    def run_manual_sql(self):
        query = self.sql_editor.get("1.0", tk.END).strip()
        if not query: return
        
        # Show the query being executed in chat
        self.append_chat("system", f"User manually executing query:\n```sql\n{query}\n```")
        
        # Add to agent's conversation history so AI is aware
        self.agent.history.append({
            "role": "user",
            "content": f"I manually executed this SQL query:\n```sql\n{query}\n```"
        })
        
        cols, rows, err = self.db.execute_query(query)
        if err:
            messagebox.showerror("SQL Error", err)
            # Inform agent about the error
            self.agent.history.append({
                "role": "assistant",
                "content": f"The query resulted in an error: {err}"
            })
            self.append_chat("system", f"Query failed: {err}")
        else:
            self.populate_results(cols, rows)
            result_msg = f"Query executed successfully. {len(rows)} rows returned."
            self.append_chat("system", result_msg)
            # Inform agent about the success
            self.agent.history.append({
                "role": "assistant",
                "content": result_msg
            })

    def populate_results(self, columns, rows):
        self.tree.delete(*self.tree.get_children())
        self.tree["columns"] = columns
        
        for col in columns:
            self.tree.heading(col, text=col)
            self.tree.column(col, width=100) # Adjust width dynamically if needed
            
        for row in rows:
            self.tree.insert("", tk.END, values=list(row))

if __name__ == "__main__":
    app = ModernSQLApp()
    app.mainloop()
