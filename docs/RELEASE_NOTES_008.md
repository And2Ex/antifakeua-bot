# AntiFakeUA Bot — release 008

## UI cleanup and feedback flow

### Changed
- Private Telegram command menu now shows only `/start` and `/menu`.
- `/check` is moved to group command scope because private users can simply send text.
- Combined “how to use”, “about bot” and “why trust” into one clearer help page.
- Removed user-facing MVP/token/cache wording from help texts.
- Added cleaner “Open links / transparency” page with GitHub, methodology and prompt reference.
- Made feedback button interactive: user can press “Write feedback” and send the next message without typing `/feedback`.
- Added admin button for viewing recent feedback.

### Kept
- Old callbacks `menu:how` and `menu:trust` still work for compatibility with old messages.
- `/feedback текст` still works manually.
- `/check текст` still works manually, even though it is no longer shown in private command menu.
