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
    try:
        return mysql.connector.connect(**DB_CONFIG)
    except Exception as e:
        messagebox.showerror("DB Error", str(e))
        return None

def get_tables_and_columns():
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
        connection.close()
    return tables

def run_query(query):
    connection = connect_to_database()
    if not connection:
        return None, None
    try:
        cursor = connection.cursor()
        cursor.execute(query)
        if query.strip().lower().startswith("select"):
            if cursor.description is None:
                return None, "No results."
            columns = [desc[0] for desc in cursor.description]
            results = cursor.fetchall() or []
            return columns, results
        else:
            connection.commit()
            return None, f"Query executed successfully: {query}"
    except Exception as e:
        return None, str(e)
    finally:
        connection.close()

# --- OPENAI ---
openai_client = openai.Client(api_key=OPENAI_API_KEY)

def ask_ai(messages):
    try:
        response = openai_client.responses.create(
            model="gpt-4.1-mini",
            input=messages
        )
        return response.output_text
    except Exception as e:
        return f"AI Error: {e}"

def ask_ai_with_tools(messages, tool_outputs=None):
    """
    Use OpenAI tool-calling API to allow the AI to request running SQL queries.
    If tool_outputs is provided, it should be a list of tool call output messages.
    """
    tools = [{
        "type": "function",
        "name": "run_sql_query",
        "description": "Run a SQL query on the MySQL database. Only use this tool for safe, well-formed queries that match the schema. You don't need to ask the user to confirm the running of a query as the user will be asked to confirm it automatically through the app's gui. The user may choose to edit the query before running it through the gui, meaning the result may be different from what you expected, you will always be notified of the final query that was run.",
        "strict": True,
        "parameters": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "The SQL query to run."}
            },
            "required": ["query"],
            "additionalProperties": False
        }
    }]
    input_msgs = messages.copy()
    if tool_outputs:
        input_msgs.extend(tool_outputs)
    response = openai_client.responses.create(
        model="gpt-4.1-mini",
        input=input_msgs,
        tools=tools,
    )
    return response

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
        self.geometry("900x1000")
        self.is_dark_mode = False
        self.set_modern_style()
        self.tables = get_tables_and_columns()
        self.create_widgets()
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
        else:
            bg = "#f3f3f3"
            fg = "#222"
            border = "#bbb"
            entry_bg = "#f3f3f3"
            select_bg = "#cce5ff"
        self.configure(background=bg)  # Set root window background
        default_font = ("Segoe UI", 12)
        self.option_add("*Font", default_font)
        self.option_add("*TButton.Font", default_font)
        self.option_add("*TLabel.Font", default_font)
        self.option_add("*TEntry.Font", default_font)
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

    def toggle_dark_mode(self, event=None):
        self.is_dark_mode = not self.is_dark_mode
        self.set_modern_style()
        self.update_section_styles()

    def update_section_styles(self):
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
        # Remove direct config for ttk.Entry (not supported)
        # self.chat_entry.config(background=self.entry_bg, foreground=self.section_fg, insertbackground=self.section_fg)

    def create_widgets(self):
        """Set up all widgets for the GUI."""
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
        run_btn = ttk.Button(btn_frame, text="Run Query", command=self.run_sql_query)
        run_btn.pack(side='right', padx=(8,0))
        ai_btn = ttk.Button(btn_frame, text="Use AI", command=self.use_ai_for_query)
        ai_btn.pack(side='right', padx=(8,0))
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
        chat_entry_frame = ttk.Frame(self.chat_section)
        chat_entry_frame.pack(fill='x', padx=0, pady=(8,0), side='bottom')
        self.chat_entry = ttk.Entry(chat_entry_frame, font=("Segoe UI", 12))
        self.chat_entry.pack(side='left', fill='x', expand=True)
        self.chat_entry.bind('<Return>', self.send_chat)
        send_btn = ttk.Button(chat_entry_frame, text="Send", command=self.send_chat)
        send_btn.pack(side='left', padx=(8,0))
        self.send_btn = send_btn  # Reference to toggle state
        clear_btn = ttk.Button(chat_entry_frame, text="Clear Chat", command=self.clear_chat)
        clear_btn.pack(side='left', padx=(8,0))
        # Update all section styles for current mode
        self.update_section_styles()

    def run_sql_query(self):
        """Run the SQL query in the editor and display results. If a tool call is pending, send result back to AI."""
        query = self.sql_text.get('1.0', tk.END).strip()
        if not query:
            return
        if not self.sql_history or (self.sql_history and query != self.sql_history[-1]):
            self.sql_history.append(query)
        self.sql_history_index = None
        def run():
            columns, result = run_query(query)
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
                messagebox.showinfo("Result", msg)
            # If a tool call is pending, send result back to AI
            if hasattr(self, 'pending_tool_call') and self.pending_tool_call:
                tool_call = self.pending_tool_call
                del self.pending_tool_call
                # Prepare tool output message
                # Include executed query and result (including errors) for AI awareness
                tool_output_msg = {
                    "type": "function_call_output",
                    "call_id": tool_call.call_id,
                    "output": json.dumps({
                        "query_executed": query,
                        "columns": columns,
                        "result": result
                    }, default=str)
                }
                # Continue the AI chat loop with the tool output
                def continue_ai():
                    # Show thinking state during AI continuation
                    self.disable_chat_input()
                    try:
                        # Rebuild messages up to the tool call
                        schema_string = ""
                        for table_name, columns_ in self.tables.items():
                            schema_string += f"Table: {table_name}\n"
                            for col in columns_:
                                schema_string += f" - {col}\n"
                            schema_string += "\n"
                        system_prompt = (
                            "You are a helpful, high-agency AI assistant for SQL and database questions. "
                            "The user has approved and executed a SQL query. Use the provided output to inform your next reasoning steps without asking for confirmation again. "
                            "Suggest additional safe, well-formed SQL queries matching the schema only if needed, and do not request confirmation for already executed actions. "
                            "Here is the schema for all tables in the database:\n\n" + schema_string
                        )
                        messages = [
                            {"role": "system", "content": system_prompt}
                        ] + self.chat_history + [tool_call]
                        tool_outputs = [tool_output_msg]
                        response = ask_ai_with_tools(messages, tool_outputs)
                        for msg in response.output:
                            if msg.type == "function_call":
                                args2 = json.loads(msg.arguments)
                                sql_query2 = args2.get("query", "")
                                self.sql_text.delete('1.0', tk.END)
                                self.sql_text.insert(tk.END, sql_query2)
                                self.pending_tool_call = msg
                                return
                            elif msg.type == "message":
                                text2 = ''.join(getattr(part, 'text', str(part)) for part in msg.content)
                                self.chat_history.append({"role": "assistant", "content": text2})
                                self.append_chat_message("AI", text2)
                                return
                        # Fallback
                        fallback2 = str(response.output)
                        self.chat_history.append({"role": "assistant", "content": fallback2})
                        self.append_chat_message("AI", fallback2)
                    finally:
                        # Restore chat input after thinking
                        self.enable_chat_input()
                threading.Thread(target=continue_ai).start()
        threading.Thread(target=run).start()

    def send_chat(self, event=None):
        """Send a message to the AI chat and display the response, supporting tool calls."""
        user_msg = self.chat_entry.get().strip()
        if not user_msg:
            return
        # Disable input while AI is thinking
        self.send_btn.config(text="Thinking...", state='disabled')
        self.chat_entry.config(state='disabled')
        self.chat_history.append({"role": "user", "content": user_msg})
        self.append_chat_message("You", user_msg)
        self.chat_entry.delete(0, tk.END)
        def ask():
            try:
                schema_string = ""
                for table_name, columns in self.tables.items():
                    schema_string += f"Table: {table_name}\n"
                    for col in columns:
                        schema_string += f" - {col}\n"
                    schema_string += "\n"
                system_prompt = (
                    "You are a high-agency expert at SQL and databases and your job is a world-class, seasoned senior developer and now assistant for SQL and database questions for the user. You may also be asked to make changes to the database, you should be assertive and lead the user with a action plan while considering the users wants and requirements, which they may not make clear. First, review the user's request and outline a clear multi-step plan in natural language. "
                    "For read-only (SELECT) queries, execute them automatically without asking for individual confirmation. "
                    "For data-changing operations (INSERT, UPDATE, DELETE): ask for confirmation ONCE, then when the user approves (says yes, okay, go ahead, proceed, etc.), IMMEDIATELY execute the operation using the run_sql_query tool in the same response. Do not describe what you will do again - just execute it. "
                    "Do not display raw SQL unless necessary; instead, describe your intended actions and reasoning. "
                    "Use only safe, well-formed SQL that matches the provided schema. "
                    "Here is the database schema:\n\n" + schema_string
                )
                messages = [
                    {"role": "system", "content": system_prompt}
                ] + self.chat_history
                response = ask_ai_with_tools(messages, [])
                
                # Process all messages in the response
                message_text = ""
                function_call = None
                
                for msg in response.output:
                    if msg.type == "function_call":
                        function_call = msg
                    elif msg.type == "message":
                        text = ''.join(getattr(part, 'text', str(part)) for part in msg.content)
                        message_text += text
                
                # Display any message text first
                if message_text:
                    self.chat_history.append({"role": "assistant", "content": message_text})
                    self.append_chat_message("AI", message_text)
                
                # Then execute any function call
                if function_call:
                    args = json.loads(function_call.arguments)
                    sql_query = args.get("query", "")
                    self.sql_text.delete('1.0', tk.END)
                    self.sql_text.insert(tk.END, sql_query)
                    self.pending_tool_call = function_call
                    if sql_query.strip().lower().startswith("select"):
                        # Auto-execute read-only queries immediately
                        self.run_sql_query()
                    # For data-changing queries, user confirmation still required
                    return


                # Only show fallback if no message was processed
                if not message_text:
                    fallback = str(response.output)
                    self.chat_history.append({"role": "assistant", "content": fallback})
                    self.append_chat_message("AI", fallback)
            finally:
                # Re-enable input and clear entry
                self.send_btn.config(text="Send", state='normal')
                self.chat_entry.config(state='normal')
                self.chat_entry.delete(0, tk.END)  # Clear the chat entry after AI response
                self.chat_entry.focus_set()        # Focus back to input
        threading.Thread(target=ask).start()

    def append_chat_message(self, sender, message):
        """Append a message to the chat display."""
        self.chat_display.config(state='normal')
        self.chat_display.insert(tk.END, f"{sender}: {message}\n\n")
        self.chat_display.config(state='disabled')
        self.chat_display.see(tk.END)

    def clear_chat(self):
        """Clear the chat history and display."""
        self.chat_history = []
        self.chat_display.config(state='normal')
        self.chat_display.delete('1.0', tk.END)
        self.chat_display.config(state='disabled')

    def on_tree_select(self, event):
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

    def use_ai_for_query(self):
        """Generate a SQL query using AI based on the editor's text."""
        prompt = self.sql_text.get('1.0', tk.END).strip()
        if not prompt:
            messagebox.showinfo("AI SQL Generator", "Please enter your request in the SQL editor area.")
            return
        schema_string = ""
        for table_name, columns in self.tables.items():
            schema_string += f"Table: {table_name}\n"
            for col in columns:
                schema_string += f" - {col}\n"
            schema_string += "\n"
        messages = [
            {"role": "system", "content": f"You are a helpful AI assistant that generates SQL queries based on user requests (which may be very vague, but you must try your best!). Only output the completed SQL prompt, nothing else, DO NOT USE BACKTICKS!. For reference here is the database's entire schema for every table, you may want to infer the desire of the user's request based on the context given here:\n\n{schema_string}"},
            {"role": "user", "content": prompt}
        ]
        def ai_generate():
            query = ask_ai(messages)
            self.sql_text.delete('1.0', tk.END)
            self.sql_text.insert(tk.END, query)
        threading.Thread(target=ai_generate).start()

    def disable_chat_input(self):
        """Disable the chat input and send button, show thinking cursor."""
        self.chat_entry.config(state='disabled')
        self.send_btn.config(state='disabled')
        self.chat_entry.delete(0, tk.END)  # Clear the chat entry
        self.chat_entry.insert(0, "Thinking...")
        self.chat_entry.icursor(tk.END)

    def enable_chat_input(self):
        """Enable the chat input and send button."""
        self.chat_entry.config(state='normal')
        self.send_btn.config(state='normal')
        self.chat_entry.delete(0, tk.END)  # Clear the chat entry
        self.chat_entry.focus_set()        # Focus back to input

if __name__ == "__main__":
    app = DBViewerGUI()
    app.mainloop()
