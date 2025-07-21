import tkinter as tk
from tkinter import ttk, scrolledtext, messagebox
import threading
import mysql.connector
import openai
import sys
import json
import os
from dotenv import load_dotenv

# --- CONFIG ---
load_dotenv()

DB_CONFIG = {
    'host': os.getenv('DB_HOST'),
    'user': os.getenv('DB_USER'),
    'password': os.getenv('DB_PASSWORD'),
    'database': os.getenv('DB_NAME'),
    'port': int(os.getenv('DB_PORT', 3306)),
}
OPENAI_API_KEY = os.getenv('OPENAI_API_KEY')

# --- DB UTILS ---
def connect_to_database():
    """Establishes a connection to the MySQL database using the global DB_CONFIG."""
    try:
        return mysql.connector.connect(**DB_CONFIG)
    except Exception as e:
        messagebox.showerror("DB Error", str(e))
        return None

def get_tables_and_columns():
    """Fetches the schema (table names and their columns) from the database."""
    connection = connect_to_database()
    tables = {}
    if not connection:
        return tables
    try:
        cursor = connection.cursor()
        cursor.execute("SHOW TABLES")
        for (table_name,) in cursor.fetchall():
            cursor.execute(f"DESCRIBE {table_name}")
            tables[table_name] = [list(col)[0] for col in cursor.fetchall()]
    except Exception as e:
        messagebox.showerror("DB Error", str(e))
    finally:
        if connection:
            connection.close()
    return tables

def run_query(query):
    """
    Executes a given SQL query on the database.
    Returns (columns, results) for SELECT queries or (None, message) for other queries/errors.
    """
    connection = connect_to_database()
    if not connection:
        return None, "Failed to connect to database"
    try:
        cursor = connection.cursor()
        cursor.execute(query)
        # Check if the query is a SELECT statement to fetch results
        if query.strip().lower().startswith(("select", "show", "describe", "explain")):
            if cursor.description is None:
                return [], []
            columns = [desc[0] for desc in cursor.description]
            results = cursor.fetchall() or []
            return columns, results
        else:
            # For DML/DDL queries, commit changes and return success message
            connection.commit()
            affected_rows = cursor.rowcount
            return None, f"Query executed successfully. {affected_rows} rows affected."
    except Exception as e:
        return None, f"Error: {str(e)}"
    finally:
        if connection:
            connection.close()

# --- OPENAI ---
openai_client = openai.Client(api_key=OPENAI_API_KEY)

def ask_ai(messages):
    """Sends a list of messages to the AI model and returns the text response."""
    try:
        response = openai_client.chat.completions.create(
            model="gpt-4o-mini",
            messages=messages
        )
        return response.choices[0].message.content
    except Exception as e:
        return f"AI Error: {e}"

def ask_ai_with_tools(messages):
    """
    Uses OpenAI tool-calling API to allow the AI to request running SQL queries.
    """
    tools: list[ChatCompletionToolParam] = [{
        "type": "function",
        "function": {
            "name": "run_sql_query",
            "description": "Run a SQL query on the MySQL database. Use this for all database operations.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "The SQL query to run."}
                },
                "required": ["query"],
            }
        }
    }]

    try:
        response = openai_client.chat.completions.create(
            model="gpt-4o-mini",
            messages=messages,
            tools=tools,
            tool_choice="auto"
        )
        return response.choices[0].message
    except Exception as e:
        # Return a mock message object with error content
        class MockMessage:
            def __init__(self, content):
                self.content = content
                self.tool_calls = None
        return MockMessage(f"AI Error: {e}")

# --- DPI AWARENESS (Windows) ---
if sys.platform == "win32":
    try:
        import ctypes
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except Exception:
        pass

# --- GUI ---
class DBViewerGUI(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Database Viewer & AI Chat")
        self.geometry("1200x1000")
        self.is_dark_mode = False
        self.create_widgets()
        self.tables = get_tables_and_columns()
        self.chat_history = []
        self.sql_history = []
        self.sql_history_index = None
        self.sql_text.bind('<Up>', self.sql_history_up)
        self.sql_text.bind('<Down>', self.sql_history_down)
        self.bind_all('<Control-d>', self.toggle_dark_mode)
        
        # Focus and bring window to front on launch
        self.lift()
        self.attributes('-topmost', True)
        self.after(100, lambda: self.attributes('-topmost', False))
        self.focus_force()

        # State variables
        self.is_query_running = False
        self.is_ai_thinking = False

    def set_modern_style(self):
        """Apply a modern, flat style to the app. Supports light and dark mode."""
        style = ttk.Style(self)
        try:
            style.theme_use('clam')
        except Exception:
            pass
            
        if getattr(self, 'is_dark_mode', False):
            bg = "#23272e"
            fg = "#e6e6e6"
            border = "#444"
            entry_bg = "#2c313a"
            select_bg = "#3a3f4b"
            chat_user_bg = "#4a4e55"
            chat_ai_bg = "#3a3f4b"
        else:
            bg = "#f3f3f3"
            fg = "#222"
            border = "#bbb"
            entry_bg = "#f3f3f3"
            select_bg = "#cce5ff"
            chat_user_bg = "#e0e0e0"
            chat_ai_bg = "#f0f0f0"

        self.configure(background=bg)
        default_font = ("Segoe UI", 12)
        self.option_add("*Font", default_font)
        self.option_add("*TButton.Font", default_font)
        self.option_add("*TLabel.Font", default_font)
        self.option_add("*Treeview.Heading.Font", ("Segoe UI Semibold", 12))
        
        style.configure("TFrame", background=bg)
        style.configure("TLabel", background=bg, foreground=fg)
        style.configure("TButton", relief="flat", borderwidth=0, padding=8, background=bg, foreground=fg)
        style.map("TButton", background=[('active', border)])
        style.configure("TEntry", relief="flat", borderwidth=1, padding=6, fieldbackground=entry_bg, background=entry_bg, foreground=fg)
        style.configure("Treeview", rowheight=24, font=default_font, borderwidth=0, relief="flat", background=entry_bg, fieldbackground=entry_bg, foreground=fg)
        style.configure("Treeview.Heading", font=("Segoe UI Semibold", 12), borderwidth=0, relief="flat", background=bg, foreground=fg)
        style.layout("TNotebook.Tab", [])
        style.configure("Vertical.TScrollbar", gripcount=0, background=bg, troughcolor=bg, bordercolor=bg, arrowcolor=fg)
        style.configure("Horizontal.TScrollbar", gripcount=0, background=bg, troughcolor=bg, bordercolor=bg, arrowcolor=fg)
        style.map("TButton", focuscolor=[('!focus', 'none')])

        self.section_border_color = border
        self.section_bg = bg
        self.section_fg = fg
        self.entry_bg = entry_bg
        self.select_bg = select_bg

        # Re-apply chat display tags with current colors
        if hasattr(self, 'chat_display'):
            self.chat_display.tag_configure("user", foreground=fg, background=chat_user_bg, justify='right', lmargin1=10, lmargin2=10, rmargin=10)
            self.chat_display.tag_configure("ai", foreground=fg, background=chat_ai_bg, justify='left', lmargin1=10, lmargin2=10, rmargin=10)
            self.chat_display.tag_configure("separator", foreground=border, background=bg, justify='center')

    def toggle_dark_mode(self, event=None):
        """Toggles between dark and light mode and updates the UI style."""
        self.is_dark_mode = not self.is_dark_mode
        self.set_modern_style()
        self.update_section_styles()

    def update_section_styles(self):
        """Updates the styles of various UI elements based on the current theme."""
        self.configure(background=self.section_bg)
        for frame in [self.sql_section, self.result_section, self.chat_section]:
            frame.config(background=self.section_bg, highlightbackground=self.section_border_color, highlightcolor=self.section_border_color)
        for label in [self.sql_label, self.result_label, self.chat_label]:
            label.config(background=self.section_bg, foreground=self.section_fg)
        self.sql_text.config(background=self.entry_bg, foreground=self.section_fg, insertbackground=self.section_fg)
        self.result_tree.tag_configure('selected_cell', background=self.select_bg)
        self.selected_value_label.config(background=self.section_bg, foreground=self.section_fg)
        self.chat_display.config(background=self.entry_bg, foreground=self.section_fg, insertbackground=self.section_fg)
        self.chat_entry.config(background=self.entry_bg, foreground=self.section_fg, insertbackground=self.section_fg,
                               highlightbackground=self.section_border_color, highlightcolor=self.section_border_color)

    def create_widgets(self):
        """Set up all widgets for the GUI."""
        self.set_modern_style()

        # SQL Editor Section
        self.sql_section = tk.Frame(self, background=self.section_bg, highlightbackground=self.section_border_color, 
                                   highlightcolor=self.section_border_color, highlightthickness=1, bd=0)
        self.sql_section.pack(fill='x', padx=16, pady=(16, 8))
        
        self.sql_label = ttk.Label(self.sql_section, text="SQL Editor", font=("Segoe UI Semibold", 13), 
                                  background=self.section_bg, foreground=self.section_fg)
        self.sql_label.pack(anchor='w', padx=2, pady=(0, 4))
        
        self.sql_text = scrolledtext.ScrolledText(self.sql_section, height=4, font=("Consolas", 12), 
                                                 borderwidth=0, relief="flat", background=self.entry_bg, 
                                                 foreground=self.section_fg, insertbackground=self.section_fg)
        self.sql_text.pack(fill='x', padx=0, pady=0)
        self.sql_text.bind('<Control-Return>', self.ctrl_enter_run_query)
        self.sql_text.bind('<Control-Shift-Return>', lambda e: self.use_ai_for_query())
        self.sql_text.bind('<Control-Shift-Enter>', lambda e: self.use_ai_for_query())

        btn_frame = ttk.Frame(self.sql_section)
        btn_frame.pack(fill='x', padx=0, pady=(8, 0))
        self.run_btn = ttk.Button(btn_frame, text="Run Query", command=self.run_sql_query)
        self.run_btn.pack(side='right', padx=(8,0))
        self.ai_btn = ttk.Button(btn_frame, text="Use AI", command=self.use_ai_for_query)
        self.ai_btn.pack(side='right', padx=(8,0))

        # Results Section
        self.result_section = tk.Frame(self, background=self.section_bg, highlightbackground=self.section_border_color, 
                                      highlightcolor=self.section_border_color, highlightthickness=1, bd=0)
        self.result_section.pack(fill='both', expand=True, padx=16, pady=(8, 4))
        
        self.result_label = ttk.Label(self.result_section, text="Results", font=("Segoe UI Semibold", 13), 
                                     background=self.section_bg, foreground=self.section_fg)
        self.result_label.pack(anchor='w', padx=2, pady=(0, 4))
        
        result_tree_frame = ttk.Frame(self.result_section)
        result_tree_frame.pack(fill='both', expand=True)
        
        self.result_tree = ttk.Treeview(result_tree_frame, show='headings')
        vsb = ttk.Scrollbar(result_tree_frame, orient="vertical", command=self.result_tree.yview, style="Vertical.TScrollbar")
        self.result_tree.configure(yscrollcommand=vsb.set)
        self.result_tree.pack(side='left', fill='both', expand=True)
        vsb.pack(side='right', fill='y')
        
        self.result_tree.bind('<ButtonRelease-1>', self.on_tree_select)
        self.result_tree.bind('<Control-c>', self.copy_selected_cell)
        self.result_tree.bind('<Control-C>', self.copy_selected_cell)
        self.result_tree.tag_configure('selected_cell', background=self.select_bg)
        
        self.selected_item = None
        self.selected_col = None
        self.selected_value_label = ttk.Label(self.result_section, text="Selected: None", anchor='w', 
                                            background=self.section_bg, foreground=self.section_fg)
        self.selected_value_label.pack(fill='x', padx=2, pady=(4,0))

        # AI Chat Section
        self.chat_section = tk.Frame(self, background=self.section_bg, highlightbackground=self.section_border_color, 
                                    highlightcolor=self.section_border_color, highlightthickness=1, bd=0)
        self.chat_section.pack(fill='both', expand=True, padx=16, pady=(4, 16))
        
        self.chat_label = ttk.Label(self.chat_section, text="AI Chat", font=("Segoe UI Semibold", 13), 
                                   background=self.section_bg, foreground=self.section_fg)
        self.chat_label.pack(anchor='w', padx=2, pady=(0, 4))

        self.chat_display = scrolledtext.ScrolledText(self.chat_section, height=8, state='normal', wrap='word', 
                                                     font=("Segoe UI", 12), borderwidth=0, relief="flat", 
                                                     background=self.entry_bg, foreground=self.section_fg, 
                                                     insertbackground=self.section_fg)
        self.chat_display.pack(fill='both', expand=True, padx=0, pady=(0,0))
        self.chat_display.config(state='disabled')

        # Enable text selection in chat_display
        self.chat_display.config(state='normal')
        self.chat_display.bind('<1>', lambda e: self.chat_display.focus_set())
        self.chat_display.config(state='disabled')

        # Chat message tags
        self.chat_display.tag_configure("user", justify='right', lmargin1=10, lmargin2=10, rmargin=10)
        self.chat_display.tag_configure("ai", justify='left', lmargin1=10, lmargin2=10, rmargin=10)
        self.chat_display.tag_configure("separator", justify='center')

        chat_entry_frame = ttk.Frame(self.chat_section)
        chat_entry_frame.pack(fill='x', padx=0, pady=(8,0), side='bottom')

        self.chat_entry = scrolledtext.ScrolledText(chat_entry_frame, height=3, font=("Segoe UI", 12), 
                                                   borderwidth=1, relief="flat", background=self.entry_bg, 
                                                   foreground=self.section_fg, insertbackground=self.section_fg,
                                                   highlightthickness=1, highlightbackground=self.section_border_color)
        self.chat_entry.pack(side='left', fill='x', expand=True)
        self.chat_entry.bind('<Control-Return>', self.send_chat)

        self.send_btn = ttk.Button(chat_entry_frame, text="Send", command=self.send_chat)
        self.send_btn.pack(side='left', padx=(8,0))

        clear_btn = ttk.Button(chat_entry_frame, text="Clear Chat", command=self.confirm_clear_chat)
        clear_btn.pack(side='left', padx=(8,0))

        self.update_section_styles()

    def set_query_running_state(self, running):
        """Sets the state of query-related buttons and flags."""
        self.is_query_running = running
        state = 'disabled' if running else 'normal'
        self.run_btn.config(state=state)
        self.ai_btn.config(state=state)

    def set_ai_thinking_state(self, thinking):
        """Sets the state of AI chat-related buttons and flags."""
        self.is_ai_thinking = thinking
        state = 'disabled' if thinking else 'normal'
        self.send_btn.config(state=state, text="Thinking..." if thinking else "Send")
        self.chat_entry.config(state=state)
        if thinking:
            self.chat_entry.delete('1.0', tk.END)
            self.chat_entry.insert(tk.END, "Thinking...")
            self.chat_entry.mark_set(tk.INSERT, tk.END)
        else:
            self.chat_entry.delete('1.0', tk.END)
            self.chat_entry.focus_set()

    def refresh_schema(self):
        """Refresh the schema cache from the database."""
        self.tables = get_tables_and_columns()

    def get_latest_schema_string(self):
        """Always fetch the latest schema from the DB and return as a string for prompts."""
        tables = get_tables_and_columns()
        schema_string = ""
        for table_name, columns in tables.items():
            schema_string += f"Table: {table_name}\n"
            for col in columns:
                schema_string += f"  - {col}\n"
            schema_string += "\n"
        return schema_string

    def _update_result_tree(self, columns, result):
        """Helper to update the result treeview on the main thread."""
        self.result_tree.delete(*self.result_tree.get_children())
        if columns:
            self.result_tree['columns'] = columns
            for col in columns:
                self.result_tree.heading(col, text=col)
            if result:
                for row in result:
                    self.result_tree.insert('', tk.END, values=list(row) if not isinstance(row, (list, tuple)) else row)
        else:
            msg = result if isinstance(result, str) else str(result)
            messagebox.showinfo("Query Result", msg)

    def run_sql_query(self, from_ai=False, ai_query=None):
        """Run the SQL query in the editor and display results."""
        if self.is_query_running:
            return

        query = ai_query if from_ai and ai_query else self.sql_text.get('1.0', tk.END).strip()
        if not query:
            return

        self.set_query_running_state(True)

        if not from_ai and (not self.sql_history or (self.sql_history and query != self.sql_history[-1])):
            self.sql_history.append(query)
        self.sql_history_index = None

        def run_in_thread():
            # Check if DDL and refresh schema if needed
            first_word = query.strip().split()[0].lower()
            if first_word in {"create", "drop", "alter", "rename"}:
                self.refresh_schema()

            columns, result = run_query(query)
            self.after(0, lambda: self._update_result_tree(columns, result))
            self.after(0, lambda: self.set_query_running_state(False))

            # Return results if this was called from AI
            if from_ai:
                return columns, result

        if from_ai:
            # Run synchronously for AI calls
            columns, result = run_query(query)
            self._update_result_tree(columns, result)
            self.set_query_running_state(False)
            
            # Check if DDL and refresh schema if needed
            first_word = query.strip().split()[0].lower()
            if first_word in {"create", "drop", "alter", "rename"}:
                self.refresh_schema()
                
            return columns, result
        else:
            # Run asynchronously for user calls
            threading.Thread(target=run_in_thread).start()

    def process_ai_response_with_tools(self):
        """Process AI response, handling any tool calls synchronously."""
        schema_string = self.get_latest_schema_string()
        system_prompt = (
            "You are a high-agency expert at SQL and databases. You're a world-class senior developer and assistant. "
            "Review user requests and outline clear multi-step plans. "
            "For SELECT queries, execute them automatically. "
            "For data-changing operations (INSERT, UPDATE, DELETE), ask for confirmation ONCE, then execute immediately when approved. "
            "Use the run_sql_query tool to execute queries. Don't display raw SQL unless necessary. "
            "Database schema:\n\n" + schema_string
        )
        
        # Build the complete messages list including system prompt
        messages_for_api = [{"role": "system", "content": system_prompt}] + self.chat_history
        
        response_message = ask_ai_with_tools(messages_for_api)
        
        # Handle content response
        if hasattr(response_message, 'content') and response_message.content:
            # Add assistant's content message to history
            assistant_msg = {
                "role": "assistant",
                "content": response_message.content
            }
            if hasattr(response_message, 'tool_calls') and response_message.tool_calls:
                # Convert tool calls to serializable format
                assistant_msg["tool_calls"] = json.dumps([
                    tc.model_dump() if hasattr(tc, 'model_dump') else tc 
                    for tc in response_message.tool_calls
                ])
            self.chat_history.append(assistant_msg)
            self.append_chat_message("AI", response_message.content)
        elif hasattr(response_message, 'tool_calls') and response_message.tool_calls:
            # Add assistant message with only tool calls (no content)
            assistant_msg = {
                "role": "assistant",
                "tool_calls": [
                    tc.model_dump() if hasattr(tc, 'model_dump') else tc 
                    for tc in response_message.tool_calls
                ]
            }
            self.chat_history.append(assistant_msg)
        
        # Handle tool calls
        if hasattr(response_message, 'tool_calls') and response_message.tool_calls:
            tool_responses_added = False
            
            # Process each tool call
            for tool_call in response_message.tool_calls:
                if hasattr(tool_call, 'function'):
                    func = tool_call.function
                    if func.name == "run_sql_query":
                        try:
                            func_args = json.loads(func.arguments)
                            sql_query = func_args.get("query", "")
                            
                            # Update SQL editor
                            self.sql_text.delete('1.0', tk.END)
                            self.sql_text.insert(tk.END, sql_query)
                            
                            # Execute query
                            columns, result = self.run_sql_query(from_ai=True, ai_query=sql_query) or ([], [])
                            
                            # Add tool response to chat history
                            tool_response = {
                                "role": "tool",
                                "tool_call_id": tool_call.id,
                                "content": json.dumps({
                                    "query_executed": sql_query,
                                    "columns": columns,
                                    "result": result
                                }, default=str)
                            }
                            self.chat_history.append(tool_response)
                            tool_responses_added = True
                            
                        except Exception as e:
                            # Add error response
                            error_response = {
                                "role": "tool",
                                "tool_call_id": tool_call.id,
                                "content": f"Error executing query: {str(e)}"
                            }
                            self.chat_history.append(error_response)
                            tool_responses_added = True
            
            # If we added tool responses, continue the conversation
            if tool_responses_added:
                self.process_ai_response_with_tools()

    def send_chat(self, event=None):
        """Send a message to the AI chat and display the response, supporting tool calls."""
        if self.is_ai_thinking:
            return 'break'

        user_msg = self.chat_entry.get('1.0', tk.END).strip()
        if not user_msg:
            return 'break'

        self.set_ai_thinking_state(True)
        self.chat_history.append({"role": "user", "content": user_msg})
        self.append_chat_message("You", user_msg)
        self.chat_entry.delete('1.0', tk.END)

        def ask_in_thread():
            try:
                self.process_ai_response_with_tools()
            except Exception as e:
                self.append_chat_message("System", f"Error: {str(e)}")
            finally:
                self.set_ai_thinking_state(False)
                
        threading.Thread(target=ask_in_thread).start()
        return 'break'

    def use_ai_for_query(self):
        """Generate a SQL query using AI based on the editor's text."""
        if self.is_ai_thinking:
            return

        prompt = self.sql_text.get('1.0', tk.END).strip()
        if not prompt:
            messagebox.showinfo("AI SQL Generator", "Please enter your request in the SQL editor area.")
            return

        self.set_ai_thinking_state(True)

        schema_string = self.get_latest_schema_string()
        messages = [
            {"role": "system", "content": f"You are a SQL query generator. Output only the SQL query, no explanations or backticks. Database schema:\n\n{schema_string}"},
            {"role": "user", "content": prompt}
        ]
        
        def ai_generate():
            try:
                query = ask_ai(messages)
                if query:
                    self.sql_text.delete('1.0', tk.END)
                    self.sql_text.insert(tk.END, query.strip())
            finally:
                self.set_ai_thinking_state(False)

        threading.Thread(target=ai_generate).start()

    def append_chat_message(self, sender, message):
        """Append a message to the chat display with distinct styling."""
        self.chat_display.config(state='normal')
        if sender == "You":
            self.chat_display.insert(tk.END, f"{sender}:\n", "user")
            self.chat_display.insert(tk.END, f"{message}\n\n", "user")
        elif sender == "AI":
            self.chat_display.insert(tk.END, f"{sender}:\n", "ai")
            self.chat_display.insert(tk.END, f"{message}\n\n", "ai")
        else:
            self.chat_display.insert(tk.END, f"{sender}: {message}\n\n")
        self.chat_display.insert(tk.END, "─" * 40 + "\n\n", "separator")
        self.chat_display.config(state='disabled')
        self.chat_display.see(tk.END)

    def confirm_clear_chat(self):
        """Asks for confirmation before clearing the chat history."""
        if messagebox.askyesno("Clear Chat", "Are you sure you want to clear the AI chat history?"):
            self.clear_chat()

    def clear_chat(self):
        """Clear the chat history and display."""
        self.chat_history = []
        self.chat_display.config(state='normal')
        self.chat_display.delete('1.0', tk.END)
        self.chat_display.config(state='disabled')

    def sql_history_up(self, event=None):
        """Cycle up through SQL history."""
        if not self.sql_history:
            return 'break'
        if self.sql_history_index is None:
            self.sql_history_index = len(self.sql_history) - 1
        elif self.sql_history_index > 0:
            self.sql_history_index -= 1
        self.sql_text.delete('1.0', tk.END)
        self.sql_text.insert(tk.END, self.sql_history[self.sql_history_index])
        return 'break'

    def sql_history_down(self, event=None):
        """Cycle down through SQL history."""
        if self.sql_history_index is None:
            return 'break'
        if self.sql_history_index < len(self.sql_history) - 1:
            self.sql_history_index += 1
            self.sql_text.delete('1.0', tk.END)
            self.sql_text.insert(tk.END, self.sql_history[self.sql_history_index])
        else:
            self.sql_text.delete('1.0', tk.END)
            self.sql_history_index = None
        return 'break'

    def on_tree_select(self, event):
        """Handles selection of a cell in the result treeview."""
        if self.selected_item is not None:
            self.result_tree.item(self.selected_item, tags=())
        item = self.result_tree.identify_row(event.y)
        col = self.result_tree.identify_column(event.x)
        if item and col:
            col_num = int(col.replace('#', '')) - 1
            values = self.result_tree.item(item, 'values')
            if 0 <= col_num < len(values):
                self.selected_value = str(values[col_num])
                self.selected_item = item
                self.selected_col = col_num
                self.result_tree.item(item, tags=('selected_cell',))
                preview = self.selected_value.replace('\n', ' ')
                if len(preview) > 80:
                    preview = preview[:77] + '...'
                self.selected_value_label.config(text=f"Selected: {preview}")
            else:
                self.selected_value = None
                self.selected_item = None
                self.selected_col = None
                self.selected_value_label.config(text="Selected: None")
        else:
            self.selected_value = None
            self.selected_item = None
            self.selected_col = None
            self.selected_value_label.config(text="Selected: None")

    def copy_selected_cell(self, event=None):
        """Copy the selected cell value to the clipboard."""
        if hasattr(self, 'selected_value') and self.selected_value:
            self.clipboard_clear()
            self.clipboard_append(self.selected_value)

    def ctrl_enter_run_query(self, event=None):
        """Run the SQL query with Ctrl+Enter."""
        self.run_sql_query()
        return 'break'

if __name__ == "__main__":
    app = DBViewerGUI()
    app.mainloop()
