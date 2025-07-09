# lazy-mysql-wizard

A modern Python Tkinter application for effortless MySQL database management, powered by GPT-4.1 AI integration. 

## Features
- **AI MySQL Assistant**: Ask an AI expert to generate, review, and run SQL queries for you. The AI is context-aware of your database schema and can chain together complex operations, only asking for confirmation when needed.
- **Modern GUI**: Clean, flat, and responsive interface with dark mode, section borders, and a results table.
- **SQL Editor & History**: Edit, review, and run SQL queries. Browse your query history with up/down arrows.
- **Results Viewer**: View, select, and copy table results. Highlight and preview cell values.
- **AI Chat**: Natural language chat with the AI, which can plan, reason, and execute database operations on your behalf.
- **Safety**: The AI will only ask for confirmation before running data-changing queries (INSERT, UPDATE, DELETE). SELECT queries and safe operations are run automatically.
- **Customizable**: Edit queries before running, and view all AI-generated SQL before execution.
- **No API Key Required**: AI features are optional; you can use the app as a lightweight DB viewer without OpenAI integration.

![screenshot](https://github.com/user-attachments/assets/b5322851-ec20-4c84-b0fd-26e987c91978)

## Setup
1. **Install dependencies**
   ```sh
   pip install -r requirements.txt
   ```
2. **Configure database connection**
   - Set your DB credentials in a `.env` file or directly in the script.
   ```env
   DB_HOST=your-db-host
   DB_USER=your-db-user
   DB_PASSWORD=your-db-password
   DB_NAME=your-db-name
   DB_PORT=3306
   OPENAI_API_KEY=your-openai-api-key
   ```
3. **Run the app**
   ```sh
   python db_viewer_gui.py
   ```

## Keyboard Shortcuts
- `Ctrl+D`: Toggle light/dark mode
- `Ctrl+Enter`: Run query (when in SQL editor)
- `Ctrl+Shift+Enter`: Use AI to generate a query from your prompt
- `Up/Down`: Browse previous SQL commands

## Why Use lazy-mysql-wizard?
- No need to memorize MySQL syntax or best practices
- Get expert-level SQL help instantly
- Edit, review, and run queries safely
- Modern, user-friendly interface
- Optional AI features—works as a classic DB viewer too

## Author
- Xander

Happy Programming!

