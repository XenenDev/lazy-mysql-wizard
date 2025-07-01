# lazy-mysql-wizard
Python tkinter util application that provides handy MySQL and GPT-4.1 integration, allowing you to ask an AI MySQL expert to alter your database.
Perfect for those that don't have the time or are too lazy to learn all MySQL terms, syntax and best practices. lazy-mysql-wizard provides you with a SQL expert AI assistant to help make any changes you'd like to your database. You will clearly see what commands the AI wishes to run and can edit, run, and view tables with this app.
![image](https://github.com/user-attachments/assets/b5322851-ec20-4c84-b0fd-26e987c91978)

setup:
-install the required libraries (listed in requirements.txt) in the CLI you can do 'pip install -r requirements.txt
-provide env variables for the DB connection string or credentials in the .env file
-run the python script to launch the application

The AI chat feature is context-aware of your database's schema and will generate queries or sets of queries acting as a MySQL DB specalist on your behalf. Saves you time and effort from learning MySQL, or cumbersome prompting with ChatGPT (or other AI assistant) to get SQL queries and run them. This app also acts as a lightweight DB viewer, similiar to Phpmyadmin. the AI features are optional and an API key isn't required

Shortcuts:
ctrl + d: toggle between light and dark mode
ctrl + enter: run query (when cursor is in query edit box)
ctrl + shift + enter: turn the text in the edit box into a prompt, returns the AI generated prompt
up / down keys: toggle through previosuly executed MySQL commands

Happy Programming!
- Xander
