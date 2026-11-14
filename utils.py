"""
Pure utility helpers with no external dependencies.

These functions have no imports from the app, no DB access, no Flask
context, and no third-party service calls. They can be imported from
anywhere — routes, services, scripts, tests — without side effects.
"""

import random

import markdown


def md_to_html(content):
    """Convert Markdown to HTML using the same extension set as the app."""
    return markdown.markdown(
        content,
        extensions=["fenced_code", "tables", "pymdownx.arithmatex"],
        extension_configs={"pymdownx.arithmatex": {"generic": True}},
    )


def create_code():
    """Generate a 6-digit verification code as a string."""
    return str(random.randint(100000, 999999))


def get_welcome_message(username):
    """Return a random greeting for the given user's name."""
    return random.choice(
        [
            f"Ready to learn something new {username}?",
            f"What are we conquering today {username}?",
            f"Back for more? Let's dive in {username}.",
            f"What are we up to today {username}?",
            f"Let's get it {username}.",
            f"What's the plan today {username}?",
            f"Time to crush your goals {username}!",
            f"Make today count {username}!",
            f"Your future self will thank you {username}.",
            f"Ready to unlock your potential today {username}?",
        ]
    )