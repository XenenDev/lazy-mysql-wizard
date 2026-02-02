# LAZY MYSQL WIZARD 🧙🪄📊

<img height="400" alt="image" src="https://github.com/user-attachments/assets/4ea54d8d-136e-4036-8d10-4018efb48391" />

An intelligent Python Tkinter application for MySQL database management powered by OpenAI's language models. Features an AI agent with configurable autonomy levels for natural language database interactions.

## Features

### AI-Powered Database Agent
- **Natural Language Interface**: Chat with an AI Database Reliability Engineer that understands your database schema
- **Configurable Agency Levels**: Control how autonomous the AI is with your data
  - **Level 1 - Draft Only**: AI generates SQL queries but never executes them automatically
  - **Level 2 - Moderate Autonomy**: AI executes simple SELECT queries; requires review for complex operations
  - **Level 3 - Full Autonomy**: AI conducts comprehensive investigations with multiple queries
- **Context-Aware**: AI maintains conversation history and understands your database schema automatically
- **Safety First**: Destructive operations (DELETE, UPDATE, DROP, ALTER) always require manual execution

### Modern Dark-Themed GUI
- **Split-Pane Interface**: Chat on the left, SQL editor and results on the right
- **Markdown Rendering**: AI responses support formatted text, code blocks, tables, and more
- **SQL Editor**: Review and manually execute AI-generated queries
- **Results Viewer**: Treeview table for displaying query results with scrollable columns
- **High-DPI Support**: Optimized for high-resolution displays on Windows

### Intelligent Query Handling
- **Tool Calling**: AI uses function calling to execute SQL or ask for clarification
- **Schema Discovery**: Automatically fetches and caches database schema for AI context
- **Safe Execution**: Built-in protection against accidental data modifications
- **Real-time Feedback**: See queries in the SQL editor as the AI generates them

## Requirements

- Python 3.7+
- MySQL database
- OpenAI API key

## Installation

1. **Clone the repository**
   ```sh
   git clone https://github.com/XenenDev/lazy-mysql-wizard.git
   cd lazy-mysql-wizard
   ```

2. **Install dependencies**
   ```sh
   pip install -r requirements.txt
   ```

3. **Configure environment variables**
   
   Create a `.env` file in the project root with your database and OpenAI credentials:
   ```env
   DB_HOST=your-db-host
   DB_USER=your-db-user
   DB_PASS=your-db-password
   DB_NAME=your-db-name
   DB_PORT=3306
   OPENAI_API_KEY=your-openai-api-key
   OPENAI_MODEL_ID=gpt-5.2
   ```
   
   **Note**: Replace the values with your actual credentials. For `OPENAI_MODEL_ID`, you can use models like `gpt-5.2`.

4. **Run the application**
   ```sh
   python app.py
   ```

## Usage

### Getting Started

1. Launch the application with `python app.py`
2. The AI will automatically load your database schema
3. Select an agency level (default is Level 2 - Moderate)
4. Start chatting with the AI about your data

### Example Queries

- "Show me all tables in the database"
- "What are the top 10 users by registration date?"
- "Find all orders from the last 30 days"
- "Create a summary of sales by product category"

### Agency Levels Explained

**Level 1 - Draft Only**
- AI generates SQL queries and explains them
- All queries must be manually executed via "Run SQL Manually" button
- Best for learning or when you want full control

**Level 2 - Moderate Autonomy** (Default)
- AI automatically executes simple SELECT queries
- Complex queries (with JOINs, subqueries) are drafted for review
- Destructive operations always require manual approval
- Balanced approach for most users

**Level 3 - Full Autonomy**
- AI executes multiple queries to thoroughly investigate your questions
- Proactively searches through tables and analyzes patterns
- Still blocks destructive operations for safety
- Best for advanced users who trust the AI

### Keyboard Shortcuts

- `Ctrl+Return` (in chat input): Send message to AI

### Manual SQL Execution

- AI-generated queries appear in the SQL Editor (right pane)
- Review the query and click "Run SQL Manually" to execute
- All destructive queries (DELETE, UPDATE, DROP, ALTER) require manual execution
- Results appear in the table below the SQL Editor

## Architecture

### Core Components

**DatabaseManager** (`class DatabaseManager`)
- Manages MySQL connections
- Fetches and caches database schema
- Executes queries with error handling

**Agent** (`class Agent`)
- OpenAI client wrapper with tool calling support
- Configurable agency levels with distinct system prompts
- Maintains conversation history and context
- Supports two tools: `run_sql_query` and `ask_user_clarification`

**MarkdownRenderer** (`class MarkdownRenderer`)
- Parses markdown text for rich formatting in chat
- Supports headers, code blocks, tables, bold, italic, and inline code
- Renders directly into Tkinter Text widgets with custom tags

**ModernSQLApp** (`class ModernSQLApp`)
- Main Tkinter GUI application
- Handles user interactions and displays results
- Coordinates between AI agent and database manager
- Implements safety checks for destructive operations

### Tool Functions

The AI agent has access to two tools:

1. **run_sql_query**: Execute SQL queries against the database
2. **ask_user_clarification**: Request more information when requests are ambiguous

## Safety Features

- **Destructive Query Protection**: DELETE, UPDATE, DROP, TRUNCATE, and ALTER queries always require manual execution
- **Agency Level Controls**: Limit AI autonomy based on your comfort level
- **Query Visibility**: All AI-generated SQL is shown in the editor before execution
- **Manual Override**: Users can always review and modify queries before running
- **Error Handling**: Database errors are caught and displayed clearly

## Dependencies

- `openai>=1.93.0` - OpenAI API client for AI agent functionality
- `mysql-connector-python` - MySQL database connectivity
- `python-dotenv` - Environment variable management from .env file
- `tkinter` - GUI framework (included with Python)

## Troubleshooting

**Connection Issues**
- Verify your `.env` file has correct database credentials
- Ensure MySQL server is running and accessible
- Check that `DB_PORT` matches your MySQL configuration

**OpenAI API Issues**
- Confirm your `OPENAI_API_KEY` is valid and has credits
- Verify the `OPENAI_MODEL_ID` is a supported model
- Check your internet connection

**High-DPI Display Issues (Windows)**
- The application includes automatic DPI awareness
- If text appears blurry, try running as administrator

## Author

Created by Xander ([XenenDev](https://github.com/XenenDev))

## License

See repository for license information.

---

**Happy Database Wizarding!** 🧙‍♂️

