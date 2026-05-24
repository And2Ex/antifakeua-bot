# Release 011 — public text cleanup and beta readiness fixes

- Removed internal/service wording from the public transparency message.
- Reworked the main menu texts to look like a user-facing product, not developer notes.
- Added a button for viewing the fact-check prompt from the transparency screen.
- Changed cache wording to user-friendly wording: “already checked earlier”.
- Restricted automatic text checking to private chats only. In groups, the bot now checks messages only through `/check`.
- Feedback now sends a notification to admins and still stores the message in the database.
- Kept hidden technical commands for admin use, but they are not shown in the Telegram command menu.
