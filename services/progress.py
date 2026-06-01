import asyncio
from collections.abc import Awaitable
from typing import TypeVar

from aiogram.types import LinkPreviewOptions, Message


T = TypeVar("T")

PROGRESS_FRAMES = (
    "Перевіряю",
    "Перевіряю.",
    "Перевіряю..",
    "Перевіряю...",
)
PROGRESS_FRAME_SECONDS = 1.0


async def safe_edit_message(
    message: Message,
    text: str,
    *,
    parse_mode: str | None = None,
    link_preview_options: LinkPreviewOptions | None = None,
) -> bool:
    try:
        await message.edit_text(
            text,
            parse_mode=parse_mode,
            link_preview_options=link_preview_options,
        )
        return True
    except Exception as error:
        if "message is not modified" in str(error).lower():
            return True

        print(f"PROGRESS EDIT ERROR: {error}")
        return False


async def safe_delete_message(message: Message) -> None:
    try:
        await message.delete()
    except Exception as error:
        print(f"PROGRESS DELETE ERROR: {error}")


async def run_with_progress(
    status_message: Message,
    work: Awaitable[T],
    *,
    frame_seconds: float = PROGRESS_FRAME_SECONDS,
) -> T:
    """Run work while displaying at least one full four-frame dot cycle."""
    task = asyncio.create_task(work)
    frame_index = 0
    visible_intervals = 0
    delay = max(frame_seconds, 0.5)

    while True:
        await asyncio.sleep(delay)
        visible_intervals += 1

        if task.done() and visible_intervals >= len(PROGRESS_FRAMES):
            break

        frame_index = (frame_index + 1) % len(PROGRESS_FRAMES)
        await safe_edit_message(status_message, PROGRESS_FRAMES[frame_index])

    return await task
