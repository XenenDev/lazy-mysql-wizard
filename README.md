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

## Project Requirements

The application is built with Python and requires the following major dependencies:

- **Python 3.7+**: Core runtime environment
- **tkinter**: GUI framework (usually included with Python)
- **mysql-connector-python**: MySQL database connectivity
- **openai**: AI integration (optional, for GPT-4 features)
- **python-dotenv**: Environment variable management
- **Additional GUI libraries**: For enhanced interface components

![screenshot](https://github.com/user-attachments/assets/b5322851-ec20-4c84-b0fd-26e987c91978)

## Setup
1. **Install dependencies**
   ```sh
   pip install -r requirements.txt
   ```
2. **Configure database connection**
   - Create a `.env` file in the project root with your database credentials:
   ```env
   # Database Configuration
   DB_HOST=localhost
   DB_PORT=3306
   DB_USER=your_username
   DB_PASSWORD=your_password
   DB_NAME=your_database_name
   
   # AI Integration (Optional)
   OPENAI_API_KEY=your_openai_api_key_here
   ```
   - Alternatively, you can set these values directly in the script.
3. **Run the app**
   ```sh
   python db_viewer_gui.py
   ```

## AI Features Setup

The AI integration is **completely optional** and the application works perfectly as a standard MySQL database viewer without it.

### Using AI Features
- **OpenAI API Key**: To enable AI features, add your OpenAI API key to the `.env` file as shown above
- **No API Key**: If no API key is provided, the AI chat and query generation features will be disabled
- **Cost**: AI features use OpenAI's API and will incur costs based on your usage
- **Privacy**: Your database schema and queries are sent to OpenAI for processing when using AI features

### Without AI Features
- Full SQL editor with syntax highlighting
- Query execution and results viewing
- Query history browsing
- Dark/light mode toggle
- All core database management functionality

## Supported Platforms

lazy-mysql-wizard has been tested and is supported on:

- **Windows**: Windows 10/11 (Python 3.7+)
- **macOS**: macOS 10.14+ (Python 3.7+)
- **Linux**: Most distributions with Python 3.7+ and tkinter support
  - Ubuntu 18.04+
  - Debian 10+
  - CentOS 7+
  - Fedora 30+

### Platform-Specific Notes
- **Linux**: Some distributions may require installing tkinter separately: `sudo apt-get install python3-tk`
- **macOS**: Python installed via Homebrew includes tkinter by default
- **Windows**: Python from python.org includes tkinter by default

## Keyboard Shortcuts
- `Ctrl+D`: Toggle light/dark mode
- `Ctrl+Enter`: Run query (when in SQL editor)
- `Ctrl+Shift+Enter`: Use AI to generate a query from your prompt
- `Up/Down`: Browse previous SQL commands

## Troubleshooting

### Common Issues

#### "tkinter not found" Error
- **Linux**: Install tkinter with `sudo apt-get install python3-tk` (Ubuntu/Debian) or equivalent for your distribution
- **macOS**: Ensure you're using Python from python.org or Homebrew, not the system Python
- **Windows**: Reinstall Python from python.org with the "Add to PATH" option checked

#### MySQL Connection Errors
- **"Access denied"**: Check your username and password in the `.env` file
- **"Can't connect to MySQL server"**: Verify the host and port are correct
- **"Unknown database"**: Ensure the database name exists and you have access to it
- **Firewall issues**: Check if your firewall allows connections to MySQL port (default 3306)

#### AI API Errors
- **"Invalid API key"**: Verify your OpenAI API key is correct in the `.env` file
- **"Rate limit exceeded"**: You've exceeded your OpenAI API quota, wait or upgrade your plan
- **"API timeout"**: Check your internet connection or try again later

#### Application Won't Start
- **Missing dependencies**: Run `pip install -r requirements.txt` to install all required packages
- **Python version**: Ensure you're using Python 3.7 or higher
- **File not found**: Make sure you're running the command from the project directory

#### GUI Issues
- **Interface appears broken**: Try toggling dark/light mode with `Ctrl+D`
- **Text too small/large**: This may be a display scaling issue on high-DPI screens
- **Window won't resize**: Close and restart the application

## Why Use lazy-mysql-wizard?
- No need to memorize MySQL syntax or best practices
- Get expert-level SQL help instantly
- Edit, review, and run queries safely
- Modern, user-friendly interface
- Optional AI features—works as a classic DB viewer too

## Contributing

We welcome contributions to lazy-mysql-wizard! Whether you're reporting bugs, suggesting features, or submitting code changes, your help is appreciated.

### How to Contribute
- **Bug Reports**: Use [GitHub Issues](https://github.com/XenenDev/lazy-mysql-wizard/issues) to report bugs
- **Feature Requests**: Submit feature ideas through [GitHub Issues](https://github.com/XenenDev/lazy-mysql-wizard/issues)
- **Code Contributions**: Fork the repository, make your changes, and submit a pull request

For detailed contribution guidelines, please see [CONTRIBUTING.md](CONTRIBUTING.md) *(coming soon)*.

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## Contact / Support

- **Bug Reports**: [GitHub Issues](https://github.com/XenenDev/lazy-mysql-wizard/issues)
- **Feature Requests**: [GitHub Issues](https://github.com/XenenDev/lazy-mysql-wizard/issues)
- **General Questions**: Open a [GitHub Discussion](https://github.com/XenenDev/lazy-mysql-wizard/discussions)

For urgent issues or security concerns, please contact the maintainer directly through GitHub.

## Author
- Xander

Happy Programming!

