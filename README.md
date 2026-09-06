# NVLearn

NVLearn is a Flask-based study companion that helps students turn their notes into active learning material. It combines note taking, AI-assisted organization, flashcards, quizzes, search, and email verification in one personal study workspace.

## What This Project Solves

Students often collect notes but do not always have an easy way to revise them actively. NVLearn solves that by turning a simple note library into a study system:

- Store personal notes in one account-based workspace.
- Automatically generate metadata such as tags and summaries for notes.
- Search through notes from the navigation search using note titles.
- Use AI note actions with vector similarity search across note titles, tags, summaries, and note content.
- Sort the notes list by title or recent activity.
- Ask an AI assistant to create notes, retrieve relevant notes, modify notes, generate flashcards, and generate quizzes.
- Save useful flashcard sets and quiz results for later practice.
- Keep unfinished AI-generated flashcards and quizzes temporary so the database does not fill up with unused practice material.

In short: NVLearn helps a learner move from passive note storage to active revision.

## Main Features

- User registration and login with password hashing.
- Six-digit email verification during registration and login.
- Personal note CRUD workflow:
  - create notes
  - edit notes
  - read notes
  - move notes to bin
  - restore notes
  - permanently delete notes
- Markdown note rendering with support for code blocks, tables, and math formatting.
- AI assistant chat.
- AI note generation.
- AI note search, edit-note actions, and note actions, including ChromaDB-backed vector search for note actions.
- AI flashcard generation.
- AI quiz generation.
- Practice Hub for saved flashcards and saved quizzes.
- Quiz scoring with correct, wrong, unanswered, and percentage score tracking.
- Client-side note sorting by title and last-opened time.
- Background cleanup jobs for unsaved flashcards and quizzes.
- SQLite database storage through SQLAlchemy.
- Local ChromaDB vector storage for semantic note retrieval.

## Tech Stack

- Python
- Flask
- Flask-SQLAlchemy
- SQLAlchemy
- Flask-Login
- Flask-WTF
- WTForms
- SQLite
- APScheduler
- python-dotenv
- Markdown / pymdown-extensions
- Google Gemini API
- Groq API
- ChromaDB
- Gmail SMTP or another compatible SMTP email account
- HTML, CSS, and vanilla JavaScript

## Project Structure

```text
study-project/
+-- server.py              # Main Flask app, routes, models, scheduler, database setup
+-- helpers.py             # Email helpers, AI clients, AI parsing, markdown rendering
+-- forms.py               # Flask-WTF forms for notes, auth, and verification
+-- prompts.py             # AI system prompts for chat, notes, flashcards, quizzes, metadata
+-- vector_store.py        # ChromaDB vector store helpers for note embeddings and semantic search
+-- .env.example           # Example environment variables
+-- .env                   # Local secrets file, should not be committed
+-- instance/
|   +-- notes.db           # SQLite database, created/used locally
|   +-- chroma_db/         # ChromaDB vector database, created/used locally
+-- static/
|   +-- css/styles.css     # App styles
|   +-- js/script.js       # Client-side interactions
|   +-- assets/logo.png    # App logo
+-- templates/             # Jinja templates
```

## Requirements

Install Python 3.10 or newer. Python 3.11+ is recommended.

You also need API keys for the AI features and an email account that can send verification emails.

## Installation Guide

### 1. Open the Project Folder

On Windows PowerShell:

```powershell
cd C:\Users\Naveeb\Desktop\study-project
```

### 2. Create a Virtual Environment

```powershell
python -m venv .venv
```

### 3. Activate the Virtual Environment

```powershell
.\.venv\Scripts\Activate.ps1
```

If PowerShell blocks activation scripts, run this once in the same terminal:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
```

Then activate again:

```powershell
.\.venv\Scripts\Activate.ps1
```

### 4. Install Dependencies

Install the project dependencies from `requirements.txt`:

```powershell
pip install -r requirements.txt
```

Optional but recommended:

```powershell
python -m pip install --upgrade pip
```

### 5. Create the Environment File

Copy `.env.example` to `.env`:

```powershell
copy .env.example .env
```

Then edit `.env` and replace the placeholder values.

## Environment Variables and API Keys

The app reads secrets from `.env` in `helpers.py` using `python-dotenv`.

### Required Variables

```env
APP_PASSWORD=yourgmailapppasswordhere
EMAIL=example@email.com
GROQ_API_KEY=yourGROQAPIkeyhere
GEMINI_API_KEY=yourGeminiAPIkeyhere
```

### `EMAIL`

The email address used to send verification codes during registration and login.

Example:

```env
EMAIL=myaccount@gmail.com
```

### `APP_PASSWORD`

The password used by the app to log in to the SMTP email account.

If you use Gmail, do not use your normal Google password. Use a Gmail App Password:

1. Enable two-factor authentication on the Google account.
2. Open your Google Account security settings.
3. Create an App Password.
4. Put that generated password in `.env`.

Example:

```env
APP_PASSWORD=abcd efgh ijkl mnop
```

The current SMTP settings in `helpers.py` are:

```python
SMTP_SERVER = "smtp.gmail.com"
SMTP_PORT = 587
```

If you use another email provider, update those SMTP values in `helpers.py`.

### `GROQ_API_KEY`

Used by the AI router/chat flow in `ask_groq()`.

The app currently uses Groq with this model:

```text
qwen/qwen3.6-27b
```

Groq helps decide whether the assistant should chat, create notes, find notes, modify notes, generate flashcards, or generate quizzes.

### `GEMINI_API_KEY`

Used by `ask_gemini()` for content generation tasks, including:

- note creation
- note actions
- metadata generation
- response summarization
- flashcard generation
- quiz generation

The app attempts several Gemini model names in sequence. If one fails, it tries the next one.

## Important Secret Notes

- Never commit `.env` to Git.
- `.env.example` is safe to commit because it contains placeholders.
- API keys can cost money depending on provider usage.
- If an API key is missing or invalid, AI features may fail even if the Flask app starts.
- Email verification depends on `EMAIL` and `APP_PASSWORD`; registration and login verification may fail if SMTP is not configured correctly.

## Running the App

From the project folder with the virtual environment activated:

```powershell
python server.py
```

The app runs in Flask debug mode because `server.py` contains:

```python
app.run(debug=True, use_reloader=False)
```

Open the local URL shown in the terminal. It is usually:

```text
http://127.0.0.1:5000
```

## Database Setup

The app uses SQLite:

```python
app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///notes.db"
```

Flask stores this database under the app instance folder:

```text
instance/notes.db
```

You do not need to run a separate migration command for a fresh local setup. On startup, the app calls:

```python
db.create_all()
```

That creates the database tables if they do not exist.

## How to Use NVLearn

### 1. Register

Go to `/register`, create an account, and enter the verification code sent to your email.

### 2. Log In

Go to `/login`, enter your credentials, and complete email verification.

### 3. Create Notes

Use `/add` to create notes manually. Notes support markdown-style content, and the app stores both markdown and rendered HTML.

### 4. Search Notes

Use the search bar to find notes by title. The search modal calls `/search/<query>` for quick JSON results, and pressing Enter opens `/search-results/<query>`.

AI note actions use semantic vector search instead of title-only matching. When you ask the assistant to summarize, explain, rewrite, edit, or extract information from existing notes, NVLearn searches your ChromaDB note vectors using the note title, tags, summary, and markdown content. For supported actions across the full notebook, the AI can use the special `all_notes` topic to process every active non-binned note instead of matching one topic.

### 5. Sort Notes

On `/notes`, use the `Sort By` menu to reorder notes in the browser without changing the database:

- `Title: A to Z`
- `Title: Z to A`
- `Recently Opened`
- `Least recently opened`

### 6. Use the AI Chat

Open `/ai-chat` and ask the assistant to help with study tasks. Example prompts:

```text
Create a note about photosynthesis.
Generate flashcards from my biology notes.
Make a quiz from my latest chemistry note.
Find my notes about recursion.
Summarize my note about databases.
Edit my note about photosynthesis to make it simpler.
Summarize all my notes.
```

### 7. Practice

Generated flashcards and quizzes open in their own views. Save the ones you want to keep.

Saved practice material appears in:

```text
/practice-hub
```

Note: only saved quizzes and saved flashcard sets appear in Practice Hub.

## Main Routes

| Route | Purpose |
| --- | --- |
| `/` | Home page and recent notes |
| `/notes` | All active notes |
| `/add` | Add a note |
| `/edit/<note_id>` | Edit a note |
| `/read_note/<note_id>` | Read a note |
| `/move_to_bin/<note_id>` | Move note to bin |
| `/note-bin` | View deleted notes |
| `/restore/<note_id>` | Restore a note |
| `/delete/<note_id>` | Permanently delete a note |
| `/register` | Register account and verify email |
| `/login` | Login and verify email |
| `/logout` | Logout |
| `/search/<query>` | JSON search endpoint |
| `/search-results/<query>` | Search results page |
| `/ai-chat` | AI assistant page |
| `/ai-response` | AI assistant API endpoint |
| `/flashcards/<flashcard_id>` | View generated flashcards |
| `/save-flashcards/<flashcard_id>` | Save flashcard set |
| `/delete-flashcards/<flashcard_id>` | Delete flashcard set |
| `/quiz/<quiz_id>` | Take generated quiz |
| `/save-quiz/<quiz_id>` | Save quiz score |
| `/practice-hub` | Saved flashcards and quizzes |
| `/about` | About page |

## Background Jobs

The app starts an APScheduler background scheduler when `server.py` runs.

It has three interval jobs:

- Generate metadata for notes that need it.
- Delete the oldest unsaved flashcard set.
- Delete the oldest unsaved quiz.

Each job runs every 10 minutes.

This means generated flashcards and quizzes are temporary until the user saves them.

## Vector Search

NVLearn uses ChromaDB for local semantic note search in AI note-action workflows, including AI edit-note actions.

Vector data is stored locally at:

```text
instance/chroma_db/
```

Each user gets a separate Chroma collection named like:

```text
user_<user_id>_notes
```

When a note is created, edited, or restored, the app upserts the note into ChromaDB. When a note is moved to the bin or permanently deleted, the app removes that note from ChromaDB. On startup, active notes are synced into ChromaDB so the vector store can be rebuilt from SQLite if needed.

The vector document includes:

- note title
- metadata tags
- metadata summary
- markdown note content

By default, vector results are filtered with a cosine-distance threshold in `vector_store.py`. Requests routed with the `all_notes` topic bypass vector matching and load every active note for supported whole-notebook actions.

## Troubleshooting

### App starts, but registration or login emails fail

Check:

- `EMAIL` is set correctly.
- `APP_PASSWORD` is set correctly.
- Gmail App Passwords are enabled.
- The SMTP server and port in `helpers.py` match your email provider.
- Your email provider has not blocked SMTP sign-in.

### AI chat responds with errors

Check:

- `GROQ_API_KEY` is present and valid.
- `GEMINI_API_KEY` is present and valid.
- Your API accounts have available quota.
- The model names in `helpers.py` are available for your API accounts.

### Practice Hub does not show a quiz

Only saved quizzes appear in Practice Hub. After taking a quiz, click `Save Quiz` on the quiz summary screen.

### Database looks empty

The SQLite database is local to the Flask app instance path. Check:

```text
instance/notes.db
```

If you delete this file, the app will create a fresh database on next startup.

### Vector search does not find expected notes

Check:

- `chromadb` is installed from `requirements.txt`.
- The app has write access to `instance/chroma_db/`.
- Notes have been created, edited, restored, or synced on startup.
- The distance threshold in `vector_store.py` is not too strict for your note content.
- The note is not in the bin, because binned notes are removed from vector search.

### CSS or JavaScript changes do not appear

The app sets:

```python
app.config['SEND_FILE_MAX_AGE_DEFAULT'] = 0
```

That helps reduce caching, but the browser may still cache files. Try a hard refresh.

## Development Notes

- Most backend behavior lives in `server.py`.
- AI provider logic lives in `helpers.py`.
- Prompt design lives in `prompts.py`.
- Vector search logic lives in `vector_store.py`.
- Forms live in `forms.py`.
- Shared layout and navigation live in `templates/base.html`.
- Main client-side behavior lives in `static/js/script.js`.

## Production Notes

This project is currently structured for local development. Before deploying publicly, consider:

- Move `SECRET_KEY` to an environment variable instead of generating it randomly on every server start.
- Turn off Flask debug mode.
- Use a production WSGI server.
- Add proper database migrations instead of relying only on `db.create_all()`.
- Use a production database such as PostgreSQL.
- Add CSRF handling for JSON POST endpoints if exposed publicly.
- Add rate limiting for auth and AI routes.
- Review API key storage and provider billing limits.
- Add automated tests for auth, note ownership, AI fallback behavior, and practice flows.

## License

This project is licensed under the MIT License.

Copyright (c) 2026 Naveeb Pacheerikkuth.

See `LICENSE` for the full license text.
