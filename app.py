import os
import json
import threading
import tkinter as tk
from tkinter import ttk, scrolledtext, messagebox, font
import mysql.connector
from mysql.connector import pooling, Error
from openai import OpenAI
from dotenv import load_dotenv
import re
import ctypes
import time

# --- WINDOWS DPI AWARENESS ---
try:
    ctypes.windll.shcore.SetProcessDpiAwareness(2) 
except:
    try:
        ctypes.windll.user32.SetProcessDPIAware()
    except:
        pass

# --- CONFIGURATION ---
load_dotenv()

DB_CONFIG = {
    'host': os.getenv("DB_HOST", "localhost"),
    'user': os.getenv("DB_USER", "root"),
    'password': os.getenv("DB_PASS", ""),
    'database': os.getenv("DB_NAME", ""),
    'port': int(os.getenv("DB_PORT", 3306)),
    'ssl_ca': os.getenv("DB_SSL_CA"),        # Path to CA file if needed
    'ssl_disabled': os.getenv("DB_SSL_DISABLED", "False").lower() == "true"
}

# Remove None values for SSL keys if not provided
DB_CONFIG = {k: v for k, v in DB_CONFIG.items() if v is not None}

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
OPENAI_MODEL_ID = os.getenv("OPENAI_MODEL_ID", "gpt-4-turbo")

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
    "warning": "#ce9178",
    "error": "#f48771"
}

# --- SAFETY VALIDATOR ---
class SQLValidator:
    """Parses SQL to determine intent and safety."""
    
    DESTRUCTIVE_COMMANDS = {'DELETE', 'DROP', 'TRUNCATE', 'ALTER', 'UPDATE', 'INSERT', 'CREATE', 'GRANT', 'REVOKE'}

    @staticmethod
    def get_command_type(query):
        """Extracts the primary command word, ignoring comments."""
        # Remove -- comments
        query = re.sub(r'--.*', '', query)
        # Remove /* */ comments
        query = re.sub(r'/\*.*?\*/', '', query, flags=re.DOTALL)
        
        # Normalize whitespace
        tokens = query.strip().split()
        if not tokens:
            return None
        
        return tokens[0].upper()

    @staticmethod
    def is_safe_read_only(query):
        cmd = SQLValidator.get_command_type(query)
        if cmd in SQLValidator.DESTRUCTIVE_COMMANDS:
            return False, cmd
        return True, cmd

# --- DATABASE MANAGER (POOLED) ---
class DatabaseManager:
    def __init__(self, config):
        self.config = config
        self.pool = None
        self.schema_summary = "" # Only table names
        
    def connect_pool(self):
        """Initializes the connection pool in a thread-safe way."""
        try:
            self.pool = mysql.connector.pooling.MySQLConnectionPool(
                pool_name="mypool",
                pool_size=5,
                **self.config
            )
            return True, "Connected successfully."
        except Error as e:
            return False, str(e)

    def get_connection(self):
        if not self.pool:
            return None
        return self.pool.get_connection()

    def get_table_names(self):
        """Fetches ONLY table names for the initial context."""
        conn = self.get_connection()
        if not conn: return "Error: No DB connection."
        
        try:
            cursor = conn.cursor()
            cursor.execute("SHOW TABLES")
            tables = [r[0] for r in cursor.fetchall()]
            conn.close()
            
            self.schema_summary = "Available Tables:\n" + "\n".join([f"- {t}" for t in tables])
            return self.schema_summary
        except Error as e:
            if conn: conn.close()
            return f"Error fetching tables: {e}"

    def get_table_details(self, table_name):
        """Fetches detailed schema for a specific table (Lazy Loading)."""
        conn = self.get_connection()
        if not conn: return "Error: No DB connection."
        
        output = f"=== SCHEMA FOR {table_name} ===\n"
        try:
            cursor = conn.cursor()
            
            # Columns
            cursor.execute(f"DESCRIBE {table_name}")
            columns = cursor.fetchall()
            output += "Columns:\n"
            for col in columns:
                output += f"  - {col[0]} ({col[1]}) key={col[3]} null={col[2]}\n"
                
            # Indexes (Simplified)
            cursor.execute(f"SHOW INDEX FROM {table_name}")
            indexes = cursor.fetchall()
            if indexes:
                output += "Indexes:\n"
                seen_idx = set()
                for idx in indexes:
                    idx_name = idx[2]
                    col_name = idx[4]
                    if idx_name not in seen_idx:
                        output += f"  - {idx_name} (starts with {col_name})\n"
                        seen_idx.add(idx_name)

            conn.close()
            return output
        except Error as e:
            if conn: conn.close()
            return f"Error fetching details for {table_name}: {e}"

    def execute_query(self, query):
        conn = self.get_connection()
        if not conn: return None, None, "No connection."
        
        try:
            cursor = conn.cursor()
            cursor.execute(query)
            
            if cursor.description:
                columns = [desc[0] for desc in cursor.description]
                rows = cursor.fetchall()
                conn.close()
                return columns, rows, None
            else:
                conn.commit()
                affected = cursor.rowcount
                conn.close()
                return ["Info"], [[f"Rows affected: {affected}"]], None
        except Error as e:
            if conn: conn.close()
            return None, None, str(e)

# --- AGENT (Context Optimized) ---
class Agent:
    def __init__(self, db_manager: DatabaseManager):
        self.client = OpenAI(api_key=OPENAI_API_KEY)
        self.db = db_manager
        self.model = OPENAI_MODEL_ID
        self.history = []
        self.agency_level = 2
        
        # Token Tracking
        self.tokens_in = 0
        self.tokens_out = 0

    def refresh_context(self):
        """Rebuilds system prompt with minimal schema."""
        table_list = self.db.schema_summary or "Tables not loaded yet."
        
        system_prompt = (
            "You are a SQL Database Expert. \n"
            "GUIDELINES:\n"
            "1. **Lazy Loading**: You have the list of tables below. You DO NOT know column names yet. "
            "If you need to write a query, first use `get_table_details` to see the columns, THEN write the SQL.\n"
            "2. **Safety**: Do not guess column names. Verify them.\n"
            f"\n{table_list}"
        )
        self.history = [{"role": "system", "content": system_prompt}]

    def trim_history(self):
        """Prevents context window explosion."""
        MAX_HISTORY = 12 # Keep system prompt + last 11 messages
        if len(self.history) > MAX_HISTORY:
            # Keep system prompt (index 0) and the recent messages
            self.history = [self.history[0]] + self.history[-(MAX_HISTORY-1):]

    def chat(self, user_input, tool_handler, stream_callback):
        self.trim_history()
        self.history.append({"role": "user", "content": user_input})

        tools = [
            {
                "type": "function",
                "function": {
                    "name": "run_sql_query",
                    "description": "Execute a SQL query. Ensure you have checked table schema first.",
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
                    "name": "get_table_details",
                    "description": "Get column definitions and keys for a specific table.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "table_name": {"type": "string"}
                        },
                        "required": ["table_name"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "ask_user_clarification",
                    "description": "Ask user for details if request is ambiguous.",
                    "parameters": {"type": "object", "properties": {"question": {"type": "string"}}}
                }
            }
        ]

        try:
            # 1. First Call
            response = self.client.chat.completions.create(
                model=self.model,
                messages=self.history,
                tools=tools,
                tool_choice="auto",
                stream=True,
                stream_options={"include_usage": True}
            )
            
            full_content = ""
            tool_calls = []
            
            for chunk in response:
                if chunk.usage: 
                    self.tokens_in += chunk.usage.prompt_tokens
                    self.tokens_out += chunk.usage.completion_tokens
                
                delta = chunk.choices[0].delta if chunk.choices else None
                if delta:
                    if delta.content:
                        full_content += delta.content
                        stream_callback(delta.content)
                    
                    if delta.tool_calls:
                        for tc in delta.tool_calls:
                            idx = tc.index
                            while len(tool_calls) <= idx:
                                tool_calls.append({'id': '', 'func': {'name': '', 'args': ''}})
                            if tc.id: tool_calls[idx]['id'] = tc.id
                            if tc.function.name: tool_calls[idx]['func']['name'] = tc.function.name
                            if tc.function.arguments: tool_calls[idx]['func']['args'] += tc.function.arguments

            # 2. Process Tools
            if tool_calls:
                self.history.append({"role": "assistant", "content": full_content, 
                                     "tool_calls": [{"id": t['id'], "type": "function", 
                                                     "function": {"name": t['func']['name'], "arguments": t['func']['args']}} for t in tool_calls]})
                
                for tc in tool_calls:
                    name = tc['func']['name']
                    args = json.loads(tc['func']['args'])
                    result = tool_handler(name, args) # Call back to UI
                    
                    self.history.append({
                        "role": "tool",
                        "tool_call_id": tc['id'],
                        "content": str(result)
                    })

                # 3. Final Answer (Streamed)
                follow_up = self.client.chat.completions.create(
                    model=self.model, messages=self.history, stream=True, stream_options={"include_usage": True}
                )
                
                final_text = ""
                for chunk in follow_up:
                    if chunk.usage: 
                        self.tokens_in += chunk.usage.prompt_tokens
                        self.tokens_out += chunk.usage.completion_tokens
                        
                    delta = chunk.choices[0].delta if chunk.choices else None
                    if delta and delta.content:
                        final_text += delta.content
                        stream_callback(delta.content)
                
                self.history.append({"role": "assistant", "content": final_text})
                return final_text
            
            else:
                self.history.append({"role": "assistant", "content": full_content})
                return full_content

        except Exception as e:
            return f"API Error: {e}"

# --- MARKDOWN RENDERER ---
class MarkdownRenderer:
    @staticmethod
    def render(text_widget, text, tag="ai"):
        try:
            lines = text.split('\n')
            in_code_block = False
            
            for line in lines:
                # Code blocks
                if line.strip().startswith('```'):
                    in_code_block = not in_code_block
                    text_widget.insert(tk.END, line + "\n", "code_block")
                    continue
                
                if in_code_block:
                    text_widget.insert(tk.END, line + "\n", "code_block")
                    continue
                
                # Headers
                header_match = re.match(r'^(#{1,6})\s+(.+)$', line)
                if header_match:
                    level = len(header_match.group(1))
                    header_text = header_match.group(2)
                    header_tag = f"h{level}"
                    MarkdownRenderer._parse_inline(text_widget, header_text, header_tag)
                    text_widget.insert(tk.END, "\n")
                    continue
                
                # Blockquotes
                if line.strip().startswith('>'):
                    quote_text = line.strip()[1:].strip()
                    text_widget.insert(tk.END, "❝ ", "blockquote")
                    MarkdownRenderer._parse_inline(text_widget, quote_text, "blockquote")
                    text_widget.insert(tk.END, "\n")
                    continue
                
                # Horizontal rule
                if re.match(r'^(---|\*\*\*|___)$', line.strip()):
                    text_widget.insert(tk.END, "―" * 50 + "\n", "hr")
                    continue
                
                # Unordered lists
                list_match = re.match(r'^[\s]*([-*+])\s+(.+)$', line)
                if list_match:
                    indent = len(line) - len(line.lstrip())
                    bullet = "  " * (indent // 2) + "• "
                    text_widget.insert(tk.END, bullet, "list")
                    MarkdownRenderer._parse_inline(text_widget, list_match.group(2), tag)
                    text_widget.insert(tk.END, "\n")
                    continue
                
                # Ordered lists
                ordered_match = re.match(r'^[\s]*(\d+)\.\.?\s+(.+)$', line)
                if ordered_match:
                    indent = len(line) - len(line.lstrip())
                    number = "  " * (indent // 2) + ordered_match.group(1) + ". "
                    text_widget.insert(tk.END, number, "list")
                    MarkdownRenderer._parse_inline(text_widget, ordered_match.group(2), tag)
                    text_widget.insert(tk.END, "\n")
                    continue
                
                # Regular text with inline formatting
                MarkdownRenderer._parse_inline(text_widget, line, tag)
                text_widget.insert(tk.END, "\n")
                
        except Exception as e:
            text_widget.insert(tk.END, text + "\n", tag)
    
    @staticmethod
    def _parse_inline(text_widget, text, base_tag="ai"):
        """Parse inline markdown: bold, italic, inline code, links"""
        # Pattern for inline elements: bold, italic, code, links
        pattern = r'(\*\*\*[^*]+\*\*\*|\*\*[^*]+\*\*|\*[^*]+\*|_[^_]+_|`[^`]+`|\[([^\]]+)\]\(([^)]+)\)|~~[^~]+~~)'
        
        parts = re.split(pattern, text)
        
        for i, part in enumerate(parts):
            if not part:
                continue
                
            # Bold + Italic (***text***)
            if part.startswith('***') and part.endswith('***') and len(part) > 6:
                text_widget.insert(tk.END, part[3:-3], "bold_italic")
            # Bold (**text**)
            elif part.startswith('**') and part.endswith('**') and len(part) > 4:
                text_widget.insert(tk.END, part[2:-2], "bold")
            # Italic (*text* or _text_)
            elif (part.startswith('*') and part.endswith('*') and len(part) > 2) or \
                 (part.startswith('_') and part.endswith('_') and len(part) > 2):
                text_widget.insert(tk.END, part[1:-1], "italic")
            # Inline code (`code`)
            elif part.startswith('`') and part.endswith('`') and len(part) > 2:
                text_widget.insert(tk.END, part[1:-1], "inline_code")
            # Strikethrough (~~text~~)
            elif part.startswith('~~') and part.endswith('~~') and len(part) > 4:
                text_widget.insert(tk.END, part[2:-2], "strikethrough")
            # Links [text](url) - simplified, just show as underlined text
            elif i + 2 < len(parts) and parts[i+1] and parts[i+2]:
                # This is a link match
                if part.startswith('['):
                    link_text = parts[i+1]
                    text_widget.insert(tk.END, link_text, "link")
            # Regular text
            elif not re.match(r'^[\[\]\(\)]+$', part):  # Skip brackets/parens from link parsing
                text_widget.insert(tk.END, part, base_tag)

# --- GUI APPLICATION ---
class ModernSQLApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("AI SQL Manager (Safe & Optimized)")
        self.geometry("1400x900")
        self.configure(bg=COLORS["bg"])
        
        # Data & Logic
        self.db = DatabaseManager(DB_CONFIG)
        self.agent = Agent(self.db)
        self.agency_level = tk.IntVar(value=2)
        
        # UI Setup
        self._setup_styles()
        self._build_layout()
        self._configure_tags()
        
        # Async Initialization
        self.status_var = tk.StringVar(value="Initializing...")
        self.status_bar = tk.Label(self, textvariable=self.status_var, bg=COLORS["accent"], fg="white", font=("Segoe UI", 9))
        self.status_bar.pack(side=tk.BOTTOM, fill=tk.X)
        
        # Start DB thread
        threading.Thread(target=self._init_backend, daemon=True).start()

    def _init_backend(self):
        """Connects to DB in background without freezing UI."""
        self._update_status("Connecting to Database...")
        success, msg = self.db.connect_pool()
        
        if success:
            self._update_status("Fetching Schema...")
            self.db.get_table_names()
            self.agent.refresh_context()
            self._update_status(f"Ready. Connected to {self.db.config['host']}.")
            # Enable input
            self.after(0, lambda: self.chat_input.config(state=tk.NORMAL))
            self.after(0, lambda: self.append_chat("system", "System Ready. Database connected."))
        else:
            self._update_status(f"Connection Failed: {msg}")
            self.after(0, lambda: messagebox.showerror("Connection Error", msg))

    def _update_status(self, text):
        self.after(0, lambda: self.status_var.set(text))

    def _setup_styles(self):
        style = ttk.Style(self)
        style.theme_use('clam')
        style.configure("TFrame", background=COLORS["bg"])
        style.configure("TButton", background=COLORS["accent"], foreground="white", borderwidth=0)
        style.map("TButton", background=[("active", COLORS["accent_hover"])])
        
        style.configure("Treeview", background=COLORS["entry_bg"], foreground=COLORS["fg"], fieldbackground=COLORS["entry_bg"], font=("Consolas", 10))
        style.configure("Treeview.Heading", background=COLORS["border"], foreground="white", relief="flat")

    def _build_layout(self):
        main_pane = ttk.PanedWindow(self, orient=tk.HORIZONTAL)
        main_pane.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

        # LEFT: CHAT
        left_frame = ttk.Frame(main_pane)
        main_pane.add(left_frame, weight=4)
        
        # Toolbar
        tool_frame = ttk.Frame(left_frame)
        tool_frame.pack(fill=tk.X, pady=5)
        
        ttk.Label(tool_frame, text="Autonomy:", background=COLORS["bg"], foreground="white").pack(side=tk.LEFT)
        for i, text in [(1, "Draft"), (2, "Standard"), (3, "Full")]:
            tk.Radiobutton(tool_frame, text=text, variable=self.agency_level, value=i, 
                           bg=COLORS["bg"], fg="white", selectcolor=COLORS["entry_bg"], activebackground=COLORS["bg"]).pack(side=tk.LEFT, padx=5)

        self.lbl_tokens = ttk.Label(tool_frame, text="Tokens: 0", background=COLORS["bg"], foreground=COLORS["warning"])
        self.lbl_tokens.pack(side=tk.RIGHT)

        # Chat Area
        self.chat_display = scrolledtext.ScrolledText(left_frame, bg=COLORS["entry_bg"], fg=COLORS["fg"], font=("Segoe UI", 11), wrap=tk.WORD, borderwidth=0)
        self.chat_display.pack(fill=tk.BOTH, expand=True)
        
        # Input
        input_cont = ttk.Frame(left_frame)
        input_cont.pack(fill=tk.X, pady=5)
        self.chat_input = tk.Text(input_cont, height=3, bg=COLORS["entry_bg"], fg="white", font=("Segoe UI", 11), state=tk.DISABLED)
        self.chat_input.pack(side=tk.LEFT, fill=tk.X, expand=True)
        self.chat_input.bind("<Return>", self.on_send)
        self.chat_input.bind("<Shift-Return>", lambda e: None) # Allow newlines
        
        ttk.Button(input_cont, text="Send", command=self.on_send).pack(side=tk.RIGHT, fill=tk.Y, padx=5)

        # RIGHT: SQL & RESULTS
        right_frame = ttk.Frame(main_pane)
        main_pane.add(right_frame, weight=6)
        
        # SQL Editor
        self.sql_editor = scrolledtext.ScrolledText(right_frame, bg=COLORS["entry_bg"], fg=COLORS["success"], font=("Consolas", 12), height=8)
        self.sql_editor.pack(fill=tk.X, pady=(0,5))
        
        btn_bar = ttk.Frame(right_frame)
        btn_bar.pack(fill=tk.X)
        ttk.Button(btn_bar, text="Run SQL Manually", command=self.run_manual_sql).pack(side=tk.RIGHT)
        
        # Results Table
        self.tree = ttk.Treeview(right_frame, show='headings')
        vsb = ttk.Scrollbar(right_frame, orient="vertical", command=self.tree.yview)
        hsb = ttk.Scrollbar(right_frame, orient="horizontal", command=self.tree.xview)
        self.tree.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)
        
        self.tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, pady=5)
        vsb.pack(side=tk.RIGHT, fill=tk.Y)
        hsb.pack(side=tk.BOTTOM, fill=tk.X)

    def _configure_tags(self):
        self.chat_display.tag_config("user", foreground="#ffffff", background=COLORS["chat_user"], lmargin1=10, rmargin=50)
        self.chat_display.tag_config("ai", foreground="#ffffff", background=COLORS["chat_ai"], lmargin1=10, rmargin=50)
        self.chat_display.tag_config("system", foreground=COLORS["warning"], font=("Segoe UI", 9, "italic"))
        
        # Code formatting
        self.chat_display.tag_config("code_block", font=("Consolas", 10), background="#111", foreground=COLORS["success"])
        self.chat_display.tag_config("inline_code", font=("Consolas", 10), background="#2d2d30", foreground=COLORS["success"])
        
        # Text formatting
        self.chat_display.tag_config("bold", font=("Segoe UI", 11, "bold"))
        self.chat_display.tag_config("italic", font=("Segoe UI", 11, "italic"))
        self.chat_display.tag_config("bold_italic", font=("Segoe UI", 11, "bold italic"))
        self.chat_display.tag_config("strikethrough", font=("Segoe UI", 11), overstrike=True)
        
        # Headers
        self.chat_display.tag_config("h1", font=("Segoe UI", 18, "bold"), foreground="#4ec9b0")
        self.chat_display.tag_config("h2", font=("Segoe UI", 16, "bold"), foreground="#4ec9b0")
        self.chat_display.tag_config("h3", font=("Segoe UI", 14, "bold"), foreground="#4ec9b0")
        self.chat_display.tag_config("h4", font=("Segoe UI", 12, "bold"), foreground="#9cdcfe")
        self.chat_display.tag_config("h5", font=("Segoe UI", 11, "bold"), foreground="#9cdcfe")
        self.chat_display.tag_config("h6", font=("Segoe UI", 10, "bold"), foreground="#9cdcfe")
        
        # Other elements
        self.chat_display.tag_config("link", foreground="#3794ff", underline=True)
        self.chat_display.tag_config("blockquote", foreground="#808080", lmargin1=20, font=("Segoe UI", 10, "italic"))
        self.chat_display.tag_config("list", foreground=COLORS["fg"])
        self.chat_display.tag_config("hr", foreground=COLORS["border"])

    def append_chat(self, role, text):
        self.chat_display.config(state=tk.NORMAL)
        self.chat_display.insert(tk.END, f"\n[{role.upper()}]\n", "system")
        MarkdownRenderer.render(self.chat_display, text, role)
        self.chat_display.see(tk.END)
        self.chat_display.config(state=tk.DISABLED)

    def on_send(self, event=None):
        if event and event.keysym == 'Return' and not event.state & 0x0001: # Check shift
            pass
        else:
            return 
            
        msg = self.chat_input.get("1.0", tk.END).strip()
        if not msg: return "break"
        
        self.chat_input.delete("1.0", tk.END)
        self.append_chat("user", msg)
        
        threading.Thread(target=self._run_agent, args=(msg,), daemon=True).start()
        return "break"

    def _run_agent(self, msg):
        self.current_stream = ""
        
        # 1. Prepare UI (Header + Spacing) on main thread
        self.after(0, self.start_streaming_message)

        # 2. Callback for raw streaming
        def callback(chunk):
            self.current_stream += chunk
            self.after(0, lambda: self._stream_raw_chunk(chunk))

        # 3. Agent Logic
        try:
            final_text = self.agent.chat(msg, self.handle_tool, callback)
            
            # 4. Finalize (Replace raw text with Markdown)
            self.after(0, lambda: self.finalize_streaming_message(final_text))
            self.after(0, self._update_token_display)
            
        except Exception as e:
            self.after(0, lambda: self.append_chat("system", f"Error: {e}"))

    def start_streaming_message(self):
        """Prepares chat window with [AGENT] header and proper spacing."""
        self.chat_display.config(state=tk.NORMAL)
        
        # A. Force separation from previous message if needed
        if self.chat_display.get("end-2c", "end-1c") != "\n":
            self.chat_display.insert(tk.END, "\n")
        
        # B. Add an empty line above the header
        self.chat_display.insert(tk.END, "\n")
        
        # C. Insert Header with an EXTRA newline below it
        self.chat_display.insert(tk.END, "[AGENT]\n\n", "system")
        
        # D. Set the 'stream_start' mark AFTER that extra newline.
        # This protects the header and the empty line from being deleted later.
        self.chat_display.mark_set("stream_start", "end-1c")
        self.chat_display.mark_gravity("stream_start", tk.LEFT)
        
        self.chat_display.see(tk.END)
        self.chat_display.config(state=tk.DISABLED)

    def _stream_raw_chunk(self, chunk):
        """Inserts raw text during streaming."""
        self.chat_display.config(state=tk.NORMAL)
        self.chat_display.insert(tk.END, chunk, "ai")
        self.chat_display.see(tk.END)
        self.chat_display.config(state=tk.DISABLED)

    def finalize_streaming_message(self, final_text):
        """Replaces raw text with Markdown."""
        if not final_text: return
        
        if "stream_start" not in self.chat_display.mark_names():
            return

        self.chat_display.config(state=tk.NORMAL)
        
        # 1. Delete raw text (Header and gap remain safe above 'stream_start')
        self.chat_display.delete("stream_start", tk.END)
        
        # 2. Render Markdown
        MarkdownRenderer.render(self.chat_display, final_text, "ai")
        
        # 3. Add trailing newline for next user message
        self.chat_display.insert(tk.END, "\n")
        
        self.chat_display.mark_unset("stream_start")
        self.chat_display.see(tk.END)
        self.chat_display.config(state=tk.DISABLED)

    def _finalize_markdown_render(self, full_text):
        """Deletes the raw stream and re-inserts as formatted Markdown."""
        if not full_text: return
        
        self.chat_display.config(state=tk.NORMAL)
        
        # Delete the raw text from our start mark to the end
        self.chat_display.delete("response_start", tk.END)
        
        # Re-insert using the Markdown Renderer
        MarkdownRenderer.render(self.chat_display, full_text, "ai")
        
        self.chat_display.see(tk.END)
        self.chat_display.config(state=tk.DISABLED)

    def _update_token_display(self):
        t_in = self.agent.tokens_in
        t_out = self.agent.tokens_out
        self.lbl_tokens.config(text=f"Tokens: {t_in + t_out} (In: {t_in}, Out: {t_out})")

    def handle_tool(self, name, args):
        if name == "ask_user_clarification":
            return args.get("question")
        
        if name == "get_table_details":
            table = args.get("table_name")
            self.after(0, lambda: self.append_chat("system", f"Fetching schema for: {table}..."))
            return self.db.get_table_details(table)

        if name == "run_sql_query":
            query = args.get("query")
            
            # Update Editor
            self.after(0, lambda: self.sql_editor.delete("1.0", tk.END))
            self.after(0, lambda: self.sql_editor.insert(tk.END, query))
            
            # 1. Level 1: Draft Only
            if self.agency_level.get() == 1:
                return "Query drafted in editor. User must run manually."
            
            # 2. Safety Check
            is_safe, cmd = SQLValidator.is_safe_read_only(query)
            if not is_safe:
                msg = f"HALTED: Destructive command '{cmd}' detected. Please click 'Run SQL Manually' if you are sure."
                self.after(0, lambda: messagebox.showwarning("Safety Block", msg))
                return msg
            
            # 3. Execution
            cols, rows, err = self.db.execute_query(query)
            if err: return f"DB Error: {err}"
            
            self.after(0, lambda: self.populate_results(cols, rows))
            if len(rows) > 5:
                return f"Success. {len(rows)} rows. Top 5: {rows[:5]}"
            return f"Success. Data: {rows}"

    def run_manual_sql(self):
        query = self.sql_editor.get("1.0", tk.END).strip()
        if not query: return
        
        # Manual bypasses safety checks in Agent, but user accepts risk
        cols, rows, err = self.db.execute_query(query)
        if err:
            messagebox.showerror("Error", err)
        else:
            self.populate_results(cols, rows)
            self.append_chat("system", f"Manual Query: {len(rows)} rows returned.")

    def populate_results(self, columns, rows):
        self.tree.delete(*self.tree.get_children())
        self.tree["columns"] = columns
        for col in columns:
            self.tree.heading(col, text=col)
            self.tree.column(col, width=120)
        
        for row in rows:
            self.tree.insert("", tk.END, values=list(row))

if __name__ == "__main__":
    app = ModernSQLApp()
    app.mainloop()
