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
        return None, None # Connection failed, return None for both
    try:
        cursor = connection.cursor()
        cursor.execute(query)
        # Check if the query is a SELECT statement to fetch results
        if query.strip().lower().startswith("select") or query.strip().lower().startswith("show"):
            if cursor.description is None:
                return [], [] # No columns or results for some SHOW commands
            columns = [desc[0] for desc in cursor.description]
            results = cursor.fetchall() or []
            return columns, results
        else:
            # For DML/DDL queries, commit changes and return success message
            connection.commit()
            return None, f"Query executed successfully: {query}"
    except Exception as e:
        # Return error message if query fails
        return None, str(e)
    finally:
        if connection:
            connection.close()

# --- OPENAI ---
openai_client = openai.Client(api_key=OPENAI_API_KEY)

def ask_ai(messages):
    """Sends a list of messages to the AI model and returns the text response."""
    try:
        response = openai_client.chat.completions.create( # Use chat.completions.create for chat models
            model="gpt-4o-mini", # Using gpt-4o-mini as a common alternative
            messages=messages # 'messages' instead of 'input' for chat models
        )
        return response.choices[0].message.content
    except Exception as e:
        return f"AI Error: {e}"

def ask_ai_with_tools(messages, tool_outputs=None):
    """
    Uses OpenAI tool-calling API to allow the AI to request running SQL queries.
    If tool_outputs is provided, it should be a list of tool call output messages.
    """
    tools = [{
        "type": "function",
        "function": {
            "name": "run_sql_query",
            "description": "Run a SQL query on the MySQL database. Only use this tool for safe, well-formed queries that match the schema. You don't need to ask the user to confirm the running of a query as the user will be asked to confirm it automatically through the app's gui. The user may choose to edit the query before running it through the gui, meaning the result may be different from what you expected, you will always be notified of the final query that was run.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "The SQL query to run."}
                },
                "required": ["query"],
            }
        }
    }]
    input_msgs = messages.copy()
    if tool_outputs:
        input_msgs.extend(tool_outputs)

    try:
        response = openai_client.chat.completions.create(
            model="gpt-4o-mini", # Using gpt-4o-mini as a common alternative
            messages=input_msgs,
            tools=tools,
            tool_choice="auto" # Let the model decide whether to call a tool
        )
        return response.choices[0].message # Return the message object directly
    except Exception as e:
        # Return a message object with error content
        return type('obj', (object,), {'content': f"AI Error: {e}", 'tool_calls': None})()


# --- DPI AWARENESS (Windows) ---
if sys.platform == "win32":
    try:
        import ctypes
        ctypes.windll.shcore.SetProcessDpiAwareness(1)  # Enable per-monitor DPI awareness
    except Exception:
        pass

# --- GUI ---
class DBViewerGUI(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Database Viewer & AI Chat")
        self.geometry("1200x1000")
        self.is_dark_mode = False
        self.create_widgets() # Create widgets and set initial style properties
        self.tables = get_tables_and_columns()
        self.chat_history = []
        self.sql_history = []
        self.sql_history_index = None
        self.pending_tool_call = None  # Initialize pending tool call
        self.sql_text.bind('<Up>', self.sql_history_up)
        self.sql_text.bind('<Down>', self.sql_history_down)
        self.bind_all('<Control-d>', self.toggle_dark_mode)
        # Focus and bring window to front on launch (Windows)
        self.lift()
        self.attributes('-topmost', True)
        self.after(100, lambda: self.attributes('-topmost', False))
        self.focus_force()

        # State variables for button disabling
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
            chat_user_bg = "#4a4e55" # Darker background for user messages
            chat_ai_bg = "#3a3f4b"   # Slightly lighter background for AI messages
        else:
            bg = "#f3f3f3"
            fg = "#222"
            border = "#bbb"
            entry_bg = "#f3f3f3"
            select_bg = "#cce5ff"
            chat_user_bg = "#e0e0e0" # Light background for user messages
            chat_ai_bg = "#f0f0f0"   # Even lighter background for AI messages

        self.configure(background=bg)  # Set root window background
        default_font = ("Segoe UI", 12)
        self.option_add("*Font", default_font)
        self.option_add("*TButton.Font", default_font)
        self.option_add("*TLabel.Font", default_font)
        # self.option_add("*TEntry.Font", default_font) # Removed for multiline chat_entry
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
        # Ensure chat_display exists before configuring its tags
        if hasattr(self, 'chat_display'):
            # Swapped justify for user and AI messages
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
        # Update backgrounds and borders for all section frames and widgets
        self.configure(background=self.section_bg)  # Update root window background
        for frame in [self.sql_section, self.result_section, self.chat_section]:
            frame.config(background=self.section_bg, highlightbackground=self.section_border_color, highlightcolor=self.section_border_color)
        for label in [self.sql_label, self.result_label, self.chat_label]:
            label.config(background=self.section_bg, foreground=self.section_fg)
        self.sql_text.config(background=self.entry_bg, foreground=self.section_fg, insertbackground=self.section_fg)
        self.result_tree.tag_configure('selected_cell', background=self.select_bg)
        self.selected_value_label.config(background=self.section_bg, foreground=self.section_fg)
        self.chat_display.config(background=self.entry_bg, foreground=self.section_fg, insertbackground=self.section_fg)
        # Update chat entry (now scrolledtext)
        self.chat_entry.config(background=self.entry_bg, foreground=self.section_fg, insertbackground=self.section_fg,
                               highlightbackground=self.section_border_color, highlightcolor=self.section_border_color) # Added highlight for border

    def create_widgets(self):
        """Set up all widgets for the GUI."""
        # Call set_modern_style first to initialize style properties
        self.set_modern_style()

        # SQL Editor Section
        self.sql_section = tk.Frame(self, background=self.section_bg, highlightbackground=self.section_border_color, highlightcolor=self.section_border_color, highlightthickness=1, bd=0)
        self.sql_section.pack(fill='x', padx=16, pady=(16, 8))
        self.sql_label = ttk.Label(self.sql_section, text="SQL Editor", font=("Segoe UI Semibold", 13), background=self.section_bg, foreground=self.section_fg)
        self.sql_label.pack(anchor='w', padx=2, pady=(0, 4))
        self.sql_text = scrolledtext.ScrolledText(self.sql_section, height=4, font=("Consolas", 12), borderwidth=0, relief="flat", background=self.entry_bg, foreground=self.section_fg, insertbackground=self.section_fg)
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
        self.result_section = tk.Frame(self, background=self.section_bg, highlightbackground=self.section_border_color, highlightcolor=self.section_border_color, highlightthickness=1, bd=0)
        self.result_section.pack(fill='both', expand=True, padx=16, pady=(8, 4))
        self.result_label = ttk.Label(self.result_section, text="Results", font=("Segoe UI Semibold", 13), background=self.section_bg, foreground=self.section_fg)
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
        self.selected_value_label = ttk.Label(self.result_section, text="Selected: None", anchor='w', background=self.section_bg, foreground=self.section_fg)
        self.selected_value_label.pack(fill='x', padx=2, pady=(4,0))

        # AI Chat Section
        self.chat_section = tk.Frame(self, background=self.section_bg, highlightbackground=self.section_border_color, highlightcolor=self.section_border_color, highlightthickness=1, bd=0)
        self.chat_section.pack(fill='both', expand=True, padx=16, pady=(4, 16))
        self.chat_label = ttk.Label(self.chat_section, text="AI Chat", font=("Segoe UI Semibold", 13), background=self.section_bg, foreground=self.section_fg)
        self.chat_label.pack(anchor='w', padx=2, pady=(0, 4))

        self.chat_display = scrolledtext.ScrolledText(self.chat_section, height=8, state='normal', wrap='word', font=("Segoe UI", 12), borderwidth=0, relief="flat", background=self.entry_bg, foreground=self.section_fg, insertbackground=self.section_fg)
        self.chat_display.pack(fill='both', expand=True, padx=0, pady=(0,0))
        self.chat_display.config(state='disabled')

        # Enable text selection in chat_display
        self.chat_display.config(state='normal')  # Allow selection
        self.chat_display.bind('<1>', lambda e: self.chat_display.focus_set())  # Focus on click
        self.chat_display.config(state='disabled')  # Keep disabled for editing, but selection is possible

        # Chat message tags configured here, after chat_display is created
        # These will be updated again in set_modern_style and update_section_styles for theme changes
        # Swapped justify for user and AI messages
        self.chat_display.tag_configure("user", justify='right', lmargin1=10, lmargin2=10, rmargin=10)
        self.chat_display.tag_configure("ai", justify='left', lmargin1=10, lmargin2=10, rmargin=10)
        self.chat_display.tag_configure("separator", justify='center')


        chat_entry_frame = ttk.Frame(self.chat_section)
        chat_entry_frame.pack(fill='x', padx=0, pady=(8,0), side='bottom')

        # Changed to ScrolledText for multiline chat input
        # Added highlightthickness and highlightbackground for a visible border
        self.chat_entry = scrolledtext.ScrolledText(chat_entry_frame, height=3, font=("Segoe UI", 12), borderwidth=1, relief="flat",
                                                    background=self.entry_bg, foreground=self.section_fg, insertbackground=self.section_fg,
                                                    highlightthickness=1, highlightbackground=self.section_border_color)
        self.chat_entry.pack(side='left', fill='x', expand=True)
        self.chat_entry.bind('<Control-Return>', self.send_chat) # Bind Ctrl+Enter to send_chat

        self.send_btn = ttk.Button(chat_entry_frame, text="Send", command=self.send_chat)
        self.send_btn.pack(side='left', padx=(8,0))

        clear_btn = ttk.Button(chat_entry_frame, text="Clear Chat", command=self.confirm_clear_chat)
        clear_btn.pack(side='left', padx=(8,0))

        # Update all section styles for current mode
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
            self.chat_entry.mark_set(tk.INSERT, tk.END) # Set cursor to end
        else:
            self.chat_entry.delete('1.0', tk.END) # Clear "Thinking..."
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
                schema_string += f" - {col}\n"
            schema_string += "\n"
        return schema_string

    def _execute_sql_and_handle_tool_output(self, query, tool_call_obj=None):
        """
        Executes a SQL query and handles potential tool output for AI continuation.
        This function is intended to be called synchronously within a thread.
        """
        columns, result = run_query(query)  # Synchronous DB call

        # If DDL, refresh schema
        if query.strip().split()[0].lower() in {"create", "drop", "alter", "rename"}:
            self.refresh_schema()

        # Update UI with results (must be done on the main thread)
        self.after(0, lambda: self._update_result_tree(columns, result))

        # If this execution was triggered by an AI tool call, prepare and append tool output
        if tool_call_obj:
            # append the "tool" message expected by the API, answering the tool_call_id
            tool_output_msg = {
                "role": "tool",
                "tool_call_id": tool_call_obj.id,
                "content": json.dumps({
                    "query_executed": query,
                    "columns": columns,
                    "result": result
                }, default=str)
            }
            self.chat_history.append(tool_output_msg)
            return True  # Indicate that tool output was handled
        return False  # Indicate no tool output handling was done
    
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

    def run_sql_query(self):
        """Run the SQL query in the editor and display results."""
        if self.is_query_running:
            return

        query = self.sql_text.get('1.0', tk.END).strip()
        if not query:
            return

        self.set_query_running_state(True)

        if not self.sql_history or (self.sql_history and query != self.sql_history[-1]):
            self.sql_history.append(query)
        self.sql_history_index = None

        def run_in_thread():
            # Capture any pending tool call (from AI) and clear it
            current_pending_tool_call = self.pending_tool_call
            self.pending_tool_call = None

            tool_output_handled = self._execute_sql_and_handle_tool_output(query, current_pending_tool_call)

            if tool_output_handled:
                # Continue the AI conversation now that the tool output has been appended
                self.continue_ai_conversation()
            else:
                # No tool involved, simply re-enable buttons
                self.after(0, lambda: self.set_query_running_state(False))

        threading.Thread(target=run_in_thread).start()

    def continue_ai_conversation(self):
        """Continues the AI conversation after a tool call output has been processed."""
        def continue_ai_in_thread():
            self.set_ai_thinking_state(True)
            try:
                schema_string = self.get_latest_schema_string()
                system_prompt = (
                    "You are a helpful, high-agency AI assistant for SQL and database questions. "
                    "The user has approved and executed a SQL query. Use the provided output to inform your next reasoning steps without asking for confirmation again. "
                    "Suggest additional safe, well-formed SQL queries matching the schema only if needed, and do not request confirmation for already executed actions. "
                    "Here is the schema for all tables in the database:\n\n" + schema_string
                )
                messages_for_ai = [{"role": "system", "content": system_prompt}] + self.chat_history

                response_message = ask_ai_with_tools(messages_for_ai)
                tool_calls = self.get_tool_calls(response_message)
                if tool_calls:
                    # Assistant message with tool_calls
                    self.chat_history.append({
                        "role": "assistant",
                        "tool_calls": [tc.model_dump() if hasattr(tc, 'model_dump') else tc for tc in tool_calls]
                    })

                    # **FIX**: immediately follow up with the corresponding "tool" messages
                    for tc in tool_calls:
                        func = self.get_func(tc)
                        func_name = self.get_func_name(func)
                        func_args = json.loads(self.get_func_args(func) or "{}")
                        if func_name == "run_sql_query":
                            sql = func_args.get("query", "")
                            # execute the tool
                            self._execute_sql_and_handle_tool_output(sql, tc)

                    # no further re-enabling here; continue_ai_conversation will handle it
                elif self.get_content(response_message):
                    text2 = self.get_content(response_message)
                    self.chat_history.append({"role": "assistant", "content": text2})
                    self.append_chat_message("AI", text2)
                else:
                    fallback2 = "AI did not provide a clear response or tool call."
                    self.chat_history.append({"role": "assistant", "content": fallback2})
                    self.append_chat_message("AI", fallback2)
            finally:
                self.set_ai_thinking_state(False)
                self.set_query_running_state(False)
        threading.Thread(target=continue_ai_in_thread).start()

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
                schema_string = self.get_latest_schema_string()
                system_prompt = (
                    "You are a high-agency expert at SQL and databases and your job is a world-class, seasoned senior developer and now assistant for SQL and database questions for the user. You may also be asked to make changes to the database, you should be assertive and lead the user with a action plan while considering the users wants and requirements, which they may not make clear. First, review the user's request and outline a clear multi-step plan in natural language. "
                    "For read-only (SELECT) queries, execute them automatically without asking for individual confirmation. "
                    "For data-changing operations (INSERT, UPDATE, DELETE): ask for confirmation ONCE, then when the user approves (says yes, okay, go ahead, proceed, etc.), IMMEDIATELY execute the operation using the run_sql_query tool in the same response. Do not describe what you will do again - just execute it. "
                    "Do not display raw SQL unless necessary; instead, describe your intended actions and reasoning. "
                    "Use only safe, well-formed SQL that matches the provided schema. "
                    "Here is the database schema:\n\n" + schema_string
                )
                messages_for_ai = [{"role": "system", "content": system_prompt}] + self.chat_history

                response_message = ask_ai_with_tools(messages_for_ai)
                tool_calls = self.get_tool_calls(response_message)
                if tool_calls:
                    # Assistant message with tool_calls
                    self.chat_history.append({
                        "role": "assistant",
                        "tool_calls": [tc.model_dump() if hasattr(tc, 'model_dump') else tc for tc in tool_calls]
                    })

                    # **FIX**: immediately follow up with each tool execution message
                    for tc in tool_calls:
                        func = self.get_func(tc)
                        func_name = self.get_func_name(func)
                        func_args = json.loads(self.get_func_args(func) or "{}")
                        if func_name == "run_sql_query":
                            sql_query = func_args.get("query", "")
                            self.sql_text.delete('1.0', tk.END)
                            self.sql_text.insert(tk.END, sql_query)
                            self.pending_tool_call = tc
                            # execute regardless of SELECT vs. modification
                            self.run_sql_query()
                        else:
                            self.append_chat_message("AI", f"AI requested an unknown tool: {func_name}")
                elif self.get_content(response_message):
                    text = self.get_content(response_message)
                    self.chat_history.append({"role": "assistant", "content": text})
                    self.append_chat_message("AI", text)
                else:
                    fallback = "AI did not provide a clear response."
                    self.chat_history.append({"role": "assistant", "content": fallback})
                    self.append_chat_message("AI", fallback)
            finally:
                # Note: run_sql_query / continue_ai_conversation will reset thinking state
                if not self.is_query_running:
                    self.set_ai_thinking_state(False)
        threading.Thread(target=ask_in_thread).start()
        return 'break'

    def use_ai_for_query(self):
        """Generate a SQL query using AI based on the editor's text."""
        if self.is_ai_thinking:
            return # Prevent multiple AI calls

        prompt = self.sql_text.get('1.0', tk.END).strip()
        if not prompt:
            messagebox.showinfo("AI SQL Generator", "Please enter your request in the SQL editor area.")
            return

        self.set_ai_thinking_state(True) # Disable chat input and show thinking

        schema_string = self.get_latest_schema_string()
        messages = [
            {"role": "system", "content": f"You are a helpful AI assistant that generates SQL queries based on user requests (which may be very vague, but you must try your best!). Only output the completed SQL prompt, nothing else, DO NOT USE BACKTICKS!. For reference here is the database's entire schema for every table, you may want to infer the desire of the user's request based on the context given here:\n\n{schema_string}"},
            {"role": "user", "content": prompt}
        ]
        # Patch: fix NoneType for query in use_ai_for_query
        def ai_generate():
            try:
                query = ask_ai(messages)
                if query is None:
                    query = ''
                self.sql_text.delete('1.0', tk.END)
                self.sql_text.insert(tk.END, query)
            finally:
                self.set_ai_thinking_state(False) # Re-enable chat input

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
        # Add a separator line
        self.chat_display.insert(tk.END, "----------------------------------------\n\n", "separator")
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
        # Remove previous highlight
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
                # Truncate preview to 80 chars, single line
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
        if self.selected_value:
            self.clipboard_clear()
            self.clipboard_append(self.selected_value)

    def ctrl_enter_run_query(self, event=None):
        """Run the SQL query with Ctrl+Enter."""
        self.run_sql_query()
        return 'break'


# --- OpenAI response helper methods (class scope) ---
    def get_tool_calls(self, resp):
        if hasattr(resp, 'tool_calls'):
            return resp.tool_calls
        if isinstance(resp, dict) and 'tool_calls' in resp:
            return resp['tool_calls']
        return None

    def get_content(self, resp):
        if hasattr(resp, 'content'):
            return resp.content
        if isinstance(resp, dict) and 'content' in resp:
            return resp['content']
        return None

    def get_func(self, function_call):
        if hasattr(function_call, 'function'):
            return function_call.function
        elif isinstance(function_call, dict) and 'function' in function_call:
            return function_call['function']
        return None

    def get_func_name(self, func):
        if hasattr(func, 'name'):
            return func.name
        elif isinstance(func, dict) and 'name' in func:
            return func['name']
        return None

    def get_func_args(self, func):
        if hasattr(func, 'arguments'):
            return func.arguments
        elif isinstance(func, dict) and 'arguments' in func:
            return func['arguments']
        return None

if __name__ == "__main__":
    app = DBViewerGUI()
    app.mainloop()
